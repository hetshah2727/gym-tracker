"""Website crawl + deterministic SEO rules.

Every finding records ``evidence`` - what was actually observed - so it can be traced and re-checked.
Score (transparent, GymFlow's own checklist - not a Google metric):
    score = 100 - sum over distinct issue types of (base penalty by severity + min(extra pages, 4))
"""
import re
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from urllib.parse import urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.modules.seo.analyzer import PageFacts, clean_url, is_crawlable_link, parse_html
from app.modules.seo.fetcher import FetchResult, SafeFetcher, UnsafeUrlError, normalize_url, validate_url

AI_CRAWLERS = ("GPTBot", "OAI-SearchBot", "ChatGPT-User", "PerplexityBot", "Google-Extended", "ClaudeBot")
PENALTY = {"critical": 20, "high": 10, "medium": 5, "low": 2, "info": 0}
LOCAL_SCHEMA_TYPES = {"LocalBusiness", "SportsActivityLocation", "ExerciseGym", "HealthClub", "SportsClub",
                      "Organization"}


@dataclass
class CrawledPage:
    url: str
    fetch: FetchResult
    facts: PageFacts | None = None
    image_bytes: dict = field(default_factory=dict)


@dataclass
class CrawlResult:
    start_url: str
    host: str
    pages: list[CrawledPage] = field(default_factory=list)
    robots: dict = field(default_factory=dict)
    sitemap: dict = field(default_factory=dict)
    https: dict = field(default_factory=dict)
    skipped_by_robots: list[str] = field(default_factory=list)
    link_checks: dict = field(default_factory=dict)       # url -> status (uncrawled internal links)
    errors: list[str] = field(default_factory=list)


def _origin(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "", "", ""))


def _parse_sitemap(xml: bytes) -> tuple[list[str], list[str]]:
    """Returns (page urls, child sitemap urls)."""
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return [], []
    locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
    if root.tag.endswith("sitemapindex"):
        return [], locs
    return locs, []


def crawl(url: str, fetcher: SafeFetcher, max_pages: int = 25, progress=None) -> CrawlResult:
    start = clean_url(validate_url(normalize_url(url), fetcher.resolver))
    host = (urlsplit(start).hostname or "").lower()
    result = CrawlResult(start_url=start, host=host)
    origin = _origin(start)

    # robots.txt
    robots = fetcher.fetch(origin + "/robots.txt", max_bytes=500_000)
    parser = RobotFileParser()
    sitemaps: list[str] = []
    if robots.status == 200 and not robots.is_html:
        lines = robots.text().splitlines()
        parser.parse(lines)
        sitemaps = [ln.split(":", 1)[1].strip() for ln in lines if ln.lower().startswith("sitemap:")]
        disallow_all = bool(re.search(r"(?ims)^user-agent:\s*\*\s*$(?:\n(?!user-agent).*)*?^disallow:\s*/\s*$",
                                      robots.text()))
        result.robots = {"status": 200, "found": True, "sitemaps": sitemaps, "disallows_all": disallow_all}
    else:
        parser.parse([])
        result.robots = {"status": robots.status, "found": False, "error": robots.error}

    def allowed(u: str) -> bool:
        return parser.can_fetch(fetcher.user_agent, u)

    result.robots["ai_crawlers"] = {ua: parser.can_fetch(ua, start) for ua in AI_CRAWLERS} \
        if result.robots.get("found") else {ua: True for ua in AI_CRAWLERS}

    # sitemap
    sitemap_url = sitemaps[0] if sitemaps else origin + "/sitemap.xml"
    sm = fetcher.fetch(sitemap_url, max_bytes=5_000_000)
    sitemap_pages: list[str] = []
    if sm.status == 200 and not sm.is_html:
        pages, children = _parse_sitemap(sm.body)
        for child in children[:3]:
            cr = fetcher.fetch(child, max_bytes=5_000_000)
            if cr.status == 200:
                pages += _parse_sitemap(cr.body)[0]
        sitemap_pages = [clean_url(p) for p in pages if is_crawlable_link(p, host)]
        result.sitemap = {"url": sitemap_url, "found": True, "url_count": len(pages)}
    else:
        result.sitemap = {"url": sitemap_url, "found": False, "status": sm.status}

    # HTTPS
    if start.startswith("https://"):
        plain = fetcher.fetch("http://" + start[len("https://"):], method="GET", max_bytes=50_000)
        result.https = {"available": True,
                        "http_redirects_to_https": plain.final_url.startswith("https://") if not plain.error else None}
    else:
        secure = fetcher.fetch("https://" + start[len("http://"):], max_bytes=50_000)
        result.https = {"available": bool(secure.status and secure.status < 400), "http_redirects_to_https": False}

    # BFS crawl
    queue: list[str] = [start] + [p for p in sitemap_pages if p != start]
    seen: set[str] = set()
    discovered: Counter = Counter()
    while queue and len(result.pages) < max_pages:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        if not allowed(current):
            result.skipped_by_robots.append(current)
            continue
        if progress:
            progress(len(result.pages), current)
        fetched = fetcher.fetch(current)
        if current == start and not fetched.error:
            final_host = (urlsplit(fetched.final_url).hostname or "").lower()
            if final_host and final_host != host:  # e.g. example.com -> www.example.com
                host = result.host = final_host
        page = CrawledPage(url=current, fetch=fetched)
        if fetched.status and fetched.is_html and fetched.body:
            page.facts = parse_html(fetched.text(), fetched.final_url)
            for link in page.facts.links:
                link = clean_url(link)
                if is_crawlable_link(link, host):
                    discovered[link] += 1
                    if link not in seen and link not in queue:
                        queue.append(link)
        result.pages.append(page)
        if fetched.error and current == start:
            result.errors.append(f"Homepage could not be fetched: {fetched.error}")
            break

    # Light checks: uncrawled internal links (HEAD) and image weights
    crawled = {p.url for p in result.pages}
    for link in [u for u in discovered if u not in crawled][:15]:
        if allowed(link):
            r = fetcher.fetch(link, method="HEAD")
            result.link_checks[link] = r.status if not r.error else None
    checked_images = 0
    for page in result.pages:
        if not page.facts:
            continue
        for img in page.facts.images:
            src = img.get("src")
            if not src or src.startswith("data:") or checked_images >= 20 or src in page.image_bytes:
                continue
            checked_images += 1
            r = fetcher.fetch(src, method="HEAD")
            size = r.headers.get("content-length")
            if size and size.isdigit():
                page.image_bytes[src] = int(size)
    return result


# ---------------------------------------------------------------- rules

@dataclass
class Finding:
    code: str
    category: str
    severity: str
    title: str
    evidence: str
    recommendation: str
    page_url: str | None = None

    @property
    def fingerprint(self) -> str:
        return f"{self.code}|{self.page_url or '*'}"[:300]


def _trim(value: str | None, n: int = 120) -> str:
    value = value or ""
    return value if len(value) <= n else value[: n - 1] + "…"


def evaluate(crawl_result: CrawlResult) -> list[Finding]:
    out: list[Finding] = []
    add = out.append
    start = crawl_result.start_url
    pages = crawl_result.pages
    html_pages = [p for p in pages if p.facts]

    if crawl_result.errors:
        add(Finding("site_unreachable", "technical", "critical", "Website could not be reached",
                    "; ".join(crawl_result.errors), "Check the domain, hosting and SSL certificate.", start))
        return out

    # Site-level technical checks
    if not crawl_result.https.get("available"):
        add(Finding("no_https", "technical", "critical", "Website is not available over HTTPS",
                    f"Audited URL {start} uses http and https did not respond successfully.",
                    "Install an SSL certificate and redirect all http traffic to https."))
    elif crawl_result.https.get("http_redirects_to_https") is False:
        add(Finding("http_not_redirected", "technical", "medium", "HTTP does not redirect to HTTPS",
                    "The http:// version of the homepage did not end on an https:// URL.",
                    "Add a permanent (301) redirect from http to https."))
    robots = crawl_result.robots
    if not robots.get("found"):
        add(Finding("robots_missing", "technical", "low", "No robots.txt file",
                    f"GET /robots.txt returned {robots.get('status') or robots.get('error')}.",
                    "Add a robots.txt that allows crawling and lists your sitemap."))
    elif robots.get("disallows_all"):
        add(Finding("robots_blocks_all", "technical", "critical", "robots.txt blocks all crawlers",
                    "robots.txt contains 'User-agent: *' with 'Disallow: /'.",
                    "Remove the blanket Disallow so search engines can crawl the site."))
    if not crawl_result.sitemap.get("found"):
        add(Finding("sitemap_missing", "technical", "medium", "No XML sitemap found",
                    f"{crawl_result.sitemap.get('url')} returned {crawl_result.sitemap.get('status')}.",
                    "Publish an XML sitemap and reference it in robots.txt and Google Search Console."))
    if crawl_result.skipped_by_robots:
        add(Finding("pages_blocked_by_robots", "technical", "info", "Some pages are blocked by robots.txt",
                    f"{len(crawl_result.skipped_by_robots)} discovered URL(s) skipped, e.g. "
                    f"{crawl_result.skipped_by_robots[0]}", "Make sure no important page is disallowed."))

    titles: dict[str, list[str]] = defaultdict(list)
    descriptions: dict[str, list[str]] = defaultdict(list)
    any_local_schema = False
    for page in pages:
        f, fr, url = page.facts, page.fetch, page.url
        is_home = url == start
        if fr.error or (fr.status and fr.status >= 400):
            add(Finding("http_error", "technical", "critical" if is_home else "high",
                        "Page returns an error", f"{url} -> {fr.status or fr.error}",
                        "Fix the page or redirect it to a working URL and update internal links.", url))
            continue
        if len(fr.redirect_chain) > 1:
            add(Finding("redirect_chain", "technical", "low", "Redirect chain",
                        f"{len(fr.redirect_chain)} redirects before {fr.final_url}",
                        "Link straight to the final URL and keep redirects to one hop.", url))
        if fr.elapsed_ms > 3000:
            add(Finding("slow_response", "technical", "medium", "Slow page response",
                        f"Full HTML took {fr.elapsed_ms} ms to download (measured from the GymFlow server).",
                        "Improve hosting, caching and image sizes. Verify with PageSpeed Insights.", url))
        if fr.truncated or len(fr.body) > 1_500_000:
            add(Finding("heavy_html", "technical", "low", "Very large HTML document",
                        f"HTML size ≥ {len(fr.body) // 1024} KB.", "Reduce inline scripts, styles and markup.", url))
        if f is None:
            continue
        if f.robots_meta and "noindex" in f.robots_meta:
            add(Finding("noindex", "technical", "critical" if is_home else "high", "Page is set to noindex",
                        f'<meta name="robots" content="{f.robots_meta}">',
                        "Remove noindex if this page should appear in Google.", url))
        if "noindex" in (fr.headers.get("x-robots-tag") or "").lower():
            add(Finding("noindex_header", "technical", "high", "X-Robots-Tag noindex header",
                        f"X-Robots-Tag: {fr.headers.get('x-robots-tag')}", "Remove the noindex header.", url))
        if not f.has_viewport:
            add(Finding("missing_viewport", "technical", "high", "No mobile viewport",
                        "No <meta name=\"viewport\" content=\"width=device-width…\"> tag.",
                        "Add a responsive viewport meta tag; most gym searches happen on phones.", url))
        if not f.canonical:
            add(Finding("missing_canonical", "technical", "low", "No canonical tag",
                        "No <link rel=\"canonical\"> found.", "Add a self-referencing canonical URL.", url))
        elif (urlsplit(f.canonical).hostname or "").lower() not in (crawl_result.host, "www." + crawl_result.host,
                                                                     crawl_result.host.removeprefix("www.")):
            add(Finding("canonical_other_host", "technical", "medium", "Canonical points to another site",
                        f"canonical = {f.canonical}", "Point the canonical at this site's own URL.", url))
        if not f.lang:
            add(Finding("missing_lang", "on_page", "low", "No language declared",
                        "<html> has no lang attribute.", 'Add lang="en-IN" (or the page language).', url))
        # Titles & descriptions
        if not f.title:
            add(Finding("missing_title", "on_page", "high", "Missing page title", "No <title> text found.",
                        "Write a unique title (50-60 characters) with the service and area.", url))
        else:
            titles[f.title.strip().lower()].append(url)
            if len(f.title) > 65:
                add(Finding("title_too_long", "on_page", "low", "Title is too long",
                            f'{len(f.title)} characters: "{_trim(f.title)}"', "Keep titles under ~60 characters.",
                            url))
            elif len(f.title) < 20:
                add(Finding("title_too_short", "on_page", "low", "Title is very short",
                            f'{len(f.title)} characters: "{f.title}"',
                            "Include the service, area and gym name in the title.", url))
        if not f.meta_description:
            add(Finding("missing_meta_description", "on_page", "medium", "Missing meta description",
                        'No <meta name="description"> content.',
                        "Write a 140-160 character description that invites a visit or trial.", url))
        else:
            descriptions[f.meta_description.strip().lower()].append(url)
            if len(f.meta_description) > 170:
                add(Finding("meta_description_too_long", "on_page", "low", "Meta description is too long",
                            f"{len(f.meta_description)} characters.", "Keep it under ~160 characters.", url))
        h1 = [h for h in f.headings["h1"] if h]
        if not h1:
            add(Finding("missing_h1", "on_page", "medium", "No H1 heading", "No <h1> with text on the page.",
                        "Add one H1 that says what the page offers and where.", url))
        elif len(h1) > 1:
            add(Finding("multiple_h1", "on_page", "low", "Several H1 headings",
                        f"{len(h1)} H1s: " + " | ".join(_trim(h, 40) for h in h1[:3]),
                        "Use a single H1 and H2s for sections.", url))
        missing_alt = [img["src"] for img in f.images if img["alt"] is None and img["src"]]
        if missing_alt:
            add(Finding("images_missing_alt", "on_page", "medium", "Images without alt text",
                        f"{len(missing_alt)} of {len(f.images)} images have no alt attribute, e.g. "
                        f"{_trim(missing_alt[0], 90)}", "Describe each image (e.g. 'Free weights area at …').",
                        url))
        heavy = {src: b for src, b in page.image_bytes.items() if b > 300_000}
        if heavy:
            src, size = max(heavy.items(), key=lambda kv: kv[1])
            add(Finding("large_images", "technical", "medium", "Large images",
                        f"{len(heavy)} image(s) over 300 KB, largest {size // 1024} KB: {_trim(src, 90)}",
                        "Compress and resize images (WebP, ≤ 200 KB).", url))
        words = f.word_count
        if words < 250:
            add(Finding("thin_content", "content", "medium" if is_home else "low", "Very little text",
                        f"About {words} words of visible text.",
                        "Explain services, facilities, timings and location in useful detail.", url))
        if not f.open_graph.get("og:title") or not f.open_graph.get("og:image"):
            add(Finding("missing_open_graph", "on_page", "low", "Incomplete Open Graph tags",
                        "Missing " + ", ".join(k for k in ("og:title", "og:image") if not f.open_graph.get(k)),
                        "Add og:title, og:description and og:image so shares on WhatsApp look good.", url))
        if f.json_ld_errors:
            add(Finding("invalid_json_ld", "technical", "medium", "Invalid structured data",
                        f"{f.json_ld_errors} JSON-LD block(s) could not be parsed.", "Fix the JSON syntax.", url))
        if LOCAL_SCHEMA_TYPES & set(f.schema_types()):
            any_local_schema = True
        path = urlsplit(url).path
        if path != "/" and (re.search(r"[A-Z_]", path) or len(path) > 100 or path.count("?") or
                            len(urlsplit(url).query) > 60):
            add(Finding("url_structure", "on_page", "low", "URL could be cleaner", f"Path: {_trim(path, 100)}",
                        "Use short, lowercase, hyphenated URLs such as /personal-training-gotri.", url))
        if is_home and not f.phones:
            add(Finding("phone_not_on_homepage", "local", "medium", "No phone number on the homepage",
                        "No Indian mobile/landline pattern found in the homepage text.",
                        "Show the phone number as text (not only an image) on every page.", url))

    for text, urls in titles.items():
        if len(urls) > 1:
            add(Finding("duplicate_title", "on_page", "medium", "Duplicate titles",
                        f'"{_trim(text, 80)}" is used on {len(urls)} pages: ' + ", ".join(urls[:3]),
                        "Give each page its own title.", urls[0]))
    for text, urls in descriptions.items():
        if len(urls) > 1:
            add(Finding("duplicate_meta_description", "on_page", "low", "Duplicate meta descriptions",
                        f"Same description on {len(urls)} pages: " + ", ".join(urls[:3]),
                        "Write a unique description for each page.", urls[0]))
    broken = {u: s for u, s in crawl_result.link_checks.items() if s is None or s >= 400}
    if broken:
        url, code = next(iter(broken.items()))
        add(Finding("broken_internal_links", "technical", "high", "Broken internal links",
                    f"{len(broken)} linked page(s) failed, e.g. {url} -> {code or 'no response'}",
                    "Fix or remove links to missing pages."))
    if html_pages and not any_local_schema:
        add(Finding("missing_local_schema", "local", "medium", "No local business structured data",
                    "No LocalBusiness / SportsActivityLocation / ExerciseGym JSON-LD on crawled pages.",
                    "Add JSON-LD with name, address, phone, hours and geo (use the Structured Data Assistant)."))
    return out


def score(findings: list[Finding]) -> int:
    by_code: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        by_code[f.code].append(f)
    total = 0
    for items in by_code.values():
        worst = max(PENALTY[i.severity] for i in items)
        total += worst + (min(len(items) - 1, 4) if worst else 0)
    return max(0, 100 - total)


__all__ = ["CrawlResult", "Finding", "SafeFetcher", "UnsafeUrlError", "crawl", "evaluate", "score"]

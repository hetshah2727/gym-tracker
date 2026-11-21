"""Parse one HTML page into the SEO facts the audit rules need (stdlib only)."""
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit, urlunsplit

PHONE_RE = re.compile(r"(?:\+?91[\s-]?)?(?<!\d)[6-9]\d{4}[\s-]?\d{5}(?!\d)")
SKIP_EXT = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".pdf", ".zip", ".mp4", ".mp3", ".css", ".js",
            ".ico", ".xml", ".doc", ".docx", ".xls", ".xlsx")


@dataclass
class PageFacts:
    title: str | None = None
    meta_description: str | None = None
    robots_meta: str | None = None
    canonical: str | None = None
    lang: str | None = None
    has_viewport: bool = False
    headings: dict = field(default_factory=lambda: {f"h{i}": [] for i in range(1, 7)})
    links: list = field(default_factory=list)            # absolute URLs
    images: list = field(default_factory=list)           # {"src", "alt"} alt None = attribute missing
    json_ld: list = field(default_factory=list)
    json_ld_errors: int = 0
    open_graph: dict = field(default_factory=dict)
    text: str = ""

    @property
    def word_count(self) -> int:
        return len(re.findall(r"\w+", self.text))

    @property
    def phones(self) -> list[str]:
        return sorted({re.sub(r"\D", "", m)[-10:] for m in PHONE_RE.findall(self.text)})

    def schema_types(self) -> list[str]:
        types: list[str] = []

        def walk(node):
            if isinstance(node, dict):
                t = node.get("@type")
                if isinstance(t, str):
                    types.append(t)
                elif isinstance(t, list):
                    types.extend(str(x) for x in t)
                for key in ("@graph", "mainEntity", "itemListElement"):
                    if key in node:
                        walk(node[key])
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        walk(self.json_ld)
        return types


class _Parser(HTMLParser):
    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base = base_url
        self.facts = PageFacts()
        self._stack: list[str] = []
        self._buf: list[str] = []
        self._text: list[str] = []
        self._capture: str | None = None
        self._script_ld = False

    def handle_starttag(self, tag, attrs):
        a = {k.lower(): (v or "") for k, v in attrs}
        f = self.facts
        if tag == "html" and a.get("lang"):
            f.lang = a["lang"]
        elif tag == "base" and a.get("href"):
            self.base = urljoin(self.base, a["href"])
        elif tag == "meta":
            name = (a.get("name") or "").lower()
            prop = (a.get("property") or "").lower()
            if name == "description" and f.meta_description is None:
                f.meta_description = a.get("content", "").strip()
            elif name == "robots":
                f.robots_meta = a.get("content", "").strip().lower()
            elif name == "viewport":
                f.has_viewport = "width" in a.get("content", "")
            if prop.startswith("og:"):
                f.open_graph[prop] = a.get("content", "")
        elif tag == "link" and "canonical" in (a.get("rel") or "").lower().split():
            f.canonical = urljoin(self.base, a.get("href", ""))
        elif tag == "a" and a.get("href"):
            href = a["href"].strip()
            if not href.startswith(("mailto:", "tel:", "javascript:", "#", "whatsapp:", "sms:")):
                f.links.append(urljoin(self.base, href))
        elif tag == "img":
            f.images.append({"src": urljoin(self.base, a.get("src", "")) if a.get("src") else "",
                             "alt": a["alt"] if "alt" in a else None})
        elif tag == "script":
            self._script_ld = "ld+json" in (a.get("type") or "").lower()
            self._capture = "script"
            self._buf = []
        elif tag in ("style", "noscript", "template"):
            self._capture = tag
        elif tag == "title" or tag in self.facts.headings:
            self._capture = tag
            self._buf = []
        self._stack.append(tag)

    def handle_endtag(self, tag):
        f = self.facts
        if tag == "script" and self._capture == "script":
            if self._script_ld:
                raw = "".join(self._buf).strip()
                try:
                    data = json.loads(raw)
                    f.json_ld.extend(data if isinstance(data, list) else [data])
                except ValueError:
                    f.json_ld_errors += 1
            self._capture = None
        elif tag in ("style", "noscript", "template") and self._capture == tag:
            self._capture = None
        elif tag == self._capture and (tag == "title" or tag in f.headings):
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            if tag == "title":
                if f.title is None:
                    f.title = text
            else:
                f.headings[tag].append(text)
            self._capture = None
        if self._stack and self._stack[-1] == tag:
            self._stack.pop()

    def handle_data(self, data):
        if self._capture in ("script", "title") or self._capture in self.facts.headings:
            self._buf.append(data)
        if self._capture in ("script", "style", "noscript", "template"):
            return
        if self._capture != "title":
            self._text.append(data)

    def close(self):
        super().close()
        self.facts.text = re.sub(r"\s+", " ", " ".join(self._text)).strip()


def parse_html(html: str, base_url: str) -> PageFacts:
    parser = _Parser(base_url)
    try:
        parser.feed(html)
        parser.close()
    except Exception:  # noqa: BLE001 - malformed HTML: keep what was parsed
        parser.facts.text = re.sub(r"\s+", " ", " ".join(parser._text)).strip()
    return parser.facts


def clean_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, parts.query, ""))


def is_crawlable_link(url: str, host: str) -> bool:
    parts = urlsplit(url)
    return (parts.scheme in ("http", "https") and (parts.hostname or "").lower() == host
            and not parts.path.lower().endswith(SKIP_EXT))

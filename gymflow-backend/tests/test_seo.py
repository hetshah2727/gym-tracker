"""Website SEO engine: SSRF protection, crawl restrictions, audit persistence, suggestions, schema, claims."""
import httpx
import pytest

from app.modules.seo import audit as engine
from app.modules.seo import service as seo_service
from app.modules.seo.fetcher import SafeFetcher, UnsafeUrlError, is_public_ip, validate_url
from app.services.content import check_claims
from tests.conftest import API, fill_profile, publish_site

PUBLIC_IP = "93.184.216.34"


def public_resolver(host):
    return ["10.0.0.5"] if host == "rebind.example" else [PUBLIC_IP]


HOME = """<html lang="en"><head><title>Iron Temple Gym</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="canonical" href="https://irontemple.example/"></head>
<body><h1>Iron Temple</h1><p>Strength gym in Gotri, Vadodara. Call 98765 43210.</p>
<img src="/img/weights.jpg"><img src="/img/logo.png" alt="Iron Temple logo">
<a href="/about">About</a><a href="/private/admin">Admin</a><a href="/missing">Old page</a></body></html>"""
ABOUT = """<html lang="en"><head><title>Iron Temple Gym</title><meta name="description" content="About us">
<meta name="viewport" content="width=device-width"></head><body><h1>About</h1><h1>Team</h1>
<script type="application/ld+json">{"@context":"https://schema.org","@type":"ExerciseGym","name":"Iron Temple"}</script>
</body></html>"""


def site_handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if request.url.scheme == "http":
        return httpx.Response(301, headers={"location": f"https://{request.url.host}{path}"})
    if path == "/robots.txt":
        return httpx.Response(200, text="User-agent: *\nDisallow: /private\nUser-agent: GPTBot\nDisallow: /\n"
                                         "Sitemap: https://irontemple.example/sitemap.xml",
                              headers={"content-type": "text/plain"})
    if path == "/sitemap.xml":
        return httpx.Response(200, text="<urlset><url><loc>https://irontemple.example/about</loc></url></urlset>",
                              headers={"content-type": "application/xml"})
    if path == "/":
        return httpx.Response(200, text=HOME, headers={"content-type": "text/html; charset=utf-8"})
    if path == "/about":
        return httpx.Response(200, text=ABOUT, headers={"content-type": "text/html"})
    if path.startswith("/private"):
        raise AssertionError("crawler fetched a robots.txt-disallowed URL")
    if path.startswith("/img/"):
        return httpx.Response(200, headers={"content-type": "image/jpeg", "content-length": "450000"})
    return httpx.Response(404, text="not found", headers={"content-type": "text/html"})


class MockFetcher(SafeFetcher):
    resolver_override = staticmethod(public_resolver)

    def __init__(self, **kwargs):
        super().__init__(resolver=public_resolver, transport=httpx.MockTransport(site_handler), **kwargs)


@pytest.mark.parametrize("url", [
    "http://localhost/", "http://127.0.0.1/", "http://169.254.169.254/latest/meta-data/", "http://10.1.2.3/",
    "http://192.168.1.1/", "http://[::1]/", "http://[::ffff:127.0.0.1]/", "file:///etc/passwd",
    "ftp://example.com/", "http://example.com:8080/", "http://metadata.google.internal/", "http://gym.local/",
    "http://user:pass@example.com/", "http://100.64.0.1/", "http://rebind.example/",
])
def test_ssrf_urls_are_rejected(url):
    with pytest.raises(UnsafeUrlError):
        validate_url(url, public_resolver)


def test_public_url_allowed_and_ip_classification():
    assert validate_url("https://irontemple.example/", public_resolver)
    assert is_public_ip("8.8.8.8") and not is_public_ip("172.16.0.1") and not is_public_ip("::1")


def test_redirect_to_private_address_is_blocked():
    def handler(request):
        return httpx.Response(302, headers={"location": "http://127.0.0.1/admin"})

    f = SafeFetcher(resolver=public_resolver, transport=httpx.MockTransport(handler))
    result = f.fetch("https://irontemple.example/")
    assert result.status is None and "private" in result.error.lower()


def test_crawl_respects_robots_and_finds_issues():
    result = engine.crawl("irontemple.example", MockFetcher(), max_pages=10)
    urls = {p.url for p in result.pages}
    assert "https://irontemple.example/" in urls and "https://irontemple.example/about" in urls
    assert any("/private" in u for u in result.skipped_by_robots)
    assert result.robots["ai_crawlers"]["GPTBot"] is False
    assert result.https["http_redirects_to_https"] is True
    findings = engine.evaluate(result)
    codes = {f.code for f in findings}
    assert {"missing_meta_description", "images_missing_alt", "duplicate_title", "multiple_h1", "large_images",
            "http_error"} <= codes  # /missing was crawled and returned 404
    broken = next(f for f in findings if f.code == "http_error")
    assert broken.page_url.endswith("/missing") and "404" in broken.evidence
    assert "missing_local_schema" not in codes  # the about page has ExerciseGym JSON-LD
    assert "phone_not_on_homepage" not in codes
    # every finding carries evidence of what was observed
    assert all(f.evidence for f in findings)
    assert 0 < engine.score(findings) < 100


def test_audit_api_end_to_end_with_history(client, owner):
    seo_service.FETCHER_FACTORY = MockFetcher
    assert client.post(f"{API}/seo/audits", headers=owner, json={"url": "http://127.0.0.1"}).status_code == 422
    resp = client.post(f"{API}/seo/audits", headers=owner, json={"url": "https://irontemple.example"})
    assert resp.status_code == 202, resp.text
    audit_id = resp.json()["id"]
    detail = client.get(f"{API}/seo/audits/{audit_id}", headers=owner).json()  # background task ran
    assert detail["audit"]["status"] == "completed" and detail["audit"]["pages_crawled"] == 3
    assert detail["audit"]["summary"]["score_method"].startswith("100 minus")
    assert any(f["code"] == "missing_meta_description" and f["basis"] == "observed" for f in detail["findings"])

    suggestions = client.post(f"{API}/seo/audits/{audit_id}/suggestions", headers=owner).json()
    meta = next(s for s in suggestions if s["field"] == "meta_description"
                and s["target"].rstrip("/") == "https://irontemple.example")
    assert meta["current_value"] is None and meta["suggested_value"] and meta["reason"]
    assert meta["status"] == "draft"  # nothing is applied automatically
    decided = client.post(f"{API}/seo/suggestions/{meta['id']}/decide", headers=owner, json={"approve": True}).json()
    assert decided["applied_to_gymflow_site"] is False and decided["copy_ready"]

    second = client.post(f"{API}/seo/audits", headers=owner, json={"url": "https://irontemple.example"}).json()
    comp = client.get(f"{API}/seo/audits/{second['id']}", headers=owner).json()["audit"]["summary"]["comparison"]
    assert comp["previous_audit_id"] == audit_id and comp["new_count"] == 0

    report = client.post(f"{API}/seo/reports/seo_audit", headers=owner).json()
    assert report["content"]["latest"]["score"] == detail["audit"]["score"]
    assert all(f["basis"] == "observed" for f in report["content"]["top_findings"])


def test_keywords_never_fabricate_metrics(client, owner):
    fill_profile(client, owner)
    kws = client.post(f"{API}/seo/keywords/generate", headers=owner).json()
    assert kws and all(k["metrics_verified"] is False and k["search_volume"] is None for k in kws)
    assert any(k["keyword"] == "gym in gotri" for k in kws)
    assert all(k["source"] == "rule_suggestion" for k in kws)


def test_landing_pages_only_for_real_areas(client, owner):
    fill_profile(client, owner)
    publish_site(client, owner)
    bad = client.post(f"{API}/seo/landing-pages", headers=owner, json={"service": "Personal Training", "area": "Mumbai"})
    assert bad.status_code == 422
    page = client.post(f"{API}/seo/landing-pages", headers=owner, json={"service": "Personal Training", "area": "Gotri"})
    assert page.status_code == 201, page.text
    page = page.json()
    assert page["status"] == "draft" and "Gotri" in page["h1"] and len(page["seo_title"]) <= 60
    dup = client.post(f"{API}/seo/landing-pages", headers=owner, json={"service": "Personal Training", "area": "Gotri"})
    assert dup.status_code == 409
    published = client.post(f"{API}/seo/landing-pages/{page['id']}/publish", headers=owner).json()
    assert published["status"] == "published"
    assert all("aggregateRating" not in str(x) for x in published["json_ld"])
    site = client.get(f"{API}/websites", headers=owner).json()[0]
    public = client.get(f"{API}/public/sites/{site['slug']}/pages/{page['slug']}")
    assert public.status_code == 200 and public.json()["page"]["h1"] == page["h1"]
    sitemap = client.get(f"{API}/public/sites/{site['slug']}/sitemap.xml").text
    assert page["slug"] in sitemap
    # Enquiries from the landing page are attributed to it
    client.post(f"{API}/public/sites/{site['slug']}/leads", json={"name": "LP", "phone": "9777700001",
                                                                   "landing_page": page["slug"]})
    lead = client.get(f"{API}/crm/leads", headers=owner).json()["items"][0]
    assert lead["source"] == "seo_landing_page" and lead["landing_page_id"] == page["id"]


def test_structured_data_generation_and_validation(client, owner):
    fill_profile(client, owner)
    gen = client.post(f"{API}/ai-search/schema/generate", headers=owner, json={"kind": "local_business"}).json()
    assert gen["json_ld"]["@type"] == "ExerciseGym" and gen["validation"]["valid"]
    assert gen["json_ld"]["openingHoursSpecification"][0]["dayOfWeek"][0] == "Monday"
    assert len(gen["json_ld"]["openingHoursSpecification"][0]["dayOfWeek"]) == 6
    bad = {**gen["json_ld"], "aggregateRating": {"@type": "AggregateRating", "ratingValue": 5}}
    res = client.post(f"{API}/ai-search/schema/validate", headers=owner, json={"json_ld": bad}).json()
    assert not res["valid"] and any("aggregateRating" in e for e in res["errors"])
    res = client.post(f"{API}/ai-search/schema/validate", headers=owner, json={"json_ld": "{not json"}).json()
    assert not res["valid"]
    mismatch = {**gen["json_ld"], "telephone": "9000000000"}
    res = client.post(f"{API}/ai-search/schema/validate", headers=owner, json={"json_ld": mismatch}).json()
    assert res["valid"] and any("telephone" in w for w in res["warnings"])


def test_claims_guard():
    assert check_claims("Best gym in Vadodara - lose 10 kg in 30 days, guaranteed!")
    warnings = " ".join(check_claims("We help with diabetes and cure back pain"))
    assert "Medical claim" in warnings and "Health condition" in warnings
    assert check_claims("Strength training in Gotri with experienced coaches.") == []

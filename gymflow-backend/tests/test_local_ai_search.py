"""Google Business Profile (OAuth, sync, isolation, replies), reviews policy, AI-search readiness & monitoring."""
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.core.config import settings
from app.modules.integrations import google
from tests.conftest import API, create_member, fill_profile, register_gym, set_plan


def test_review_requests_follow_policy(client, owner):
    create_member(client, owner)
    msg = "Hi {name}, please review {gym}: {link}"
    assert client.post(f"{API}/local/review-requests", headers=owner,
                       json={"message": msg, "all_active_members": True}).status_code == 409  # no review link yet
    client.put(f"{API}/local/review-link", headers=owner, json={"review_url": "https://g.page/r/abc123/review"})
    incentive = "Leave a 5-star review and get a free protein shake: {link}"
    assert client.post(f"{API}/local/review-requests", headers=owner,
                       json={"message": incentive, "all_active_members": True}).status_code == 422
    ok = client.post(f"{API}/local/review-requests", headers=owner, json={"message": msg, "all_active_members": True})
    assert ok.status_code == 200 and ok.json()["queued"] == 1
    again = client.post(f"{API}/local/review-requests", headers=owner, json={"message": msg, "all_active_members": True})
    assert again.json()["queued"] == 0 and again.json()["skipped_recently_asked"] == 1
    qr = client.get(f"{API}/local/review-qr.svg", headers=owner)
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg")


def test_manual_profile_audit_detects_inconsistencies(client, owner):
    fill_profile(client, owner)
    resp = client.post(f"{API}/local/profile-audit/manual", headers=owner, json={
        "name": "Iron Temple Gym & Spa", "primary_category": "Spa", "phone": "9000000000",
        "website": "https://irontemple.example", "description": "Gym.", "services": ["Weight training"],
        "hours": [{"day": "MONDAY", "opens": "05:30", "closes": "22:00"}], "review_count": 4}).json()
    codes = {f["code"] for f in resp["findings"]}
    assert {"name_inconsistent", "phone_inconsistent", "category_mismatch", "weak_description", "services_missing",
            "few_reviews"} <= codes
    assert all(f["requires_approval"] for f in resp["findings"]) and resp["source"] == "manual"
    weak = next(f for f in resp["findings"] if f["code"] == "weak_description")
    assert weak["suggested_correction"]


def test_review_reply_workflow_manual_review(client, owner):
    fill_profile(client, owner)
    review = client.post(f"{API}/local/reviews", headers=owner, json={"author": "Amit P", "rating": 2,
                                                                       "text": "Crowded in the evening"}).json()
    assert review["sentiment"] == "negative" and review["reply_status"] == "none"
    drafted = client.post(f"{API}/local/reviews/{review['id']}/draft", headers=owner).json()
    assert drafted["reply_status"] == "drafted" and "sorry" in drafted["draft_reply"].lower()
    # A manually recorded review can't be published through the API - copy-ready only
    assert client.post(f"{API}/local/reviews/{review['id']}/approve", headers=owner,
                       json={"text": drafted["draft_reply"], "publish": True}).status_code == 409
    approved = client.post(f"{API}/local/reviews/{review['id']}/approve", headers=owner,
                           json={"text": drafted["draft_reply"], "publish": False}).json()
    assert approved["published"] is False and approved["copy_ready"]


class FakeGoogle:
    """Stands in for Google's OAuth + Business Profile endpoints."""

    def __init__(self):
        self.calls = []

    def __call__(self, method, url, **kwargs):
        self.calls.append((method, url))
        req = httpx.Request(method, url)
        if url == google.TOKEN_URL:
            return httpx.Response(200, json={"access_token": "at-1", "refresh_token": "rt-1", "expires_in": 3600,
                                             "scope": "https://www.googleapis.com/auth/business.manage"}, request=req)
        if url.endswith("/accounts"):
            return httpx.Response(200, json={"accounts": [{"name": "accounts/111"}]}, request=req)
        if url.endswith("accounts/111/locations"):
            return httpx.Response(200, json={"locations": [{"name": "locations/222", "title": "Iron Temple",
                                                            "storefrontAddress": {"locality": "Vadodara"}}]}, request=req)
        if url.endswith("/locations/222") and "mybusinessbusinessinformation" in url:
            return httpx.Response(200, json={
                "title": "Iron Temple", "categories": {"primaryCategory": {"displayName": "Gym"}},
                "phoneNumbers": {"primaryPhone": "098765 43210"}, "websiteUri": "https://irontemple.example",
                "storefrontAddress": {"addressLines": ["12 Race Course Road"], "locality": "Vadodara"},
                "regularHours": {"periods": [{"openDay": "MONDAY", "openTime": {"hours": 5, "minutes": 30},
                                              "closeTime": {"hours": 22}}]},
                "metadata": {"newReviewUri": "https://search.google.com/local/writereview?placeid=X"}}, request=req)
        if url.endswith("/reviews"):
            return httpx.Response(200, json={"totalReviewCount": 1, "averageRating": 4.0, "reviews": [
                {"reviewId": "rev-1", "reviewer": {"displayName": "Sneha"}, "starRating": "FOUR",
                 "comment": "Good trainers", "createTime": "2026-11-01T10:00:00Z"}]}, request=req)
        if url.endswith("/reply") and method == "PUT":
            return httpx.Response(200, json={"comment": "ok"}, request=req)
        return httpx.Response(404, json={}, request=req)


@pytest.fixture
def google_configured(monkeypatch):
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_ID", "cid")
    monkeypatch.setattr(settings, "GOOGLE_CLIENT_SECRET", "csecret")
    fake = FakeGoogle()
    monkeypatch.setattr(google, "request", fake)
    return fake


def test_google_requires_server_configuration(client, owner):
    assert client.post(f"{API}/integrations/google/google_business_profile/connect", headers=owner).status_code == 409
    perf = client.get(f"{API}/seo/performance", headers=owner).json()
    assert perf["connected"] is False and "does not estimate" in perf["message"]


def test_google_business_profile_oauth_sync_and_reply(client, owner, google_configured):
    fill_profile(client, owner)
    url = client.post(f"{API}/integrations/google/google_business_profile/connect", headers=owner).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    assert "business.manage" in url and "access_type=offline" in url
    assert client.get(f"{API}/integrations/google/callback", params={"state": "forged", "code": "x"}).status_code == 400
    cb = client.get(f"{API}/integrations/google/callback", params={"state": state, "code": "auth-code"},
                    follow_redirects=False)
    assert cb.status_code == 307 and "connected=google_business_profile" in cb.headers["location"]
    status = client.get(f"{API}/integrations/google/google_business_profile/status", headers=owner).json()
    assert status["status"] == "pending" and status["choices"][0]["id"] == "accounts/111/locations/222"
    # Can't pick a location the Google account doesn't have
    assert client.post(f"{API}/integrations/google/google_business_profile/select", headers=owner,
                       json={"external_id": "accounts/999/locations/1"}).status_code == 403
    assert client.post(f"{API}/integrations/google/google_business_profile/select", headers=owner,
                       json={"external_id": "accounts/111/locations/222"}).json()["status"] == "connected"

    # Another gym sees nothing of this connection
    other, _ = register_gym(client, name="Other Gym", email="other2@gym.example.com")
    assert client.get(f"{API}/integrations/google/google_business_profile/status",
                      headers=other).json()["status"] == "not_connected"
    assert client.post(f"{API}/local/reviews/sync", headers=other).status_code == 409

    audit = client.post(f"{API}/local/profile-audit/sync", headers=owner).json()
    assert audit["source"] == "google_business_profile"
    assert "phone_inconsistent" not in {f["code"] for f in audit["findings"]}  # same digits, different formatting
    reviews = client.get(f"{API}/local/reviews", headers=owner).json()
    assert reviews[0]["source"] == "google_business_profile" and reviews[0]["rating"] == 4
    approved = client.post(f"{API}/local/reviews/{reviews[0]['id']}/approve", headers=owner,
                           json={"text": "Thank you Sneha!", "publish": True}).json()
    assert approved["published"] is True
    assert any(m == "PUT" and u.endswith("reviews/rev-1/reply") for m, u in google_configured.calls)
    health = {i["key"]: i for i in client.get(f"{API}/integrations/health", headers=owner).json()["integrations"]}
    assert health["google_business_profile"]["connection"] == "connected"
    assert health["whatsapp"]["state"] == "simulation"


def test_ai_readiness_and_monitoring_labels(client, owner):
    fill_profile(client, owner)
    check = client.post(f"{API}/ai-search/readiness", headers=owner).json()
    assert 0 <= check["score"] <= 100 and check["content_gaps"]
    assert any("Run a website audit" in (c["fix"] or "") for c in check["checklist"] if not c["passed"])
    latest = client.get(f"{API}/ai-search/readiness", headers=owner).json()
    assert "not a Google, OpenAI" in latest["disclaimer"]

    assert client.get(f"{API}/ai-search/visibility", headers=owner).status_code == 402  # Pro feature
    set_plan(client, owner, "pro")
    q = client.post(f"{API}/ai-search/visibility/queries", headers=owner,
                    json={"question": "Best gyms in Gotri, Vadodara"}).json()
    client.post(f"{API}/ai-search/visibility/queries/{q['id']}/results", headers=owner,
                json={"provider": "chatgpt", "mentioned": True, "position": 2, "competitors_mentioned": ["FitZone"]})
    summary = client.get(f"{API}/ai-search/visibility", headers=owner).json()
    assert summary["providers"]["chatgpt"]["mention_rate"] == 1.0 and summary["sample_size"] == 1
    assert summary["queries"][0]["last"]["method"] == "manual_research"
    assert "do not measure all answers" in summary["limitations"]


def test_content_studio_drafts_are_grounded(client, owner):
    fill_profile(client, owner)
    out = client.post(f"{API}/ai-search/content", headers=owner, json={"kind": "membership_explanation"}).json()
    assert out["generated_by"] == "template" and out["status"] == "draft"
    plans = client.get(f"{API}/membership-plans", headers=owner).json()
    assert all(f"{p['price']:,.0f}" in out["body_markdown"] for p in plans)
    faqs = client.post(f"{API}/gym-profile/faqs/generate", headers=owner).json()
    assert faqs["faqs"] and all(f["approved"] is False for f in faqs["faqs"])

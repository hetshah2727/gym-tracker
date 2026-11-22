"""Password reset, member import, timeline, UPI pay page, owner report and SaaS billing webhooks."""
import hashlib
import hmac
import json
from datetime import date, timedelta

from tests.conftest import API, create_member


def test_password_reset_link_works_once_and_cannot_log_in(client, owner, monkeypatch):
    from app.modules.authentication import service

    sent = {}
    monkeypatch.setattr(service, "send_reset_email", lambda user: sent.setdefault("token", service.reset_token(user)))
    assert client.post(f"{API}/auth/forgot-password", json={"email": "owner@iron.example.com"}).status_code == 202
    assert client.post(f"{API}/auth/forgot-password", json={"email": "nobody@example.com"}).status_code == 202
    token = sent["token"]
    # A reset token is not a login token
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    r = client.post(f"{API}/auth/reset-password", json={"token": token, "password": "brand-new-pass"})
    assert r.status_code == 200 and r.json()["access_token"]
    assert client.post(f"{API}/auth/reset-password", json={"token": token, "password": "another-pass1"}).status_code == 400
    assert client.post(f"{API}/auth/login", json={"email": "owner@iron.example.com", "password": "brand-new-pass"}).status_code == 200


def test_member_import_preview_then_commit_without_duplicates(client, owner):
    end = (date.today() + timedelta(days=10)).strftime("%d/%m/%Y")
    csv = ("Member Name,Mobile,Plan,Expiry,Paid\n"
           f"Ravi Patel,+91 98240 11111,Monthly,{end},Yes\n"
           "Neha Shah,9824022222,,,\n"
           "No Phone,,Monthly,,\n"
           "Ravi Again,9824011111,,,\n")
    files = {"file": ("register.csv", csv.encode(), "text/csv")}
    prev = client.post(f"{API}/members/import", headers=owner, files=files).json()
    assert prev["preview"] and prev["created"] == 2 and prev["skipped"] == 2 and prev["with_membership"] == 1
    assert client.get(f"{API}/members", headers=owner).json()["total"] == 0  # preview saves nothing
    done = client.post(f"{API}/members/import?preview=false", headers=owner, files=files).json()
    assert done["created"] == 2
    again = client.post(f"{API}/members/import?preview=false", headers=owner, files=files).json()
    assert again["created"] == 0  # already in GymFlow
    ravi = next(m for m in client.get(f"{API}/members", headers=owner).json()["items"] if m["phone"] == "9824011111")
    assert ravi["plan_name"] == "Monthly" and ravi["days_left"] == 10 and ravi["due_amount"] == 0
    tl = client.get(f"{API}/members/{ravi['id']}/timeline", headers=owner).json()
    assert tl["memberships"][0]["plan"] == "Monthly" and tl["payments"][0]["status"] == "paid"
    bad = client.post(f"{API}/members/import", headers=owner, files={"file": ("x.txt", b"hi", "text/plain")})
    assert bad.status_code == 400
    assert client.get(f"{API}/members/import/template.csv", headers=owner).text.startswith("Name,Phone")


def test_upi_pay_page_and_reminder_link(client, owner):
    slug = client.get(f"{API}/gym", headers=owner).json()["slug"]
    assert client.get(f"{API}/public/sites/{slug}/pay").status_code == 404  # not set up yet
    client.patch(f"{API}/gym", headers=owner, json={"settings": {"upi_id": "irontemple@okicici"}})
    info = client.get(f"{API}/public/sites/{slug}/pay", params={"amount": 1500, "note": "Fee"}).json()
    assert info["upi_uri"].startswith("upi://pay?pa=irontemple%40okicici") and "am=1500.00" in info["upi_uri"]
    qr = client.get(f"{API}/public/sites/{slug}/pay/qr.svg", params={"amount": 1500})
    assert qr.status_code == 200 and qr.headers["content-type"].startswith("image/svg")
    member = create_member(client, owner)
    client.post(f"{API}/payments", headers=owner, json={"member_id": member["id"], "amount": 1500, "paid": False,
                                                        "due_date": (date.today() - timedelta(days=3)).isoformat()})
    client.post(f"{API}/recovery/sync", headers=owner)
    due = client.get(f"{API}/recovery/due", headers=owner).json()
    assert due["upi_payments"] and f"/pay/{slug}?amount=1500" in due["items"][0]["message"]


def test_owner_report(client, owner):
    month = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    r = client.get(f"{API}/growth/owner-report", headers=owner, params={"month": month}).json()
    assert r["month"] == month and "Collected" in r["text"] and r["plan_price"]
    assert client.post(f"{API}/growth/owner-report/email", headers=owner).json()["sent"] == 0  # email not configured


def _signed(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    return raw, hmac.new(b"whsec_test", raw, hashlib.sha256).hexdigest()


def test_saas_subscription_webhook_switches_plan(client, owner):
    gym_id = client.get(f"{API}/gym", headers=owner).json()["id"]
    assert client.post(f"{API}/subscriptions/checkout", headers=owner, json={"plan_code": "pro"}).json() == {"configured": False}
    body = {"event": "subscription.activated", "payload": {"subscription": {"entity": {
        "id": "sub_123", "paid_count": 1, "current_end": 1893456000, "notes": {"gym_id": gym_id, "plan_code": "pro"}}}}}
    raw, sig = _signed(body)
    headers = {"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": "evt_sub_1", "Content-Type": "application/json"}
    assert client.post(f"{API}/payments/webhooks/razorpay", content=raw, headers=headers).json()["status"] == "ok"
    assert client.post(f"{API}/payments/webhooks/razorpay", content=raw, headers=headers).json()["status"] == "duplicate"
    ent = client.get(f"{API}/subscriptions/entitlements", headers=owner).json()
    assert ent["plan_code"] == "pro" and ent["status"] == "active"


def test_referral_longer_trial_and_reward_when_referred_gym_pays(client, owner):
    from datetime import datetime

    from tests.conftest import register_gym

    me = client.get(f"{API}/subscriptions/referral", headers=owner).json()
    assert me["link"].endswith(f"/register?ref={me['code']}") and me["joined"] == 0
    before = client.get(f"{API}/subscriptions/current", headers=owner).json()["current_period_end"]
    r = client.post(f"{API}/auth/register", json={"gym_name": "Friend Gym", "owner_name": "Friend Owner",
                                                  "email": "friend@example.com", "password": "friendpass1",
                                                  "referral_code": me["code"]})
    friend = {"Authorization": f"Bearer {r.json()['access_token']}"}
    trial_end = datetime.fromisoformat(client.get(f"{API}/subscriptions/current", headers=friend).json()["current_period_end"])
    assert (trial_end.replace(tzinfo=None) - datetime.utcnow()).days >= 29
    assert client.get(f"{API}/subscriptions/referral", headers=owner).json()["joined"] == 1
    gym_id = client.get(f"{API}/gym", headers=friend).json()["id"]
    body = {"event": "subscription.activated", "payload": {"subscription": {"entity": {
        "id": "sub_f1", "paid_count": 1, "current_end": 1893456000, "notes": {"gym_id": gym_id, "plan_code": "growth"}}}}}
    raw, sig = _signed(body)
    client.post(f"{API}/payments/webhooks/razorpay", content=raw,
                headers={"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": "evt_f1", "Content-Type": "application/json"})
    after = client.get(f"{API}/subscriptions/current", headers=owner).json()["current_period_end"]
    assert (datetime.fromisoformat(after) - datetime.fromisoformat(before)).days >= 29
    assert client.get(f"{API}/subscriptions/referral", headers=owner).json()["paying"] == 1


def test_cron_endpoints_need_the_secret_and_docs_stay_available_in_dev(client, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "CRON_SECRET", "cron-test-secret")
    assert client.get(f"{API}/cron/daily").status_code == 404
    assert client.get(f"{API}/cron/daily", headers={"Authorization": "Bearer wrong"}).status_code == 404
    r = client.get(f"{API}/cron/daily", headers={"Authorization": "Bearer cron-test-secret"})
    assert r.status_code == 200 and {"expiry", "payments", "growth", "notifications"} <= set(r.json())
    assert client.get(f"{API}/cron/notifications", headers={"Authorization": "Bearer cron-test-secret"}).status_code == 200
    monkeypatch.setattr(settings, "CRON_SECRET", None)
    assert client.get(f"{API}/cron/daily", headers={"Authorization": "Bearer "}).status_code == 404
    assert client.get("/health").headers["x-content-type-options"] == "nosniff"

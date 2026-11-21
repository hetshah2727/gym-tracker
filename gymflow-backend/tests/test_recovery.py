"""Renewals, payment recovery, verified webhooks and revenue accounting."""
import hashlib
import hmac
import json
from datetime import date, timedelta

from tests.conftest import API, create_member


def _sync(client, owner):
    resp = client.post(f"{API}/recovery/sync", headers=owner)
    assert resp.status_code == 200, resp.text
    return resp.json()


def _member_with_membership(client, owner, start_days_ago: int, paid=True, phone="9123456780"):
    member = create_member(client, owner, phone=phone)
    plan = client.get(f"{API}/membership-plans", headers=owner).json()[0]  # Monthly, 30 days
    ms = client.post(f"{API}/memberships", headers=owner, json={
        "member_id": member["id"], "plan_id": plan["id"], "paid": paid, "payment_method": "cash",
        "start_date": (date.today() - timedelta(days=start_days_ago)).isoformat()}).json()
    return member, plan, ms


def _opps(client, owner, **params):
    return client.get(f"{API}/recovery/opportunities", headers=owner, params=params).json()


def test_renewal_opportunity_milestones_without_duplicates(client, owner):
    member, plan, ms = _member_with_membership(client, owner, start_days_ago=24)  # ends in 5 days
    _sync(client, owner)
    _sync(client, owner)
    opps = _opps(client, owner, tab="renewals")
    assert opps["total"] == 1
    opp = opps["items"][0]
    assert opp["membership_id"] == ms["id"] and opp["potential_revenue"] == plan["price"]
    assert opp["milestones"] == ["7"]
    tasks = client.get(f"{API}/crm/tasks", headers=owner, params={"kind": "renewal"}).json()["items"]
    assert len(tasks) == 1 and tasks[0]["draft_message"]
    # Potential revenue is never collected/recovered revenue
    rev = client.get(f"{API}/growth/revenue", headers=owner).json()["summary"]
    assert rev["potential"] == plan["price"] and rev["recovered"] == 0 and rev["collected"] == plan["price"]


def test_paid_renewal_recovers_revenue_exactly_once(client, owner):
    member, plan, ms = _member_with_membership(client, owner, start_days_ago=24)
    _sync(client, owner)
    renewed = client.post(f"{API}/memberships/{ms['id']}/renew", headers=owner,
                          json={"paid": True, "payment_method": "upi"})
    assert renewed.status_code == 201
    opp = _opps(client, owner, tab="history")["items"][0]
    assert opp["status"] == "won" and opp["recovered_revenue"] == plan["price"] and opp["recovered_payment_id"]
    # Re-running the sync or recording another payment never double counts
    _sync(client, owner)
    client.post(f"{API}/payments", headers=owner, json={"member_id": member["id"], "amount": 500, "paid": True})
    rev = client.get(f"{API}/growth/revenue", headers=owner).json()["summary"]
    assert rev["recovered"] == plan["price"]
    assert rev["collected"] == plan["price"] * 2 + 500


def test_unpaid_renewal_is_in_progress_not_recovered(client, owner):
    member, plan, ms = _member_with_membership(client, owner, start_days_ago=24)
    _sync(client, owner)
    client.post(f"{API}/memberships/{ms['id']}/renew", headers=owner, json={"paid": False})
    _sync(client, owner)
    opp = _opps(client, owner, tab="renewals")["items"][0]
    assert opp["status"] == "in_progress" and opp["recovered_revenue"] == 0


def test_outstanding_payment_closes_when_paid(client, owner):
    member = create_member(client, owner)
    pay = client.post(f"{API}/payments", headers=owner, json={
        "member_id": member["id"], "amount": 1500, "paid": False,
        "due_date": (date.today() - timedelta(days=3)).isoformat()}).json()
    _sync(client, owner)
    opp = _opps(client, owner, tab="outstanding")["items"][0]
    assert opp["payment_id"] == pay["id"] and opp["potential_revenue"] == 1500
    # Manual "won" without a payment is refused
    assert client.post(f"{API}/recovery/opportunities/{opp['id']}/close", headers=owner,
                       json={"status": "won", "outcome": "said they paid"}).status_code == 400
    client.post(f"{API}/payments/{pay['id']}/mark-paid", headers=owner, json={"method": "upi"})
    closed = _opps(client, owner, tab="history")["items"][0]
    assert closed["status"] == "won" and closed["recovered_revenue"] == 1500
    summary = client.get(f"{API}/recovery/summary", headers=owner).json()
    assert summary["revenue"]["recovered"] == 1500 and summary["revenue"]["outstanding"] == 0


def test_payment_cannot_be_credited_twice(client, owner):
    member = create_member(client, owner)
    p1 = client.post(f"{API}/payments", headers=owner, json={"member_id": member["id"], "amount": 800, "paid": False,
                                                              "due_date": date.today().isoformat()}).json()
    p2 = client.post(f"{API}/payments", headers=owner, json={"member_id": member["id"], "amount": 900, "paid": False,
                                                              "due_date": date.today().isoformat()}).json()
    _sync(client, owner)
    paid = client.post(f"{API}/payments", headers=owner, json={"member_id": member["id"], "amount": 800}).json()
    opps = {o["payment_id"]: o for o in _opps(client, owner, tab="outstanding")["items"]}
    first = client.post(f"{API}/recovery/opportunities/{opps[p1['id']]['id']}/record-payment", headers=owner,
                        json={"payment_id": paid["id"]})
    assert first.status_code == 200 and first.json()["recovered_revenue"] == 800
    second = client.post(f"{API}/recovery/opportunities/{opps[p2['id']]['id']}/record-payment", headers=owner,
                         json={"payment_id": paid["id"]})
    assert second.status_code == 409


def _signed(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    return raw, hmac.new(b"whsec_test", raw, hashlib.sha256).hexdigest()


def test_razorpay_webhook_verification_dedup_and_failure(client, owner):
    member = create_member(client, owner)
    pay = client.post(f"{API}/payments", headers=owner, json={"member_id": member["id"], "amount": 4000, "paid": False,
                                                               "due_date": date.today().isoformat()}).json()
    order = client.post(f"{API}/payments/{pay['id']}/checkout", headers=owner).json()
    failed = {"event": "payment.failed", "payload": {"payment": {"entity": {
        "id": "pay_fail1", "order_id": order["order_id"], "error_description": "Card declined"}}}}
    raw, sig = _signed(failed)
    url = f"{API}/payments/webhooks/razorpay"
    assert client.post(url, content=raw, headers={"X-Razorpay-Signature": "bad"}).status_code == 400
    assert client.post(url, content=raw, headers={"X-Razorpay-Signature": sig,
                                                  "X-Razorpay-Event-Id": "evt_1"}).json()["status"] == "ok"
    p = client.get(f"{API}/payments", headers=owner, params={"member_id": member["id"]}).json()["items"][0]
    assert p["status"] == "failed" and p["failure_reason"] == "Card declined"
    assert _opps(client, owner, tab="failed")["total"] == 1

    captured = {"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_ok1", "order_id": order["order_id"]}}}}
    raw, sig = _signed(captured)
    headers = {"X-Razorpay-Signature": sig, "X-Razorpay-Event-Id": "evt_2"}
    assert client.post(url, content=raw, headers=headers).json()["status"] == "ok"
    assert client.post(url, content=raw, headers=headers).json()["status"] == "duplicate"
    p = client.get(f"{API}/payments", headers=owner, params={"member_id": member["id"]}).json()["items"][0]
    assert p["status"] == "paid" and p["verified_by"] == "gateway"
    won = _opps(client, owner, tab="history")["items"][0]
    assert won["status"] == "won" and won["recovered_revenue"] == 4000


def test_recovery_requires_growth_plan(client, owner):
    client.post(f"{API}/subscriptions/change-plan", headers=owner, json={"plan_code": "starter"})
    assert client.get(f"{API}/recovery/opportunities", headers=owner).status_code == 402
    ent = client.get(f"{API}/subscriptions/entitlements", headers=owner).json()
    assert ent["features"]["recovery_center"] is False and ent["features"]["lead_crm"] is True
    history = client.get(f"{API}/subscriptions/history", headers=owner).json()
    assert [h["event"] for h in history][:2] == ["plan_changed", "trial_started"]

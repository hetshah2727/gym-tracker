import hashlib
import hmac
import json
from datetime import date, timedelta

from app.database.models import Membership, Notification, Payment
from app.database.models.enums import MembershipStatus
from app.database.session import SessionLocal
from app.workers import expiry_worker, notification_worker, payment_worker
from tests.conftest import API, create_member


def _monthly_plan(client, headers):
    return next(p for p in client.get(f"{API}/membership-plans", headers=headers).json() if p["name"] == "Monthly")


def test_assign_membership_creates_pending_fee(client, owner):
    member = create_member(client, owner)
    plan = _monthly_plan(client, owner)
    ms = client.post(f"{API}/memberships", headers=owner,
                     json={"member_id": member["id"], "plan_id": plan["id"]}).json()
    assert ms["end_date"] == (date.today() + timedelta(days=29)).isoformat()
    assert ms["days_left"] == 29

    payments = client.get(f"{API}/payments?status=pending", headers=owner).json()
    assert payments["total"] == 1 and payments["items"][0]["amount"] == 1500

    pid = payments["items"][0]["id"]
    paid = client.post(f"{API}/payments/{pid}/mark-paid", headers=owner, json={"method": "upi"}).json()
    assert paid["status"] == "paid"
    overview = client.get(f"{API}/analytics/overview", headers=owner).json()
    assert overview["revenue_this_month"] == 1500 and overview["pending_count"] == 0


def test_renewal_continues_from_end_date(client, owner):
    member = create_member(client, owner)
    plan = _monthly_plan(client, owner)
    ms = client.post(f"{API}/memberships", headers=owner,
                     json={"member_id": member["id"], "plan_id": plan["id"], "paid": True,
                           "payment_method": "cash"}).json()
    renewed = client.post(f"{API}/memberships/{ms['id']}/renew", headers=owner, json={"paid": True}).json()
    assert renewed["start_date"] == (date.fromisoformat(ms["end_date"]) + timedelta(days=1)).isoformat()


def test_razorpay_webhook_marks_payment_paid(client, owner):
    member = create_member(client, owner)
    pay = client.post(f"{API}/payments", headers=owner,
                      json={"member_id": member["id"], "amount": 999, "paid": False}).json()
    order = client.post(f"{API}/payments/{pay['id']}/checkout", headers=owner).json()
    body = json.dumps({"event": "payment.captured", "payload": {"payment": {"entity": {
        "id": "pay_123", "order_id": order["order_id"]}}}}).encode()
    bad = client.post(f"{API}/payments/webhooks/razorpay", content=body,
                      headers={"X-Razorpay-Signature": "nope"})
    assert bad.status_code == 400
    sig = hmac.new(b"whsec_test", body, hashlib.sha256).hexdigest()
    ok = client.post(f"{API}/payments/webhooks/razorpay", content=body, headers={"X-Razorpay-Signature": sig})
    assert ok.json() == {"status": "ok"}
    assert client.get(f"{API}/payments?status=paid", headers=owner).json()["total"] == 1


def test_expiry_worker_expires_and_reminds_once(client, owner):
    member = create_member(client, owner)
    expiring = create_member(client, owner, full_name="Soon Expiring", phone="9000000002")
    plan = _monthly_plan(client, owner)
    old = client.post(f"{API}/memberships", headers=owner, json={
        "member_id": member["id"], "plan_id": plan["id"],
        "start_date": (date.today() - timedelta(days=30)).isoformat()}).json()  # ended yesterday
    # Ends exactly 7 days from today -> matches the default "7 days" rule
    client.post(f"{API}/memberships", headers=owner, json={
        "member_id": expiring["id"], "plan_id": plan["id"],
        "start_date": (date.today() - timedelta(days=22)).isoformat()})

    result = expiry_worker.run()
    assert result["expired"] == 1
    assert result["queued"] == 2  # 7-day reminder + "membership expired" (ended yesterday)
    assert expiry_worker.run()["queued"] == 0  # idempotent

    with SessionLocal() as db:
        assert db.get(Membership, __import__("uuid").UUID(old["id"])).status == MembershipStatus.EXPIRED
        messages = [n.message for n in db.query(Notification).all()]
    assert any("expires on" in m and "Soon" in m for m in messages)
    assert client.get(f"{API}/members/{member['id']}", headers=owner).json()["status"] == "expired"

    assert notification_worker.run() == 2
    sent = client.get(f"{API}/notifications?status=sent", headers=owner).json()
    assert sent["total"] == 2


def test_payment_worker_marks_overdue(client, owner):
    member = create_member(client, owner)
    client.post(f"{API}/payments", headers=owner, json={
        "member_id": member["id"], "amount": 500, "paid": False,
        "due_date": (date.today() - timedelta(days=3)).isoformat()})
    assert payment_worker.run()["overdue"] == 1
    with SessionLocal() as db:
        assert db.query(Payment).one().status.value == "overdue"


def test_attendance_requires_active_member(client, owner):
    member = create_member(client, owner)
    assert client.post(f"{API}/attendance/check-in", headers=owner,
                       json={"member_id": member["id"]}).status_code == 201
    client.patch(f"{API}/members/{member['id']}", headers=owner, json={"status": "expired"})
    assert client.post(f"{API}/attendance/check-in", headers=owner,
                       json={"member_id": member["id"]}).status_code == 409
    assert len(client.get(f"{API}/attendance", headers=owner).json()) == 1


def test_broadcast_message(client, owner):
    create_member(client, owner)
    create_member(client, owner, full_name="Bob Singh", phone="9000000003")
    resp = client.post(f"{API}/notifications/send", headers=owner,
                       json={"message": "Hi {name}, gym closed on Sunday.", "all_active_members": True}).json()
    assert resp == {"queued": 2, "sent": 2}
    items = client.get(f"{API}/notifications", headers=owner).json()["items"]
    assert {i["message"] for i in items} == {"Hi Asha, gym closed on Sunday.", "Hi Bob, gym closed on Sunday."}

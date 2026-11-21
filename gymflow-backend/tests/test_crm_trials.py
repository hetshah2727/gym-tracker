"""Lead CRM (capture, attribution, dedupe, scoring, pipeline, conversion) and the trial engine."""
from datetime import datetime, timedelta, timezone

from app.core.tenant_context import tenant_scope
from app.database.models import Gym
from app.database.session import SessionLocal
from tests.conftest import API, publish_site, register_gym


def _lead(client, slug, **data):
    payload = {"name": "Neha Shah", "phone": "9000011111", **data}
    resp = client.post(f"{API}/public/sites/{slug}/leads", json=payload)
    assert resp.status_code == 201, resp.text


def _leads(client, owner, **q):
    return client.get(f"{API}/crm/leads", headers=owner, params=q).json()["items"]


def test_attribution_uses_only_real_evidence(client, owner):
    site = publish_site(client, owner)
    _lead(client, site["slug"], phone="9000000001", utm_source="google", utm_medium="gbp")
    _lead(client, site["slug"], phone="9000000002", referrer="https://chatgpt.com/")
    _lead(client, site["slug"], phone="9000000003", referrer="https://www.google.com/")
    _lead(client, site["slug"], phone="9000000004")  # no evidence: stays "website", never guessed as Maps
    by_phone = {l["phone"]: l for l in _leads(client, owner)}
    assert by_phone["9000000001"]["source"] == "google_business_profile"
    assert by_phone["9000000001"]["attribution"]["method"] == "utm"
    assert by_phone["9000000002"]["source"] == "ai_search"
    assert by_phone["9000000002"]["attribution"]["method"] == "referrer"
    assert by_phone["9000000003"]["source"] == "organic_search"
    assert by_phone["9000000004"]["source"] == "website"
    assert by_phone["9000000004"]["attribution"]["method"] == "unknown"


def test_duplicate_enquiry_is_merged(client, owner):
    site = publish_site(client, owner)
    _lead(client, site["slug"], phone="+91 90000 11111")
    _lead(client, site["slug"], phone="9000011111", message="Still interested", wants_trial=True)
    leads = _leads(client, owner)
    assert len(leads) == 1 and leads[0]["wants_trial"] is True
    detail = client.get(f"{API}/crm/leads/{leads[0]['id']}", headers=owner).json()
    assert any("Repeat enquiry" in (i["body"] or "") for i in detail["interactions"])
    assert len([t for t in detail["tasks"] if t["title"].startswith("Contact new enquiry")]) == 1


def test_honeypot_and_validation(client, owner):
    site = publish_site(client, owner)
    assert client.post(f"{API}/public/sites/{site['slug']}/leads", json={"name": "Bot", "phone": "9000000009",
                                                                          "website": "spam"}).status_code == 201
    assert _leads(client, owner) == []
    assert client.post(f"{API}/public/sites/{site['slug']}/leads", json={"name": "No contact"}).status_code == 422


def test_score_is_explained_and_contact_closes_first_task(client, owner):
    lead = client.post(f"{API}/crm/leads", headers=owner, json={"name": "Rohan", "phone": "9123400000",
                                                                 "source": "referral", "wants_trial": True}).json()
    assert lead["score"] > 0 and all("reason" in r and "points" in r for r in lead["score_reasons"])
    assert any("referral" in r["reason"] for r in lead["score_reasons"])
    tasks = client.get(f"{API}/crm/tasks", headers=owner, params={"lead_id": lead["id"]}).json()["items"]
    assert len(tasks) == 1
    client.post(f"{API}/crm/leads/{lead['id']}/interactions", headers=owner, json={"kind": "call", "body": "Spoke"})
    detail = client.get(f"{API}/crm/leads/{lead['id']}", headers=owner).json()
    assert detail["lead"]["status"] == "contacted" and detail["lead"]["first_response_at"]
    assert all(t["status"] == "done" for t in detail["tasks"])


def test_pipeline_rules_and_conversion(client, owner):
    lead = client.post(f"{API}/crm/leads", headers=owner, json={"name": "Kavya", "phone": "9123400001"}).json()
    assert client.post(f"{API}/crm/leads/{lead['id']}/status", headers=owner,
                       json={"status": "converted"}).status_code == 409
    assert client.post(f"{API}/crm/leads/{lead['id']}/status", headers=owner, json={"status": "lost"}).status_code == 422
    plan = client.get(f"{API}/membership-plans", headers=owner).json()[0]
    converted = client.post(f"{API}/crm/leads/{lead['id']}/convert", headers=owner,
                            json={"plan_id": plan["id"], "paid": True, "payment_method": "upi"}).json()
    assert converted["status"] == "converted" and converted["converted_membership_id"]
    member = client.get(f"{API}/members/{converted['converted_member_id']}", headers=owner).json()
    assert member["full_name"] == "Kavya" and member["status"] == "active"
    payments = client.get(f"{API}/payments", headers=owner, params={"member_id": member["id"]}).json()["items"]
    assert payments[0]["status"] == "paid" and payments[0]["amount"] == plan["price"]
    rev = client.get(f"{API}/growth/revenue", headers=owner).json()["summary"]
    assert rev["collected"] == plan["price"]
    sources = client.get(f"{API}/crm/analytics", headers=owner).json()["by_source"]
    assert sources["walk_in"]["joined"] == 1 and sources["walk_in"]["revenue_collected"] == plan["price"]


def test_crm_is_tenant_isolated(client, owner):
    lead = client.post(f"{API}/crm/leads", headers=owner, json={"name": "Private", "phone": "9123400002"}).json()
    other, _ = register_gym(client, name="Other Gym", email="other@gym.example.com")
    assert client.get(f"{API}/crm/leads/{lead['id']}", headers=other).status_code == 404
    assert _leads(client, other) == []
    assert client.post(f"{API}/crm/leads/{lead['id']}/status", headers=other,
                       json={"status": "contacted"}).status_code == 404


# ---------------------------------------------------------------- trials

def _first_slots(client, owner, n=2):
    slots = client.get(f"{API}/trials/slots", headers=owner, params={"days": 7}).json()
    assert len(slots) >= n
    return slots


def _new_lead(client, owner, phone):
    return client.post(f"{API}/crm/leads", headers=owner, json={"name": f"Lead {phone[-2:]}", "phone": phone}).json()


def test_trial_booking_flow_and_double_booking(client, owner):
    slots = _first_slots(client, owner)
    lead = _new_lead(client, owner, "9555500001")
    trial = client.post(f"{API}/trials", headers=owner, json={"lead_id": lead["id"], "starts_at": slots[0]["starts_at"]})
    assert trial.status_code == 201, trial.text
    detail = client.get(f"{API}/crm/leads/{lead['id']}", headers=owner).json()
    assert detail["lead"]["status"] == "trial_booked"
    # Same lead can't hold two active trials
    again = client.post(f"{API}/trials", headers=owner, json={"lead_id": lead["id"], "starts_at": slots[1]["starts_at"]})
    assert again.status_code == 409
    # Not on the grid / outside hours
    off_grid = datetime.fromisoformat(slots[0]["starts_at"]) + timedelta(minutes=7)
    other = _new_lead(client, owner, "9555500002")
    assert client.post(f"{API}/trials", headers=owner, json={"lead_id": other["id"],
                                                               "starts_at": off_grid.isoformat()}).status_code == 422


def test_trial_capacity_and_trainer_conflicts(client, owner):
    trainer = client.post(f"{API}/trainers", headers=owner, json={"full_name": "Coach A"}).json()
    cfg = client.get(f"{API}/trials/config", headers=owner).json()
    cfg["capacity"] = 2
    assert client.put(f"{API}/trials/config", headers=owner, json=cfg).status_code == 200
    slot = _first_slots(client, owner)[0]["starts_at"]
    a, b, c = (_new_lead(client, owner, f"955560000{i}") for i in range(3))
    assert client.post(f"{API}/trials", headers=owner, json={"lead_id": a["id"], "starts_at": slot,
                                                               "trainer_id": trainer["id"]}).status_code == 201
    assert client.post(f"{API}/trials", headers=owner, json={"lead_id": b["id"], "starts_at": slot,
                                                               "trainer_id": trainer["id"]}).status_code == 409
    assert client.post(f"{API}/trials", headers=owner, json={"lead_id": b["id"], "starts_at": slot}).status_code == 201
    assert client.post(f"{API}/trials", headers=owner, json={"lead_id": c["id"], "starts_at": slot}).status_code == 409
    remaining = {s["starts_at"]: s for s in client.get(f"{API}/trials/slots", headers=owner).json()}
    assert slot not in remaining  # full slots are not offered


def test_attendance_no_show_and_pending_review(client, owner):
    slots = _first_slots(client, owner, 2)
    lead = _new_lead(client, owner, "9555700001")
    trial = client.post(f"{API}/trials", headers=owner, json={"lead_id": lead["id"], "starts_at": slots[0]["starts_at"]}).json()
    # Can't confirm a no-show before the trial starts
    assert client.post(f"{API}/trials/{trial['id']}/no-show", headers=owner).status_code == 409

    # Move the slot into the past (as if time passed) and let the daily job flag it.
    from app.database.models import TrialBooking

    with SessionLocal() as db:
        t = db.get(TrialBooking, __import__("uuid").UUID(trial["id"]))
        t.starts_at = datetime.now(timezone.utc) - timedelta(hours=5)
        t.ends_at = datetime.now(timezone.utc) - timedelta(hours=4)
        db.commit()
        gym_id = t.gym_id
    with SessionLocal() as db, tenant_scope(gym_id):
        from app.modules.trials.service import flag_pending_reviews

        assert flag_pending_reviews(db) == 1
        assert flag_pending_reviews(db) == 0  # idempotent
    listed = client.get(f"{API}/trials", headers=owner, params={"status": "pending_review",
                                                                "start": (datetime.now() - timedelta(days=2)).date().isoformat()}).json()
    assert listed and listed[0]["status"] == "pending_review"  # NOT auto-marked as no-show
    ns = client.post(f"{API}/trials/{trial['id']}/no-show", headers=owner)
    assert ns.status_code == 200 and ns.json()["status"] == "no_show"
    opps = client.get(f"{API}/recovery/opportunities", headers=owner, params={"tab": "no_shows"}).json()
    assert opps["total"] == 1 and opps["items"][0]["lead_id"] == lead["id"]

    lead2 = _new_lead(client, owner, "9555700002")
    t2 = client.post(f"{API}/trials", headers=owner, json={"lead_id": lead2["id"], "starts_at": slots[1]["starts_at"]}).json()
    assert client.post(f"{API}/trials/{t2['id']}/attended", headers=owner).json()["status"] == "attended"
    assert client.get(f"{API}/crm/leads/{lead2['id']}", headers=owner).json()["lead"]["status"] == "trial_attended"


def test_trial_to_membership_conversion_is_tracked(client, owner):
    slot = _first_slots(client, owner)[0]["starts_at"]
    lead = _new_lead(client, owner, "9555800001")
    trial = client.post(f"{API}/trials", headers=owner, json={"lead_id": lead["id"], "starts_at": slot}).json()
    client.post(f"{API}/trials/{trial['id']}/attended", headers=owner)
    plan = client.get(f"{API}/membership-plans", headers=owner).json()[0]
    client.post(f"{API}/crm/leads/{lead['id']}/convert", headers=owner, json={"plan_id": plan["id"], "paid": False})
    stats = client.get(f"{API}/trials/analytics", headers=owner).json()
    assert stats["completed"] == 1 and stats["converted"] == 1 and stats["trial_to_membership"] == 1.0
    # Unpaid conversion is not collected revenue
    assert client.get(f"{API}/growth/revenue", headers=owner).json()["summary"]["collected"] == 0


def test_public_trial_booking(client, owner):
    site = publish_site(client, owner)
    slots = client.get(f"{API}/public/sites/{site['slug']}/trial-slots").json()
    assert slots["enabled"] and slots["slots"]
    resp = client.post(f"{API}/public/sites/{site['slug']}/trials", json={
        "name": "Web Visitor", "phone": "9666600001", "starts_at": slots["slots"][0]["starts_at"],
        "utm_source": "instagram", "utm_medium": "social"})
    assert resp.status_code == 201, resp.text
    lead = _leads(client, owner)[0]
    assert lead["status"] == "trial_booked" and lead["source"] == "instagram"
    with SessionLocal() as db:
        assert db.query(Gym).count() == 1

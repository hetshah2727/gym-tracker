"""IronCore Fitness demo: realistic ranges, reconciliation, isolation and reset."""
from app.demo import ironcore
from app.database.session import SessionLocal
from tests.conftest import API


def _login(client, email, password):
    tok = client.post(f"{API}/auth/login", json={"email": email, "password": password}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}


def test_demo_tenant_is_coherent_and_isolated(client, owner, admin):
    real_before = client.get(f"{API}/crm/leads", headers=owner).json()["total"]
    result = client.post(f"{API}/platform/demo/reset", headers=admin).json()
    assert result["status"] == "created" and 350 <= result["members"] <= 500
    demo = _login(client, *ironcore.OWNER)
    dash = client.get(f"{API}/growth/dashboard", headers=demo).json()
    assert dash["gym"]["is_demo"] is True
    b = dash["business"]
    assert 20 <= b["upcoming_renewals_30d"] <= 30 and 10 <= b["outstanding_count"] <= 20
    assert b["inactive_or_expired_members"] in range(20, 31)
    leads = client.get(f"{API}/crm/analytics", headers=demo, params={"days": 60}).json()
    assert 40 <= leads["total_enquiries"] <= 60
    trials = client.get(f"{API}/trials/analytics", headers=demo, params={"days": 60}).json()
    assert 15 <= trials["total"] <= 20 and 5 <= trials["no_shows"] <= 10
    # Revenue reconciles with payment records
    month = client.get(f"{API}/growth/revenue", headers=demo).json()["summary"]
    paid = client.get(f"{API}/payments", headers=demo, params={"status": "paid", "limit": 200,
                                                                "date_from": dash["period"]["start"]}).json()
    assert month["recovered"] <= month["collected"]
    history = client.get(f"{API}/recovery/opportunities", headers=demo, params={"tab": "history", "limit": 200}).json()
    won = [o for o in history["items"] if o["status"] == "won"]
    assert won and all(o["recovered_payment_id"] for o in won)
    # External-integration data is labelled simulated
    audit = client.get(f"{API}/seo/audits", headers=demo).json()[0]
    assert audit["data_source"] == "demo_simulated"
    assert client.get(f"{API}/seo/performance", headers=demo).json()["connected"] is False  # no fake GSC numbers
    assert {r["source"] for r in client.get(f"{API}/local/reviews", headers=demo).json()} == {"demo_simulated"}
    # Isolation: the real gym is untouched and can't reset the demo
    assert client.get(f"{API}/crm/leads", headers=owner).json()["total"] == real_before
    assert client.post(f"{API}/growth/demo/reset", headers=owner).status_code == 403
    # Reset rebuilds the demo only
    again = client.post(f"{API}/growth/demo/reset", headers=_login(client, *ironcore.OWNER)).json()
    assert again["status"] == "created" and again["members"] == result["members"]
    assert paid["total"] >= 1
    with SessionLocal() as db:
        from app.database.models import Gym

        assert db.query(Gym).filter(Gym.slug == ironcore.DEMO_SLUG).count() == 1

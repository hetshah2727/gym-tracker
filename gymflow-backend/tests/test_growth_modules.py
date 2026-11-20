"""Diet plans, affiliate store, website builder, member portal and platform admin."""
from app.integrations.ai.diet_generator import MemberProfile, compute_targets
from app.modules.affiliate.service import split_commission
from tests.conftest import API, create_member


def test_calorie_targets():
    p = MemberProfile(name="A", gender="male", age=30, height_cm=175, weight_kg=80, goal="weight_loss",
                      diet_type="veg")
    calories, macros = compute_targets(p)
    # BMR = 800 + 1093.75 - 150 + 5 = 1748.75; x1.55 = 2710.6; -500 -> ~2210
    assert calories == 2210
    assert macros.protein_g == 160
    assert abs(macros.protein_g * 4 + macros.carbs_g * 4 + macros.fat_g * 9 - calories) < 15


def test_diet_plan_generate_review_assign(client, owner):
    member = create_member(client, owner)
    plan = client.post(f"{API}/diet-plans/generate", headers=owner, json={"member_id": member["id"]})
    assert plan.status_code == 201, plan.text
    plan = plan.json()
    assert plan["status"] == "draft" and plan["ai_generated"] is False and len(plan["meals"]) == 5

    edited = client.patch(f"{API}/diet-plans/{plan['id']}", headers=owner,
                          json={"notes": "No sugar in tea"}).json()
    assert edited["notes"] == "No sugar in tea"
    assigned = client.post(f"{API}/diet-plans/{plan['id']}/assign", headers=owner).json()
    assert assigned["status"] == "assigned"


def test_diet_plan_requires_profile(client, owner):
    member = create_member(client, owner, height_cm=None, phone="9000000004")
    resp = client.post(f"{API}/diet-plans/generate", headers=owner, json={"member_id": member["id"]})
    assert resp.status_code == 422 and "height_cm" in resp.json()["detail"]


def test_revenue_split_always_adds_up():
    s = split_commission(333.33, has_trainer=True)
    assert s["platform_share"] + s["gym_share"] + s["trainer_share"] == s["commission_amount"]
    assert (s["gym_share"], s["trainer_share"]) == (100.0, 166.67)
    no_trainer = split_commission(100, has_trainer=False)
    assert (no_trainer["gym_share"], no_trainer["trainer_share"], no_trainer["platform_share"]) == (80, 0, 20)


def test_affiliate_flow(client, owner, admin):
    product = client.post(f"{API}/affiliate/products", headers=admin, json={
        "name": "Whey Protein 1kg", "category": "supplements", "price": 2499, "asin": "B000TEST01",
        "external_url": "https://www.amazon.in/dp/B000TEST01", "commission_rate_pct": 8}).json()
    assert client.post(f"{API}/affiliate/products", headers=owner, json={
        "name": "x", "category": "y", "external_url": "https://e.com"}).status_code == 403

    trainer = client.post(f"{API}/trainers", headers=owner, json={"full_name": "Coach A"}).json()
    link = client.post(f"{API}/affiliate/links", headers=owner,
                       json={"product_id": product["id"], "trainer_id": trainer["id"]}).json()

    redirect = client.get(f"{API}/affiliate/r/{link['code']}", follow_redirects=False)
    assert redirect.status_code == 302
    assert "B000TEST01" in redirect.headers["location"] and f"ascsubtag={link['code']}" in redirect.headers["location"]

    conv = client.post(f"{API}/affiliate/conversions", headers=admin,
                       json={"link_code": link["code"], "order_amount": 2500}).json()
    assert conv["commission_amount"] == 200 and conv["trainer_share"] == 100 and conv["gym_share"] == 60

    earnings = client.get(f"{API}/affiliate/earnings", headers=owner).json()
    assert earnings["total_clicks"] == 1 and earnings["gym_earnings"] == 60
    assert earnings["by_trainer"][0]["earnings"] == 100


def test_website_builder_publish_and_leads(client, owner):
    site = client.post(f"{API}/websites", headers=owner, json={"name": "Main site"}).json()
    assert site["slug"] == "iron-temple" and site["blocks"][0]["type"] == "hero"
    assert client.get(f"{API}/public/sites/iron-temple").status_code == 404  # not yet published

    blocks = site["blocks"]
    blocks[0]["props"]["heading"] = "Welcome!"
    client.put(f"{API}/websites/{site['id']}", headers=owner, json={"blocks": blocks})
    client.post(f"{API}/websites/{site['id']}/publish", headers=owner)

    public = client.get(f"{API}/public/sites/iron-temple").json()
    assert public["site"]["blocks"][0]["props"]["heading"] == "Welcome!"
    assert len(public["plans"]) == 4

    # Draft edits don't go live until republished
    blocks[0]["props"]["heading"] = "Draft"
    client.put(f"{API}/websites/{site['id']}", headers=owner, json={"blocks": blocks})
    assert client.get(f"{API}/public/sites/iron-temple").json()["site"]["blocks"][0]["props"]["heading"] == "Welcome!"

    bad_block = client.put(f"{API}/websites/{site['id']}", headers=owner, json={"blocks": [{"type": "script"}]})
    assert bad_block.status_code == 422

    assert client.post(f"{API}/public/sites/iron-temple/leads", json={"name": "Neha", "phone": "9000011111"}
                       ).status_code == 201
    leads = client.get(f"{API}/leads", headers=owner).json()
    assert leads[0]["name"] == "Neha" and leads[0]["status"] == "new"


def test_member_portal(client, owner, admin):
    member = create_member(client, owner)
    plan = client.get(f"{API}/membership-plans", headers=owner).json()[0]
    client.post(f"{API}/memberships", headers=owner, json={"member_id": member["id"], "plan_id": plan["id"]})
    diet = client.post(f"{API}/diet-plans/generate", headers=owner, json={"member_id": member["id"]}).json()
    client.post(f"{API}/members/{member['id']}/portal-access", headers=owner,
                json={"email": "asha@example.com", "password": "memberpass"})
    token = client.post(f"{API}/auth/login", json={"email": "asha@example.com", "password": "memberpass"})
    m = {"Authorization": f"Bearer {token.json()['access_token']}"}

    assert client.get(f"{API}/me/profile", headers=m).json()["id"] == member["id"]
    assert len(client.get(f"{API}/me/memberships", headers=m).json()) == 1
    assert client.get(f"{API}/me/diet-plans", headers=m).json() == []  # draft is hidden
    client.post(f"{API}/diet-plans/{diet['id']}/assign", headers=owner)
    assert len(client.get(f"{API}/me/diet-plans", headers=m).json()) == 1
    # Members cannot reach staff endpoints
    assert client.get(f"{API}/members", headers=m).status_code == 403


def test_platform_admin(client, owner, admin):
    gyms = client.get(f"{API}/platform/gyms", headers=admin).json()
    assert len(gyms) == 1 and gyms[0]["subscription_status"] == "trialing"
    assert client.get(f"{API}/platform/gyms", headers=owner).status_code == 403

    # Admin can act inside a gym with X-Gym-ID
    resp = client.get(f"{API}/members", headers={**admin, "X-Gym-ID": gyms[0]["id"]})
    assert resp.status_code == 200

    client.patch(f"{API}/platform/gyms/{gyms[0]['id']}", headers=admin, json={"is_active": False})
    login = client.post(f"{API}/auth/login", json={"email": "owner@iron.example.com", "password": "supersecret"})
    assert login.status_code == 403
    assert client.get(f"{API}/platform/stats", headers=admin).json()["total_gyms"] == 1

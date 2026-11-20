from tests.conftest import API, create_member, register_gym


def test_register_seeds_gym_defaults(client, owner):
    me = client.get(f"{API}/auth/me", headers=owner).json()
    assert me["role"] == "gym_owner"
    plans = client.get(f"{API}/membership-plans", headers=owner).json()
    assert [p["name"] for p in plans] == ["Monthly", "Quarterly", "Half-Yearly", "Yearly"]
    rules = client.get(f"{API}/automation/rules", headers=owner).json()
    assert len(rules) == 4
    sub = client.get(f"{API}/subscriptions/current", headers=owner).json()
    assert sub["status"] == "trialing" and sub["plan"]["code"] == "growth"


def test_login_and_duplicate_email(client, owner):
    bad = client.post(f"{API}/auth/login", json={"email": "owner@iron.example.com", "password": "wrong-pass"})
    assert bad.status_code == 401
    ok = client.post(f"{API}/auth/login", json={"email": "OWNER@iron.example.com", "password": "supersecret"})
    assert ok.status_code == 200
    dup = client.post(f"{API}/auth/register", json={"gym_name": "Other", "owner_name": "X Y",
                                                    "email": "owner@iron.example.com", "password": "supersecret"})
    assert dup.status_code == 409


def test_unauthenticated_is_rejected(client):
    assert client.get(f"{API}/members").status_code == 401


def test_gyms_cannot_see_each_others_data(client, owner):
    other, _ = register_gym(client, name="Flex Zone", email="owner@flex.example.com")
    member = create_member(client, owner)

    assert client.get(f"{API}/members", headers=other).json()["total"] == 0
    assert client.get(f"{API}/members/{member['id']}", headers=other).status_code == 404
    assert client.patch(f"{API}/members/{member['id']}", json={"full_name": "Hacked"},
                        headers=other).status_code == 404
    assert client.get(f"{API}/members", headers=owner).json()["total"] == 1


def test_trainer_sees_only_assigned_members(client, owner):
    resp = client.post(f"{API}/users", headers=owner, json={
        "full_name": "Coach Vikram", "email": "vikram@iron.example.com", "password": "trainerpass", "role": "trainer"})
    assert resp.status_code == 201
    trainer = client.get(f"{API}/trainers", headers=owner).json()[0]
    mine = create_member(client, owner, full_name="Mine", trainer_id=trainer["id"])
    create_member(client, owner, full_name="Not Mine", phone="9000000001")

    token = client.post(f"{API}/auth/login", json={"email": "vikram@iron.example.com", "password": "trainerpass"})
    t_headers = {"Authorization": f"Bearer {token.json()['access_token']}"}
    listed = client.get(f"{API}/members", headers=t_headers).json()
    assert [m["id"] for m in listed["items"]] == [mine["id"]]
    # Trainers cannot create members or touch billing
    assert client.post(f"{API}/members", json={"full_name": "x", "phone": "9999999999"},
                       headers=t_headers).status_code == 403
    assert client.get(f"{API}/payments", headers=t_headers).status_code == 403

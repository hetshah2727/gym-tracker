import os
import tempfile

# Point the app at a throwaway SQLite database before anything imports settings.
_tmpdir = tempfile.mkdtemp(prefix="gymflow-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["ANTHROPIC_API_KEY"] = ""      # use the offline diet template
os.environ["GROQ_API_KEY"] = ""           # never call live AI providers from tests
os.environ["GEMINI_API_KEY"] = ""
os.environ["RAZORPAY_KEY_ID"] = ""
os.environ["RAZORPAY_KEY_SECRET"] = ""
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "whsec_test"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"
os.environ["WHATSAPP_APP_SECRET"] = "wa_app_secret"
os.environ["WHATSAPP_VERIFY_TOKEN"] = "wa_verify"
for _key in ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET", "RAZORPAY_KEY_ID", "RAZORPAY_KEY_SECRET",
             "WHATSAPP_PHONE_NUMBER_ID", "WHATSAPP_ACCESS_TOKEN", "N8N_WEBHOOK_BASE_URL"):
    os.environ[_key] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.security import hash_password  # noqa: E402
from app.database.models import User  # noqa: E402
from app.database.models.enums import Role  # noqa: E402
from app.database.session import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402

API = "/api/v1"


@pytest.fixture(autouse=True)
def fresh_db():
    from app.core import rate_limit
    from app.modules.seo import service as seo_service

    rate_limit.reset()
    original_fetcher = seo_service.FETCHER_FACTORY
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)
    seo_service.FETCHER_FACTORY = original_fetcher


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register_gym(client, name="Iron Temple", email="owner@iron.example.com"):
    resp = client.post(f"{API}/auth/register", json={
        "gym_name": name, "owner_name": "Ravi Kumar", "email": email,
        "password": "supersecret", "phone": "9876543210", "city": "Pune",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    return {"Authorization": f"Bearer {body['access_token']}"}, body["user"]


@pytest.fixture
def owner(client):
    headers, _ = register_gym(client)
    return headers


@pytest.fixture
def admin(client):
    with SessionLocal() as db:
        db.add(User(email="admin@gymflow.example.com", hashed_password=hash_password("adminpass1"),
                    full_name="Platform Admin", role=Role.PLATFORM_ADMIN))
        db.commit()
    token = client.post(f"{API}/auth/login", json={"email": "admin@gymflow.example.com", "password": "adminpass1"})
    return {"Authorization": f"Bearer {token.json()['access_token']}"}


def create_member(client, headers, **overrides):
    payload = {"full_name": "Asha Patel", "phone": "9123456780", "gender": "female", "height_cm": 162,
               "weight_kg": 68, "fitness_goal": "weight_loss", "diet_preference": "veg",
               "date_of_birth": "1996-05-14", **overrides}
    resp = client.post(f"{API}/members", json=payload, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


def set_plan(client, headers, code):
    resp = client.post(f"{API}/subscriptions/change-plan", json={"plan_code": code}, headers=headers)
    assert resp.status_code == 200, resp.text


def publish_site(client, headers):
    site = client.post(f"{API}/websites", headers=headers, json={"name": "Main site"}).json()
    assert client.post(f"{API}/websites/{site['id']}/publish", headers=headers).status_code == 200
    return site


def fill_profile(client, headers, **overrides):
    payload = {"business_name": "Iron Temple", "address_line": "12 Race Course Road, Gotri", "area": "Gotri",
               "city": "Vadodara", "state": "Gujarat", "postal_code": "390021", "phone": "9876543210",
               "website_url": "https://irontemple.example", "description": "Strength-focused neighbourhood gym.",
               "opening_hours": [{"days": "Mon-Sat", "opens": "05:30", "closes": "22:00"}],
               "services": ["Personal training", "Weight training"], "facilities": ["Free weights", "Cardio zone"],
               "service_areas": ["Gotri", "Alkapuri"], "trial_offer": {"enabled": True, "price": 0},
               "faqs": [{"q": "Is parking available at the gym?", "a": "Yes, free two-wheeler parking.",
                         "approved": True}], **overrides}
    resp = client.put(f"{API}/gym-profile", headers=headers, json=payload)
    assert resp.status_code == 200, resp.text
    return resp.json()

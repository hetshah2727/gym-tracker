import os
import tempfile

# Point the app at a throwaway SQLite database before anything imports settings.
_tmpdir = tempfile.mkdtemp(prefix="gymflow-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["ANTHROPIC_API_KEY"] = ""      # use the offline diet template
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["RAZORPAY_WEBHOOK_SECRET"] = "whsec_test"
os.environ["SECRET_KEY"] = "test-secret-key-that-is-at-least-32-bytes-long"

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
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


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

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import SubscriptionPlan

DEFAULT_PLANS = [
    {"code": "starter", "name": "Starter", "price_monthly": 999, "max_members": 150,
     "features": {"automation": True, "ai_diet": False, "affiliate": True, "website_builder": False,
                  "voice_calls": False}},
    {"code": "growth", "name": "Growth", "price_monthly": 2499, "max_members": 500,
     "features": {"automation": True, "ai_diet": True, "affiliate": True, "website_builder": True,
                  "voice_calls": False}},
    {"code": "pro", "name": "Pro", "price_monthly": 4999, "max_members": None,
     "features": {"automation": True, "ai_diet": True, "affiliate": True, "website_builder": True,
                  "voice_calls": True}},
]


def ensure_default_plans(db: Session) -> None:
    """Idempotently seed the SaaS plans (no commit; caller commits)."""
    existing = set(db.scalars(select(SubscriptionPlan.code)).all())
    for plan in DEFAULT_PLANS:
        if plan["code"] not in existing:
            db.add(SubscriptionPlan(**plan))
    db.flush()

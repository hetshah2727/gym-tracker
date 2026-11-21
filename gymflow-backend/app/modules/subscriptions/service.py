from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.entitlements import FEATURES, plan_features
from app.database.models import SubscriptionEvent, SubscriptionPlan

# Packaging suggestions, not final prices - the platform admin edits these.
DEFAULT_PLANS = [
    {"code": "starter", "name": "Starter", "price_monthly": 999, "max_members": 200},
    {"code": "growth", "name": "Growth", "price_monthly": 2499, "max_members": 600},
    {"code": "pro", "name": "Pro", "price_monthly": 4999, "max_members": None},
]


def ensure_default_plans(db: Session) -> None:
    """Idempotently seed the SaaS plans and add newly introduced feature keys (no commit; caller commits).

    Existing feature values are never overwritten, so admin edits survive upgrades.
    """
    existing = {p.code: p for p in db.scalars(select(SubscriptionPlan)).all()}
    for plan in DEFAULT_PLANS:
        defaults = plan_features(plan["code"])
        row = existing.get(plan["code"])
        if row is None:
            db.add(SubscriptionPlan(**plan, features=defaults))
        else:
            missing = {k: v for k, v in defaults.items() if k not in (row.features or {})}
            if missing:
                row.features = {**(row.features or {}), **missing}
    db.flush()


def log_event(db: Session, gym_id, event: str, *, from_plan: str | None = None, to_plan: str | None = None,
              status: str | None = None, actor_user_id=None, notes: str | None = None) -> None:
    db.add(SubscriptionEvent(gym_id=gym_id, event=event, from_plan=from_plan, to_plan=to_plan, status=status,
                             actor_user_id=actor_user_id, notes=notes))


__all__ = ["DEFAULT_PLANS", "FEATURES", "ensure_default_plans", "log_event"]

"""Centralised subscription entitlements: which features and usage limits a gym's plan includes.

Every plan-gated endpoint uses ``gym_feature(...)`` and the frontend reads ``GET /subscriptions/entitlements``,
so plan access is defined here once instead of being hard-coded across the app.
"""
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.permissions import tenant_user
from app.core.tenant_context import get_current_gym_id
from app.database.models import GymSubscription, SubscriptionPlan, UsageCounter, User
from app.database.models.enums import Role, SubscriptionStatus
from app.database.session import get_db

# key -> (label, plan tier that first includes it)
FEATURES: dict[str, tuple[str, str]] = {
    # Starter
    "members": ("Members, plans, payments & check-in", "starter"),
    "lead_crm": ("Enquiry inbox & follow-ups", "starter"),
    "trials": ("Trial booking", "starter"),
    "seo_audit": ("Website health check", "starter"),
    "basic_reports": ("Basic reports", "starter"),
    "website_builder": ("Gym website builder", "starter"),
    "automation": ("Automatic reminders", "starter"),
    "affiliate": ("Supplement store add-on", "starter"),
    # Growth
    "ai_sales_agent": ("AI receptionist for enquiries", "growth"),
    "whatsapp_workflows": ("WhatsApp workflows", "growth"),
    "renewal_automation": ("Automatic renewal follow-ups", "growth"),
    "local_seo": ("Google Maps listing & reviews", "growth"),
    "recovery_center": ("Late fee & renewal collection", "growth"),
    "business_analyst": ("Ask GymFlow (AI answers about your gym)", "growth"),
    "ai_search_readiness": ("ChatGPT & AI search checklist", "growth"),
    "ai_diet": ("AI diet plans", "growth"),
    # Pro
    "advanced_seo": ("Google search reports", "pro"),
    "ai_search_monitoring": ("AI search tracking", "pro"),
    "advanced_analytics": ("Advanced analytics", "pro"),
    "voice_calls": ("AI voice calls (coming soon)", "pro"),
}

TIER_ORDER = ["starter", "growth", "pro"]

# Monthly usage limits per tier (None = unlimited)
LIMITS: dict[str, dict[str, int | None]] = {
    "starter": {"ai_messages": 300, "seo_audits": 4, "content_generations": 30},
    "growth": {"ai_messages": 3000, "seo_audits": 15, "content_generations": 300},
    "pro": {"ai_messages": 15000, "seo_audits": 60, "content_generations": 1500},
}

# Features that stay on when a subscription lapses, so a gym never loses access to its own records.
CORE_FEATURES = {"members", "lead_crm", "trials", "basic_reports"}


def plan_features(tier: str) -> dict[str, bool]:
    level = TIER_ORDER.index(tier) if tier in TIER_ORDER else 0
    return {key: TIER_ORDER.index(min_tier) <= level for key, (_, min_tier) in FEATURES.items()}


@dataclass
class Entitlements:
    plan_code: str | None
    plan_name: str | None
    status: str                 # active | trialing | trial_expired | past_due | cancelled | none
    trial_ends_at: datetime | None
    features: dict[str, bool]
    limits: dict[str, int | None]
    max_members: int | None

    def has(self, feature: str) -> bool:
        return bool(self.features.get(feature))


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def resolve(db: Session, gym_id=None) -> Entitlements:
    gym_id = gym_id or get_current_gym_id()
    sub = db.scalar(select(GymSubscription).where(GymSubscription.gym_id == gym_id)
                    .order_by(GymSubscription.created_at.desc()))
    if sub is None:
        restricted = {k: k in CORE_FEATURES for k in FEATURES}
        return Entitlements(None, None, "none", None, restricted, LIMITS["starter"], None)
    plan = db.get(SubscriptionPlan, sub.plan_id)
    tier = plan.code if plan and plan.code in TIER_ORDER else "starter"
    features = plan_features(tier)
    # Admin-edited plan feature flags override the tier defaults.
    for key, value in (plan.features or {}).items() if plan else []:
        if key in features:
            features[key] = bool(value)
    state = sub.status.value
    now = datetime.now(timezone.utc)
    if sub.status == SubscriptionStatus.TRIALING and _aware(sub.current_period_end) < now:
        state = "trial_expired"
    if state in ("trial_expired", "cancelled", "past_due") and not (
            state == "past_due" and (now - _aware(sub.current_period_end)).days <= 7):  # 7-day grace
        features = {k: k in CORE_FEATURES for k in features}
    return Entitlements(
        plan_code=plan.code if plan else None, plan_name=plan.name if plan else None, status=state,
        trial_ends_at=sub.current_period_end if sub.status == SubscriptionStatus.TRIALING else None,
        features=features, limits=LIMITS.get(tier, LIMITS["starter"]),
        max_members=plan.max_members if plan else None,
    )


def gym_feature(feature: str, *roles: Role) -> Callable[..., User]:
    """Dependency: tenant user with one of ``roles`` whose gym's plan includes ``feature``."""
    if feature not in FEATURES:
        raise ValueError(f"Unknown feature {feature}")
    tenant_dep = tenant_user(*roles)

    async def dependency(user: User = Depends(tenant_dep), db: Session = Depends(get_db)) -> User:
        if user.role != Role.PLATFORM_ADMIN and not resolve(db).has(feature):
            label, tier = FEATURES[feature]
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                                f"{label} is not included in your current plan (requires {tier.title()}).")
        return user

    return dependency


# ---- Usage metering ----

def _period(today: date | None = None) -> str:
    return (today or date.today()).strftime("%Y-%m")


def usage(db: Session, metric: str, gym_id=None) -> int:
    gym_id = gym_id or get_current_gym_id()
    row = db.scalar(select(UsageCounter).where(UsageCounter.gym_id == gym_id, UsageCounter.metric == metric,
                                               UsageCounter.period == _period()))
    return row.count if row else 0


def within_limit(db: Session, metric: str, gym_id=None) -> bool:
    limit = resolve(db, gym_id).limits.get(metric)
    return limit is None or usage(db, metric, gym_id) < limit


def enforce_limit(db: Session, metric: str, gym_id=None) -> None:
    if not within_limit(db, metric, gym_id):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS,
                            f"Monthly {metric.replace('_', ' ')} limit reached for your plan.")


def record_usage(db: Session, metric: str, amount: int = 1, gym_id=None) -> None:
    gym_id = gym_id or get_current_gym_id()
    period = _period()
    row = db.scalar(select(UsageCounter).where(UsageCounter.gym_id == gym_id, UsageCounter.metric == metric,
                                               UsageCounter.period == period))
    if row is None:
        try:
            with db.begin_nested():
                db.add(UsageCounter(gym_id=gym_id, metric=metric, period=period, count=amount))
            db.commit()
            return
        except IntegrityError:
            row = db.scalar(select(UsageCounter).where(UsageCounter.gym_id == gym_id,
                                                       UsageCounter.metric == metric, UsageCounter.period == period))
    row.count += amount
    db.commit()

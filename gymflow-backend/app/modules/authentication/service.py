from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.database.models import AutomationRule, Gym, GymSubscription, MembershipPlan, SubscriptionPlan, User
from app.database.models.enums import AutomationTrigger, Channel, Role, SubscriptionStatus
from app.modules.authentication.schemas import RegisterGymRequest, TokenResponse, UserOut
from app.modules.common import unique_slug
from app.modules.subscriptions.service import ensure_default_plans, log_event

DEFAULT_MEMBERSHIP_PLANS = [
    ("Monthly", 30, 1500),
    ("Quarterly", 90, 4000),
    ("Half-Yearly", 180, 7500),
    ("Yearly", 365, 13000),
]

DEFAULT_AUTOMATION_RULES = [
    ("Expiry reminder - 30 days", AutomationTrigger.MEMBERSHIP_EXPIRING, 30, Channel.WHATSAPP,
     "Hi {name}, your {gym} membership ends on {end_date}. Renew early to keep your plan running."),
    ("Expiry reminder - 15 days", AutomationTrigger.MEMBERSHIP_EXPIRING, 15, Channel.WHATSAPP,
     "Hi {name}, 15 days left on your {gym} membership (ends {end_date}). Reply to renew."),
    ("Expiry reminder - 7 days", AutomationTrigger.MEMBERSHIP_EXPIRING, 7, Channel.WHATSAPP,
     "Hi {name}, your {gym} membership expires on {end_date}. Renew now to keep your streak going!"),
    ("Expiry reminder - 1 day", AutomationTrigger.MEMBERSHIP_EXPIRING, 1, Channel.WHATSAPP,
     "Hi {name}, your {gym} membership expires tomorrow ({end_date}). Reply to renew."),
    ("Membership expired", AutomationTrigger.MEMBERSHIP_EXPIRED, 0, Channel.WHATSAPP,
     "Hi {name}, your {gym} membership expired on {end_date}. We miss you - renew today!"),
    ("Payment due", AutomationTrigger.PAYMENT_DUE, 0, Channel.WHATSAPP,
     "Hi {name}, a payment of {currency} {amount} is due on {due_date} at {gym}."),
]


def issue_token(user: User) -> TokenResponse:
    token = create_access_token(
        str(user.id), {"role": user.role.value, "gym_id": str(user.gym_id) if user.gym_id else None}
    )
    return TokenResponse(access_token=token, user=UserOut.model_validate(user))


def register_gym(db: Session, data: RegisterGymRequest) -> TokenResponse:
    """Create a new tenant: gym + owner login + default plans/rules + trial subscription."""
    if db.scalar(select(User).where(User.email == data.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    slug = unique_slug(data.gym_name, lambda s: db.scalar(select(Gym.id).where(Gym.slug == s)) is not None)
    gym = Gym(name=data.gym_name, slug=slug, email=data.email.lower(), phone=data.phone, city=data.city)
    db.add(gym)
    db.flush()

    owner = User(
        gym_id=gym.id, email=data.email.lower(), hashed_password=hash_password(data.password),
        full_name=data.owner_name, phone=data.phone, role=Role.GYM_OWNER,
    )
    db.add(owner)

    for name, days, price in DEFAULT_MEMBERSHIP_PLANS:
        db.add(MembershipPlan(gym_id=gym.id, name=name, duration_days=days, price=price))
    for name, trigger, offset, channel, template in DEFAULT_AUTOMATION_RULES:
        db.add(AutomationRule(gym_id=gym.id, name=name, trigger=trigger, offset_days=offset,
                              channel=channel, template=template))

    ensure_default_plans(db)
    trial_plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == "growth"))
    if trial_plan:
        db.add(GymSubscription(
            gym_id=gym.id, plan_id=trial_plan.id, status=SubscriptionStatus.TRIALING,
            current_period_end=datetime.now(timezone.utc) + timedelta(days=settings.TRIAL_DAYS),
        ))
        log_event(db, gym.id, "trial_started", to_plan=trial_plan.code, status="trialing",
                  notes=f"{settings.TRIAL_DAYS}-day trial")

    db.commit()
    db.refresh(owner)
    return issue_token(owner)


def authenticate(db: Session, email: str, password: str) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None or not verify_password(password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Incorrect email or password")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
    if user.gym_id is not None:
        gym = db.get(Gym, user.gym_id)
        if gym is None or not gym.is_active:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "This gym's account is suspended")
    return issue_token(user)

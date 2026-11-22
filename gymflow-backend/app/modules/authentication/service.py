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


RESET_MINUTES = 30
REFERRAL_TRIAL_DAYS = 30
REFERRAL_REWARD_DAYS = 30


def reward_referrer(db: Session, gym: Gym) -> bool:
    """Called when a referred gym's first paid subscription starts: give the referrer one free month (once)."""
    import uuid as _uuid

    from app.database.models import GymSubscription

    ref_id = (gym.settings or {}).get("referred_by")
    if not ref_id or (gym.settings or {}).get("referral_rewarded"):
        return False
    sub = db.scalar(select(GymSubscription).where(GymSubscription.gym_id == _uuid.UUID(ref_id))
                    .order_by(GymSubscription.created_at.desc()))
    if sub is None:
        return False
    base = max(sub.current_period_end if sub.current_period_end.tzinfo else sub.current_period_end.replace(tzinfo=timezone.utc),
               datetime.now(timezone.utc))
    sub.current_period_end = base + timedelta(days=REFERRAL_REWARD_DAYS)
    gym.settings = {**(gym.settings or {}), "referral_rewarded": True}
    log_event(db, sub.gym_id, "referral_reward", status=sub.status.value,
              notes=f"{REFERRAL_REWARD_DAYS} free days – {gym.name} started paying")
    return True


def _password_fingerprint(user: User) -> str:
    # Changes whenever the password changes, so a reset link stops working once it has been used.
    import hashlib

    return hashlib.sha256(user.hashed_password.encode()).hexdigest()[:16]


def reset_token(user: User) -> str:
    return create_access_token(str(user.id), {"purpose": "password_reset", "pw": _password_fingerprint(user)},
                               expires_minutes=RESET_MINUTES)


def send_reset_email(user: User) -> None:
    from app.services import email

    link = f"{settings.FRONTEND_URL.rstrip('/')}/reset-password?token={reset_token(user)}"
    email.send(user.email, "Reset your GymFlow password",
               f"Hi {user.full_name.split()[0]},\n\nUse this link to set a new password (valid for {RESET_MINUTES} "
               f"minutes):\n{link}\n\nIf you didn't ask for this, you can ignore this email.")


def reset_password(db: Session, token: str, password: str) -> TokenResponse:
    import uuid

    import jwt

    from app.core.security import decode_access_token

    invalid = HTTPException(status.HTTP_400_BAD_REQUEST, "This reset link is invalid or has expired")
    try:
        payload = decode_access_token(token)
        user = db.get(User, uuid.UUID(payload["sub"]))
    except (jwt.PyJWTError, KeyError, ValueError):
        raise invalid
    if (payload.get("purpose") != "password_reset" or user is None or not user.is_active
            or payload.get("pw") != _password_fingerprint(user)):
        raise invalid
    user.hashed_password = hash_password(password)
    db.commit()
    return issue_token(user)


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
    # Referral: the new gym gets a longer trial; the referrer is rewarded once this gym starts paying.
    referrer = None
    if data.referral_code:
        referrer = db.scalar(select(Gym).where(Gym.slug == data.referral_code.strip().lower(), Gym.id != gym.id,
                                               Gym.is_active.is_(True)))
        if referrer is not None and not (referrer.settings or {}).get("is_demo"):
            gym.settings = {**(gym.settings or {}), "referred_by": str(referrer.id)}
        else:
            referrer = None
    trial_days = max(settings.TRIAL_DAYS, REFERRAL_TRIAL_DAYS) if referrer else settings.TRIAL_DAYS
    trial_plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == "growth"))
    if trial_plan:
        db.add(GymSubscription(
            gym_id=gym.id, plan_id=trial_plan.id, status=SubscriptionStatus.TRIALING,
            current_period_end=datetime.now(timezone.utc) + timedelta(days=trial_days),
        ))
        log_event(db, gym.id, "trial_started", to_plan=trial_plan.code, status="trialing",
                  notes=f"{trial_days}-day trial" + (f" (referred by {referrer.name})" if referrer else ""))

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

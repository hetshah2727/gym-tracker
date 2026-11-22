import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import entitlements
from app.core.permissions import platform_admin, tenant_user
from app.core.tenant_context import get_current_gym_id
from app.database.models import GymSubscription, SubscriptionEvent, SubscriptionPlan
from app.database.models.enums import Role
from app.database.repositories.base import Repository, TenantRepository
from app.database.session import get_db
from app.modules.common import get_or_404
from app.modules.subscriptions.schemas import (
    ChangePlanRequest, GymSubscriptionOut, SubscriptionPlanIn, SubscriptionPlanOut, SubscriptionPlanUpdate,
)
from app.modules.subscriptions.service import ensure_default_plans, log_event

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("/plans", response_model=list[SubscriptionPlanOut])
def list_plans(db: Session = Depends(get_db)):
    """Public pricing (used by the marketing / signup page)."""
    ensure_default_plans(db)
    db.commit()
    return db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.is_active.is_(True))
                      .order_by(SubscriptionPlan.price_monthly)).all()


@router.get("/current", response_model=GymSubscriptionOut | None)
def current_subscription(db: Session = Depends(get_db), _=Depends(tenant_user())):
    sub = TenantRepository(GymSubscription, db).list(limit=1)
    if not sub:
        return None
    out = GymSubscriptionOut.model_validate(sub[0])
    out.plan = SubscriptionPlanOut.model_validate(db.get(SubscriptionPlan, sub[0].plan_id))
    return out


@router.get("/entitlements")
def get_entitlements(db: Session = Depends(get_db), _=Depends(tenant_user())):
    """Single source of truth for plan access (the frontend builds its navigation from this)."""
    ent = entitlements.resolve(db)
    return {"plan_code": ent.plan_code, "plan_name": ent.plan_name, "status": ent.status,
            "trial_ends_at": ent.trial_ends_at, "features": ent.features, "max_members": ent.max_members,
            "limits": ent.limits, "usage": {m: entitlements.usage(db, m) for m in ent.limits},
            "catalog": {k: {"label": label, "tier": tier} for k, (label, tier) in entitlements.FEATURES.items()},
            "billing": {"gateway_subscriptions": billing_enabled(),
                        "note": "Pay monthly by UPI, card or netbanking through Razorpay." if billing_enabled() else
                                "Plan changes apply immediately; invoices are handled outside GymFlow."}}


def billing_plan_id(code: str) -> str | None:
    from app.core.config import settings

    return {"starter": settings.RAZORPAY_PLAN_STARTER, "growth": settings.RAZORPAY_PLAN_GROWTH,
            "pro": settings.RAZORPAY_PLAN_PRO}.get(code)


def billing_enabled() -> bool:
    from app.integrations.payments import razorpay

    return razorpay.is_configured() and any(billing_plan_id(c) for c in ("starter", "growth", "pro"))


@router.post("/checkout")
def checkout(data: ChangePlanRequest, db: Session = Depends(get_db), user=Depends(tenant_user(Role.GYM_OWNER))):
    """Start a Razorpay subscription for a plan. The plan switches on when Razorpay confirms the first payment."""
    from app.core.config import settings
    from app.integrations.payments import razorpay

    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == data.plan_code,
                                                    SubscriptionPlan.is_active.is_(True)))
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    rp_plan = billing_plan_id(plan.code)
    if not (razorpay.is_configured() and rp_plan):
        return {"configured": False}
    try:
        sub = razorpay.create_subscription(rp_plan, notes={"gym_id": str(get_current_gym_id()), "plan_code": plan.code,
                                                           "user_id": str(user.id)})
    except razorpay.PaymentGatewayError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Payment gateway error: {exc}")
    log_event(db, get_current_gym_id(), "checkout_started", to_plan=plan.code, actor_user_id=user.id,
              notes=sub.get("id"))
    db.commit()
    return {"configured": True, "subscription_id": sub.get("id"), "short_url": sub.get("short_url"),
            "key_id": settings.RAZORPAY_KEY_ID, "plan_name": plan.name, "amount": float(plan.price_monthly)}


@router.get("/referral")
def referral(db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    """The owner's invite link and how many gyms joined through it."""
    from app.core.config import settings
    from app.database.models import Gym
    from app.modules.authentication.service import REFERRAL_REWARD_DAYS, REFERRAL_TRIAL_DAYS

    gym = db.get(Gym, get_current_gym_id())
    gid = str(gym.id)
    referred = [g for g in db.scalars(select(Gym)).all() if (g.settings or {}).get("referred_by") == gid]
    return {"code": gym.slug, "link": f"{settings.FRONTEND_URL.rstrip('/')}/register?ref={gym.slug}",
            "joined": len(referred), "paying": sum(1 for g in referred if (g.settings or {}).get("referral_rewarded")),
            "trial_days": REFERRAL_TRIAL_DAYS, "reward_days": REFERRAL_REWARD_DAYS}


@router.get("/history")
def history(db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    rows = TenantRepository(SubscriptionEvent, db).list(limit=100, order_by=SubscriptionEvent.created_at.desc())
    return [{"event": r.event, "from_plan": r.from_plan, "to_plan": r.to_plan, "status": r.status,
             "notes": r.notes, "at": r.created_at.isoformat()} for r in rows]


@router.post("/change-plan", response_model=GymSubscriptionOut)
def change_plan(data: ChangePlanRequest, db: Session = Depends(get_db), user=Depends(tenant_user(Role.GYM_OWNER))):
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == data.plan_code,
                                                    SubscriptionPlan.is_active.is_(True)))
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    repo = TenantRepository(GymSubscription, db)
    subs = repo.list(limit=1)
    if not subs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No subscription found for this gym")
    # Not implemented: Razorpay subscription creation and proration. The switch is recorded in the history.
    old = db.get(SubscriptionPlan, subs[0].plan_id)
    log_event(db, get_current_gym_id(), "plan_changed", from_plan=old.code if old else None, to_plan=plan.code,
              status=subs[0].status.value, actor_user_id=user.id,
              notes="upgrade" if old and plan.price_monthly > old.price_monthly else "downgrade")
    sub = repo.update(subs[0], {"plan_id": plan.id})
    out = GymSubscriptionOut.model_validate(sub)
    out.plan = SubscriptionPlanOut.model_validate(plan)
    return out


# ---- Platform admin: manage SaaS plans ----

@router.post("/plans", response_model=SubscriptionPlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(data: SubscriptionPlanIn, db: Session = Depends(get_db), _=Depends(platform_admin)):
    return Repository(SubscriptionPlan, db).create(**data.model_dump())


@router.patch("/plans/{plan_id}", response_model=SubscriptionPlanOut)
def update_plan(plan_id: uuid.UUID, data: SubscriptionPlanUpdate, db: Session = Depends(get_db),
                _=Depends(platform_admin)):
    repo = Repository(SubscriptionPlan, db)
    return repo.update(get_or_404(repo, plan_id, "Plan"), data.model_dump(exclude_unset=True))

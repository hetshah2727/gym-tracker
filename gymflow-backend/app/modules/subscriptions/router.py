import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import platform_admin, tenant_user
from app.database.models import GymSubscription, SubscriptionPlan
from app.database.models.enums import Role
from app.database.repositories.base import Repository, TenantRepository
from app.database.session import get_db
from app.modules.common import get_or_404
from app.modules.subscriptions.schemas import (
    ChangePlanRequest, GymSubscriptionOut, SubscriptionPlanIn, SubscriptionPlanOut, SubscriptionPlanUpdate,
)
from app.modules.subscriptions.service import ensure_default_plans

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


@router.post("/change-plan", response_model=GymSubscriptionOut)
def change_plan(data: ChangePlanRequest, db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == data.plan_code,
                                                    SubscriptionPlan.is_active.is_(True)))
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    repo = TenantRepository(GymSubscription, db)
    subs = repo.list(limit=1)
    if not subs:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No subscription found for this gym")
    # TODO: create/update the Razorpay subscription and prorate before switching.
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

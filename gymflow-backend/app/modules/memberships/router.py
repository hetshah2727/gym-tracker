import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF, GYM_STAFF_AND_TRAINERS, tenant_user
from app.database.models import Member, Membership, MembershipPlan
from app.database.models.enums import MembershipStatus, Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import get_or_404
from app.modules.memberships import service
from app.modules.memberships.schemas import (
    AssignMembershipRequest, MembershipOut, PlanIn, PlanOut, PlanUpdate, RenewRequest,
)

plans_router = APIRouter(prefix="/membership-plans", tags=["Membership plans"])
router = APIRouter(prefix="/memberships", tags=["Memberships"])


# ---- Plans ----

@plans_router.get("", response_model=list[PlanOut])
def list_plans(include_inactive: bool = False, db: Session = Depends(get_db),
               _=Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    filters = [] if include_inactive else [MembershipPlan.is_active.is_(True)]
    return TenantRepository(MembershipPlan, db).list(*filters, limit=200, order_by=MembershipPlan.duration_days)


@plans_router.post("", response_model=PlanOut, status_code=status.HTTP_201_CREATED)
def create_plan(data: PlanIn, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    return TenantRepository(MembershipPlan, db).create(**data.model_dump())


@plans_router.patch("/{plan_id}", response_model=PlanOut)
def update_plan(plan_id: uuid.UUID, data: PlanUpdate, db: Session = Depends(get_db),
                _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(MembershipPlan, db)
    return repo.update(get_or_404(repo, plan_id, "Plan"), data.model_dump(exclude_unset=True))


@plans_router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_plan(plan_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    """Plans are archived, not deleted, so past memberships keep their reference."""
    repo = TenantRepository(MembershipPlan, db)
    repo.update(get_or_404(repo, plan_id, "Plan"), {"is_active": False})


# ---- Memberships ----

@router.get("", response_model=list[MembershipOut])
def list_memberships(
    member_id: uuid.UUID | None = None,
    status_: MembershipStatus | None = Query(None, alias="status"),
    expiring_within_days: int | None = Query(None, ge=0, le=365),
    offset: int = 0,
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    _=Depends(tenant_user(*GYM_STAFF)),
):
    filters = []
    if member_id:
        filters.append(Membership.member_id == member_id)
    if status_:
        filters.append(Membership.status == status_)
    if expiring_within_days is not None:
        filters += [Membership.status == MembershipStatus.ACTIVE,
                    Membership.end_date <= date.today() + timedelta(days=expiring_within_days)]
    rows = TenantRepository(Membership, db).list(*filters, offset=offset, limit=limit,
                                                 order_by=Membership.end_date)
    return [service.with_days_left(m) for m in rows]


@router.post("", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
def assign_membership(data: AssignMembershipRequest, db: Session = Depends(get_db),
                      _=Depends(tenant_user(*GYM_STAFF))):
    member = get_or_404(TenantRepository(Member, db), data.member_id, "Member")
    plan = get_or_404(TenantRepository(MembershipPlan, db), data.plan_id, "Plan")
    membership = service.assign_membership(
        db, member, plan, start_date=data.start_date, amount=data.amount, paid=data.paid,
        payment_method=data.payment_method, auto_renew=data.auto_renew,
    )
    return service.with_days_left(membership)


@router.post("/{membership_id}/renew", response_model=MembershipOut, status_code=status.HTTP_201_CREATED)
def renew_membership(membership_id: uuid.UUID, data: RenewRequest, db: Session = Depends(get_db),
                     _=Depends(tenant_user(*GYM_STAFF))):
    current = get_or_404(TenantRepository(Membership, db), membership_id, "Membership")
    plan_id = data.plan_id or current.plan_id
    if plan_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "plan_id is required")
    plan = get_or_404(TenantRepository(MembershipPlan, db), plan_id, "Plan")
    member = get_or_404(TenantRepository(Member, db), current.member_id, "Member")
    membership = service.assign_membership(
        db, member, plan, start_date=service.renewal_start(current), paid=data.paid,
        payment_method=data.payment_method, auto_renew=current.auto_renew,
    )
    return service.with_days_left(membership)


@router.post("/{membership_id}/cancel", response_model=MembershipOut)
def cancel_membership(membership_id: uuid.UUID, db: Session = Depends(get_db),
                      _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(Membership, db)
    membership = repo.update(get_or_404(repo, membership_id, "Membership"),
                             {"status": MembershipStatus.CANCELLED, "auto_renew": False})
    return service.with_days_left(membership)

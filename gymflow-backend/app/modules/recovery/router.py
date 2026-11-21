"""Membership renewal & revenue recovery API."""
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.entitlements import gym_feature
from app.core.permissions import GYM_STAFF
from app.core.tenant_context import get_current_gym_id
from app.database.models import (
    FollowUpTask, Gym, Lead, Member, Membership, MembershipPlan, Payment, RecoveryOpportunity, User,
)
from app.database.models.enums import (
    OPEN_OPPORTUNITY_STATUSES, OpportunityStatus, OpportunityType, PaymentMethod, PaymentStatus, Priority, Role,
    TaskStatus,
)
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, Page, get_or_404
from app.modules.growth import metrics
from app.modules.recovery import service

router = APIRouter(prefix="/recovery", tags=["Revenue recovery"])
staff = gym_feature("recovery_center", *GYM_STAFF)

TABS = {
    "renewals": [OpportunityType.UPCOMING_RENEWAL],
    "expired": [OpportunityType.EXPIRED_MEMBERSHIP],
    "outstanding": [OpportunityType.OUTSTANDING_PAYMENT],
    "failed": [OpportunityType.FAILED_PAYMENT],
    "no_shows": [OpportunityType.TRIAL_NO_SHOW],
    "leads": [OpportunityType.UNCONTACTED_LEAD, OpportunityType.OVERDUE_FOLLOW_UP],
}


class OppOut(ORMModel):
    id: uuid.UUID
    type: OpportunityType
    status: OpportunityStatus
    priority: Priority
    title: str
    reason: str
    member_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    membership_id: uuid.UUID | None
    payment_id: uuid.UUID | None
    trial_id: uuid.UUID | None
    potential_revenue: float
    assigned_to_id: uuid.UUID | None
    next_action: str | None
    due_date: date | None
    milestones: list
    last_contacted_at: datetime | None
    contact_count: int
    outcome: str | None
    recovered_revenue: float
    recovered_payment_id: uuid.UUID | None
    closed_at: datetime | None
    created_at: datetime


class ContactIn(BaseModel):
    note: str | None = Field(None, max_length=255)


class CloseIn(BaseModel):
    status: OpportunityStatus
    outcome: str = Field(min_length=2, max_length=255)


class PaymentIn(BaseModel):
    payment_id: uuid.UUID


class MarkPaidIn(BaseModel):
    method: PaymentMethod = PaymentMethod.CASH
    reference: str | None = Field(None, max_length=100)


class AssignIn(BaseModel):
    assigned_to_id: uuid.UUID | None


@router.get("/summary")
def summary(db: Session = Depends(get_db), _=Depends(staff)):
    return {**metrics.recovery_overview(db), "revenue": metrics.revenue(db, *metrics.month_range())}


@router.post("/sync")
def sync(db: Session = Depends(get_db), _=Depends(staff)):
    return service.sync_all(db)


@router.get("/opportunities", response_model=Page[OppOut])
def list_opps(tab: str | None = Query(None, pattern="^(renewals|expired|outstanding|failed|no_shows|leads|history)$"),
              type: OpportunityType | None = None, status_: OpportunityStatus | None = Query(None, alias="status"),
              assigned_to_id: uuid.UUID | None = None, offset: int = 0, limit: int = Query(50, le=200),
              db: Session = Depends(get_db), _=Depends(staff)):
    f = []
    if tab == "history":
        f.append(RecoveryOpportunity.status.not_in(OPEN_OPPORTUNITY_STATUSES))
    elif tab:
        f.append(RecoveryOpportunity.type.in_(TABS[tab]))
    if type:
        f.append(RecoveryOpportunity.type == type)
    if status_:
        f.append(RecoveryOpportunity.status == status_)
    elif tab != "history":
        f.append(RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES))
    if assigned_to_id:
        f.append(RecoveryOpportunity.assigned_to_id == assigned_to_id)
    order = RecoveryOpportunity.closed_at.desc() if tab == "history" else RecoveryOpportunity.due_date
    repo = TenantRepository(RecoveryOpportunity, db)
    return Page(items=repo.list(*f, offset=offset, limit=limit, order_by=order), total=repo.count(*f),
                offset=offset, limit=limit)


@router.get("/opportunities/{opp_id}")
def detail(opp_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    opp = get_or_404(TenantRepository(RecoveryOpportunity, db), opp_id, "Opportunity")
    gym = db.get(Gym, get_current_gym_id())
    member = db.get(Member, opp.member_id) if opp.member_id else None
    membership = db.get(Membership, opp.membership_id) if opp.membership_id else None
    plan = db.get(MembershipPlan, membership.plan_id) if membership and membership.plan_id else None
    payment = db.get(Payment, opp.payment_id) if opp.payment_id else None
    lead = db.get(Lead, opp.lead_id) if opp.lead_id else None
    tasks = TenantRepository(FollowUpTask, db).list(FollowUpTask.opportunity_id == opp.id, limit=50)
    draft = None
    if member and membership:
        draft = service.renewal_message(gym, member, membership, float(opp.potential_revenue))
    elif member and payment:
        draft = service.payment_message(gym, member, payment)
    member_payments = TenantRepository(Payment, db).list(Payment.member_id == member.id,
                                                        Payment.status == PaymentStatus.PAID, limit=10) if member else []
    return {
        "opportunity": OppOut.model_validate(opp).model_dump(mode="json"),
        "member": {"id": str(member.id), "name": member.full_name, "phone": member.phone} if member else None,
        "membership": {"id": str(membership.id), "plan": plan.name if plan else None,
                       "end_date": membership.end_date.isoformat(), "amount": float(membership.amount),
                       "status": membership.status.value} if membership else None,
        "payment": {"id": str(payment.id), "amount": float(payment.amount), "status": payment.status.value,
                    "due_date": payment.due_date.isoformat() if payment.due_date else None,
                    "failure_reason": payment.failure_reason} if payment else None,
        "lead": {"id": str(lead.id), "name": lead.name, "phone": lead.phone, "status": lead.status.value} if lead else None,
        "tasks": [{"id": str(t.id), "title": t.title, "status": t.status.value, "due_at": t.due_at.isoformat()
                   if t.due_at else None, "draft_message": t.draft_message} for t in tasks],
        "draft_message": draft,
        "creditable_payments": [{"id": str(p.id), "amount": float(p.amount), "paid_at": p.paid_at.isoformat()
                                 if p.paid_at else None} for p in member_payments
                                if not TenantRepository(RecoveryOpportunity, db).first(
                                    RecoveryOpportunity.recovered_payment_id == p.id)],
    }


@router.post("/opportunities/{opp_id}/contact", response_model=OppOut)
def contact(opp_id: uuid.UUID, data: ContactIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    return service.record_contact(db, get_or_404(TenantRepository(RecoveryOpportunity, db), opp_id, "Opportunity"),
                                  user, data.note)


@router.post("/opportunities/{opp_id}/close", response_model=OppOut)
def close(opp_id: uuid.UUID, data: CloseIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    if data.status not in (OpportunityStatus.LOST, OpportunityStatus.DISMISSED):
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            "To mark revenue as recovered, link the paid payment (record-payment).")
    opp = get_or_404(TenantRepository(RecoveryOpportunity, db), opp_id, "Opportunity")
    return service.close_without_revenue(db, opp, user, lost=data.status == OpportunityStatus.LOST,
                                         outcome=data.outcome)


@router.post("/opportunities/{opp_id}/record-payment", response_model=OppOut)
def record_payment(opp_id: uuid.UUID, data: PaymentIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    opp = get_or_404(TenantRepository(RecoveryOpportunity, db), opp_id, "Opportunity")
    payment = get_or_404(TenantRepository(Payment, db), data.payment_id, "Payment")
    service.close_with_payment(db, opp, payment, outcome="Recovered (payment linked by staff)", user=user)
    db.commit()
    return opp


@router.get("/due")
def due(db: Session = Depends(get_db), _=Depends(staff)):
    """Plain "who owes money" list: overdue, ending this week, ending later."""
    return service.due_list(db)


@router.post("/opportunities/{opp_id}/mark-paid", response_model=OppOut)
def mark_paid_now(opp_id: uuid.UUID, data: MarkPaidIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    opp = get_or_404(TenantRepository(RecoveryOpportunity, db), opp_id, "Opportunity")
    return service.mark_paid_now(db, opp, user, data.method, data.reference)


@router.post("/opportunities/{opp_id}/payment-link")
def payment_link(opp_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    return service.payment_link(db, get_or_404(TenantRepository(RecoveryOpportunity, db), opp_id, "Opportunity"))


@router.post("/opportunities/{opp_id}/assign", response_model=OppOut)
def assign(opp_id: uuid.UUID, data: AssignIn, db: Session = Depends(get_db), _=Depends(staff)):
    opp = get_or_404(TenantRepository(RecoveryOpportunity, db), opp_id, "Opportunity")
    if data.assigned_to_id and not TenantRepository(User, db).first(User.id == data.assigned_to_id,
                                                                    User.role != Role.MEMBER):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assignee is not staff in this gym")
    opp.assigned_to_id = data.assigned_to_id
    for t in TenantRepository(FollowUpTask, db).list(FollowUpTask.opportunity_id == opp.id,
                                                     FollowUpTask.status == TaskStatus.OPEN, limit=20):
        t.assigned_to_id = data.assigned_to_id
    db.commit()
    return opp

"""Lead CRM & sales pipeline API."""
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.entitlements import gym_feature
from app.core.permissions import GYM_STAFF
from app.database.models import (
    Campaign, FollowUpTask, Lead, LeadInteraction, MembershipPlan, TrialBooking, User,
)
from app.database.models.enums import (
    LeadSource, LeadStatus, PaymentMethod, Priority, Role, TaskKind, TaskStatus,
)
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, Page, get_or_404
from app.modules.crm import service
from app.modules.growth import metrics
from app.services import events

router = APIRouter(prefix="/crm", tags=["CRM & sales pipeline"])
staff = gym_feature("lead_crm", *GYM_STAFF)


class LeadOut(ORMModel):
    id: uuid.UUID
    name: str
    phone: str | None
    email: str | None
    message: str | None
    source: str
    status: LeadStatus
    priority: Priority
    score: int
    score_reasons: list
    attribution: dict
    campaign_id: uuid.UUID | None
    landing_page_id: uuid.UUID | None
    fitness_interest: str | None
    interested_plan_id: uuid.UUID | None
    preferred_location: str | None
    preferred_joining_date: date | None
    wants_trial: bool
    assigned_to_id: uuid.UUID | None
    first_response_at: datetime | None
    last_contacted_at: datetime | None
    next_follow_up_at: datetime | None
    lost_reason: str | None
    notes: str | None
    existing_member_id: uuid.UUID | None
    converted_member_id: uuid.UUID | None
    converted_membership_id: uuid.UUID | None
    converted_at: datetime | None
    whatsapp_opt_in: bool
    opted_out: bool
    created_at: datetime


class LeadCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(None, max_length=32)
    email: EmailStr | None = None
    message: str | None = Field(None, max_length=2000)
    source: LeadSource = LeadSource.WALK_IN
    campaign_code: str | None = None
    fitness_interest: str | None = Field(None, max_length=120)
    interested_plan_id: uuid.UUID | None = None
    preferred_location: str | None = None
    preferred_joining_date: date | None = None
    wants_trial: bool = False
    whatsapp_opt_in: bool = False
    assigned_to_id: uuid.UUID | None = None
    notes: str | None = None


class LeadUpdate(BaseModel):
    name: str | None = Field(None, max_length=200)
    phone: str | None = None
    email: EmailStr | None = None
    fitness_interest: str | None = None
    interested_plan_id: uuid.UUID | None = None
    preferred_location: str | None = None
    preferred_joining_date: date | None = None
    wants_trial: bool | None = None
    assigned_to_id: uuid.UUID | None = None
    priority: Priority | None = None
    next_follow_up_at: datetime | None = None
    notes: str | None = None
    whatsapp_opt_in: bool | None = None
    source: LeadSource | None = None


class StatusChange(BaseModel):
    status: LeadStatus
    lost_reason: str | None = Field(None, max_length=255)
    note: str | None = None


class InteractionIn(BaseModel):
    kind: str = Field(pattern="^(note|call|whatsapp|email|sms|visit)$")
    body: str | None = Field(None, max_length=4000)
    direction: str | None = Field(None, pattern="^(in|out)$")


class ConvertIn(BaseModel):
    plan_id: uuid.UUID
    paid: bool = False
    payment_method: PaymentMethod | None = None
    amount: float | None = Field(None, ge=0)
    start_date: date | None = None


class BulkIn(BaseModel):
    lead_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    action: str = Field(pattern="^(assign|status)$")
    assigned_to_id: uuid.UUID | None = None
    status: LeadStatus | None = None
    lost_reason: str | None = None
    confirm: bool = False


class TaskOut(ORMModel):
    id: uuid.UUID
    title: str
    description: str | None
    kind: TaskKind
    status: TaskStatus
    priority: Priority
    due_at: datetime | None
    assigned_to_id: uuid.UUID | None
    lead_id: uuid.UUID | None
    member_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    trial_id: uuid.UUID | None
    source: str
    draft_message: str | None
    completed_at: datetime | None
    outcome: str | None
    created_at: datetime


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    kind: TaskKind = TaskKind.FOLLOW_UP
    priority: Priority = Priority.MEDIUM
    due_at: datetime | None = None
    lead_id: uuid.UUID | None = None
    member_id: uuid.UUID | None = None
    assigned_to_id: uuid.UUID | None = None


class TaskComplete(BaseModel):
    outcome: str | None = Field(None, max_length=255)
    cancelled: bool = False


class CampaignOut(ORMModel):
    id: uuid.UUID
    name: str
    code: str
    source: str
    channel: str | None
    status: str
    start_date: date | None
    end_date: date | None
    budget: float | None
    notes: str | None
    created_at: datetime


class CampaignIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9_\-]+$")
    source: LeadSource = LeadSource.OTHER
    channel: str | None = None
    status: str = Field("draft", pattern="^(draft|active|ended)$")
    start_date: date | None = None
    end_date: date | None = None
    budget: float | None = Field(None, ge=0)
    notes: str | None = None


def _check_assignee(db: Session, user_id: uuid.UUID | None) -> None:
    if user_id and TenantRepository(User, db).first(User.id == user_id, User.role != Role.MEMBER) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Assignee is not a staff member of this gym")


# ---------------------------------------------------------------- leads

@router.get("/leads", response_model=Page[LeadOut])
def list_leads(
    status_: LeadStatus | None = Query(None, alias="status"), source: str | None = None,
    assigned_to_id: uuid.UUID | None = None, priority: Priority | None = None, q: str | None = None,
    uncontacted: bool = False, overdue: bool = False,
    sort: str = Query("newest", pattern="^(newest|oldest|score|follow_up)$"),
    offset: int = 0, limit: int = Query(50, le=200), db: Session = Depends(get_db), _=Depends(staff),
):
    f = []
    if status_:
        f.append(Lead.status == status_)
    if source:
        f.append(Lead.source == source)
    if assigned_to_id:
        f.append(Lead.assigned_to_id == assigned_to_id)
    if priority:
        f.append(Lead.priority == priority)
    if uncontacted:
        f += [Lead.status == LeadStatus.NEW, Lead.first_response_at.is_(None)]
    if overdue:
        f += [Lead.next_follow_up_at < datetime.now(timezone.utc),
              Lead.status.not_in([LeadStatus.CONVERTED, LeadStatus.LOST])]
    if q:
        like = f"%{q}%"
        f.append(or_(Lead.name.ilike(like), Lead.phone.ilike(like), Lead.email.ilike(like)))
    order = {"newest": Lead.created_at.desc(), "oldest": Lead.created_at, "score": Lead.score.desc(),
             "follow_up": Lead.next_follow_up_at}[sort]
    repo = TenantRepository(Lead, db)
    return Page(items=repo.list(*f, offset=offset, limit=limit, order_by=order), total=repo.count(*f), offset=offset,
                limit=limit)


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(data: LeadCreate, db: Session = Depends(get_db), user: User = Depends(staff)):
    _check_assignee(db, data.assigned_to_id)
    attribution = service.attribute(db, declared_source=data.source.value,
                                    utm={"utm_campaign": data.campaign_code} if data.campaign_code else None,
                                    referrer=None)
    if attribution.method == "declared":
        attribution.method = "staff"
    lead, _ = service.capture_lead(db, service.LeadInput(
        **data.model_dump(exclude={"source", "campaign_code"})), attribution, actor="user", user=user,
        channel_note=f"Added by {user.full_name} ({data.source.value.replace('_', ' ')})")
    db.refresh(lead)
    return lead


@router.get("/leads/{lead_id}")
def lead_detail(lead_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    lead = get_or_404(TenantRepository(Lead, db), lead_id, "Lead")
    interactions = TenantRepository(LeadInteraction, db).list(LeadInteraction.lead_id == lead.id, limit=300,
                                                              order_by=LeadInteraction.created_at.desc())
    tasks = TenantRepository(FollowUpTask, db).list(FollowUpTask.lead_id == lead.id, limit=100)
    trials = TenantRepository(TrialBooking, db).list(TrialBooking.lead_id == lead.id, limit=20,
                                                     order_by=TrialBooking.starts_at.desc())
    plan = db.get(MembershipPlan, lead.interested_plan_id) if lead.interested_plan_id else None
    campaign = db.get(Campaign, lead.campaign_id) if lead.campaign_id else None
    return {
        "lead": LeadOut.model_validate(lead).model_dump(mode="json"),
        "interested_plan": {"id": str(plan.id), "name": plan.name, "price": float(plan.price)} if plan else None,
        "campaign": {"id": str(campaign.id), "name": campaign.name} if campaign else None,
        "interactions": [{"id": str(i.id), "kind": i.kind, "direction": i.direction, "body": i.body, "data": i.data,
                          "user_id": str(i.user_id) if i.user_id else None, "created_at": i.created_at.isoformat()}
                         for i in interactions],
        "tasks": [TaskOut.model_validate(t).model_dump(mode="json") for t in tasks],
        "trials": [{"id": str(t.id), "starts_at": t.starts_at.isoformat(), "status": t.status.value,
                    "trainer_id": str(t.trainer_id) if t.trainer_id else None} for t in trials],
    }


@router.patch("/leads/{lead_id}", response_model=LeadOut)
def update_lead(lead_id: uuid.UUID, data: LeadUpdate, db: Session = Depends(get_db), user: User = Depends(staff)):
    lead = get_or_404(TenantRepository(Lead, db), lead_id, "Lead")
    updates = data.model_dump(exclude_unset=True)
    if "assigned_to_id" in updates:
        _check_assignee(db, updates["assigned_to_id"])
    if "interested_plan_id" in updates and updates["interested_plan_id"]:
        get_or_404(TenantRepository(MembershipPlan, db), updates["interested_plan_id"], "Plan")
    if "source" in updates and updates["source"]:
        updates["source"] = updates["source"].value
        lead.attribution = {**(lead.attribution or {}), "method": "staff", "corrected_by": str(user.id)}
    for k, v in updates.items():
        setattr(lead, k, v)
    if "phone" in updates:
        lead.phone_key = service.phone_key(lead.phone)
    service.rescore(db, lead)
    db.commit()
    db.refresh(lead)
    return lead


@router.post("/leads/{lead_id}/status", response_model=LeadOut)
def change_status(lead_id: uuid.UUID, data: StatusChange, db: Session = Depends(get_db), user: User = Depends(staff)):
    lead = get_or_404(TenantRepository(Lead, db), lead_id, "Lead")
    service.change_status(db, lead, data.status, user, lost_reason=data.lost_reason, note=data.note)
    db.refresh(lead)
    return lead


@router.post("/leads/{lead_id}/interactions", status_code=status.HTTP_201_CREATED)
def add_interaction(lead_id: uuid.UUID, data: InteractionIn, db: Session = Depends(get_db),
                    user: User = Depends(staff)):
    lead = get_or_404(TenantRepository(Lead, db), lead_id, "Lead")
    direction = data.direction or ("out" if data.kind != "note" else None)
    item = service.record_interaction(db, lead, data.kind, data.body, direction=direction, user=user)
    service.rescore(db, lead)
    events.emit(db, "lead.interaction", entity_type="lead", entity_id=lead.id, actor_user_id=user.id,
                payload={"kind": data.kind, "direction": direction})
    return {"id": str(item.id), "status": lead.status.value}


@router.post("/leads/{lead_id}/convert", response_model=LeadOut)
def convert(lead_id: uuid.UUID, data: ConvertIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    lead = get_or_404(TenantRepository(Lead, db), lead_id, "Lead")
    service.convert_lead(db, lead, plan_id=data.plan_id, user=user, paid=data.paid,
                         payment_method=data.payment_method, amount=data.amount, start_date=data.start_date)
    db.refresh(lead)
    return lead


@router.post("/leads/bulk")
def bulk(data: BulkIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    if not data.confirm:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Confirm the bulk {data.action} of {len(data.lead_ids)} leads")
    leads = TenantRepository(Lead, db).list(Lead.id.in_(data.lead_ids), limit=len(data.lead_ids))
    done = 0
    for lead in leads:
        if data.action == "assign":
            _check_assignee(db, data.assigned_to_id)
            lead.assigned_to_id = data.assigned_to_id
            done += 1
        elif data.status:
            if data.status == LeadStatus.CONVERTED:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Convert leads one at a time")
            service.change_status(db, lead, data.status, user, lost_reason=data.lost_reason)
            done += 1
    db.commit()
    return {"updated": done}


@router.get("/pipeline")
def pipeline(per_stage: int = Query(50, le=200), source: str | None = None, assigned_to_id: uuid.UUID | None = None,
             q: str | None = None, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(Lead, db)
    base = []
    if source:
        base.append(Lead.source == source)
    if assigned_to_id:
        base.append(Lead.assigned_to_id == assigned_to_id)
    if q:
        base.append(or_(Lead.name.ilike(f"%{q}%"), Lead.phone.ilike(f"%{q}%")))
    recent = datetime.now(timezone.utc) - timedelta(days=60)
    columns = []
    for stage in service.PIPELINE:
        f = [*base, Lead.status == stage]
        if stage in (LeadStatus.CONVERTED, LeadStatus.LOST):
            f.append(Lead.updated_at >= recent)
        columns.append({"status": stage.value, "total": repo.count(*f),
                        "leads": [LeadOut.model_validate(l).model_dump(mode="json")
                                  for l in repo.list(*f, limit=per_stage, order_by=Lead.score.desc())]})
    return {"columns": columns}


@router.post("/leads/{lead_id}/rescore", response_model=LeadOut)
def rescore(lead_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    lead = get_or_404(TenantRepository(Lead, db), lead_id, "Lead")
    service.rescore(db, lead)
    db.commit()
    return lead


# ---------------------------------------------------------------- tasks

@router.get("/tasks", response_model=Page[TaskOut])
def list_tasks(status_: TaskStatus | None = Query(TaskStatus.OPEN, alias="status"), kind: TaskKind | None = None,
               due: str | None = Query(None, pattern="^(overdue|today|upcoming)$"), mine: bool = False,
               lead_id: uuid.UUID | None = None, offset: int = 0, limit: int = Query(50, le=200),
               db: Session = Depends(get_db), user: User = Depends(gym_feature("lead_crm"))):
    f = []
    if status_:
        f.append(FollowUpTask.status == status_)
    if kind:
        f.append(FollowUpTask.kind == kind)
    if lead_id:
        f.append(FollowUpTask.lead_id == lead_id)
    if mine or user.role == Role.TRAINER:
        f.append(FollowUpTask.assigned_to_id == user.id)
    now = datetime.now(timezone.utc)
    end_today = datetime.combine(date.today() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    if due == "overdue":
        f.append(FollowUpTask.due_at < now)
    elif due == "today":
        f += [FollowUpTask.due_at >= now - timedelta(hours=24), FollowUpTask.due_at < end_today]
    elif due == "upcoming":
        f.append(FollowUpTask.due_at >= end_today)
    repo = TenantRepository(FollowUpTask, db)
    return Page(items=repo.list(*f, offset=offset, limit=limit, order_by=FollowUpTask.due_at), total=repo.count(*f),
                offset=offset, limit=limit)


@router.post("/tasks", response_model=TaskOut, status_code=status.HTTP_201_CREATED)
def create_task(data: TaskIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    if data.lead_id:
        get_or_404(TenantRepository(Lead, db), data.lead_id, "Lead")
    _check_assignee(db, data.assigned_to_id)
    task = service.create_task(db, **data.model_dump(), source="manual")
    if task.lead_id:
        lead = db.get(Lead, task.lead_id)
        if task.due_at and (lead.next_follow_up_at is None or service.aware(task.due_at) < service.aware(lead.next_follow_up_at)):
            lead.next_follow_up_at = task.due_at
    db.commit()
    return task


@router.post("/tasks/{task_id}/complete", response_model=TaskOut)
def complete(task_id: uuid.UUID, data: TaskComplete, db: Session = Depends(get_db),
             user: User = Depends(gym_feature("lead_crm"))):
    task = get_or_404(TenantRepository(FollowUpTask, db), task_id, "Task")
    if user.role == Role.TRAINER and task.assigned_to_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not your task")
    if task.status != TaskStatus.OPEN:
        raise HTTPException(status.HTTP_409_CONFLICT, "Task is already closed")
    service.complete_task(db, task, user, data.outcome, cancelled=data.cancelled)
    events.emit(db, "task.completed", entity_type="task", entity_id=task.id, actor_user_id=user.id,
                payload={"kind": task.kind.value, "cancelled": data.cancelled})
    return task


# ---------------------------------------------------------------- campaigns & sources

@router.get("/campaigns", response_model=list[CampaignOut])
def list_campaigns(db: Session = Depends(get_db), _=Depends(staff)):
    return TenantRepository(Campaign, db).list(limit=200)


@router.post("/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
def create_campaign(data: CampaignIn, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(Campaign, db)
    if repo.first(Campaign.code == data.code):
        raise HTTPException(status.HTTP_409_CONFLICT, "A campaign with this code exists")
    payload = data.model_dump()
    payload["source"] = data.source.value
    return repo.create(**payload)


@router.patch("/campaigns/{campaign_id}", response_model=CampaignOut)
def update_campaign(campaign_id: uuid.UUID, data: CampaignIn, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(Campaign, db)
    payload = data.model_dump(exclude={"code"})
    payload["source"] = data.source.value
    return repo.update(get_or_404(repo, campaign_id, "Campaign"), payload)


@router.get("/campaigns/{campaign_id}/stats")
def campaign_stats(campaign_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    from app.database.models import Payment
    from app.database.models.enums import PaymentStatus

    campaign = get_or_404(TenantRepository(Campaign, db), campaign_id, "Campaign")
    leads = TenantRepository(Lead, db).list(Lead.campaign_id == campaign.id, limit=10_000)
    joined = [l for l in leads if l.status == LeadStatus.CONVERTED and l.converted_member_id]
    collected = sum(float(p.amount) for p in TenantRepository(Payment, db).list(
        Payment.member_id.in_([l.converted_member_id for l in joined]), Payment.status == PaymentStatus.PAID,
        limit=100_000)) if joined else 0
    return {"campaign": campaign.name, "code": campaign.code, "leads": len(leads), "joined": len(joined),
            "conversion_rate": round(len(joined) / len(leads), 3) if leads else 0,
            "revenue_collected_from_joined": round(collected, 2),
            "tracking_link_hint": f"?utm_source={campaign.source}&utm_medium={campaign.channel or 'other'}"
                                  f"&utm_campaign={campaign.code}"}


@router.get("/sources")
def sources(days: int = Query(90, ge=1, le=730), db: Session = Depends(get_db), _=Depends(staff)):
    today = date.today()
    stats = metrics.lead_analytics(db, today - timedelta(days=days - 1), today)["by_source"]
    return [{"source": s.value, "label": s.value.replace("_", " ").title(), **stats.get(s.value, {
        "leads": 0, "trials": 0, "joined": 0, "revenue_collected": 0, "conversion_rate": 0})} for s in LeadSource]


@router.get("/analytics")
def analytics(days: int = Query(30, ge=1, le=730), db: Session = Depends(get_db), _=Depends(staff)):
    today = date.today()
    return metrics.lead_analytics(db, today - timedelta(days=days - 1), today)

"""Trial booking & conversion API."""
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.entitlements import gym_feature
from app.core.permissions import GYM_STAFF, GYM_STAFF_AND_TRAINERS
from app.core.tenant_context import get_current_gym_id
from app.database.models import Gym, Lead, Trainer, TrialBooking, User
from app.database.models.enums import Role, TrialStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, get_or_404
from app.modules.growth import metrics
from app.modules.trials import service

router = APIRouter(prefix="/trials", tags=["Trial booking"])
staff = gym_feature("trials", *GYM_STAFF)
team = gym_feature("trials", *GYM_STAFF_AND_TRAINERS)


class TrialOut(ORMModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    trainer_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    status: TrialStatus
    source: str
    notes: str | None
    reschedule_count: int
    attended_at: datetime | None
    cancel_reason: str | None
    converted_membership_id: uuid.UUID | None
    created_at: datetime


class BookIn(BaseModel):
    lead_id: uuid.UUID
    starts_at: datetime
    trainer_id: uuid.UUID | None = None
    notes: str | None = Field(None, max_length=1000)
    source: str = Field("staff", pattern="^(staff|crm)$")


class RescheduleIn(BaseModel):
    starts_at: datetime
    trainer_id: uuid.UUID | None = None


class CancelIn(BaseModel):
    reason: str | None = Field(None, max_length=255)


class ConfigIn(BaseModel):
    slot_minutes: int = Field(60, ge=15, le=240)
    capacity: int = Field(3, ge=1, le=50)
    min_notice_hours: float = Field(2, ge=0, le=72)
    max_days_ahead: int = Field(21, ge=1, le=90)
    attendance_grace_minutes: int = Field(60, ge=0, le=600)
    hours: dict[str, list[str]]


@router.get("/config")
def get_config(db: Session = Depends(get_db), _=Depends(team)):
    return service.config(db.get(Gym, get_current_gym_id()))


@router.put("/config")
def put_config(data: ConfigIn, db: Session = Depends(get_db), _=Depends(gym_feature("trials", Role.GYM_OWNER))):
    for day, hours in data.hours.items():
        if day not in {str(i) for i in range(7)} or len(hours) != 2 or hours[0] >= hours[1]:
            from fastapi import HTTPException
            raise HTTPException(422, f"Invalid hours for day {day}")
    gym = db.get(Gym, get_current_gym_id())
    gym.settings = {**(gym.settings or {}), "trials": data.model_dump()}
    db.commit()
    return service.config(gym)


@router.get("/slots")
def slots(start: date | None = None, days: int = Query(7, ge=1, le=31), trainer_id: uuid.UUID | None = None,
          db: Session = Depends(get_db), _=Depends(team)):
    return [{"starts_at": s["starts_at"].isoformat(), "ends_at": s["ends_at"].isoformat(), "remaining": s["remaining"]}
            for s in service.available_slots(db, start or date.today(), days, trainer_id)]


@router.get("")
def list_trials(start: date | None = None, end: date | None = None, status_: TrialStatus | None = Query(None, alias="status"),
                db: Session = Depends(get_db), user: User = Depends(team)):
    start = start or date.today() - timedelta(days=7)
    end = end or date.today() + timedelta(days=30)
    f = [TrialBooking.starts_at >= metrics.start_of(start), TrialBooking.starts_at < metrics.start_of(end + timedelta(days=1))]
    if status_:
        f.append(TrialBooking.status == status_)
    if user.role == Role.TRAINER:
        me = TenantRepository(Trainer, db).first(Trainer.user_id == user.id)
        f.append(TrialBooking.trainer_id == (me.id if me else None))
    rows = TenantRepository(TrialBooking, db).list(*f, limit=2000, order_by=TrialBooking.starts_at)
    leads = {l.id: l for l in TenantRepository(Lead, db).list(Lead.id.in_([r.lead_id for r in rows]), limit=5000)} if rows else {}
    trainers = {t.id: t.full_name for t in TenantRepository(Trainer, db).list(limit=500)}
    return [{**TrialOut.model_validate(r).model_dump(mode="json"),
             "lead_name": leads[r.lead_id].name if r.lead_id in leads else None,
             "lead_phone": leads[r.lead_id].phone if r.lead_id in leads else None,
             "lead_status": leads[r.lead_id].status.value if r.lead_id in leads else None,
             "trainer_name": trainers.get(r.trainer_id)} for r in rows]


@router.post("", response_model=TrialOut, status_code=status.HTTP_201_CREATED)
def book(data: BookIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    lead = get_or_404(TenantRepository(Lead, db), data.lead_id, "Lead")
    return service.book(db, lead, data.starts_at, trainer_id=data.trainer_id, source=data.source, user=user,
                        notes=data.notes)


@router.post("/{trial_id}/reschedule", response_model=TrialOut)
def reschedule(trial_id: uuid.UUID, data: RescheduleIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    trial = get_or_404(TenantRepository(TrialBooking, db), trial_id, "Trial")
    return service.reschedule(db, trial, data.starts_at, user, data.trainer_id)


@router.post("/{trial_id}/cancel", response_model=TrialOut)
def cancel(trial_id: uuid.UUID, data: CancelIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    return service.cancel(db, get_or_404(TenantRepository(TrialBooking, db), trial_id, "Trial"), user, data.reason)


@router.post("/{trial_id}/attended", response_model=TrialOut)
def attended(trial_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(team)):
    return service.mark_attended(db, get_or_404(TenantRepository(TrialBooking, db), trial_id, "Trial"), user)


@router.post("/{trial_id}/no-show", response_model=TrialOut)
def no_show(trial_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(team)):
    return service.confirm_no_show(db, get_or_404(TenantRepository(TrialBooking, db), trial_id, "Trial"), user)


@router.get("/analytics")
def analytics(days: int = Query(30, ge=1, le=366), db: Session = Depends(get_db), _=Depends(staff)):
    today = date.today()
    return metrics.trial_analytics(db, today - timedelta(days=days - 1), today + timedelta(days=30))


__all__ = ["router", "timezone"]

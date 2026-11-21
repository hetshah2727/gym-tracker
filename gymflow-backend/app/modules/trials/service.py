"""Trial booking & conversion engine (deterministic).

Slots are a grid in the gym's local time zone defined by ``gym.settings["trials"]``. A booking is
accepted only if it is on the grid, inside opening hours, far enough ahead, under slot capacity, does
not double-book the trainer, and the lead has no other active trial. On PostgreSQL the gym row is
locked (SELECT ... FOR UPDATE) for the check-and-insert so two simultaneous bookings cannot both win.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import Gym, Lead, Trainer, TrialBooking, User
from app.database.models.enums import (
    ACTIVE_TRIAL_STATUSES, LeadStatus, OpportunityType, Priority, TaskKind, TrialStatus,
)
from app.database.repositories.base import TenantRepository
from app.modules.crm import service as crm
from app.services import events, messaging

DEFAULT_CONFIG = {
    "slot_minutes": 60,
    "capacity": 3,               # trials per slot
    "min_notice_hours": 2,
    "max_days_ahead": 21,
    "attendance_grace_minutes": 60,
    # weekday (0=Mon) -> [open, close] local time; missing day = closed
    "hours": {"0": ["06:00", "21:00"], "1": ["06:00", "21:00"], "2": ["06:00", "21:00"],
              "3": ["06:00", "21:00"], "4": ["06:00", "21:00"], "5": ["06:00", "21:00"],
              "6": ["07:00", "12:00"]},
}


def config(gym: Gym) -> dict:
    return {**DEFAULT_CONFIG, **((gym.settings or {}).get("trials") or {})}


def _tz(gym: Gym) -> ZoneInfo:
    try:
        return ZoneInfo(gym.timezone or "Asia/Kolkata")
    except Exception:  # noqa: BLE001
        return ZoneInfo("Asia/Kolkata")


def _hm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _as_utc(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc) if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def day_slots(gym: Gym, day: date) -> list[tuple[datetime, datetime]]:
    cfg, tz = config(gym), _tz(gym)
    hours = cfg["hours"].get(str(day.weekday()))
    if not hours:
        return []
    step = timedelta(minutes=int(cfg["slot_minutes"]))
    start = datetime.combine(day, _hm(hours[0]), tzinfo=tz)
    close = datetime.combine(day, _hm(hours[1]), tzinfo=tz)
    slots = []
    while start + step <= close:
        slots.append((start.astimezone(timezone.utc), (start + step).astimezone(timezone.utc)))
        start += step
    return slots


def _active_at(db: Session, starts_at: datetime, exclude_id=None) -> list[TrialBooking]:
    filters = [TrialBooking.starts_at == starts_at, TrialBooking.status.in_(ACTIVE_TRIAL_STATUSES)]
    if exclude_id:
        filters.append(TrialBooking.id != exclude_id)
    return list(TenantRepository(TrialBooking, db).list(*filters, limit=100))


def available_slots(db: Session, start: date, days: int = 7, trainer_id=None,
                    now: datetime | None = None) -> list[dict]:
    gym = db.get(Gym, get_current_gym_id())
    cfg = config(gym)
    now = now or datetime.now(timezone.utc)
    earliest = now + timedelta(hours=float(cfg["min_notice_hours"]))
    last_day = (now + timedelta(days=int(cfg["max_days_ahead"]))).date()
    window_end = datetime.combine(start + timedelta(days=days + 1), time.min, tzinfo=timezone.utc)
    booked = TenantRepository(TrialBooking, db).list(
        TrialBooking.status.in_(ACTIVE_TRIAL_STATUSES),
        TrialBooking.starts_at >= datetime.combine(start - timedelta(days=1), time.min, tzinfo=timezone.utc),
        TrialBooking.starts_at < window_end, limit=5000)
    by_start: dict[datetime, list[TrialBooking]] = {}
    for b in booked:
        by_start.setdefault(_as_utc(b.starts_at), []).append(b)
    out = []
    for offset in range(days):
        day = start + timedelta(days=offset)
        if day > last_day:
            break
        for s, e in day_slots(gym, day):
            if s < earliest:
                continue
            taken = by_start.get(s, [])
            remaining = int(cfg["capacity"]) - len(taken)
            if trainer_id and any(b.trainer_id == trainer_id for b in taken):
                remaining = 0
            if remaining > 0:
                out.append({"starts_at": s, "ends_at": e, "remaining": remaining})
    return out


def _validate_slot(db: Session, gym: Gym, starts_at: datetime, trainer_id, lead_id, exclude_id=None,
                   now: datetime | None = None) -> datetime:
    cfg = config(gym)
    starts_at = _as_utc(starts_at)
    now = now or datetime.now(timezone.utc)
    if starts_at < now + timedelta(hours=float(cfg["min_notice_hours"])):
        raise HTTPException(422,
                            f"Trials must be booked at least {cfg['min_notice_hours']} hours ahead")
    if starts_at.date() > (now + timedelta(days=int(cfg["max_days_ahead"]) + 1)).date():
        raise HTTPException(422, "That date is too far ahead")
    local_day = starts_at.astimezone(_tz(gym)).date()
    if starts_at not in {s for s, _ in day_slots(gym, local_day)}:
        raise HTTPException(422, "Not an available trial slot (outside trial hours)")
    if trainer_id and TenantRepository(Trainer, db).get(trainer_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trainer not found in this gym")
    taken = _active_at(db, starts_at, exclude_id)
    if len(taken) >= int(cfg["capacity"]):
        raise HTTPException(status.HTTP_409_CONFLICT, "That slot is fully booked")
    if trainer_id and any(b.trainer_id == trainer_id for b in taken):
        raise HTTPException(status.HTTP_409_CONFLICT, "That trainer already has a trial at this time")
    other = TenantRepository(TrialBooking, db).first(TrialBooking.lead_id == lead_id,
                                                    TrialBooking.status.in_(ACTIVE_TRIAL_STATUSES),
                                                    *( [TrialBooking.id != exclude_id] if exclude_id else []))
    if other:
        raise HTTPException(status.HTTP_409_CONFLICT, "This lead already has an upcoming trial - reschedule it instead")
    return starts_at


def _lock_gym(db: Session) -> Gym:
    return db.scalars(select(Gym).where(Gym.id == get_current_gym_id()).with_for_update()).one()


def _fmt_local(gym: Gym, dt: datetime) -> str:
    return _as_utc(dt).astimezone(_tz(gym)).strftime("%a %d %b, %I:%M %p")


def book(db: Session, lead: Lead, starts_at: datetime, *, trainer_id=None, source: str = "staff",
         user: User | None = None, notes: str | None = None, actor: str = "user") -> TrialBooking:
    """Workflow 3 - check availability, create booking, update lead, schedule confirmation + reminder."""
    if lead.status in (LeadStatus.CONVERTED, LeadStatus.LOST):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Lead is {lead.status.value}; reopen it first")
    gym = _lock_gym(db)
    starts_at = _validate_slot(db, gym, starts_at, trainer_id, lead.id)
    ends_at = starts_at + timedelta(minutes=int(config(gym)["slot_minutes"]))
    trial = TenantRepository(TrialBooking, db).add(lead_id=lead.id, trainer_id=trainer_id, starts_at=starts_at,
                                                   ends_at=ends_at, status=TrialStatus.BOOKED, source=source,
                                                   notes=notes, status_changed_by_id=user.id if user else None)
    lead.wants_trial = True
    crm.advance(db, lead, LeadStatus.TRIAL_BOOKED, user, note=f"Trial booked for {_fmt_local(gym, starts_at)}")
    crm.record_interaction(db, lead, "system", f"Trial booked ({source}) for {_fmt_local(gym, starts_at)}",
                           user=user, data={"trial_id": str(trial.id)})
    when = _fmt_local(gym, starts_at)
    messaging.send_to_lead(db, lead, f"Hi {lead.name.split()[0]}, your free trial at {gym.name} is confirmed for "
                           f"{when}. Reply here if you need to change it.", category="trial_confirmation",
                           template_params=[lead.name.split()[0], gym.name, when],
                           dedup_key=f"trial_confirm:{trial.id}", draft_title=f"Confirm trial with {lead.name}")
    remind_at = starts_at - timedelta(hours=3)
    if remind_at > datetime.now(timezone.utc):
        messaging.send_to_lead(db, lead, f"Reminder: your trial at {gym.name} is today at "
                               f"{_as_utc(starts_at).astimezone(_tz(gym)).strftime('%I:%M %p')}. See you soon!",
                               category="trial_reminder", scheduled_for=remind_at,
                               template_params=[lead.name.split()[0], gym.name, when],
                               dedup_key=f"trial_remind:{trial.id}", due_at=remind_at,
                               draft_title=f"Remind {lead.name} about today's trial")
    crm.rescore(db, lead)
    events.emit(db, "trial.booked", entity_type="trial", entity_id=trial.id, actor=actor,
                actor_user_id=user.id if user else None,
                payload={"lead_id": lead.id, "starts_at": starts_at.isoformat(), "source": source})
    return trial


def reschedule(db: Session, trial: TrialBooking, starts_at: datetime, user: User | None,
               trainer_id=None) -> TrialBooking:
    if trial.status not in ACTIVE_TRIAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Trial is {trial.status.value}")
    gym = _lock_gym(db)
    trainer_id = trainer_id or trial.trainer_id
    starts_at = _validate_slot(db, gym, starts_at, trainer_id, trial.lead_id, exclude_id=trial.id)
    old = trial.starts_at
    trial.starts_at, trial.trainer_id = starts_at, trainer_id
    trial.ends_at = starts_at + timedelta(minutes=int(config(gym)["slot_minutes"]))
    trial.status = TrialStatus.BOOKED
    trial.reschedule_count += 1
    lead = db.get(Lead, trial.lead_id)
    crm.record_interaction(db, lead, "system", f"Trial rescheduled to {_fmt_local(gym, starts_at)}", user=user)
    events.emit(db, "trial.rescheduled", entity_type="trial", entity_id=trial.id,
                actor_user_id=user.id if user else None,
                payload={"from": _as_utc(old).isoformat(), "to": starts_at.isoformat()})
    return trial


def cancel(db: Session, trial: TrialBooking, user: User | None, reason: str | None) -> TrialBooking:
    if trial.status not in ACTIVE_TRIAL_STATUSES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Trial is {trial.status.value}")
    trial.status = TrialStatus.CANCELLED
    trial.cancel_reason = reason
    trial.status_changed_by_id = user.id if user else None
    lead = db.get(Lead, trial.lead_id)
    crm.record_interaction(db, lead, "system", f"Trial cancelled{': ' + reason if reason else ''}", user=user)
    crm.close_open_tasks(db, trial_id=trial.id, outcome="Trial cancelled")
    events.emit(db, "trial.cancelled", entity_type="trial", entity_id=trial.id,
                actor_user_id=user.id if user else None, payload={"reason": reason})
    return trial


def mark_attended(db: Session, trial: TrialBooking, user: User) -> TrialBooking:
    if trial.status not in (TrialStatus.BOOKED, TrialStatus.PENDING_REVIEW, TrialStatus.NO_SHOW):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Trial is {trial.status.value}")
    trial.status = TrialStatus.ATTENDED
    trial.attended_at = crm.now_utc()
    trial.status_changed_by_id = user.id
    lead = db.get(Lead, trial.lead_id)
    crm.advance(db, lead, LeadStatus.TRIAL_ATTENDED, user, note="Attended trial")
    crm.close_open_tasks(db, trial_id=trial.id, outcome="Attendance recorded")
    crm.create_task(db, title=f"Post-trial follow-up: {lead.name}", kind=TaskKind.FOLLOW_UP, lead_id=lead.id,
                    trial_id=trial.id, priority=Priority.HIGH, due_at=crm.now_utc() + timedelta(hours=20),
                    source="workflow", dedup_key=f"post_trial:{trial.id}",
                    description="Ask how the trial went and share the membership options.")
    crm.rescore(db, lead)
    events.emit(db, "trial.attended", entity_type="trial", entity_id=trial.id, actor_user_id=user.id,
                payload={"lead_id": lead.id})
    return trial


def confirm_no_show(db: Session, trial: TrialBooking, user: User) -> TrialBooking:
    """Workflow 4 - only staff can confirm a no-show (unrecorded attendance is not assumed to be one)."""
    if trial.status not in (TrialStatus.BOOKED, TrialStatus.PENDING_REVIEW):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Trial is {trial.status.value}")
    if _as_utc(trial.starts_at) > crm.now_utc():
        raise HTTPException(status.HTTP_409_CONFLICT, "The trial has not started yet")
    from app.modules.recovery.service import upsert_opportunity

    trial.status = TrialStatus.NO_SHOW
    trial.status_changed_by_id = user.id
    lead = db.get(Lead, trial.lead_id)
    gym = db.get(Gym, trial.gym_id)
    crm.close_open_tasks(db, trial_id=trial.id, outcome="No-show confirmed")
    crm.record_interaction(db, lead, "system", "No-show confirmed by staff", user=user)
    opp = upsert_opportunity(
        db, dedup_key=f"trial_no_show:{trial.id}", type=OpportunityType.TRIAL_NO_SHOW, lead_id=lead.id,
        trial_id=trial.id, title=f"Trial no-show: {lead.name}", reason=f"Missed trial on {_fmt_local(gym, trial.starts_at)}",
        potential_revenue=_lead_value(db, lead), priority=Priority.MEDIUM, next_action="Call to rebook the trial",
        due_date=crm.now_utc().date() + timedelta(days=1))
    draft = (f"Hi {lead.name.split()[0]}, we missed you at your trial today at {gym.name}. "
             "Would you like to pick another time this week?")
    crm.create_task(db, title=f"Rebook no-show: {lead.name}", kind=TaskKind.NO_SHOW, lead_id=lead.id,
                    trial_id=trial.id, opportunity_id=opp.id, priority=Priority.MEDIUM,
                    due_at=crm.now_utc() + timedelta(hours=4), source="workflow", draft_message=draft,
                    dedup_key=f"no_show_task:{trial.id}")
    events.emit(db, "trial.no_show", entity_type="trial", entity_id=trial.id, actor_user_id=user.id,
                payload={"lead_id": lead.id})
    return trial


def _lead_value(db: Session, lead: Lead) -> float:
    from app.database.models import MembershipPlan

    plans = TenantRepository(MembershipPlan, db)
    if lead.interested_plan_id and (plan := plans.get(lead.interested_plan_id)):
        return float(plan.price)
    cheapest = plans.first(MembershipPlan.is_active.is_(True), order_by=MembershipPlan.duration_days)
    return float(cheapest.price) if cheapest else 0.0


def flag_pending_reviews(db: Session, now: datetime | None = None) -> int:
    """Booked trials whose slot has passed without attendance -> pending review + a task to confirm."""
    now = now or crm.now_utc()
    gym = db.get(Gym, get_current_gym_id())
    grace = timedelta(minutes=int(config(gym)["attendance_grace_minutes"]))
    count = 0
    for trial in TenantRepository(TrialBooking, db).list(TrialBooking.status == TrialStatus.BOOKED,
                                                         TrialBooking.ends_at < now - grace, limit=1000):
        trial.status = TrialStatus.PENDING_REVIEW
        lead = db.get(Lead, trial.lead_id)
        crm.create_task(db, title=f"Record trial attendance: {lead.name}", kind=TaskKind.NO_SHOW, lead_id=lead.id,
                        trial_id=trial.id, priority=Priority.HIGH, due_at=now, source="workflow",
                        dedup_key=f"attendance_review:{trial.id}",
                        description="Mark as attended, or confirm a no-show. Nothing is assumed automatically.")
        count += 1
    db.commit()
    return count

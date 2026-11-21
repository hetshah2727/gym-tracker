"""Lead CRM: capture, attribution, duplicate detection, scoring, pipeline, tasks and conversion.

All deterministic. Shared by the public enquiry form, the AI sales agent, WhatsApp, staff and workers.
"""
import re
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import (
    Campaign, FollowUpTask, Gym, LandingPage, Lead, LeadInteraction, Member, MembershipPlan, TrialBooking, User,
)
from app.database.models.enums import (
    OPEN_LEAD_STATUSES, LeadSource, LeadStatus, PaymentMethod, Priority, Role, TaskKind, TaskStatus, TrialStatus,
)
from app.database.repositories.base import TenantRepository
from app.services import events

AI_REFERRERS = {
    "chatgpt.com": "chatgpt", "chat.openai.com": "chatgpt", "perplexity.ai": "perplexity",
    "www.perplexity.ai": "perplexity", "gemini.google.com": "gemini", "copilot.microsoft.com": "copilot",
    "claude.ai": "claude",
}
SEARCH_REFERRERS = ("google.", "bing.com", "duckduckgo.com", "search.yahoo.com")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def phone_key(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    return digits[-10:] if len(digits) >= 10 else (digits or None)


# ---------------------------------------------------------------- attribution

@dataclass
class Attribution:
    source: str
    method: str                     # utm | referrer | landing_page | declared | staff | unknown
    evidence: dict = field(default_factory=dict)
    campaign_id: uuid.UUID | None = None
    landing_page_id: uuid.UUID | None = None


def attribute(db: Session, *, declared_source: str | None, utm: dict | None, referrer: str | None,
              landing_page_slug: str | None = None, channel_default: str = LeadSource.WEBSITE.value) -> Attribution:
    """Work out where an enquiry came from, using only evidence we actually have.

    Never guesses Google Maps: a lead counts as ``google_business_profile`` only when it arrives through a
    tracked link (utm_source=google & utm_medium=gbp/maps, or a campaign tagged with that source).
    """
    utm = {k: v for k, v in (utm or {}).items() if v}
    evidence = {"utm": utm} if utm else {}
    if referrer:
        evidence["referrer"] = referrer[:500]
    campaign = None
    if utm.get("utm_campaign"):
        campaign = TenantRepository(Campaign, db).first(Campaign.code == utm["utm_campaign"][:80])
    landing = None
    if landing_page_slug:
        landing = TenantRepository(LandingPage, db).first(LandingPage.slug == landing_page_slug)
        if landing:
            evidence["landing_page"] = landing.slug
    result = Attribution(source=channel_default, method="unknown", evidence=evidence,
                         campaign_id=campaign.id if campaign else None,
                         landing_page_id=landing.id if landing else None)

    src, medium = (utm.get("utm_source") or "").lower(), (utm.get("utm_medium") or "").lower()
    if campaign:
        result.source, result.method = campaign.source, "utm"
    elif src:
        result.method = "utm"
        if src == "google" and medium in ("gbp", "maps", "google_business_profile", "local"):
            result.source = LeadSource.GOOGLE_BUSINESS_PROFILE.value
        elif src in ("chatgpt.com", "chatgpt", "perplexity", "gemini", "copilot") or medium == "ai_search":
            result.source = LeadSource.AI_SEARCH.value
        elif src in ("instagram", "ig"):
            result.source = LeadSource.INSTAGRAM.value
        elif src == "qr" or medium == "qr":
            result.source = LeadSource.QR_CODE.value
        elif medium in ("cpc", "paid", "ppc", "paid_social"):
            result.source = LeadSource.PAID_CAMPAIGN.value
        elif src == "referral" or medium == "referral":
            result.source = LeadSource.REFERRAL.value
        else:
            result.source = LeadSource.OTHER.value
    elif referrer:
        host = (urlparse(referrer).hostname or "").lower()
        if host in AI_REFERRERS:
            result.source, result.method = LeadSource.AI_SEARCH.value, "referrer"
            evidence["ai_assistant"] = AI_REFERRERS[host]
        elif any(s in host for s in SEARCH_REFERRERS):
            result.source, result.method = LeadSource.ORGANIC_SEARCH.value, "referrer"
        elif "instagram.com" in host:
            result.source, result.method = LeadSource.INSTAGRAM.value, "referrer"
    if result.method == "unknown" and landing:
        result.source, result.method = LeadSource.SEO_LANDING_PAGE.value, "landing_page"
    if result.method == "unknown" and declared_source:
        valid = {s.value for s in LeadSource}
        result.source = declared_source if declared_source in valid else LeadSource.OTHER.value
        result.method = "declared"
    return result


# ---------------------------------------------------------------- tasks

def create_task(db: Session, *, title: str, kind: TaskKind = TaskKind.FOLLOW_UP, lead_id=None, member_id=None,
                opportunity_id=None, trial_id=None, priority: Priority = Priority.MEDIUM,
                due_at: datetime | None = None, assigned_to_id=None, source: str = "manual",
                description: str | None = None, draft_message: str | None = None,
                dedup_key: str | None = None) -> FollowUpTask:
    """Create a task, or return the existing one with the same ``dedup_key`` (idempotent). Flushes only."""
    repo = TenantRepository(FollowUpTask, db)
    if dedup_key:
        existing = repo.first(FollowUpTask.dedup_key == dedup_key)
        if existing:
            return existing
    data = dict(title=title[:255], kind=kind, lead_id=lead_id, member_id=member_id, opportunity_id=opportunity_id,
                trial_id=trial_id, priority=priority, due_at=due_at, assigned_to_id=assigned_to_id, source=source,
                description=description, draft_message=draft_message, dedup_key=dedup_key)
    try:
        with db.begin_nested():
            task = repo.add(**data)
        return task
    except IntegrityError:  # concurrent creator won the race
        return repo.first(FollowUpTask.dedup_key == dedup_key)


def complete_task(db: Session, task: FollowUpTask, user: User | None, outcome: str | None = None,
                  cancelled: bool = False) -> FollowUpTask:
    task.status = TaskStatus.CANCELLED if cancelled else TaskStatus.DONE
    task.completed_at = now_utc()
    task.completed_by_id = user.id if user else None
    task.outcome = outcome
    db.flush()
    return task


def close_open_tasks(db: Session, *, lead_id=None, trial_id=None, kinds: tuple[TaskKind, ...] | None = None,
                     outcome: str = "Resolved automatically") -> int:
    filters = [FollowUpTask.status == TaskStatus.OPEN]
    if lead_id:
        filters.append(FollowUpTask.lead_id == lead_id)
    if trial_id:
        filters.append(FollowUpTask.trial_id == trial_id)
    if kinds:
        filters.append(FollowUpTask.kind.in_(kinds))
    tasks = TenantRepository(FollowUpTask, db).list(*filters, limit=500)
    for t in tasks:
        complete_task(db, t, None, outcome)
    return len(tasks)


# ---------------------------------------------------------------- scoring

DEFAULT_SCORING = {
    "fresh_24h": 20, "fresh_72h": 10, "stale_14d": -10, "wants_trial": 20, "trial_booked": 25,
    "trial_attended": 30, "plan_selected": 10, "joining_soon": 15, "inbound_message": 5, "inbound_cap": 15,
    "negotiation": 15, "overdue_follow_up": -10, "has_phone": 5,
    "source_bonus": {"referral": 10, "walk_in": 10, "website_chat": 5, "whatsapp": 5},
}


def scoring_rules(gym: Gym) -> dict:
    custom = (gym.settings or {}).get("lead_scoring") or {}
    return {**DEFAULT_SCORING, **custom, "source_bonus": {**DEFAULT_SCORING["source_bonus"],
                                                         **custom.get("source_bonus", {})}}


def score_lead(db: Session, lead: Lead, now: datetime | None = None) -> tuple[int, list[dict], Priority]:
    """Rule-based, explainable score (0-100). Every point comes with a reason."""
    now = now or now_utc()
    rules = scoring_rules(db.get(Gym, lead.gym_id))
    reasons: list[dict] = []

    def add(points: int, why: str):
        if points:
            reasons.append({"points": points, "reason": why})

    age = now - aware(lead.created_at) if lead.created_at else timedelta(0)
    if age <= timedelta(hours=24):
        add(rules["fresh_24h"], "Enquired in the last 24 hours")
    elif age <= timedelta(hours=72):
        add(rules["fresh_72h"], "Enquired in the last 3 days")
    elif age > timedelta(days=14):
        add(rules["stale_14d"], "Enquiry is more than 14 days old")
    if lead.phone:
        add(rules["has_phone"], "Phone number available")
    trial = TenantRepository(TrialBooking, db).first(TrialBooking.lead_id == lead.id,
                                                    order_by=TrialBooking.starts_at.desc()) if lead.id else None
    if trial and trial.status == TrialStatus.ATTENDED:
        add(rules["trial_attended"], "Attended a trial session")
    elif trial and trial.status in (TrialStatus.BOOKED, TrialStatus.PENDING_REVIEW):
        add(rules["trial_booked"], "Has a trial booked")
    elif lead.wants_trial:
        add(rules["wants_trial"], "Asked for a trial")
    if lead.interested_plan_id:
        add(rules["plan_selected"], "Chose a membership plan")
    if lead.preferred_joining_date and lead.preferred_joining_date <= (now.date() + timedelta(days=14)):
        add(rules["joining_soon"], "Wants to join within 2 weeks")
    if lead.id:
        inbound = TenantRepository(LeadInteraction, db).count(LeadInteraction.lead_id == lead.id,
                                                              LeadInteraction.direction == "in")
        if inbound:
            add(min(inbound * rules["inbound_message"], rules["inbound_cap"]), f"{inbound} message(s) from the lead")
    if lead.status == LeadStatus.NEGOTIATION:
        add(rules["negotiation"], "In price negotiation")
    if lead.next_follow_up_at and aware(lead.next_follow_up_at) < now:
        add(rules["overdue_follow_up"], "Follow-up is overdue")
    add(rules["source_bonus"].get(lead.source, 0), f"Source: {lead.source.replace('_', ' ')}")

    score = max(0, min(100, sum(r["points"] for r in reasons)))
    uncontacted = lead.status == LeadStatus.NEW and lead.first_response_at is None
    if score >= 60 or (uncontacted and age > timedelta(hours=2)):
        priority = Priority.HIGH
    elif score >= 30:
        priority = Priority.MEDIUM
    else:
        priority = Priority.LOW
    return score, reasons, priority


def rescore(db: Session, lead: Lead) -> Lead:
    if lead.status in (LeadStatus.CONVERTED, LeadStatus.LOST):
        return lead
    lead.score, lead.score_reasons, lead.priority = score_lead(db, lead)
    db.flush()
    return lead


# ---------------------------------------------------------------- interactions

def record_interaction(db: Session, lead: Lead, kind: str, body: str | None = None, *, direction: str | None = None,
                       user: User | None = None, is_contact: bool | None = None, data: dict | None = None,
                       at: datetime | None = None) -> LeadInteraction:
    """Add to the lead timeline. Outbound calls/messages count as contact and move NEW -> CONTACTED."""
    if is_contact is None:
        is_contact = direction == "out" and kind in ("call", "whatsapp", "email", "sms", "visit")
    at = at or now_utc()
    item = TenantRepository(LeadInteraction, db).add(lead_id=lead.id, user_id=user.id if user else None, kind=kind,
                                                     direction=direction, body=body, data=data or {},
                                                     is_contact=is_contact, created_at=at)
    if direction == "in" and kind == "whatsapp":
        lead.last_inbound_at = at  # only a WhatsApp message opens the 24-hour customer-service window
    if direction == "out" and lead.first_response_at is None:
        lead.first_response_at = at  # an AI chat reply is a response, but not a staff contact
    if is_contact:
        lead.last_contacted_at = at
        if lead.status == LeadStatus.NEW:
            _set_status(db, lead, LeadStatus.CONTACTED, user, note="First contact recorded")
        close_open_tasks(db, lead_id=lead.id, kinds=(TaskKind.FOLLOW_UP,), outcome="Lead contacted")
    db.flush()
    return item


# ---------------------------------------------------------------- pipeline

PIPELINE = [LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.TRIAL_BOOKED,
            LeadStatus.TRIAL_ATTENDED, LeadStatus.NEGOTIATION, LeadStatus.CONVERTED, LeadStatus.LOST]


def _set_status(db: Session, lead: Lead, new: LeadStatus, user: User | None, note: str | None = None) -> None:
    old = lead.status
    if old == new:
        return
    lead.status = new
    TenantRepository(LeadInteraction, db).add(
        lead_id=lead.id, user_id=user.id if user else None, kind="stage_change", body=note,
        data={"from": old.value, "to": new.value}, is_contact=False, created_at=now_utc())


def advance(db: Session, lead: Lead, new: LeadStatus, user: User | None = None, note: str | None = None) -> None:
    """Move forward only (used by automation, e.g. trial booked). Never reopens closed leads."""
    if lead.status in (LeadStatus.CONVERTED, LeadStatus.LOST):
        return
    if PIPELINE.index(new) > PIPELINE.index(lead.status):
        _set_status(db, lead, new, user, note)


def change_status(db: Session, lead: Lead, new: LeadStatus, user: User | None, *, lost_reason: str | None = None,
                  note: str | None = None, actor: str = "user") -> Lead:
    """Staff/agent stage change with validation."""
    if new == LeadStatus.CONVERTED and not lead.converted_membership_id:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            "Use 'Convert to member' so the membership and payment are recorded.")
    if new == LeadStatus.LOST:
        if not lost_reason:
            raise HTTPException(422, "A lost reason is required")
        lead.lost_reason = lost_reason[:255]
        close_open_tasks(db, lead_id=lead.id, outcome="Lead marked lost")
    old = lead.status
    _set_status(db, lead, new, user, note or (f"Lost: {lost_reason}" if new == LeadStatus.LOST else None))
    rescore(db, lead)
    events.emit(db, "lead.status_changed", entity_type="lead", entity_id=lead.id, actor=actor,
                actor_user_id=user.id if user else None, payload={"from": old.value, "to": new.value})
    return lead


# ---------------------------------------------------------------- capture

@dataclass
class LeadInput:
    name: str
    phone: str | None = None
    email: str | None = None
    message: str | None = None
    fitness_interest: str | None = None
    interested_plan_id: uuid.UUID | None = None
    preferred_location: str | None = None
    preferred_joining_date: date | None = None
    wants_trial: bool = False
    whatsapp_opt_in: bool = False
    website_id: uuid.UUID | None = None
    notes: str | None = None
    assigned_to_id: uuid.UUID | None = None


def find_duplicate(db: Session, phone: str | None, email: str | None) -> Lead | None:
    """Most recent OPEN lead with the same phone (last 10 digits) or email."""
    conds = []
    if key := phone_key(phone):
        conds.append(Lead.phone_key == key)
    if email:
        conds.append(func.lower(Lead.email) == email.lower())
    if not conds:
        return None
    return TenantRepository(Lead, db).first(or_(*conds), Lead.status.in_(OPEN_LEAD_STATUSES),
                                            order_by=Lead.created_at.desc())


def match_member(db: Session, phone: str | None, email: str | None) -> Member | None:
    """An existing member with the same phone (last 10 digits) or email, if any."""
    key = phone_key(phone)
    conds = ([Member.phone.like(f"%{key}")] if key else []) +         ([func.lower(Member.email) == email.lower()] if email else [])
    if not conds:
        return None
    for member in TenantRepository(Member, db).list(or_(*conds), limit=10):
        if (key and phone_key(member.phone) == key) or (email and (member.email or "").lower() == email.lower()):
            return member
    return None


def capture_lead(db: Session, data: LeadInput, attribution: Attribution, *, actor: str = "public",
                 user: User | None = None, channel_note: str | None = None) -> tuple[Lead, bool]:
    """Workflow 1 (website enquiry) - validate, de-duplicate, create/merge, attribute, score, task, notify.

    Returns (lead, created). A repeat enquiry from an open lead is merged into it instead of duplicated.
    """
    if not data.phone and not data.email:
        raise HTTPException(422, "Phone or email is required")
    if data.interested_plan_id and not TenantRepository(MembershipPlan, db).get(data.interested_plan_id):
        data.interested_plan_id = None
    repo = TenantRepository(Lead, db)
    existing = find_duplicate(db, data.phone, data.email)
    if existing:
        lead = existing
        for attr in ("phone", "email", "fitness_interest", "interested_plan_id", "preferred_location",
                     "preferred_joining_date"):
            if getattr(lead, attr) in (None, "") and getattr(data, attr):
                setattr(lead, attr, getattr(data, attr))
        if attr_phone := data.phone:
            lead.phone_key = phone_key(attr_phone)
        lead.wants_trial = lead.wants_trial or data.wants_trial
        lead.whatsapp_opt_in = lead.whatsapp_opt_in or data.whatsapp_opt_in
        record_interaction(db, lead, "system", f"Repeat enquiry via {attribution.source.replace('_', ' ')}"
                           + (f": {data.message}" if data.message else ""), direction="in",
                           data={"attribution": attribution.evidence, "method": attribution.method})
        rescore(db, lead)
        events.emit(db, "lead.duplicate_merged", entity_type="lead", entity_id=lead.id, actor=actor,
                    payload={"source": attribution.source})
        return lead, False

    member = match_member(db, data.phone, data.email)
    lead = repo.add(
        name=data.name.strip()[:200], phone=data.phone, phone_key=phone_key(data.phone), email=data.email,
        message=data.message, source=attribution.source, status=LeadStatus.NEW, website_id=data.website_id,
        campaign_id=attribution.campaign_id, landing_page_id=attribution.landing_page_id,
        attribution={"method": attribution.method, **attribution.evidence},
        fitness_interest=data.fitness_interest, interested_plan_id=data.interested_plan_id,
        preferred_location=data.preferred_location, preferred_joining_date=data.preferred_joining_date,
        wants_trial=data.wants_trial, whatsapp_opt_in=data.whatsapp_opt_in, notes=data.notes,
        assigned_to_id=data.assigned_to_id, existing_member_id=member.id if member else None,
        priority=Priority.MEDIUM, score=0, score_reasons=[],
    )
    record_interaction(db, lead, "system", channel_note or f"Enquiry received via {attribution.source.replace('_', ' ')}"
                       + (f": {data.message}" if data.message else ""), direction="in",
                       data={"attribution": attribution.evidence, "method": attribution.method})
    rescore(db, lead)

    gym = db.get(Gym, get_current_gym_id())
    sla_minutes = int(((gym.settings or {}).get("crm") or {}).get("first_response_minutes", 15))
    create_task(db, title=f"Contact new enquiry: {lead.name}", kind=TaskKind.FOLLOW_UP, lead_id=lead.id,
                priority=Priority.HIGH, due_at=now_utc() + timedelta(minutes=sla_minutes), source="workflow",
                assigned_to_id=lead.assigned_to_id, dedup_key=f"lead_first_contact:{lead.id}",
                description=("Existing member - check before selling. " if member else "")
                + f"Respond within {sla_minutes} minutes. Interest: {lead.fitness_interest or 'not stated'}.")
    lead.next_follow_up_at = now_utc() + timedelta(minutes=sla_minutes)
    events.emit(db, "lead.created", entity_type="lead", entity_id=lead.id, actor=actor,
                actor_user_id=user.id if user else None,
                payload={"name": lead.name, "source": lead.source, "method": attribution.method,
                         "campaign_id": attribution.campaign_id, "landing_page_id": attribution.landing_page_id})
    return lead, True


# ---------------------------------------------------------------- conversion

def convert_lead(db: Session, lead: Lead, *, plan_id: uuid.UUID, user: User, paid: bool,
                 payment_method: PaymentMethod | None, amount: float | None = None,
                 start_date: date | None = None) -> Lead:
    """Turn a lead into a member with a real membership + payment record. Revenue counts only when paid."""
    from app.modules.memberships.service import assign_membership

    if lead.status == LeadStatus.CONVERTED:
        raise HTTPException(status.HTTP_409_CONFLICT, "Lead is already converted")
    plan = TenantRepository(MembershipPlan, db).get(plan_id)
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Plan not found")
    members = TenantRepository(Member, db)
    member = members.get(lead.existing_member_id) if lead.existing_member_id else None
    if member is None:
        if not lead.phone:
            raise HTTPException(422, "A phone number is needed to create a member")
        member = members.create(full_name=lead.name, phone=lead.phone, email=lead.email,
                                notes=f"Converted from lead ({lead.source})")
    membership = assign_membership(db, member, plan, start_date=start_date, amount=amount, paid=paid,
                                   payment_method=payment_method)
    lead.converted_member_id = member.id
    lead.converted_membership_id = membership.id
    lead.converted_at = now_utc()
    _set_status(db, lead, LeadStatus.CONVERTED, user, note=f"Joined: {plan.name}")
    trial = TenantRepository(TrialBooking, db).first(TrialBooking.lead_id == lead.id,
                                                    TrialBooking.status == TrialStatus.ATTENDED)
    if trial:
        trial.converted_membership_id = membership.id
    close_open_tasks(db, lead_id=lead.id, outcome="Lead joined")
    events.emit(db, "lead.converted", entity_type="lead", entity_id=lead.id, actor_user_id=user.id,
                payload={"member_id": member.id, "membership_id": membership.id, "plan": plan.name,
                         "amount": float(membership.amount), "paid": paid, "source": lead.source,
                         "trial_id": trial.id if trial else None})
    return lead


def staff_users(db: Session) -> list[User]:
    return list(db.scalars(select(User).where(User.gym_id == get_current_gym_id(), User.is_active.is_(True),
                                              User.role.in_([Role.GYM_OWNER, Role.GYM_MANAGER]))).all())

"""Agent tools (deterministic) and the eight GymFlow agent definitions."""
import hashlib
import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.agents.registry import OWNER, PUBLIC, STAFF, AgentContext, AgentSpec, define, tool
from app.database.models import (
    FollowUpTask, GrowthReport, Gym, Lead, Member, Membership, MembershipPlan, Payment, RecoveryOpportunity, Review,
    SeoAudit, SeoFinding, TrialBooking,
)
from app.database.models.enums import (
    OPEN_OPPORTUNITY_STATUSES, AuditStatus, LeadSource, LeadStatus, MembershipStatus, OpportunityType,
    PaymentStatus, Priority, ReplyStatus, TaskKind, TaskStatus, TrialStatus,
)
from app.database.repositories.base import TenantRepository
from app.modules.crm import service as crm
from app.modules.growth import insights, metrics
from app.services import content, messaging

TRAINERS_TOO = (*STAFF, "trainer")


def _money(v: float) -> float:
    return round(float(v), 2)


def _lead_out(l: Lead) -> dict:
    return {"id": str(l.id), "name": l.name, "phone": l.phone, "source": l.source, "status": l.status.value,
            "score": l.score, "priority": l.priority.value, "created_at": l.created_at.isoformat(),
            "first_response_at": l.first_response_at.isoformat() if l.first_response_at else None,
            "interest": l.fitness_interest}


class NoArgs(BaseModel):
    pass


class PeriodArgs(BaseModel):
    days: int = Field(30, ge=1, le=366, description="Look-back window in days")


def _period(days: int) -> tuple[date, date]:
    today = date.today()
    return today - timedelta(days=days - 1), today


# ================================================================ Lead conversion (public-facing)

@tool("get_gym_info", "Approved facts about the gym: address, hours, services, facilities, trial offer, FAQs.",
      NoArgs, (PUBLIC, *TRAINERS_TOO))
def get_gym_info(ctx: AgentContext, _: NoArgs) -> dict:
    f = content.load_facts(ctx.db)
    return {"gym": f.gym, "address": f.address, "area": f.area, "city": f.city, "phone": f.phone, "hours": f.hours,
            "services": f.services, "facilities": f.facilities, "trial_offer": f.trial, "offers": f.offers,
            "faqs": f.faqs, "trainers": f.trainers}


@tool("list_membership_plans", "Current membership plans with prices (only these may be quoted).", NoArgs,
      (PUBLIC, *TRAINERS_TOO))
def list_membership_plans(ctx: AgentContext, _: NoArgs) -> dict:
    gym = ctx.db.get(Gym, ctx.gym_id)
    plans = TenantRepository(MembershipPlan, ctx.db).list(MembershipPlan.is_active.is_(True),
                                                          order_by=MembershipPlan.duration_days)
    return {"currency": gym.currency, "plans": [{"id": str(p.id), "name": p.name, "price": _money(p.price),
                                                 "duration_days": p.duration_days, "description": p.description}
                                                for p in plans]}


class SlotArgs(BaseModel):
    start_date: date | None = Field(None, description="First day to search (default today)")
    days: int = Field(4, ge=1, le=14)


@tool("find_trial_slots", "Available trial slots (start times in the gym's timezone).", SlotArgs,
      (PUBLIC, *TRAINERS_TOO), feature="trials")
def find_trial_slots(ctx: AgentContext, args: SlotArgs) -> dict:
    from app.modules.trials.service import _tz, available_slots

    gym = ctx.db.get(Gym, ctx.gym_id)
    slots = available_slots(ctx.db, args.start_date or date.today(), args.days)[:12]
    tz = _tz(gym)
    return {"timezone": str(tz), "slots": [{"starts_at": s["starts_at"].isoformat(),
                                            "local": s["starts_at"].astimezone(tz).strftime("%a %d %b, %I:%M %p"),
                                            "remaining": s["remaining"]} for s in slots]}


class LeadDetails(BaseModel):
    name: str | None = Field(None, max_length=200)
    phone: str | None = Field(None, max_length=32)
    email: str | None = Field(None, max_length=255)
    fitness_interest: str | None = Field(None, max_length=120, description="e.g. weight loss, strength, yoga")
    preferred_plan: str | None = Field(None, description="Plan name the visitor prefers")
    preferred_joining_date: date | None = None
    wants_trial: bool | None = None
    whatsapp_opt_in: bool | None = Field(None, description="Visitor agreed to WhatsApp messages")


def _conversation_lead(ctx: AgentContext) -> Lead | None:
    conv = ctx.conversation
    return ctx.db.get(Lead, conv.lead_id) if conv and conv.lead_id else None


@tool("save_lead_details", "Create or update the visitor's enquiry with details they gave. Never ask for health "
      "or medical information.", LeadDetails, (PUBLIC,), feature="lead_crm")
def save_lead_details(ctx: AgentContext, args: LeadDetails) -> dict:
    db, conv = ctx.db, ctx.conversation
    plan_id = None
    if args.preferred_plan:
        plan = TenantRepository(MembershipPlan, db).first(MembershipPlan.name.ilike(args.preferred_plan.strip()))
        plan_id = plan.id if plan else None
    lead = _conversation_lead(ctx)
    if lead is None:
        phone = args.phone or (conv.external_ref if conv and conv.channel == "whatsapp" else None)
        if not (phone or args.email):
            return {"saved": False, "need": "phone or email"}
        source = LeadSource.WHATSAPP.value if ctx.channel == "whatsapp" else LeadSource.WEBSITE_CHAT.value
        attribution = crm.attribute(db, declared_source=None, utm=(conv.state or {}).get("utm") if conv else None,
                                    referrer=(conv.state or {}).get("referrer") if conv else None,
                                    channel_default=source)
        if attribution.method == "unknown":
            attribution.source = source
        lead, _created = crm.capture_lead(db, crm.LeadInput(
            name=args.name or "Website visitor", phone=phone, email=args.email,
            fitness_interest=args.fitness_interest, interested_plan_id=plan_id,
            preferred_joining_date=args.preferred_joining_date, wants_trial=bool(args.wants_trial),
            whatsapp_opt_in=bool(args.whatsapp_opt_in) or ctx.channel == "whatsapp"),
            attribution, actor="agent", channel_note=f"Enquiry via {source.replace('_', ' ')} (AI agent)")
        if conv:
            conv.lead_id = lead.id
    else:
        for attr in ("name", "phone", "email", "fitness_interest", "preferred_joining_date"):
            value = getattr(args, attr)
            if value and (attr != "name" or lead.name in ("Website visitor", "WhatsApp contact")):
                setattr(lead, attr, value)
        if args.phone:
            lead.phone_key = crm.phone_key(args.phone)
        if plan_id:
            lead.interested_plan_id = plan_id
        if args.wants_trial:
            lead.wants_trial = True
        if args.whatsapp_opt_in:
            lead.whatsapp_opt_in = True
        if lead.status == LeadStatus.CONTACTED and (args.fitness_interest or plan_id or args.wants_trial):
            crm.advance(db, lead, LeadStatus.INTERESTED, None, note="Qualified by AI agent")
        crm.rescore(db, lead)
    db.commit()
    return {"saved": True, "lead_id": str(lead.id), "status": lead.status.value}


class BookArgs(BaseModel):
    starts_at: datetime = Field(description="Exact slot start time returned by find_trial_slots (ISO 8601)")


@tool("book_trial", "Book a trial for the visitor in an available slot. Requires their name and phone saved first.",
      BookArgs, (PUBLIC,), feature="trials")
def book_trial(ctx: AgentContext, args: BookArgs) -> dict:
    from app.modules.trials.service import _fmt_local, book

    lead = _conversation_lead(ctx)
    if lead is None or not lead.phone:
        return {"booked": False, "error": "Save the visitor's name and phone first"}
    try:
        trial = book(ctx.db, lead, args.starts_at, source="ai_agent", actor="agent")
    except HTTPException as exc:
        ctx.db.rollback()
        return {"booked": False, "error": exc.detail}
    gym = ctx.db.get(Gym, ctx.gym_id)
    return {"booked": True, "trial_id": str(trial.id), "when": _fmt_local(gym, trial.starts_at)}


class EscalateArgs(BaseModel):
    reason: str = Field(max_length=255, description="Why a person is needed")
    stop_ai: bool = Field(True, description="Hand the conversation to staff so the AI stops replying")


@tool("escalate_to_staff", "Hand over to a staff member (complaints, refunds, injuries, medical questions, anything "
      "not in the approved information, or when the visitor asks for a person).", EscalateArgs, (PUBLIC,))
def escalate_to_staff(ctx: AgentContext, args: EscalateArgs) -> dict:
    from app.database.models.enums import ConversationStatus

    conv, lead = ctx.conversation, _conversation_lead(ctx)
    task = crm.create_task(ctx.db, title=f"AI escalation: {lead.name if lead else 'website visitor'}",
                           kind=TaskKind.ESCALATION, lead_id=lead.id if lead else None, priority=Priority.HIGH,
                           due_at=datetime.now(timezone.utc) + timedelta(minutes=30), source="agent",
                           description=f"Reason: {args.reason}. Conversation {conv.id if conv else ''}.",
                           dedup_key=f"escalation:{conv.id}" if conv else None)
    if conv:
        conv.escalation_reason = args.reason
        if args.stop_ai:
            conv.status = ConversationStatus.HUMAN
    ctx.db.commit()
    return {"escalated": True, "task_id": str(task.id)}


# ================================================================ CRM & follow-up

class LeadQuery(BaseModel):
    status: LeadStatus | None = None
    uncontacted_only: bool = False
    limit: int = Field(10, ge=1, le=50)


@tool("list_leads", "List leads (newest first) with optional filters.", LeadQuery, STAFF, feature="lead_crm")
def list_leads(ctx: AgentContext, args: LeadQuery) -> dict:
    filters = []
    if args.status:
        filters.append(Lead.status == args.status)
    if args.uncontacted_only:
        filters += [Lead.status == LeadStatus.NEW, Lead.first_response_at.is_(None)]
    repo = TenantRepository(Lead, ctx.db)
    return {"total": repo.count(*filters), "leads": [_lead_out(l) for l in repo.list(*filters, limit=args.limit)]}


@tool("leads_to_follow_up_today", "Leads that need contact today: uncontacted, overdue tasks, high score.", NoArgs,
      STAFF, feature="lead_crm")
def leads_to_follow_up_today(ctx: AgentContext, _: NoArgs) -> dict:
    now = datetime.now(timezone.utc)
    repo = TenantRepository(Lead, ctx.db)
    uncontacted = repo.list(Lead.status == LeadStatus.NEW, Lead.first_response_at.is_(None), limit=20)
    due_tasks = TenantRepository(FollowUpTask, ctx.db).list(
        FollowUpTask.status == TaskStatus.OPEN, FollowUpTask.lead_id.is_not(None),
        FollowUpTask.due_at <= now + timedelta(hours=12), limit=30, order_by=FollowUpTask.due_at)
    due_leads = [repo.get(t.lead_id) for t in due_tasks]
    hot = repo.list(Lead.status.in_([LeadStatus.INTERESTED, LeadStatus.TRIAL_ATTENDED, LeadStatus.NEGOTIATION]),
                    Lead.score >= 50, limit=10, order_by=Lead.score.desc())
    seen, out = set(), []
    for why, items in (("No response yet", uncontacted), ("Follow-up due", due_leads), ("High score", hot)):
        for l in items:
            if l and l.id not in seen:
                seen.add(l.id)
                out.append({**_lead_out(l), "why": why})
    return {"count": len(out), "leads": out[:25]}


class TaskArgs(BaseModel):
    title: str = Field(max_length=255)
    lead_id: uuid.UUID | None = None
    member_id: uuid.UUID | None = None
    due_in_hours: int = Field(4, ge=0, le=24 * 30)
    priority: Priority = Priority.MEDIUM
    note: str | None = Field(None, max_length=1000)


@tool("create_follow_up_task", "Create an internal follow-up task for staff (no message is sent).", TaskArgs, STAFF,
      feature="lead_crm")
def create_follow_up_task(ctx: AgentContext, args: TaskArgs) -> dict:
    if args.lead_id and not TenantRepository(Lead, ctx.db).get(args.lead_id):
        return {"created": False, "error": "Lead not found"}
    if args.member_id and not TenantRepository(Member, ctx.db).get(args.member_id):
        return {"created": False, "error": "Member not found"}
    task = crm.create_task(ctx.db, title=args.title, lead_id=args.lead_id, member_id=args.member_id,
                           priority=args.priority, due_at=datetime.now(timezone.utc) + timedelta(hours=args.due_in_hours),
                           source="agent", description=args.note, assigned_to_id=ctx.user.id if ctx.user else None)
    ctx.db.commit()
    return {"created": True, "task_id": str(task.id), "title": task.title}


class MessageArgs(BaseModel):
    lead_id: uuid.UUID
    message: str = Field(max_length=1000)


@tool("send_message_to_lead", "Send a WhatsApp message to a lead (requires confirmation; respects opt-in/opt-out).",
      MessageArgs, STAFF, feature="whatsapp_workflows", consequential=True,
      summarize=lambda a: f"Send WhatsApp to lead {a.lead_id}: \"{a.message[:120]}\"")
def send_message_to_lead(ctx: AgentContext, args: MessageArgs) -> dict:
    lead = TenantRepository(Lead, ctx.db).get(args.lead_id)
    if lead is None:
        return {"sent": False, "error": "Lead not found"}
    outcome = messaging.send_to_lead(ctx.db, lead, args.message, category="sales_follow_up",
                                     dedup_key=f"agent_msg:{lead.id}:{hashlib.sha1(args.message.encode()).hexdigest()[:12]}")
    if outcome.status == "queued":
        crm.record_interaction(ctx.db, lead, "whatsapp", args.message, direction="out", user=ctx.user)
    ctx.db.commit()
    return {"status": outcome.status, "reason": outcome.reason}


# ================================================================ Trials

@tool("trial_stats", "Trial counts, attendance and conversion over a period.", PeriodArgs, TRAINERS_TOO,
      feature="trials")
def trial_stats(ctx: AgentContext, args: PeriodArgs) -> dict:
    return metrics.trial_analytics(ctx.db, *_period(args.days))


@tool("list_upcoming_trials", "Upcoming booked trials.", NoArgs, TRAINERS_TOO, feature="trials")
def list_upcoming_trials(ctx: AgentContext, _: NoArgs) -> dict:
    rows = TenantRepository(TrialBooking, ctx.db).list(TrialBooking.status == TrialStatus.BOOKED,
                                                       TrialBooking.starts_at >= datetime.now(timezone.utc),
                                                       limit=25, order_by=TrialBooking.starts_at)
    leads = TenantRepository(Lead, ctx.db)
    return {"trials": [{"id": str(t.id), "starts_at": t.starts_at.isoformat(),
                        "lead": (leads.get(t.lead_id).name if leads.get(t.lead_id) else None)} for t in rows]}


# ================================================================ Recovery

class ExpiringArgs(BaseModel):
    days: int = Field(7, ge=0, le=60)


@tool("list_expiring_memberships", "Active memberships ending within N days.", ExpiringArgs, STAFF,
      feature="members")
def list_expiring_memberships(ctx: AgentContext, args: ExpiringArgs) -> dict:
    today = date.today()
    rows = TenantRepository(Membership, ctx.db).list(Membership.status == MembershipStatus.ACTIVE,
                                                     Membership.end_date >= today,
                                                     Membership.end_date <= today + timedelta(days=args.days),
                                                     limit=200, order_by=Membership.end_date)
    members = TenantRepository(Member, ctx.db)
    out = []
    for ms in rows:
        m = members.get(ms.member_id)
        out.append({"membership_id": str(ms.id), "member": m.full_name if m else None, "end_date": ms.end_date.isoformat(),
                    "amount": _money(ms.amount)})
    return {"count": len(out), "memberships": out}


class OppQuery(BaseModel):
    type: OpportunityType | None = None
    limit: int = Field(15, ge=1, le=50)


@tool("list_recovery_opportunities", "Open revenue recovery opportunities (values are estimates).", OppQuery, STAFF,
      feature="recovery_center")
def list_recovery_opportunities(ctx: AgentContext, args: OppQuery) -> dict:
    filters = [RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES)]
    if args.type:
        filters.append(RecoveryOpportunity.type == args.type)
    repo = TenantRepository(RecoveryOpportunity, ctx.db)
    rows = repo.list(*filters, limit=args.limit, order_by=RecoveryOpportunity.potential_revenue.desc())
    return {"total": repo.count(*filters), "note": "potential_revenue is an estimate, not revenue",
            "opportunities": [{"id": str(o.id), "type": o.type.value, "title": o.title, "reason": o.reason,
                               "potential_revenue": _money(o.potential_revenue), "priority": o.priority.value,
                               "due_date": o.due_date.isoformat() if o.due_date else None} for o in rows]}


@tool("revenue_summary", "Collected, recovered, outstanding, potential and forecast revenue for a period.",
      PeriodArgs, STAFF, feature="basic_reports")
def revenue_summary(ctx: AgentContext, args: PeriodArgs) -> dict:
    return metrics.revenue(ctx.db, *_period(args.days))


class DraftArgs(BaseModel):
    opportunity_id: uuid.UUID


@tool("draft_recovery_message", "Draft a personalised renewal/payment reminder for an opportunity (not sent).",
      DraftArgs, STAFF, feature="recovery_center")
def draft_recovery_message(ctx: AgentContext, args: DraftArgs) -> dict:
    from app.modules.recovery.service import renewal_message

    opp = TenantRepository(RecoveryOpportunity, ctx.db).get(args.opportunity_id)
    if opp is None:
        return {"error": "Opportunity not found"}
    gym = ctx.db.get(Gym, ctx.gym_id)
    member = ctx.db.get(Member, opp.member_id) if opp.member_id else None
    if opp.membership_id and member:
        ms = ctx.db.get(Membership, opp.membership_id)
        return {"draft": renewal_message(gym, member, ms, float(opp.potential_revenue)), "sent": False}
    if opp.payment_id and member:
        p = ctx.db.get(Payment, opp.payment_id)
        return {"draft": f"Hi {member.full_name.split()[0]}, a payment of {gym.currency} {float(p.amount):,.0f} is "
                         f"pending at {gym.name}. You can pay at the desk or reply for a payment link.", "sent": False}
    lead = ctx.db.get(Lead, opp.lead_id) if opp.lead_id else None
    return {"draft": f"Hi {lead.name.split()[0] if lead else ''}, this is {gym.name}. Would you like to book your "
                     "free trial this week?", "sent": False}


# ================================================================ SEO / local / AI search

@tool("seo_status", "Latest website SEO audit: score, issue counts, top issues.", NoArgs, STAFF, feature="seo_audit")
def seo_status(ctx: AgentContext, _: NoArgs) -> dict:
    audit = TenantRepository(SeoAudit, ctx.db).first(SeoAudit.status == AuditStatus.COMPLETED,
                                                    order_by=SeoAudit.finished_at.desc())
    if audit is None:
        return {"audited": False}
    findings = TenantRepository(SeoFinding, ctx.db).list(SeoFinding.audit_id == audit.id, limit=500)
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    top = sorted(findings, key=lambda f: order[f.severity.value])[:8]
    return {"audited": True, "url": audit.url, "score": audit.score, "data_source": audit.data_source,
            "finished_at": audit.finished_at.isoformat() if audit.finished_at else None,
            "counts": (audit.summary or {}).get("counts"), "comparison": (audit.summary or {}).get("comparison"),
            "top_issues": [{"title": f.title, "severity": f.severity.value, "page": f.page_url, "evidence": f.evidence}
                           for f in top]}


class AuditArgs(BaseModel):
    url: str = Field(description="Website URL to audit")


@tool("run_seo_audit", "Start a new website SEO audit (requires confirmation).", AuditArgs, STAFF,
      feature="seo_audit", consequential=True, summarize=lambda a: f"Run an SEO audit of {a.url}")
def run_seo_audit(ctx: AgentContext, args: AuditArgs) -> dict:
    from app.modules.seo import service as seo

    audit = seo.start_audit(ctx.db, args.url, ctx.user)
    seo.run_audit(audit.id, ctx.gym_id)
    ctx.db.expire_all()
    audit = TenantRepository(SeoAudit, ctx.db).get(audit.id)
    return {"audit_id": str(audit.id), "status": audit.status.value, "score": audit.score}


@tool("local_visibility", "Google Business Profile connection, completeness, reviews and local opportunities.",
      NoArgs, STAFF, feature="local_seo")
def local_visibility(ctx: AgentContext, _: NoArgs) -> dict:
    acq = metrics.acquisition(ctx.db, *_period(30))
    return {"google_business_profile": acq["google_business_profile"], "lead_sources_30d": acq["lead_sources"]}


@tool("reviews_needing_reply", "Reviews without a published reply.", NoArgs, STAFF, feature="local_seo")
def reviews_needing_reply(ctx: AgentContext, _: NoArgs) -> dict:
    rows = TenantRepository(Review, ctx.db).list(Review.reply_status.in_([ReplyStatus.NONE, ReplyStatus.DRAFTED]),
                                                 limit=20, order_by=Review.review_date.desc())
    return {"count": len(rows), "reviews": [{"id": str(r.id), "author": r.author, "rating": r.rating,
                                             "text": (r.text or "")[:300], "source": r.source} for r in rows]}


class PostArgs(BaseModel):
    kind: str = Field("update", description="update | offer | event | service")
    details: str | None = Field(None, max_length=500)


@tool("draft_profile_post", "Draft a Google Business Profile post for owner review (not published).", PostArgs,
      STAFF, feature="local_seo")
def draft_profile_post(ctx: AgentContext, args: PostArgs) -> dict:
    post, by, warnings = content.profile_post(ctx.db, args.kind, args.details)
    return {**post, "generated_by": by, "warnings": warnings, "published": False}


@tool("ai_search_readiness", "Latest AI-search readiness checklist result and gaps.", NoArgs, STAFF,
      feature="ai_search_readiness")
def ai_search_readiness(ctx: AgentContext, _: NoArgs) -> dict:
    from app.database.models import AiReadinessCheck

    row = TenantRepository(AiReadinessCheck, ctx.db).first(order_by=AiReadinessCheck.created_at.desc())
    if row is None:
        return {"checked": False}
    return {"checked": True, "score": row.score, "note": "GymFlow checklist score, not an AI provider ranking",
            "gaps": row.content_gaps, "inconsistencies": row.inconsistencies}


class SchemaArgs(BaseModel):
    kind: str = Field("local_business", description="local_business | organization | website | faq | services")


@tool("generate_structured_data", "Generate and validate JSON-LD from the approved profile (draft only).",
      SchemaArgs, STAFF, feature="ai_search_readiness")
def generate_structured_data(ctx: AgentContext, args: SchemaArgs) -> dict:
    from app.modules.ai_search.service import generate_schema, validate_schema

    data = generate_schema(ctx.db, args.kind)
    return {"json_ld": data, "validation": validate_schema(ctx.db, data), "published": False}


class FaqArgs(BaseModel):
    topic: str | None = None


@tool("draft_faqs", "Draft FAQs from approved gym information (owner must approve before use).", FaqArgs, STAFF,
      feature="ai_search_readiness")
def draft_faqs(ctx: AgentContext, args: FaqArgs) -> dict:
    faqs, by, warnings = content.generate_faqs(ctx.db, args.topic)
    return {"faqs": faqs, "generated_by": by, "warnings": warnings, "approved": False}


# ================================================================ Business analyst

@tool("business_overview", "Members, leads, trials, memberships, revenue and renewals for a period.", PeriodArgs,
      STAFF, feature="basic_reports")
def business_overview(ctx: AgentContext, args: PeriodArgs) -> dict:
    return metrics.business_overview(ctx.db, *_period(args.days))


@tool("lead_analytics", "Enquiries, conversion, sources (with collected revenue), staff performance, response time.",
      PeriodArgs, STAFF, feature="lead_crm")
def lead_analytics(ctx: AgentContext, args: PeriodArgs) -> dict:
    return metrics.lead_analytics(ctx.db, *_period(args.days))


@tool("todays_actions", "Prioritised actions for today, each linked to records.", NoArgs, STAFF,
      feature="basic_reports")
def todays_actions(ctx: AgentContext, _: NoArgs) -> dict:
    return {"actions": metrics.todays_actions(ctx.db)}


@tool("recommendations", "Evidence-backed growth recommendations from current data.", NoArgs, STAFF,
      feature="basic_reports")
def recommendations(ctx: AgentContext, _: NoArgs) -> dict:
    return {"recommendations": insights.recommendations(ctx.db)}


class ReportArgs(BaseModel):
    kind: str = Field("weekly_revenue", description="daily_growth | weekly_revenue | lead_conversion | renewals | "
                                                    "seo_progress | local_visibility | revenue_recovery")


@tool("generate_report", "Generate and save a report from current data.", ReportArgs, STAFF, feature="basic_reports")
def generate_report(ctx: AgentContext, args: ReportArgs) -> dict:
    from app.modules.growth.reports import build_report

    report = build_report(ctx.db, args.kind, generated_by="agent")
    return {"report_id": str(report.id), "title": report.title}


# ================================================================ agent definitions

ANALYST_READ = ["business_overview", "revenue_summary", "lead_analytics", "trial_stats", "todays_actions",
                "recommendations", "list_expiring_memberships", "list_recovery_opportunities",
                "leads_to_follow_up_today", "seo_status", "local_visibility", "ai_search_readiness"]

define(AgentSpec("seo_growth", "SEO Growth Agent", "Audits the website and suggests on-page improvements.",
                 ["seo_status", "run_seo_audit", "generate_report"], "seo_audit"))
define(AgentSpec("local_seo", "Google Maps & Local SEO Agent",
                 "Business Profile completeness, reviews and local content drafts.",
                 ["local_visibility", "reviews_needing_reply", "draft_profile_post", "get_gym_info"], "local_seo"))
define(AgentSpec("ai_search", "AI Search Visibility Agent",
                 "Entity clarity, structured data and AI-search readiness.",
                 ["ai_search_readiness", "generate_structured_data", "draft_faqs", "get_gym_info"],
                 "ai_search_readiness"))
define(AgentSpec("lead_conversion", "Lead Conversion Agent",
                 "Answers prospects from approved information, qualifies them and books trials.",
                 ["get_gym_info", "list_membership_plans", "find_trial_slots", "save_lead_details", "book_trial",
                  "escalate_to_staff"], "ai_sales_agent", public=True))
define(AgentSpec("crm_follow_up", "CRM & Follow-Up Agent", "Finds leads to contact and creates follow-ups.",
                 ["list_leads", "leads_to_follow_up_today", "create_follow_up_task", "send_message_to_lead",
                  "lead_analytics"], "lead_crm"))
define(AgentSpec("trial_conversion", "Trial Conversion Agent", "Trial schedule, attendance and conversion.",
                 ["trial_stats", "list_upcoming_trials", "find_trial_slots", "create_follow_up_task"], "trials"))
define(AgentSpec("recovery", "Renewal & Revenue Recovery Agent",
                 "Expiring memberships, dues and recovery follow-ups.",
                 ["list_expiring_memberships", "list_recovery_opportunities", "revenue_summary",
                  "draft_recovery_message", "create_follow_up_task", "send_message_to_lead"], "recovery_center"))
define(AgentSpec("business_analyst", "Gym Business Analyst Agent",
                 "Analyses all gym data and recommends revenue actions.",
                 sorted(set(ANALYST_READ + ["create_follow_up_task", "generate_report", "draft_recovery_message",
                                            "send_message_to_lead", "run_seo_audit", "draft_profile_post"])),
                 "business_analyst"))

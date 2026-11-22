"""Growth Dashboard, analytics, reports and the Workflow Center."""
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import entitlements
from app.core.entitlements import gym_feature
from app.core.permissions import GYM_STAFF, tenant_user
from app.core.tenant_context import get_current_gym_id
from app.database.models import (
    Attendance, EventLog, Gym, GrowthReport, IntegrationConnection, Lead, Member, MembershipPlan, RecoveryOpportunity,
    SubscriptionPlan, Trainer, User, Website,
)
from app.database.models.enums import OPEN_OPPORTUNITY_STATUSES, ConnectionStatus, LeadStatus, Role
from app.modules.recovery import service as recovery_service
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import get_or_404
from app.modules.growth import insights, metrics, reports

router = APIRouter(prefix="/growth", tags=["Growth dashboard & intelligence"])
staff = tenant_user(*GYM_STAFF)


def _range(days: int | None) -> tuple[date, date]:
    if days:
        today = date.today()
        return today - timedelta(days=days - 1), today
    return metrics.month_range()


def _subscription(db: Session) -> dict:
    ent = entitlements.resolve(db)
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == ent.plan_code)) if ent.plan_code else None
    return {"plan_name": ent.plan_name, "status": ent.status,
            "price_monthly": float(plan.price_monthly) if plan else None}


def _setup(db: Session, gym: Gym) -> list[dict]:
    """Owner onboarding checklist - each step is derived from real data, never ticked by hand."""
    wa = TenantRepository(IntegrationConnection, db).first(IntegrationConnection.provider == "whatsapp")
    return [
        {"key": "profile", "label": "Add your gym's phone and address", "done": bool(gym.phone and gym.address),
         "href": "/dashboard/settings"},
        {"key": "plans", "label": "Set your membership plans and prices",
         "done": TenantRepository(MembershipPlan, db).count() > 0, "href": "/dashboard/memberships"},
        {"key": "members", "label": "Add or import your members", "done": TenantRepository(Member, db).count() > 0,
         "href": "/dashboard/members"},
        {"key": "staff", "label": "Add your trainers and front-desk staff",
         "done": TenantRepository(Trainer, db).count() > 0, "href": "/dashboard/trainers"},
        {"key": "whatsapp", "label": "Connect WhatsApp for automatic reminders",
         "done": bool(wa and wa.status == ConnectionStatus.CONNECTED), "href": "/dashboard/integrations?tab=whatsapp"},
        {"key": "website", "label": "Publish your gym website",
         "done": TenantRepository(Website, db).count(Website.is_published.is_(True)) > 0,
         "href": "/dashboard/website-builder"},
    ]


@router.get("/dashboard")
def dashboard(days: int | None = Query(None, ge=1, le=366), db: Session = Depends(get_db),
              user: User = Depends(staff)):
    start, end = _range(days)
    gym = db.get(Gym, get_current_gym_id())
    la = metrics.lead_analytics(db, start, end)
    ta = metrics.trial_analytics(db, start, end)
    lo = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    due = recovery_service.due_list(db)
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "gym": {"name": gym.name, "currency": gym.currency, "is_demo": bool((gym.settings or {}).get("is_demo"))},
        "owner_name": user.full_name,
        "subscription": _subscription(db),
        "setup": _setup(db, gym),
        "money": {"due_total": due["total"], "due_count": due["count"], "buckets": due["buckets"]},
        "checkins": TenantRepository(Attendance, db).count(Attendance.check_in_at >= lo, Attendance.check_in_at < hi),
        "business": metrics.business_overview(db, start, end),
        "acquisition": metrics.acquisition(db, start, end),
        "sales": {"new_leads": la["new"], "total_enquiries": la["total_enquiries"], "contacted": la["contacted"],
                  "uncontacted": la["uncontacted_now"], "overdue_follow_ups": la["overdue_follow_ups"],
                  "upcoming_trials": ta["upcoming"], "trial_conversion": ta["trial_to_membership"],
                  "conversion_rate": la["conversion_rate"], "avg_first_response_minutes": la["avg_first_response_minutes"]},
        "recovery": metrics.recovery_overview(db),
        "revenue_series": metrics.revenue_series(db, 6),
        "actions": metrics.todays_actions(db),
        "recommendations": insights.recommendations(db)[:6],
    }


@router.get("/owner-report")
def owner_report_view(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), db: Session = Depends(get_db),
                      _=Depends(gym_feature("basic_reports", *GYM_STAFF))):
    """Last month's (or ``month``'s) owner summary, with WhatsApp-ready text."""
    from app.modules.growth import owner_report

    return owner_report.build(db, month)


@router.post("/owner-report/email")
def owner_report_email(month: str | None = Query(None, pattern=r"^\d{4}-\d{2}$"), db: Session = Depends(get_db),
                       _=Depends(tenant_user(Role.GYM_OWNER))):
    from app.modules.growth import owner_report
    from app.services import email

    if not email.is_configured():
        return {"sent": 0, "detail": "Email isn't set up yet. Share it on WhatsApp instead."}
    return {"sent": owner_report.email_owners(db, owner_report.build(db, month))}


@router.get("/badges")
def badges(db: Session = Depends(get_db), _=Depends(staff)):
    """Small counts for the navigation: people who owe money, enquiries nobody has replied to."""
    due = TenantRepository(RecoveryOpportunity, db).count(
        RecoveryOpportunity.type.in_(recovery_service.MONEY_TYPES),
        RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES))
    unreplied = TenantRepository(Lead, db).count(Lead.status == LeadStatus.NEW, Lead.first_response_at.is_(None))
    return {"money": due, "enquiries": unreplied}


@router.get("/actions")
def actions(db: Session = Depends(get_db), _=Depends(staff)):
    return metrics.todays_actions(db)


@router.get("/recommendations")
def recs(db: Session = Depends(get_db), _=Depends(staff)):
    return insights.recommendations(db)


@router.get("/revenue")
def revenue(days: int | None = Query(None, ge=1, le=730), months: int = Query(6, ge=1, le=24),
            db: Session = Depends(get_db), _=Depends(gym_feature("basic_reports", *GYM_STAFF))):
    start, end = _range(days)
    la = metrics.lead_analytics(db, start - timedelta(days=60), end)
    return {"summary": metrics.revenue(db, start, end), "series": metrics.revenue_series(db, months),
            "by_lead_source": {k: v["revenue_collected"] for k, v in la["by_source"].items()},
            "renewal_rate": metrics.renewal_rate(db)}


@router.get("/analytics/leads")
def lead_analytics(days: int = Query(30, ge=1, le=730), db: Session = Depends(get_db), _=Depends(staff)):
    return metrics.lead_analytics(db, *_range(days))


@router.get("/analytics/trials")
def trial_analytics(days: int = Query(30, ge=1, le=730), db: Session = Depends(get_db), _=Depends(staff)):
    return metrics.trial_analytics(db, *_range(days))


# ---------------------------------------------------------------- reports

class ReportIn(BaseModel):
    kind: str


@router.get("/reports")
def list_reports(kind: str | None = None, db: Session = Depends(get_db), _=Depends(staff)):
    f = [GrowthReport.kind == kind] if kind else []
    return [{"id": str(r.id), "kind": r.kind, "title": r.title, "generated_by": r.generated_by,
             "period_start": r.period_start, "period_end": r.period_end, "created_at": r.created_at}
            for r in TenantRepository(GrowthReport, db).list(*f, limit=100)]


@router.post("/reports")
def create_report(data: ReportIn, db: Session = Depends(get_db), _=Depends(gym_feature("basic_reports", *GYM_STAFF))):
    if data.kind not in reports.KINDS:
        raise HTTPException(404, "Unknown report type")
    if data.kind in ("seo_progress", "monthly_seo") and not entitlements.resolve(db).has("advanced_seo"):
        raise HTTPException(402, "Advanced SEO reports need the Pro plan")
    r = reports.build_report(db, data.kind)
    return {"id": str(r.id), "title": r.title, "content": r.content}


@router.get("/reports/kinds")
def kinds(_=Depends(staff)):
    return reports.KINDS


@router.get("/reports/{report_id}")
def get_report(report_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    r = get_or_404(TenantRepository(GrowthReport, db), report_id, "Report")
    return {"id": str(r.id), "kind": r.kind, "title": r.title, "period_start": r.period_start,
            "period_end": r.period_end, "content": r.content, "generated_by": r.generated_by, "created_at": r.created_at}


# ---------------------------------------------------------------- workflow center

WORKFLOWS = [
    {"key": "website_enquiry", "name": "Website enquiry", "trigger": "Enquiry form / chat / landing page",
     "steps": ["Validate", "Duplicate check", "Create or merge lead", "Attribute source", "Score", "Follow-up task",
               "Notify"], "events": ["lead.created", "lead.duplicate_merged"]},
    {"key": "ai_sales_conversation", "name": "AI sales conversation", "trigger": "Website chat / WhatsApp message",
     "steps": ["Identify gym", "Load approved knowledge", "Reply or escalate", "Update CRM"],
     "events": ["lead.created", "trial.booked"]},
    {"key": "trial_booking", "name": "Trial booking", "trigger": "Agent, website, CRM or staff",
     "steps": ["Check availability", "Reserve slot", "Update lead", "Confirmation", "Reminder"], "events": ["trial.booked"]},
    {"key": "trial_no_show", "name": "Trial no-show", "trigger": "Daily job + staff confirmation",
     "steps": ["Flag unrecorded attendance", "Staff confirms", "Recovery opportunity", "Draft follow-up"],
     "events": ["trial.no_show"]},
    {"key": "membership_expiry", "name": "Membership expiry", "trigger": "Daily job",
     "steps": ["Find expiries (30/15/7/0/after)", "Renewal opportunity", "Staff task with draft", "Track payment"],
     "events": ["worker.growth_daily", "recovery.won"]},
    {"key": "payment_recovery", "name": "Payment recovery", "trigger": "Daily job + payment webhooks",
     "steps": ["Overdue/failed payment", "Opportunity", "Reminder", "Verified payment", "Close once"],
     "events": ["payment.failed", "payment.paid", "recovery.won"]},
    {"key": "seo_audit", "name": "SEO audit", "trigger": "Owner request",
     "steps": ["Validate URL (SSRF-safe)", "Crawl (robots.txt)", "Findings", "Suggestions", "Owner approves"],
     "events": ["seo.audit_completed", "seo.suggestion_approved"]},
    {"key": "review_reply", "name": "Google review reply", "trigger": "Review sync",
     "steps": ["Store review", "Sentiment", "Draft", "Owner approves", "Publish via API or copy"],
     "events": ["review.reply_approved"]},
    {"key": "daily_analysis", "name": "Daily business analysis", "trigger": "Daily job",
     "steps": ["KPIs", "Opportunities", "Recommendations", "Daily report"], "events": ["report.generated"]},
]


@router.get("/workflows")
def workflows(db: Session = Depends(get_db), _=Depends(staff)):
    since = datetime.now(timezone.utc) - timedelta(days=30)
    rows = TenantRepository(EventLog, db).list(EventLog.created_at >= since, limit=50_000)
    counts = Counter(r.event_type for r in rows)
    last = {}
    for r in sorted(rows, key=lambda r: r.created_at):
        last[r.event_type] = r.created_at.isoformat()
    daily = TenantRepository(EventLog, db).first(EventLog.event_type == "worker.growth_daily",
                                                order_by=EventLog.created_at.desc())
    return {"workflows": [{**w, "runs_30d": {e: counts.get(e, 0) for e in w["events"]},
                           "last_event_at": max((last[e] for e in w["events"] if e in last), default=None)}
                          for w in WORKFLOWS],
            "daily_job": {"last_run_at": daily.created_at.isoformat() if daily else None,
                          "last_result": daily.payload if daily else None},
            "recent_events": [{"type": r.event_type, "actor": r.actor, "entity_type": r.entity_type,
                               "at": r.created_at.isoformat()} for r in sorted(rows, key=lambda r: r.created_at,
                                                                              reverse=True)[:40]]}


@router.post("/workflows/daily/run")
def run_daily(db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER, Role.GYM_MANAGER))):
    from app.workers.growth_worker import run_for_gym

    return run_for_gym(db, db.get(Gym, get_current_gym_id()))


@router.post("/demo/reset")
def reset_own_demo(db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    """Demo owners can restore the demo data. Refused for every real gym."""
    from app.demo import ironcore

    gym = db.get(Gym, get_current_gym_id())
    if not (gym.settings or {}).get("is_demo") or gym.slug != ironcore.DEMO_SLUG:
        raise HTTPException(403, "Only the demo gym can be reset")
    return ironcore.reset(db)

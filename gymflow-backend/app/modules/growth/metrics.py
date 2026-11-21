"""Deterministic KPIs computed from database records only.

Used by the Growth Dashboard, analytics pages, reports and the AI Business Analyst - so every number
the AI quotes comes from here, never from the model.

Revenue categories are kept strictly apart:
  collected  = PAID payments (paid_at in period)
  recovered  = WON recovery opportunities, each backed by exactly one PAID payment (subset of collected)
  outstanding= unpaid (pending / overdue / failed) payment records right now
  potential  = estimated value of open recovery opportunities (NOT revenue)
  forecast   = unpaid payments due in the next 30 days + open renewals x historical renewal rate
"""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import (
    AiReadinessCheck, BusinessProfileSnapshot, FollowUpTask, Gym, IntegrationConnection, Lead, Member, Membership,
    Payment, RecoveryOpportunity, Review, SearchPerformance, SeoAudit, SeoFinding, TrialBooking, User,
)
from app.database.models.enums import (
    OPEN_LEAD_STATUSES, OPEN_OPPORTUNITY_STATUSES, AuditStatus, ConnectionStatus, FindingStatus, LeadStatus, MembershipStatus,
    MemberStatus, OpportunityStatus, OpportunityType, PaymentStatus, ReplyStatus, Severity, TaskStatus, TrialStatus,
)
from app.database.repositories.base import TenantRepository

UNPAID = (PaymentStatus.PENDING, PaymentStatus.OVERDUE, PaymentStatus.FAILED)
WEBSITE_SOURCES = ("website", "website_chat", "seo_landing_page", "organic_search", "ai_search",
                   "google_business_profile")


def start_of(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def month_range(today: date | None = None) -> tuple[date, date]:
    today = today or date.today()
    return today.replace(day=1), today


def _sum(db: Session, model, column, *where) -> float:
    stmt = select(func.coalesce(func.sum(column), 0)).select_from(model).where(
        model.gym_id == get_current_gym_id(), *where)
    return round(float(db.scalar(stmt) or 0), 2)


def _count(db: Session, model, *where) -> int:
    return TenantRepository(model, db).count(*where)


# ---------------------------------------------------------------- revenue

def revenue(db: Session, start: date, end: date) -> dict:
    lo, hi = start_of(start), start_of(end + timedelta(days=1))
    today = date.today()
    collected = _sum(db, Payment, Payment.amount, Payment.status == PaymentStatus.PAID, Payment.paid_at >= lo,
                     Payment.paid_at < hi)
    recovered = _sum(db, RecoveryOpportunity, RecoveryOpportunity.recovered_revenue,
                     RecoveryOpportunity.status == OpportunityStatus.WON, RecoveryOpportunity.closed_at >= lo,
                     RecoveryOpportunity.closed_at < hi, RecoveryOpportunity.recovered_payment_id.is_not(None))
    outstanding = _sum(db, Payment, Payment.amount, Payment.status.in_(UNPAID))
    outstanding_count = _count(db, Payment, Payment.status.in_(UNPAID))
    overdue = _sum(db, Payment, Payment.amount, Payment.status.in_(UNPAID), Payment.due_date < today)
    potential_by_type = {}
    for t in OpportunityType:
        v = _sum(db, RecoveryOpportunity, RecoveryOpportunity.potential_revenue, RecoveryOpportunity.type == t,
                 RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES))
        if v:
            potential_by_type[t.value] = v
    due_soon = _sum(db, Payment, Payment.amount, Payment.status.in_(UNPAID), Payment.due_date >= today,
                    Payment.due_date <= today + timedelta(days=30))
    renewal_potential = potential_by_type.get("upcoming_renewal", 0)
    rate = renewal_rate(db)
    forecast = round(due_soon + (renewal_potential * rate["rate"] if rate["rate"] is not None else 0), 2)
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "collected": collected, "payments_collected": _count(db, Payment, Payment.status == PaymentStatus.PAID,
                                                             Payment.paid_at >= lo, Payment.paid_at < hi),
        "recovered": recovered, "outstanding": outstanding, "outstanding_count": outstanding_count,
        "overdue": overdue, "potential": round(sum(potential_by_type.values()), 2),
        "potential_by_type": potential_by_type,
        "forecast_next_30_days": forecast,
        "forecast_basis": {"unpaid_due_next_30_days": due_soon, "open_renewal_value": renewal_potential,
                           "historical_renewal_rate": rate},
        "definitions": {
            "collected": "Payments marked paid in the period (staff-recorded or verified by the payment gateway).",
            "recovered": "Part of collected revenue that closed a recovery opportunity; each payment counted once.",
            "outstanding": "Unpaid payment records today (pending, overdue or failed).",
            "potential": "Estimated value of open opportunities. Not revenue.",
            "forecast": "Unpaid amounts due in 30 days plus open renewals x past renewal rate. An estimate.",
        },
    }


def renewal_rate(db: Session, days: int = 120) -> dict:
    since = start_of(date.today() - timedelta(days=days))
    closed = TenantRepository(RecoveryOpportunity, db).list(
        RecoveryOpportunity.type.in_([OpportunityType.UPCOMING_RENEWAL, OpportunityType.EXPIRED_MEMBERSHIP]),
        RecoveryOpportunity.status.in_([OpportunityStatus.WON, OpportunityStatus.LOST, OpportunityStatus.DISMISSED]),
        RecoveryOpportunity.closed_at >= since, limit=10_000)
    won = sum(1 for o in closed if o.status == OpportunityStatus.WON)
    if len(closed) < 5:
        return {"rate": None, "won": won, "closed": len(closed), "note": "Not enough history (need 5+ closed renewals)"}
    return {"rate": round(won / len(closed), 2), "won": won, "closed": len(closed), "note": f"Last {days} days"}


def revenue_series(db: Session, months: int = 6) -> list[dict]:
    first = date.today().replace(day=1)
    for _ in range(months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    collected, recovered = defaultdict(float), defaultdict(float)
    for p in TenantRepository(Payment, db).list(Payment.status == PaymentStatus.PAID, Payment.paid_at >= start_of(first),
                                                limit=1_000_000):
        collected[p.paid_at.strftime("%Y-%m")] += float(p.amount)
    for o in TenantRepository(RecoveryOpportunity, db).list(RecoveryOpportunity.status == OpportunityStatus.WON,
                                                            RecoveryOpportunity.closed_at >= start_of(first),
                                                            limit=100_000):
        recovered[o.closed_at.strftime("%Y-%m")] += float(o.recovered_revenue)
    out, cursor = [], first
    for _ in range(months):
        key = cursor.strftime("%Y-%m")
        out.append({"month": key, "collected": round(collected[key], 2), "recovered": round(recovered[key], 2)})
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return out


# ---------------------------------------------------------------- leads

def lead_analytics(db: Session, start: date, end: date) -> dict:
    lo, hi = start_of(start), start_of(end + timedelta(days=1))
    now = datetime.now(timezone.utc)
    leads = TenantRepository(Lead, db).list(Lead.created_at >= lo, Lead.created_at < hi, limit=100_000)
    status = Counter(l.status.value for l in leads)
    joined = [l for l in leads if l.status == LeadStatus.CONVERTED]
    response_minutes = [(_aware(l.first_response_at) - _aware(l.created_at)).total_seconds() / 60
                        for l in leads if l.first_response_at]
    member_ids = [l.converted_member_id for l in joined if l.converted_member_id]
    paid_by_member: dict = defaultdict(float)
    if member_ids:
        for p in TenantRepository(Payment, db).list(Payment.member_id.in_(member_ids),
                                                    Payment.status == PaymentStatus.PAID, limit=100_000):
            paid_by_member[p.member_id] += float(p.amount)
    by_source: dict = defaultdict(lambda: {"leads": 0, "trials": 0, "joined": 0, "revenue_collected": 0.0})
    trial_leads = {t.lead_id for t in TenantRepository(TrialBooking, db).list(
        TrialBooking.lead_id.in_([l.id for l in leads]), limit=100_000)} if leads else set()
    for l in leads:
        row = by_source[l.source]
        row["leads"] += 1
        row["trials"] += int(l.id in trial_leads)
        if l.status == LeadStatus.CONVERTED:
            row["joined"] += 1
            row["revenue_collected"] += paid_by_member.get(l.converted_member_id, 0)
    for row in by_source.values():
        row["conversion_rate"] = round(row["joined"] / row["leads"], 3) if row["leads"] else 0
        row["revenue_collected"] = round(row["revenue_collected"], 2)
    users = {u.id: u.full_name for u in db.scalars(select(User).where(User.gym_id == get_current_gym_id())).all()}
    by_staff: dict = defaultdict(lambda: {"assigned": 0, "contacted": 0, "joined": 0})
    for l in leads:
        name = users.get(l.assigned_to_id, "Unassigned")
        by_staff[name]["assigned"] += 1
        by_staff[name]["contacted"] += int(l.first_response_at is not None or l.last_contacted_at is not None)
        by_staff[name]["joined"] += int(l.status == LeadStatus.CONVERTED)
    open_all = TenantRepository(Lead, db)
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "total_enquiries": len(leads),
        "by_status": dict(status),
        "new": status.get("new", 0),
        "contacted": sum(1 for l in leads if l.last_contacted_at or l.status not in (LeadStatus.NEW,)),
        "uncontacted_now": open_all.count(Lead.status == LeadStatus.NEW, Lead.first_response_at.is_(None)),
        "overdue_follow_ups": _count(db, FollowUpTask, FollowUpTask.status == TaskStatus.OPEN,
                                     FollowUpTask.lead_id.is_not(None), FollowUpTask.due_at < now),
        "qualified": sum(1 for l in leads if l.score >= 50 or l.status in (
            LeadStatus.INTERESTED, LeadStatus.TRIAL_BOOKED, LeadStatus.TRIAL_ATTENDED, LeadStatus.NEGOTIATION,
            LeadStatus.CONVERTED)),
        "trials_booked": len(trial_leads),
        "joined": len(joined), "lost": status.get("lost", 0),
        "conversion_rate": round(len(joined) / len(leads), 3) if leads else 0,
        "avg_first_response_minutes": round(sum(response_minutes) / len(response_minutes), 1)
        if response_minutes else None,
        "by_source": dict(by_source),
        "by_staff": dict(by_staff),
        "lost_reasons": dict(Counter(l.lost_reason for l in leads if l.status == LeadStatus.LOST and l.lost_reason)),
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# ---------------------------------------------------------------- trials

def trial_analytics(db: Session, start: date, end: date) -> dict:
    lo, hi = start_of(start), start_of(end + timedelta(days=1))
    now = datetime.now(timezone.utc)
    trials = TenantRepository(TrialBooking, db).list(TrialBooking.starts_at >= lo, TrialBooking.starts_at < hi,
                                                     limit=100_000)
    s = Counter(t.status.value for t in trials)
    past = [t for t in trials if _aware(t.starts_at) < now and t.status != TrialStatus.CANCELLED]
    attended = s.get("attended", 0)
    converted = sum(1 for t in trials if t.converted_membership_id)
    leads = {l.id: l for l in TenantRepository(Lead, db).list(Lead.id.in_([t.lead_id for t in trials]),
                                                              limit=100_000)} if trials else {}
    by_source = Counter(leads[t.lead_id].source for t in trials if t.lead_id in leads)
    lost_reasons = Counter(leads[t.lead_id].lost_reason for t in trials
                           if t.lead_id in leads and leads[t.lead_id].status == LeadStatus.LOST
                           and leads[t.lead_id].lost_reason)
    return {
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "total": len(trials), "by_status": dict(s),
        "upcoming": _count(db, TrialBooking, TrialBooking.status == TrialStatus.BOOKED, TrialBooking.starts_at >= now),
        "completed": attended, "no_shows": s.get("no_show", 0), "cancellations": s.get("cancelled", 0),
        "pending_attendance_review": _count(db, TrialBooking, TrialBooking.status == TrialStatus.PENDING_REVIEW),
        "attendance_rate": round(attended / len(past), 3) if past else None,
        "trial_to_membership": round(converted / attended, 3) if attended else None,
        "converted": converted, "by_source": dict(by_source), "lost_reasons": dict(lost_reasons),
    }


# ---------------------------------------------------------------- acquisition / visibility

def acquisition(db: Session, start: date, end: date) -> dict:
    lo, hi = start_of(start), start_of(end + timedelta(days=1))
    audit = TenantRepository(SeoAudit, db).first(SeoAudit.status == AuditStatus.COMPLETED,
                                                order_by=SeoAudit.finished_at.desc())
    critical = _count(db, SeoFinding, SeoFinding.audit_id == audit.id,
                      SeoFinding.severity.in_([Severity.CRITICAL, Severity.HIGH])) if audit else 0
    conns = {c.provider: c for c in TenantRepository(IntegrationConnection, db).list(limit=20)}
    gbp, gsc = conns.get("google_business_profile"), conns.get("google_search_console")
    snap = TenantRepository(BusinessProfileSnapshot, db).first(order_by=BusinessProfileSnapshot.fetched_at.desc())
    ready = TenantRepository(AiReadinessCheck, db).first(order_by=AiReadinessCheck.created_at.desc())
    leads = TenantRepository(Lead, db).list(Lead.created_at >= lo, Lead.created_at < hi, limit=100_000)
    search = None
    if gsc and gsc.status == ConnectionStatus.CONNECTED:
        rows = TenantRepository(SearchPerformance, db).list(SearchPerformance.day >= date.today() - timedelta(days=30),
                                                            limit=200_000)
        clicks, impr = sum(r.clicks for r in rows), sum(r.impressions for r in rows)
        search = {"clicks": clicks, "impressions": impr, "ctr": round(clicks / impr, 4) if impr else None,
                  "source": "google_search_console", "days": 30}
    reviews = TenantRepository(Review, db)
    return {
        "website_seo": {"score": audit.score if audit else None, "audited_at": audit.finished_at.isoformat()
                        if audit and audit.finished_at else None, "serious_issues": critical,
                        "data_source": audit.data_source if audit else None, "audit_id": str(audit.id) if audit else None},
        "google_business_profile": {
            "connection": gbp.status.value if gbp else "not_connected",
            "completeness": snap.completeness if snap else None, "snapshot_source": snap.source if snap else None,
            "rating": (snap.data or {}).get("rating") if snap else None,
            "review_count": (snap.data or {}).get("review_count") if snap else None,
            "open_findings": len(snap.findings or []) if snap else 0,
            "reviews_awaiting_reply": reviews.count(Review.reply_status.in_([ReplyStatus.NONE, ReplyStatus.DRAFTED])),
        },
        "ai_search_readiness": {"score": ready.score if ready else None,
                                "checked_at": ready.created_at.isoformat() if ready else None,
                                "gaps": len(ready.content_gaps or []) if ready else None},
        "search_console": search or {"connection": gsc.status.value if gsc else "not_connected"},
        "website_enquiries": sum(1 for l in leads if l.source in WEBSITE_SOURCES),
        "lead_sources": dict(Counter(l.source for l in leads)),
    }


# ---------------------------------------------------------------- overview & actions

def business_overview(db: Session, start: date, end: date) -> dict:
    lo, hi = start_of(start), start_of(end + timedelta(days=1))
    today = date.today()
    now = datetime.now(timezone.utc)
    rev = revenue(db, start, end)
    return {
        "active_members": _count(db, Member, Member.status == MemberStatus.ACTIVE),
        "inactive_or_expired_members": _count(db, Member, Member.status != MemberStatus.ACTIVE),
        "new_leads": _count(db, Lead, Lead.created_at >= lo, Lead.created_at < hi),
        "trials_scheduled": _count(db, TrialBooking, TrialBooking.status == TrialStatus.BOOKED,
                                   TrialBooking.starts_at >= now),
        "new_memberships": _count(db, Membership, Membership.created_at >= lo, Membership.created_at < hi),
        "membership_revenue": rev["collected"],
        "outstanding": rev["outstanding"], "outstanding_count": rev["outstanding_count"],
        "upcoming_renewals_30d": _count(db, Membership, Membership.status == MembershipStatus.ACTIVE,
                                        Membership.end_date >= today, Membership.end_date <= today + timedelta(days=30)),
        "recovered_revenue": rev["recovered"],
        "currency": db.get(Gym, get_current_gym_id()).currency,
    }


def recovery_overview(db: Session) -> dict:
    opps = TenantRepository(RecoveryOpportunity, db).list(RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES),
                                                          limit=100_000)
    by_type = Counter(o.type.value for o in opps)
    today = date.today()
    month = month_range()
    return {
        "open_opportunities": len(opps), "by_type": dict(by_type),
        "expiring_7d": _count(db, Membership, Membership.status == MembershipStatus.ACTIVE, Membership.end_date >= today,
                              Membership.end_date <= today + timedelta(days=7)),
        "pending_payments": _count(db, Payment, Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.OVERDUE])),
        "failed_payments": _count(db, Payment, Payment.status == PaymentStatus.FAILED),
        "potential_value": round(sum(float(o.potential_revenue) for o in opps), 2),
        "recovered_this_month": revenue(db, *month)["recovered"],
    }


def todays_actions(db: Session) -> list[dict]:
    """Concrete actions for today. Each links to the records it is based on."""
    now = datetime.now(timezone.utc)
    today = date.today()
    actions = []

    def add(key, title, count, href, priority, detail):
        if count:
            actions.append({"key": key, "title": title, "count": count, "href": href, "priority": priority,
                            "detail": detail})

    uncontacted = _count(db, Lead, Lead.status == LeadStatus.NEW, Lead.first_response_at.is_(None))
    add("contact_new_leads", f"Reply to {uncontacted} new enquir{'y' if uncontacted == 1 else 'ies'}", uncontacted,
        "/dashboard/leads?status=new", "high", "Nobody has replied to them yet. Quick replies win more joins.")
    overdue = _count(db, FollowUpTask, FollowUpTask.status == TaskStatus.OPEN, FollowUpTask.due_at < now)
    add("overdue_tasks", f"Clear {overdue} overdue follow-up{'s' if overdue != 1 else ''}", overdue,
        "/dashboard/follow-ups?due=overdue", "high", "Calls and messages you planned that are now late.")
    review = _count(db, TrialBooking, TrialBooking.status == TrialStatus.PENDING_REVIEW)
    add("trial_attendance", f"Did {review} trial visitor{'s' if review != 1 else ''} show up? Mark it", review,
        "/dashboard/trials?tab=no-shows", "high", "Tell GymFlow who came, so it can follow up with the rest.")
    noshow = _count(db, RecoveryOpportunity, RecoveryOpportunity.type == OpportunityType.TRIAL_NO_SHOW,
                    RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES))
    add("no_shows", f"Follow up with {noshow} confirmed trial no-show{'s' if noshow != 1 else ''}", noshow,
        "/dashboard/recovery?tab=opportunities&type=trial_no_show", "medium", "They booked a trial but didn't come. Offer a new time.")
    trials_today = _count(db, TrialBooking, TrialBooking.status == TrialStatus.BOOKED,
                          TrialBooking.starts_at >= start_of(today), TrialBooking.starts_at < start_of(today + timedelta(days=1)))
    add("trials_today", f"{trials_today} trial{'s' if trials_today != 1 else ''} booked today", trials_today,
        "/dashboard/trials?view=day", "medium", "Make sure a trainer is ready for each visitor.")
    expiring = _count(db, RecoveryOpportunity, RecoveryOpportunity.type == OpportunityType.UPCOMING_RENEWAL,
                      RecoveryOpportunity.status == OpportunityStatus.OPEN, RecoveryOpportunity.due_date <= today + timedelta(days=7))
    add("renewals", f"{expiring} membership{'s' if expiring != 1 else ''} ending this week", expiring,
        "/dashboard/money", "high", "Remind them now so they renew before the last day.")
    overdue_pay = _count(db, Payment, Payment.status.in_([PaymentStatus.OVERDUE, PaymentStatus.FAILED]))
    add("payments", f"Collect {overdue_pay} late fee{'s' if overdue_pay != 1 else ''}", overdue_pay,
        "/dashboard/money", "high", "Fees past their due date, or online payments that didn't go through.")
    audit = TenantRepository(SeoAudit, db).first(SeoAudit.status == AuditStatus.COMPLETED,
                                                order_by=SeoAudit.finished_at.desc())
    if audit:
        crit = _count(db, SeoFinding, SeoFinding.audit_id == audit.id, SeoFinding.status == FindingStatus.OPEN,
                      SeoFinding.severity.in_([Severity.CRITICAL, Severity.HIGH]))
        add("seo_issues", f"Fix {crit} problem{'s' if crit != 1 else ''} that stop Google showing your website", crit,
            f"/dashboard/seo/audits/{audit.id}", "medium", f"Found when GymFlow checked {audit.url}.")
    pending_reviews = _count(db, Review, Review.reply_status.in_([ReplyStatus.NONE, ReplyStatus.DRAFTED]))
    add("reviews", f"Reply to {pending_reviews} Google review{'s' if pending_reviews != 1 else ''}", pending_reviews,
        "/dashboard/local/reviews", "low", "Replying to reviews helps you rank higher on Google Maps.")
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(actions, key=lambda a: order[a["priority"]])

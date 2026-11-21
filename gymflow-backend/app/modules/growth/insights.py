"""Evidence-backed recommendations (deterministic rules over real records).

Each recommendation carries the exact figures it is based on and a link to the records, so the owner
(and the AI Business Analyst, which only rephrases these) can always check the claim.
"""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.database.models import (
    AiReadinessCheck, IntegrationConnection, Lead, RecoveryOpportunity, SeoAudit, SeoFinding,
)
from app.database.models.enums import (
    OPEN_OPPORTUNITY_STATUSES, AuditStatus, ConnectionStatus, LeadStatus, OpportunityType,
)
from app.database.repositories.base import TenantRepository
from app.modules.growth import metrics


def _rec(rid, title, detail, priority, evidence, href, module):
    return {"id": rid, "title": title, "detail": detail, "priority": priority, "evidence": evidence,
            "href": href, "module": module}


def recommendations(db: Session, today: date | None = None) -> list[dict]:
    today = today or date.today()
    now = datetime.now(timezone.utc)
    start = today - timedelta(days=90)
    out: list[dict] = []
    leads = TenantRepository(Lead, db)

    uncontacted = leads.list(Lead.status == LeadStatus.NEW, Lead.first_response_at.is_(None), limit=1000,
                             order_by=Lead.created_at)
    if uncontacted:
        oldest = metrics._aware(uncontacted[0].created_at)
        hours = int((now - oldest).total_seconds() // 3600)
        out.append(_rec("uncontacted_leads", f"{len(uncontacted)} enquiries have no recorded response",
                        "Fast replies win trials. Contact these leads first, newest-intent first.", "high",
                        [{"label": "Uncontacted leads", "value": len(uncontacted)},
                         {"label": "Oldest waiting (hours)", "value": hours}],
                        "/dashboard/leads?status=new", "crm"))

    opps = TenantRepository(RecoveryOpportunity, db)
    expiring = opps.list(RecoveryOpportunity.type == OpportunityType.UPCOMING_RENEWAL,
                         RecoveryOpportunity.status.in_(OPEN_OPPORTUNITY_STATUSES),
                         RecoveryOpportunity.due_date <= today + timedelta(days=7), limit=1000)
    if expiring:
        untouched = [o for o in expiring if o.contact_count == 0]
        value = sum(float(o.potential_revenue) for o in expiring)
        out.append(_rec("expiring_no_follow_up",
                        f"{len(expiring)} memberships expire within about 7 days; {len(untouched)} have no renewal "
                        "follow-up recorded",
                        "Call or message these members today. The value below is an estimate, not revenue.", "high",
                        [{"label": "Expiring soon", "value": len(expiring)},
                         {"label": "Not contacted", "value": len(untouched)},
                         {"label": "Potential renewal value", "value": round(value, 2), "kind": "currency_estimate"}],
                        "/dashboard/recovery?tab=renewals", "recovery"))

    rev = metrics.revenue(db, today.replace(day=1), today)
    if rev["outstanding"] > 0:
        out.append(_rec("outstanding", f"{rev['outstanding_count']} unpaid fee records "
                        f"({rev['outstanding']:,.0f} outstanding)",
                        "Send reminders through the Recovery Center and record payments as they come in.",
                        "high" if rev["overdue"] else "medium",
                        [{"label": "Outstanding", "value": rev["outstanding"], "kind": "currency"},
                         {"label": "Of which overdue", "value": rev["overdue"], "kind": "currency"}],
                        "/dashboard/recovery?tab=outstanding", "recovery"))

    la = metrics.lead_analytics(db, start, today)
    for source, row in la["by_source"].items():
        if row["leads"] >= 10 and row["conversion_rate"] < 0.2:
            out.append(_rec(f"weak_source_{source}",
                            f"{source.replace('_', ' ').title()} brought {row['leads']} enquiries but only "
                            f"{row['joined']} joined",
                            "Review how these leads are followed up (speed, trial offer, message).", "medium",
                            [{"label": "Enquiries (90 days)", "value": row["leads"]},
                             {"label": "Joined", "value": row["joined"]},
                             {"label": "Conversion", "value": row["conversion_rate"], "kind": "percent"}],
                            f"/dashboard/leads?source={source}", "crm"))
    paying = [(s, r) for s, r in la["by_source"].items() if r["revenue_collected"] > 0]
    if paying:
        best, row = max(paying, key=lambda kv: kv[1]["revenue_collected"])
        out.append(_rec("best_source", f"{best.replace('_', ' ').title()} brings the most paying members",
                        "Consider investing more effort in this channel.", "low",
                        [{"label": "Members joined (90 days)", "value": row["joined"]},
                         {"label": "Collected from them", "value": row["revenue_collected"], "kind": "currency"}],
                        "/dashboard/sales-analytics", "crm"))
    if la["avg_first_response_minutes"] and la["avg_first_response_minutes"] > 60:
        out.append(_rec("slow_response", "Average first response is over an hour",
                        "Turn on the AI sales agent for instant replies, or set staff alerts.", "medium",
                        [{"label": "Avg first response (min)", "value": la["avg_first_response_minutes"]}],
                        "/dashboard/sales-agent", "crm"))

    ta = metrics.trial_analytics(db, start, today)
    if ta["attendance_rate"] is not None and ta["total"] >= 5 and ta["attendance_rate"] < 0.6:
        out.append(_rec("trial_attendance", "Many booked trials are not attended",
                        "Send reminders and confirm the day before.", "medium",
                        [{"label": "Attendance rate", "value": ta["attendance_rate"], "kind": "percent"},
                         {"label": "Confirmed no-shows", "value": ta["no_shows"]}], "/dashboard/trials", "trials"))

    audit = TenantRepository(SeoAudit, db).first(SeoAudit.status == AuditStatus.COMPLETED,
                                                order_by=SeoAudit.finished_at.desc())
    if audit:
        missing_meta = TenantRepository(SeoFinding, db).count(SeoFinding.audit_id == audit.id,
                                                              SeoFinding.code == "missing_meta_description")
        if missing_meta:
            out.append(_rec("missing_meta", f"Your website audit found {missing_meta} page(s) with no meta description",
                            "Generate suggestions and update those pages.", "medium",
                            [{"label": "Pages", "value": missing_meta}, {"label": "Audit score", "value": audit.score}],
                            f"/dashboard/seo/audits/{audit.id}", "seo"))
    else:
        out.append(_rec("no_audit", "No website SEO audit yet", "Run an audit to find technical and on-page issues.",
                        "low", [], "/dashboard/seo", "seo"))

    gbp = TenantRepository(IntegrationConnection, db).first(IntegrationConnection.provider == "google_business_profile")
    if gbp is None or gbp.status != ConnectionStatus.CONNECTED:
        out.append(_rec("connect_gbp", "Google Business Profile is not connected",
                        "Connect it to audit your profile and reply to reviews from GymFlow.", "low",
                        [{"label": "Status", "value": gbp.status.value if gbp else "not_connected"}],
                        "/dashboard/integrations", "local"))
    ready = TenantRepository(AiReadinessCheck, db).first(order_by=AiReadinessCheck.created_at.desc())
    if ready and ready.content_gaps:
        out.append(_rec("ai_readiness", f"{len(ready.content_gaps)} gaps in your AI-search readiness checklist",
                        "Clear, consistent information helps assistants describe your gym correctly.", "low",
                        [{"label": "Checklist score", "value": ready.score}], "/dashboard/ai-search", "ai_search"))
    order = {"high": 0, "medium": 1, "low": 2}
    return sorted(out, key=lambda r: order[r["priority"]])

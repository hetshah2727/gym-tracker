"""Reports: snapshots of deterministic metrics, saved so owners can look back (Workflow 9 uses daily_growth)."""
from datetime import date, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database.models import (
    AiReadinessCheck, BusinessProfileSnapshot, GrowthReport, SeoAudit, SeoFinding,
)
from app.database.models.enums import AuditStatus
from app.database.repositories.base import TenantRepository
from app.modules.growth import insights, metrics
from app.services import events

KINDS = {
    "daily_growth": "Daily growth summary", "weekly_revenue": "Weekly revenue report",
    "lead_conversion": "Lead conversion report", "renewals": "Renewal report",
    "seo_progress": "SEO progress report", "seo_audit": "SEO audit report",
    "local_visibility": "Local visibility report", "revenue_recovery": "Revenue recovery report",
    "monthly_seo": "Monthly SEO progress report",
}


def _window(kind: str, today: date) -> tuple[date, date]:
    if kind == "daily_growth":
        return today, today
    if kind in ("weekly_revenue", "renewals", "revenue_recovery"):
        return today - timedelta(days=6), today
    if kind == "monthly_seo":
        return today.replace(day=1), today
    return today - timedelta(days=29), today


def build_content(db: Session, kind: str, start: date, end: date) -> dict:
    if kind == "daily_growth":
        return {"overview": metrics.business_overview(db, start, end), "actions": metrics.todays_actions(db),
                "recommendations": insights.recommendations(db)[:5]}
    if kind == "weekly_revenue":
        return {"revenue": metrics.revenue(db, start, end), "series": metrics.revenue_series(db, 3)}
    if kind == "lead_conversion":
        return {"leads": metrics.lead_analytics(db, start, end), "trials": metrics.trial_analytics(db, start, end)}
    if kind in ("renewals", "revenue_recovery"):
        return {"recovery": metrics.recovery_overview(db), "revenue": metrics.revenue(db, start, end),
                "renewal_rate": metrics.renewal_rate(db)}
    if kind in ("seo_progress", "seo_audit", "monthly_seo"):
        audits = TenantRepository(SeoAudit, db).list(SeoAudit.status == AuditStatus.COMPLETED, limit=12,
                                                     order_by=SeoAudit.finished_at.desc())
        latest = audits[0] if audits else None
        findings = TenantRepository(SeoFinding, db).list(SeoFinding.audit_id == latest.id, limit=1000) if latest else []
        return {
            "history": [{"id": str(a.id), "finished_at": a.finished_at.isoformat() if a.finished_at else None,
                         "score": a.score, "pages": a.pages_crawled, "data_source": a.data_source} for a in audits],
            "latest": {"url": latest.url, "score": latest.score, "summary": latest.summary} if latest else None,
            "findings_by_category": _group(findings, "category"),
            "findings_by_severity": _group(findings, "severity"),
            "top_findings": [{"title": f.title, "severity": f.severity.value, "page": f.page_url,
                              "evidence": f.evidence, "recommendation": f.recommendation, "basis": f.basis}
                             for f in sorted(findings, key=lambda f: ["critical", "high", "medium", "low", "info"]
                                             .index(f.severity.value))[:15]],
            "next_actions": [r for r in insights.recommendations(db) if r["module"] == "seo"],
            "search_console": metrics.acquisition(db, start, end)["search_console"],
        }
    if kind == "local_visibility":
        snap = TenantRepository(BusinessProfileSnapshot, db).first(order_by=BusinessProfileSnapshot.fetched_at.desc())
        ready = TenantRepository(AiReadinessCheck, db).first(order_by=AiReadinessCheck.created_at.desc())
        return {"acquisition": metrics.acquisition(db, start, end),
                "profile_findings": snap.findings if snap else [], "profile_source": snap.source if snap else None,
                "ai_readiness": {"score": ready.score, "gaps": ready.content_gaps} if ready else None}
    raise ValueError(f"Unknown report kind {kind}")


def _group(items, attr) -> dict:
    out: dict = {}
    for i in items:
        key = getattr(i, attr)
        key = key.value if hasattr(key, "value") else key
        out[key] = out.get(key, 0) + 1
    return out


def build_report(db: Session, kind: str, *, generated_by: str = "user", today: date | None = None,
                 dedup: bool = False) -> GrowthReport:
    if kind not in KINDS:
        raise ValueError(f"Unknown report kind {kind}")
    today = today or date.today()
    start, end = _window(kind, today)
    repo = TenantRepository(GrowthReport, db)
    key = f"{kind}:{end.isoformat()}" if dedup else None
    if key and (existing := repo.first(GrowthReport.dedup_key == key)):
        return existing
    data = build_content(db, kind, start, end)
    try:
        with db.begin_nested():
            report = repo.add(kind=kind, title=f"{KINDS[kind]} – {end:%d %b %Y}", period_start=start, period_end=end,
                              content=data, generated_by=generated_by, dedup_key=key)
    except IntegrityError:
        return repo.first(GrowthReport.dedup_key == key)
    events.emit(db, "report.generated", entity_type="report", entity_id=report.id, actor=generated_by
                if generated_by in ("system", "agent") else "user", payload={"kind": kind})
    return report

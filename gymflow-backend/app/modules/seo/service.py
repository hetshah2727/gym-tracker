"""Website SEO workspace: audits (Workflow 7), suggestions, keywords, landing pages and reports."""
import logging
import re
from collections import Counter
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.core import entitlements
from app.core.config import settings
from app.core.tenant_context import get_current_gym_id, tenant_scope
from app.database.models import (
    ContentSuggestion, Gym, GymProfile, LandingPage, SeoAudit, SeoFinding, SeoKeyword, SeoPage, User, Website,
)
from app.database.models.enums import AuditStatus, ContentStatus, FindingStatus, Severity
from app.database.repositories.base import TenantRepository
from app.database.session import SessionLocal
from app.modules.seo import audit as engine
from app.modules.seo.fetcher import SafeFetcher, UnsafeUrlError, normalize_url, validate_url
from app.services import content, events

logger = logging.getLogger(__name__)

# Tests replace this with a fetcher backed by httpx.MockTransport.
FETCHER_FACTORY = SafeFetcher


def start_audit(db: Session, url: str, user: User | None, max_pages: int | None = None) -> SeoAudit:
    try:
        url = validate_url(normalize_url(url), getattr(FETCHER_FACTORY, "resolver_override", None))
    except UnsafeUrlError as exc:
        raise HTTPException(422, str(exc))
    entitlements.enforce_limit(db, "seo_audits")
    running = TenantRepository(SeoAudit, db).first(SeoAudit.status.in_([AuditStatus.QUEUED, AuditStatus.RUNNING]))
    if running and running.started_at and (datetime.now(timezone.utc) - _aware(running.started_at)).total_seconds() < 600:
        raise HTTPException(status.HTTP_409_CONFLICT, "An audit is already running")
    audit = TenantRepository(SeoAudit, db).add(
        url=url, status=AuditStatus.QUEUED, requested_by_id=user.id if user else None,
        max_pages=min(max_pages or settings.SEO_MAX_PAGES, 100), summary={"progress": "Queued"})
    db.commit()
    entitlements.record_usage(db, "seo_audits")
    return audit


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run_audit(audit_id, gym_id) -> None:
    """Background job: crawl, analyse, store pages + findings, compare with the previous audit."""
    with SessionLocal() as db, tenant_scope(gym_id):
        audit = TenantRepository(SeoAudit, db).get(audit_id)
        if audit is None:
            return
        audit.status, audit.started_at = AuditStatus.RUNNING, datetime.now(timezone.utc)
        db.commit()
        fetcher = FETCHER_FACTORY()

        def progress(done: int, url: str):
            audit.summary = {**(audit.summary or {}), "progress": f"Crawling page {done + 1}: {url[:120]}"}
            db.commit()

        try:
            result = engine.crawl(audit.url, fetcher, audit.max_pages, progress=progress)
            findings = engine.evaluate(result)
            save_results(db, audit, result, findings)
        except Exception as exc:  # noqa: BLE001
            logger.exception("SEO audit %s failed", audit_id)
            db.rollback()
            audit = TenantRepository(SeoAudit, db).get(audit_id)
            audit.status, audit.error = AuditStatus.FAILED, str(exc)[:500]
            audit.finished_at = datetime.now(timezone.utc)
            db.commit()
        finally:
            fetcher.close()


def save_results(db: Session, audit: SeoAudit, result: engine.CrawlResult, findings: list[engine.Finding],
                 data_source: str = "crawl") -> SeoAudit:
    pages = TenantRepository(SeoPage, db)
    for p in result.pages:
        f = p.facts
        pages.add(audit_id=audit.id, url=p.url, final_url=p.fetch.final_url, status_code=p.fetch.status,
                  redirect_chain=p.fetch.redirect_chain, load_ms=p.fetch.elapsed_ms, size_bytes=len(p.fetch.body),
                  title=f.title if f else None, meta_description=f.meta_description if f else None,
                  canonical=f.canonical if f else None, robots_meta=f.robots_meta if f else None,
                  lang=f.lang if f else None, has_viewport=bool(f and f.has_viewport),
                  headings=f.headings if f else {}, word_count=f.word_count if f else 0,
                  images=[{**i, "bytes": p.image_bytes.get(i["src"])} for i in (f.images[:60] if f else [])],
                  internal_links=sorted({engine.clean_url(u) for u in f.links
                                         if engine.is_crawlable_link(u, result.host)})[:200] if f else [],
                  external_link_count=len([u for u in f.links if not engine.is_crawlable_link(u, result.host)])
                  if f else 0, structured_data=f.json_ld[:20] if f else [], open_graph=f.open_graph if f else {},
                  phones_found=f.phones if f else [], text_excerpt=f.text[:6000] if f else None)
    repo = TenantRepository(SeoFinding, db)
    for item in findings:
        repo.add(audit_id=audit.id, page_url=item.page_url, code=item.code, category=item.category,
                 severity=Severity(item.severity), title=item.title, evidence=item.evidence,
                 recommendation=item.recommendation, fingerprint=item.fingerprint, basis="observed")
    previous = TenantRepository(SeoAudit, db).first(SeoAudit.status == AuditStatus.COMPLETED, SeoAudit.id != audit.id,
                                                   order_by=SeoAudit.finished_at.desc())
    comparison = compare(db, audit.id, previous.id, findings=findings) if previous else None
    counts = Counter(f.severity for f in findings)
    audit.score = engine.score(findings)
    audit.pages_crawled = len(result.pages)
    audit.data_source = data_source
    audit.summary = {
        "progress": "Completed", "host": result.host, "robots_txt": result.robots, "sitemap": result.sitemap,
        "https": result.https, "skipped_by_robots": len(result.skipped_by_robots),
        "counts": {s: counts.get(s, 0) for s in ("critical", "high", "medium", "low", "info")},
        "score_method": "100 minus a penalty per issue type (critical 20, high 10, medium 5, low 2) "
                        "plus 1 per extra affected page (max 4). GymFlow checklist, not a Google score.",
        "comparison": comparison,
    }
    audit.status, audit.finished_at = AuditStatus.COMPLETED, datetime.now(timezone.utc)
    events.emit(db, "seo.audit_completed", entity_type="seo_audit", entity_id=audit.id, actor="system",
                payload={"score": audit.score, "pages": audit.pages_crawled, "critical": counts.get("critical", 0)})
    return audit


def compare(db: Session, audit_id, previous_id, findings: list | None = None) -> dict:
    repo = TenantRepository(SeoFinding, db)
    now_prints = {f.fingerprint for f in findings} if findings is not None else \
        {f.fingerprint for f in repo.list(SeoFinding.audit_id == audit_id, limit=10_000)}
    old = repo.list(SeoFinding.audit_id == previous_id, limit=10_000)
    old_prints = {f.fingerprint for f in old}
    prev = TenantRepository(SeoAudit, db).get(previous_id)
    return {"previous_audit_id": str(previous_id), "previous_score": prev.score if prev else None,
            "resolved": sorted(old_prints - now_prints)[:200], "new": sorted(now_prints - old_prints)[:200],
            "resolved_count": len(old_prints - now_prints), "new_count": len(now_prints - old_prints)}


# ---------------------------------------------------------------- suggestions

def generate_suggestions(db: Session, audit: SeoAudit, limit_pages: int = 10) -> list[ContentSuggestion]:
    """On-page suggestions for pages with title/meta/H1/alt issues. Copy only - nothing is applied."""
    entitlements.enforce_limit(db, "content_generations")
    pages = {p.url: p for p in TenantRepository(SeoPage, db).list(SeoPage.audit_id == audit.id, limit=500)}
    findings = TenantRepository(SeoFinding, db).list(
        SeoFinding.audit_id == audit.id, SeoFinding.code.in_(
            ["missing_title", "title_too_long", "title_too_short", "missing_meta_description",
             "meta_description_too_long", "missing_h1", "images_missing_alt", "duplicate_title"]), limit=500)
    repo = TenantRepository(ContentSuggestion, db)
    facts = content.load_facts(db)
    out, done_meta = [], set()
    for finding in findings:
        page = pages.get(finding.page_url or "")
        if page is None:
            continue
        if finding.code == "images_missing_alt":
            for img in [i for i in page.images if i.get("alt") is None and i.get("src")][:5]:
                out.append(repo.add(module="seo", target=page.url, field=f"alt:{img['src'][:400]}",
                                    current_value=None, suggested_value=content.alt_text(facts, img["src"]),
                                    reason="Describes the image for visually impaired visitors and image search.",
                                    relevance="Accessibility + image search", generated_by="template",
                                    warnings=[], finding_id=finding.id))
            continue
        if page.url in done_meta or len(done_meta) >= limit_pages:
            continue
        done_meta.add(page.url)
        topic = _topic_from_url(page.url)
        meta, by, warnings = content.page_meta(db, page_url=page.url, current_title=page.title,
                                               current_description=page.meta_description, page_topic=topic)
        h1 = (page.headings or {}).get("h1") or []
        for field, current, suggested in (("title", page.title, meta.title),
                                          ("meta_description", page.meta_description, meta.meta_description),
                                          ("h1", h1[0] if h1 else None, meta.h1)):
            if (current or "").strip() == suggested.strip():
                continue
            out.append(repo.add(module="seo", target=page.url, field=field, current_value=current,
                                suggested_value=suggested, reason=meta.reason,
                                relevance="Local search click-through", generated_by=by, warnings=warnings,
                                finding_id=finding.id))
    db.commit()
    entitlements.record_usage(db, "content_generations")
    return out


def _topic_from_url(url: str) -> str | None:
    path = url.split("://", 1)[-1].split("/", 1)[-1].strip("/")
    if not path:
        return None
    words = re.sub(r"[-_/]+", " ", path.split("?")[0]).strip()
    return words.title()[:80] if words else None


def decide_suggestion(db: Session, suggestion: ContentSuggestion, user: User, *, approve: bool,
                      edited_value: str | None = None) -> dict:
    """Approve (optionally edited) or reject. Approved changes are applied only to GymFlow-hosted pages;
    for an external website the owner gets copy-ready text."""
    if suggestion.status not in (ContentStatus.DRAFT, ContentStatus.APPROVED):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Suggestion is already {suggestion.status.value}")
    suggestion.decided_by_id, suggestion.decided_at = user.id, datetime.now(timezone.utc)
    if not approve:
        suggestion.status = ContentStatus.REJECTED
        db.commit()
        return {"status": "rejected"}
    if edited_value:
        suggestion.suggested_value = edited_value
        suggestion.warnings = content.check_claims(edited_value)
    suggestion.status = ContentStatus.APPROVED
    applied = _apply_to_hosted(db, suggestion)
    if applied:
        suggestion.status = ContentStatus.PUBLISHED
    events.emit(db, "seo.suggestion_approved", entity_type="content_suggestion", entity_id=suggestion.id,
                actor_user_id=user.id, payload={"field": suggestion.field, "applied": applied})
    return {"status": suggestion.status.value, "applied_to_gymflow_site": applied,
            "copy_ready": None if applied else suggestion.suggested_value,
            "instructions": None if applied else
            f"Update the {suggestion.field.split(':')[0].replace('_', ' ')} on {suggestion.target} in your "
            "website's editor, then re-run the audit to confirm."}


def _apply_to_hosted(db: Session, s: ContentSuggestion) -> bool:
    """Only GymFlow-built pages can be changed directly (and only the homepage SEO fields / landing pages)."""
    for site in TenantRepository(Website, db).list(limit=20):
        base = f"{settings.FRONTEND_URL.rstrip('/')}/sites/{site.slug}"
        if s.target.rstrip("/") == base and s.field in ("title", "meta_description"):
            site.seo = {**(site.seo or {}), {"title": "title", "meta_description": "description"}[s.field]:
                        s.suggested_value}
            db.flush()
            return True
        for page in TenantRepository(LandingPage, db).list(LandingPage.website_id == site.id, limit=200):
            if s.target.rstrip("/") == f"{base}/{page.slug}" and s.field in ("title", "meta_description", "h1"):
                setattr(page, {"title": "seo_title", "meta_description": "meta_description", "h1": "h1"}[s.field],
                        s.suggested_value)
                db.flush()
                return True
    return False


# ---------------------------------------------------------------- keywords

MODIFIERS = [
    ("{service} near me", "local", "transactional"),
    ("{service} in {area}", "local", "transactional"),
    ("{service} in {city}", "local", "transactional"),
    ("best {service} in {area}", "local", "commercial"),
    ("{service} near {area}", "local", "transactional"),
    ("{service} fees in {city}", "local", "commercial"),
]
SERVICE_CATEGORY = [("personal train", "personal_training"), ("women", "womens"), ("ladies", "womens"),
                    ("weight", "strength"), ("strength", "strength"), ("yoga", "yoga"), ("zumba", "group_classes"),
                    ("crossfit", "functional"), ("functional", "functional"), ("cardio", "cardio")]


def keyword_ideas(db: Session) -> list[SeoKeyword]:
    """Rule-based local keyword ideas from the approved profile. Labelled as suggestions: there is no
    search volume, difficulty or ranking data unless a provider is connected (KEYWORD_PROVIDER)."""
    gym = db.get(Gym, get_current_gym_id())
    profile = TenantRepository(GymProfile, db).first()
    city = (profile.city if profile else None) or gym.city or ""
    areas = list(dict.fromkeys(a for a in ([profile.area, *(profile.service_areas or [])] if profile else []) if a))
    services = ["gym", "fitness centre"] + [s.lower() for s in (profile.services if profile else []) or []][:6]
    repo = TenantRepository(SeoKeyword, db)
    existing = {(k.keyword, k.location) for k in repo.list(limit=5000)}
    created = []
    for service in dict.fromkeys(services):
        category = next((c for key, c in SERVICE_CATEGORY if key in service), "general")
        for pattern, intent_kind, intent in MODIFIERS:
            for area in (areas[:4] if "{area}" in pattern else [None]):
                if "{city}" in pattern and not city:
                    continue
                kw = pattern.format(service=service, area=area or "", city=city).strip().lower()
                loc = area or city or None
                if (kw, loc) in existing:
                    continue
                existing.add((kw, loc))
                created.append(repo.add(keyword=kw, location=loc, intent=intent if intent_kind else "local",
                                        category=category, source="rule_suggestion", metrics_verified=False))
    db.commit()
    return created

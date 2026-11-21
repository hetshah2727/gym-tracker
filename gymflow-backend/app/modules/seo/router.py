"""Website SEO Growth Engine API."""
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import entitlements
from app.core.config import settings
from app.core.entitlements import gym_feature
from app.core.permissions import GYM_STAFF
from app.core.tenant_context import get_current_gym_id
from app.database.models import (
    ContentSuggestion, GrowthReport, LandingPage, SearchPerformance, SeoAudit, SeoFinding, SeoKeyword, SeoPage,
    User, Website,
)
from app.database.models.enums import AuditStatus, ConnectionStatus, ContentStatus, FindingStatus, Severity
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, get_or_404, slugify
from app.modules.growth import reports
from app.modules.integrations import google
from app.modules.seo import service
from app.services import content, events

router = APIRouter(prefix="/seo", tags=["Website SEO"])
staff = gym_feature("seo_audit", *GYM_STAFF)
MAX_LANDING_PAGES = 25


class AuditIn(BaseModel):
    url: str = Field(min_length=3, max_length=1000)
    max_pages: int | None = Field(None, ge=1, le=100)


class AuditOut(ORMModel):
    id: uuid.UUID
    url: str
    status: AuditStatus
    started_at: datetime | None
    finished_at: datetime | None
    pages_crawled: int
    max_pages: int
    score: int | None
    summary: dict
    error: str | None
    data_source: str
    created_at: datetime


class FindingOut(ORMModel):
    id: uuid.UUID
    audit_id: uuid.UUID
    page_url: str | None
    code: str
    category: str
    severity: Severity
    title: str
    evidence: str
    recommendation: str
    basis: str
    status: FindingStatus


class SuggestionOut(ORMModel):
    id: uuid.UUID
    module: str
    target: str
    field: str
    current_value: str | None
    suggested_value: str
    reason: str
    relevance: str | None
    generated_by: str
    warnings: list
    status: ContentStatus
    created_at: datetime


class DecideIn(BaseModel):
    approve: bool
    edited_value: str | None = Field(None, max_length=2000)


class KeywordOut(ORMModel):
    id: uuid.UUID
    keyword: str
    location: str | None
    intent: str
    category: str
    source: str
    metrics_verified: bool
    search_volume: int | None
    competition: str | None
    is_tracked: bool
    notes: str | None


class KeywordIn(BaseModel):
    keyword: str = Field(min_length=2, max_length=255)
    location: str | None = None
    intent: str = Field("local", pattern="^(local|transactional|commercial|informational|navigational)$")
    category: str = "general"
    is_tracked: bool = True
    notes: str | None = None


class LandingIn(BaseModel):
    service: str = Field(min_length=2, max_length=120)
    area: str = Field(min_length=2, max_length=120)
    website_id: uuid.UUID | None = None


class LandingUpdate(BaseModel):
    slug: str | None = None
    seo_title: str | None = Field(None, max_length=255)
    meta_description: str | None = Field(None, max_length=500)
    h1: str | None = Field(None, max_length=255)
    content: dict | None = None


class LandingOut(ORMModel):
    id: uuid.UUID
    website_id: uuid.UUID | None
    slug: str
    service: str
    area: str
    city: str | None
    seo_title: str
    meta_description: str
    h1: str
    content: dict
    json_ld: list
    status: ContentStatus
    generated_by: str
    warnings: list
    published_at: datetime | None
    created_at: datetime


# ---------------------------------------------------------------- audits

@router.post("/audits", response_model=AuditOut, status_code=status.HTTP_202_ACCEPTED)
def start(data: AuditIn, background: BackgroundTasks, db: Session = Depends(get_db), user: User = Depends(staff)):
    audit = service.start_audit(db, data.url, user, data.max_pages)
    background.add_task(service.run_audit, audit.id, get_current_gym_id())
    return audit


@router.get("/audits", response_model=list[AuditOut])
def list_audits(db: Session = Depends(get_db), _=Depends(staff)):
    return TenantRepository(SeoAudit, db).list(limit=50)


@router.get("/audits/{audit_id}")
def audit_detail(audit_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    audit = get_or_404(TenantRepository(SeoAudit, db), audit_id, "Audit")
    findings = TenantRepository(SeoFinding, db).list(SeoFinding.audit_id == audit.id, limit=5000)
    pages = TenantRepository(SeoPage, db).list(SeoPage.audit_id == audit.id, limit=500, order_by=SeoPage.url)
    issues_by_page = defaultdict(int)
    for f in findings:
        issues_by_page[f.page_url] += 1
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}
    return {
        "audit": AuditOut.model_validate(audit).model_dump(mode="json"),
        "findings": [FindingOut.model_validate(f).model_dump(mode="json")
                     for f in sorted(findings, key=lambda f: (order[f.severity.value], f.code))],
        "pages": [{"id": str(p.id), "url": p.url, "status_code": p.status_code, "title": p.title,
                   "meta_description": p.meta_description, "h1": (p.headings or {}).get("h1", []),
                   "word_count": p.word_count, "load_ms": p.load_ms, "images": len(p.images or []),
                   "images_missing_alt": sum(1 for i in p.images or [] if i.get("alt") is None),
                   "structured_data_types": sorted({str(o.get("@type")) for o in p.structured_data or []
                                                   if isinstance(o, dict)}),
                   "issues": issues_by_page.get(p.url, 0)} for p in pages],
    }


@router.get("/audits/{audit_id}/compare/{other_id}")
def compare(audit_id: uuid.UUID, other_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    get_or_404(TenantRepository(SeoAudit, db), audit_id, "Audit")
    get_or_404(TenantRepository(SeoAudit, db), other_id, "Audit")
    return service.compare(db, audit_id, other_id)


class FindingUpdate(BaseModel):
    status: FindingStatus


@router.patch("/findings/{finding_id}", response_model=FindingOut)
def update_finding(finding_id: uuid.UUID, data: FindingUpdate, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(SeoFinding, db)
    return repo.update(get_or_404(repo, finding_id, "Finding"), {"status": data.status})


# ---------------------------------------------------------------- suggestions

@router.post("/audits/{audit_id}/suggestions", response_model=list[SuggestionOut])
def suggestions(audit_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    return service.generate_suggestions(db, get_or_404(TenantRepository(SeoAudit, db), audit_id, "Audit"))


@router.get("/suggestions", response_model=list[SuggestionOut])
def list_suggestions(status_: ContentStatus | None = Query(None, alias="status"), module: str = "seo",
                     db: Session = Depends(get_db), _=Depends(staff)):
    f = [ContentSuggestion.module == module]
    if status_:
        f.append(ContentSuggestion.status == status_)
    return TenantRepository(ContentSuggestion, db).list(*f, limit=500)


@router.post("/suggestions/{suggestion_id}/decide")
def decide(suggestion_id: uuid.UUID, data: DecideIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    s = get_or_404(TenantRepository(ContentSuggestion, db), suggestion_id, "Suggestion")
    return service.decide_suggestion(db, s, user, approve=data.approve, edited_value=data.edited_value)


# ---------------------------------------------------------------- keywords

@router.get("/keywords", response_model=list[KeywordOut])
def keywords(location: str | None = None, intent: str | None = None, category: str | None = None,
             q: str | None = None, tracked: bool | None = None, db: Session = Depends(get_db), _=Depends(staff)):
    f = []
    if location:
        f.append(SeoKeyword.location == location)
    if intent:
        f.append(SeoKeyword.intent == intent)
    if category:
        f.append(SeoKeyword.category == category)
    if q:
        f.append(SeoKeyword.keyword.ilike(f"%{q}%"))
    if tracked is not None:
        f.append(SeoKeyword.is_tracked.is_(tracked))
    return TenantRepository(SeoKeyword, db).list(*f, limit=1000, order_by=SeoKeyword.keyword)


@router.post("/keywords/generate", response_model=list[KeywordOut])
def generate_keywords(db: Session = Depends(get_db), _=Depends(staff)):
    return service.keyword_ideas(db)


@router.post("/keywords", response_model=KeywordOut, status_code=status.HTTP_201_CREATED)
def add_keyword(data: KeywordIn, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(SeoKeyword, db)
    if repo.first(SeoKeyword.keyword == data.keyword.lower(), SeoKeyword.location == data.location):
        raise HTTPException(status.HTTP_409_CONFLICT, "Keyword already exists")
    return repo.create(**{**data.model_dump(), "keyword": data.keyword.lower()}, source="user",
                       metrics_verified=False)


class KeywordPatch(BaseModel):
    is_tracked: bool | None = None
    notes: str | None = None


@router.patch("/keywords/{keyword_id}", response_model=KeywordOut)
def patch_keyword(keyword_id: uuid.UUID, data: KeywordPatch, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(SeoKeyword, db)
    return repo.update(get_or_404(repo, keyword_id, "Keyword"), data.model_dump(exclude_unset=True))


@router.delete("/keywords/{keyword_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_keyword(keyword_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(SeoKeyword, db)
    repo.delete(get_or_404(repo, keyword_id, "Keyword"))


# ---------------------------------------------------------------- landing pages

def _public_url(db: Session, page: LandingPage) -> str | None:
    site = db.get(Website, page.website_id) if page.website_id else None
    return f"{settings.FRONTEND_URL.rstrip('/')}/sites/{site.slug}/{page.slug}" if site else None


@router.get("/landing-pages")
def list_pages(db: Session = Depends(get_db), _=Depends(gym_feature("website_builder", *GYM_STAFF))):
    return [{**LandingOut.model_validate(p).model_dump(mode="json"), "public_url": _public_url(db, p)}
            for p in TenantRepository(LandingPage, db).list(limit=200)]


@router.post("/landing-pages", response_model=LandingOut, status_code=status.HTTP_201_CREATED)
def create_page(data: LandingIn, db: Session = Depends(get_db),
                _=Depends(gym_feature("website_builder", *GYM_STAFF))):
    from app.database.models import GymProfile

    repo = TenantRepository(LandingPage, db)
    if repo.count() >= MAX_LANDING_PAGES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Limit of {MAX_LANDING_PAGES} landing pages: thin, "
                            "near-duplicate location pages hurt rankings. Improve existing pages instead.")
    profile = TenantRepository(GymProfile, db).first()
    real_areas = {a.lower() for a in ([profile.area] if profile and profile.area else []) + list(
        (profile.service_areas or []) if profile else [])}
    if data.area.lower() not in real_areas:
        raise HTTPException(422,
                            "Add this area to 'Service areas' in the Gym Profile first - landing pages are only "
                            "created for areas you actually serve.")
    if repo.first(LandingPage.service.ilike(data.service), LandingPage.area.ilike(data.area)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A page for this service and area already exists")
    website = TenantRepository(Website, db).get(data.website_id) if data.website_id else \
        TenantRepository(Website, db).first()
    entitlements.enforce_limit(db, "content_generations")
    draft, by, warnings = content.landing_page(db, data.service, data.area)
    slug = slugify(f"{data.service}-{data.area}")[:150]
    page = repo.create(website_id=website.id if website else None, slug=slug, service=data.service, area=data.area,
                       city=profile.city if profile else None, seo_title=draft.seo_title,
                       meta_description=draft.meta_description, h1=draft.h1,
                       content={"intro": draft.intro, "sections": [s.model_dump() for s in draft.sections],
                                "faqs": [q.model_dump() for q in draft.faqs], "cta": draft.cta},
                       json_ld=[], status=ContentStatus.DRAFT, generated_by=by, warnings=warnings)
    entitlements.record_usage(db, "content_generations")
    return page


@router.patch("/landing-pages/{page_id}", response_model=LandingOut)
def update_page(page_id: uuid.UUID, data: LandingUpdate, db: Session = Depends(get_db),
                _=Depends(gym_feature("website_builder", *GYM_STAFF))):
    repo = TenantRepository(LandingPage, db)
    page = get_or_404(repo, page_id, "Landing page")
    updates = data.model_dump(exclude_unset=True)
    if "slug" in updates:
        updates["slug"] = slugify(updates["slug"])[:150]
        if repo.first(LandingPage.slug == updates["slug"], LandingPage.id != page.id):
            raise HTTPException(status.HTTP_409_CONFLICT, "Slug already used")
    merged = {**{k: getattr(page, k) for k in ("seo_title", "meta_description", "h1")}, **updates}
    text = " ".join(str(v) for v in merged.values()) + " " + str(updates.get("content", page.content))
    updates["warnings"] = content.check_claims(text)
    return repo.update(page, updates)


@router.post("/landing-pages/{page_id}/publish", response_model=LandingOut)
def publish_page(page_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(staff)):
    repo = TenantRepository(LandingPage, db)
    page = get_or_404(repo, page_id, "Landing page")
    if not page.website_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Create a GymFlow website first (Website builder)")
    from app.modules.ai_search.service import generate_schema

    try:
        local = generate_schema(db, "local_business")
    except HTTPException:
        local = None
    url = _public_url(db, page)
    page.json_ld = [x for x in [local, {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": 1, "name": "Home", "item": url.rsplit("/", 1)[0] if url else None},
        {"@type": "ListItem", "position": 2, "name": page.h1, "item": url}]}] if x]
    page.status, page.published_at = ContentStatus.PUBLISHED, datetime.now(timezone.utc)
    events.emit(db, "landing_page.published", entity_type="landing_page", entity_id=page.id, actor_user_id=user.id,
                payload={"slug": page.slug})
    return page


@router.post("/landing-pages/{page_id}/unpublish", response_model=LandingOut)
def unpublish_page(page_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(LandingPage, db)
    return repo.update(get_or_404(repo, page_id, "Landing page"), {"status": ContentStatus.DRAFT})


@router.delete("/landing-pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_page(page_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    repo = TenantRepository(LandingPage, db)
    repo.delete(get_or_404(repo, page_id, "Landing page"))


@router.get("/landing-pages/{page_id}/indexing")
def indexing_guidance(page_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    page = get_or_404(TenantRepository(LandingPage, db), page_id, "Landing page")
    url = _public_url(db, page)
    site = db.get(Website, page.website_id) if page.website_id else None
    return {"url": url, "steps": [
        "Publish the page and open it to check it looks right on a phone.",
        f"Link to it from your homepage or services section (internal link with the text '{page.h1}').",
        f"Your GymFlow sitemap lists it automatically: {settings.PUBLIC_API_URL.rstrip('/')}/public/sites/"
        f"{site.slug if site else '<site>'}/sitemap.xml",
        "In Google Search Console use URL Inspection → Request indexing (only once).",
        "Share the page with a tracking link (e.g. ?utm_source=google&utm_medium=gbp) on your Business Profile.",
    ], "note": "Indexing is decided by Google and can take days to weeks; it is not guaranteed."}


# ---------------------------------------------------------------- performance & reports

@router.get("/performance")
def performance(days: int = Query(28, ge=7, le=90), db: Session = Depends(get_db), _=Depends(staff)):
    conn = google.connection(db, "google_search_console")
    if conn is None or conn.status != ConnectionStatus.CONNECTED:
        return {"connected": False, "status": conn.status.value if conn else "not_connected",
                "configured": google.is_configured(),
                "message": "Connect Google Search Console to see clicks, impressions, CTR and positions. "
                           "GymFlow does not estimate these numbers."}
    since = date.today() - timedelta(days=days)
    rows = TenantRepository(SearchPerformance, db).list(SearchPerformance.day >= since, limit=500_000)
    by_day, by_query, by_page = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0, 0.0]), defaultdict(lambda: [0, 0])
    for r in rows:
        by_day[r.day.isoformat()][0] += r.clicks
        by_day[r.day.isoformat()][1] += r.impressions
        q = by_query[r.query]
        q[0] += r.clicks
        q[1] += r.impressions
        q[2] += r.position * r.impressions
        by_page[r.page][0] += r.clicks
        by_page[r.page][1] += r.impressions
    clicks, impressions = sum(v[0] for v in by_day.values()), sum(v[1] for v in by_day.values())
    weighted = sum(v[2] for v in by_query.values())
    return {
        "connected": True, "property": conn.external_id, "last_sync_at": conn.last_sync_at, "source": "google_search_console",
        "totals": {"clicks": clicks, "impressions": impressions, "ctr": round(clicks / impressions, 4) if impressions else None,
                   "avg_position": round(weighted / impressions, 1) if impressions else None},
        "series": [{"day": d, "clicks": v[0], "impressions": v[1]} for d, v in sorted(by_day.items())],
        "queries": sorted([{"query": k, "clicks": v[0], "impressions": v[1],
                            "position": round(v[2] / v[1], 1) if v[1] else None} for k, v in by_query.items()],
                          key=lambda x: -x["clicks"])[:50],
        "pages": sorted([{"page": k, "clicks": v[0], "impressions": v[1]} for k, v in by_page.items()],
                        key=lambda x: -x["clicks"])[:30],
    }


@router.post("/performance/sync")
def sync_performance(db: Session = Depends(get_db), _=Depends(gym_feature("advanced_seo", *GYM_STAFF))):
    return {"rows": google.sync_search_console(db)}


@router.post("/reports/{kind}")
def create_report(kind: str, db: Session = Depends(get_db), _=Depends(staff)):
    if kind not in ("seo_audit", "seo_progress", "monthly_seo"):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown SEO report")
    report = reports.build_report(db, kind)
    return {"id": str(report.id), "title": report.title, "content": report.content}


@router.get("/reports")
def list_reports(db: Session = Depends(get_db), _=Depends(staff)):
    rows = TenantRepository(GrowthReport, db).list(GrowthReport.kind.in_(["seo_audit", "seo_progress", "monthly_seo"]),
                                                   limit=50)
    return [{"id": str(r.id), "kind": r.kind, "title": r.title, "created_at": r.created_at.isoformat()} for r in rows]

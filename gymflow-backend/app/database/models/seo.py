"""Website SEO: audits, crawled pages, findings, keywords, landing pages, suggestions, search data, reports."""
import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON, Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from app.database.models.enums import AuditStatus, ContentStatus, FindingStatus, Severity
from app.database.session import Base


class SeoAudit(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "seo_audits"

    url: Mapped[str] = mapped_column(String(1000))
    status: Mapped[AuditStatus] = mapped_column(enum_column(AuditStatus), default=AuditStatus.QUEUED)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_pages: Mapped[int] = mapped_column(Integer, default=25)
    pages_crawled: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int | None] = mapped_column(Integer)
    # {"robots_txt": {...}, "sitemap": {...}, "https": bool, "counts": {...}, "progress": "..."}
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)
    # "crawl" for a real crawl, "demo_simulated" for seeded demo data.
    data_source: Mapped[str] = mapped_column(String(32), default="crawl")


class SeoPage(IdMixin, TenantMixin, Base):
    __tablename__ = "seo_pages"

    audit_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("seo_audits.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(String(1000))
    final_url: Mapped[str | None] = mapped_column(String(1000))
    status_code: Mapped[int | None] = mapped_column(Integer)
    redirect_chain: Mapped[list] = mapped_column(JSON, default=list)
    load_ms: Mapped[int | None] = mapped_column(Integer)
    size_bytes: Mapped[int | None] = mapped_column(Integer)
    title: Mapped[str | None] = mapped_column(String(1000))
    meta_description: Mapped[str | None] = mapped_column(Text)
    canonical: Mapped[str | None] = mapped_column(String(1000))
    robots_meta: Mapped[str | None] = mapped_column(String(255))
    lang: Mapped[str | None] = mapped_column(String(32))
    has_viewport: Mapped[bool] = mapped_column(Boolean, default=False)
    headings: Mapped[dict] = mapped_column(JSON, default=dict)        # {"h1": [...], "h2": [...], ...}
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    images: Mapped[list] = mapped_column(JSON, default=list)          # [{"src", "alt", "bytes"}]
    internal_links: Mapped[list] = mapped_column(JSON, default=list)
    external_link_count: Mapped[int] = mapped_column(Integer, default=0)
    structured_data: Mapped[list] = mapped_column(JSON, default=list)  # parsed JSON-LD objects
    open_graph: Mapped[dict] = mapped_column(JSON, default=dict)
    phones_found: Mapped[list] = mapped_column(JSON, default=list)
    text_excerpt: Mapped[str | None] = mapped_column(Text)


class SeoFinding(IdMixin, TimestampMixin, TenantMixin, Base):
    """One issue. ``evidence`` records exactly what was observed, so every finding is traceable."""

    __tablename__ = "seo_findings"
    __table_args__ = (Index("ix_findings_audit_sev", "audit_id", "severity"),)

    audit_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("seo_audits.id", ondelete="CASCADE"))
    page_url: Mapped[str | None] = mapped_column(String(1000))
    code: Mapped[str] = mapped_column(String(64))            # e.g. missing_meta_description
    category: Mapped[str] = mapped_column(String(32))        # technical | on_page | content | local | ai_search
    severity: Mapped[Severity] = mapped_column(enum_column(Severity))
    title: Mapped[str] = mapped_column(String(255))
    evidence: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)
    # "observed" (from the crawl) or "ai_recommendation"
    basis: Mapped[str] = mapped_column(String(32), default="observed")
    # code + url; lets us compare audits ("resolved since last audit").
    fingerprint: Mapped[str] = mapped_column(String(300), index=True)
    status: Mapped[FindingStatus] = mapped_column(enum_column(FindingStatus), default=FindingStatus.OPEN)


class SeoKeyword(IdMixin, TimestampMixin, TenantMixin, Base):
    """A keyword idea. Volume/competition are only filled from a verified provider (``metrics_verified``)."""

    __tablename__ = "seo_keywords"
    __table_args__ = (UniqueConstraint("gym_id", "keyword", "location", name="uq_keywords_gym_kw_loc"),)

    keyword: Mapped[str] = mapped_column(String(255))
    location: Mapped[str | None] = mapped_column(String(120))
    intent: Mapped[str] = mapped_column(String(32))          # local | transactional | informational | navigational
    category: Mapped[str] = mapped_column(String(64))        # general | personal_training | womens | strength ...
    source: Mapped[str] = mapped_column(String(64))          # rule_suggestion | ai_suggestion | user | <provider>
    metrics_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    search_volume: Mapped[int | None] = mapped_column(Integer)
    competition: Mapped[str | None] = mapped_column(String(16))
    is_tracked: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text)


class LandingPage(IdMixin, TimestampMixin, TenantMixin, Base):
    """SEO landing page served at /sites/<site slug>/<slug>, with an enquiry form attributed to it."""

    __tablename__ = "landing_pages"
    __table_args__ = (UniqueConstraint("gym_id", "slug", name="uq_landing_pages_gym_slug"),)

    website_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("websites.id", ondelete="SET NULL"))
    slug: Mapped[str] = mapped_column(String(160))
    service: Mapped[str] = mapped_column(String(120))        # e.g. "Personal Training"
    area: Mapped[str] = mapped_column(String(120))           # e.g. "Gotri"
    city: Mapped[str | None] = mapped_column(String(120))
    seo_title: Mapped[str] = mapped_column(String(255))
    meta_description: Mapped[str] = mapped_column(String(500))
    h1: Mapped[str] = mapped_column(String(255))
    # {"intro": str, "sections": [{"heading", "body"}], "faqs": [{"q", "a"}], "cta": str}
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    json_ld: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[ContentStatus] = mapped_column(enum_column(ContentStatus), default=ContentStatus.DRAFT)
    generated_by: Mapped[str] = mapped_column(String(32), default="template")  # template | ai | manual
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ContentSuggestion(IdMixin, TimestampMixin, TenantMixin, Base):
    """Proposed change (title, meta, H1, alt text, FAQ, slug...). Never applied without approval."""

    __tablename__ = "content_suggestions"

    module: Mapped[str] = mapped_column(String(32))          # seo | local | ai_search
    target: Mapped[str] = mapped_column(String(1000))        # page URL, "gbp:description", "website:<id>"...
    field: Mapped[str] = mapped_column(String(64))           # title | meta_description | h1 | alt | faq | ...
    current_value: Mapped[str | None] = mapped_column(Text)
    suggested_value: Mapped[str] = mapped_column(Text)
    reason: Mapped[str] = mapped_column(Text)
    relevance: Mapped[str | None] = mapped_column(String(255))
    generated_by: Mapped[str] = mapped_column(String(32), default="template")
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[ContentStatus] = mapped_column(enum_column(ContentStatus), default=ContentStatus.DRAFT)
    finding_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("seo_findings.id", ondelete="SET NULL"))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SearchPerformance(IdMixin, TenantMixin, Base):
    """Rows synced from Google Search Console (``source``) - never generated."""

    __tablename__ = "search_performance"
    __table_args__ = (Index("ix_search_perf_gym_day", "gym_id", "day"),)

    day: Mapped[date] = mapped_column(Date)
    query: Mapped[str | None] = mapped_column(String(500))
    page: Mapped[str | None] = mapped_column(String(1000))
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    ctr: Mapped[float] = mapped_column(Float, default=0)
    position: Mapped[float] = mapped_column(Float, default=0)
    source: Mapped[str] = mapped_column(String(40), default="google_search_console")
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class GrowthReport(IdMixin, TimestampMixin, TenantMixin, Base):
    """Generated report snapshot (SEO audit, daily growth summary, weekly revenue...)."""

    __tablename__ = "growth_reports"
    __table_args__ = (UniqueConstraint("gym_id", "dedup_key", name="uq_reports_gym_dedup"),)

    kind: Mapped[str] = mapped_column(String(48))
    title: Mapped[str] = mapped_column(String(255))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    content: Mapped[dict] = mapped_column(JSON, default=dict)
    generated_by: Mapped[str] = mapped_column(String(32), default="system")
    dedup_key: Mapped[str | None] = mapped_column(String(160))

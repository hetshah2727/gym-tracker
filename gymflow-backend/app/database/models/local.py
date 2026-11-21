"""Gym knowledge base (canonical entity profile), Google Business Profile, reviews, competitors, AI search."""
import uuid
from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from app.database.models.enums import ReplyStatus
from app.database.session import Base


class GymProfile(IdMixin, TimestampMixin, TenantMixin, Base):
    """Owner-approved facts about the gym. The single source for the sales agent and generated content.

    Prices and plans come from ``membership_plans`` and staff from ``trainers``; this holds the rest.
    """

    __tablename__ = "gym_profiles"
    __table_args__ = (UniqueConstraint("gym_id", name="uq_gym_profiles_gym"),)

    business_name: Mapped[str | None] = mapped_column(String(200))
    website_url: Mapped[str | None] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text)
    address_line: Mapped[str | None] = mapped_column(String(500))
    area: Mapped[str | None] = mapped_column(String(120))          # neighbourhood, e.g. Gotri
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(16))
    country: Mapped[str] = mapped_column(String(2), default="IN")
    phone: Mapped[str | None] = mapped_column(String(32))
    whatsapp: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    # [{"days": "Mon-Sat", "opens": "05:30", "closes": "22:30"}]
    opening_hours: Mapped[list] = mapped_column(JSON, default=list)
    services: Mapped[list] = mapped_column(JSON, default=list)       # ["Personal training", ...]
    facilities: Mapped[list] = mapped_column(JSON, default=list)     # ["Free weights", "Steam room", ...]
    service_areas: Mapped[list] = mapped_column(JSON, default=list)  # ["Gotri", "Vasna-Bhayli", ...]
    target_audience: Mapped[list] = mapped_column(JSON, default=list)
    social_profiles: Mapped[dict] = mapped_column(JSON, default=dict)  # {"instagram": url, ...}
    # {"enabled": true, "duration_minutes": 60, "price": 0, "notes": "..."}
    trial_offer: Mapped[dict] = mapped_column(JSON, default=dict)
    offers: Mapped[list] = mapped_column(JSON, default=list)         # [{"title", "details", "valid_until"}]
    rules: Mapped[str | None] = mapped_column(Text)
    faqs: Mapped[list] = mapped_column(JSON, default=list)           # [{"q", "a", "approved": bool}]
    review_url: Mapped[str | None] = mapped_column(String(1000))     # the gym's real "write a review" link
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))


class BusinessProfileSnapshot(IdMixin, TenantMixin, Base):
    """Business Profile data as fetched (``source`` = google_business_profile | manual | demo_simulated)."""

    __tablename__ = "business_profile_snapshots"

    source: Mapped[str] = mapped_column(String(40))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    completeness: Mapped[int | None] = mapped_column(Integer)
    findings: Mapped[list] = mapped_column(JSON, default=list)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class Review(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "reviews"
    __table_args__ = (UniqueConstraint("gym_id", "source", "external_id", name="uq_reviews_gym_source_ext"),)

    source: Mapped[str] = mapped_column(String(40))               # google_business_profile | manual | demo_simulated
    external_id: Mapped[str] = mapped_column(String(255))
    author: Mapped[str | None] = mapped_column(String(200))
    rating: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str | None] = mapped_column(Text)
    review_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sentiment: Mapped[str | None] = mapped_column(String(16))     # positive | neutral | negative
    sentiment_basis: Mapped[str | None] = mapped_column(String(16))  # rating | ai
    reply_status: Mapped[ReplyStatus] = mapped_column(enum_column(ReplyStatus), default=ReplyStatus.NONE)
    existing_reply: Mapped[str | None] = mapped_column(Text)
    draft_reply: Mapped[str | None] = mapped_column(Text)
    draft_generated_by: Mapped[str | None] = mapped_column(String(32))
    replied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    approved_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))


class ReviewRequest(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "review_requests"

    member_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("members.id", ondelete="SET NULL"))
    channel: Mapped[str] = mapped_column(String(16), default="whatsapp")
    message: Mapped[str] = mapped_column(Text)
    review_url: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(16), default="queued")  # queued | sent | failed | reminded
    notification_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("notifications.id", ondelete="SET NULL"))
    remind_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_recorded: Mapped[bool] = mapped_column(Boolean, default=False)


class Competitor(IdMixin, TimestampMixin, TenantMixin, Base):
    """Competitor details. Everything here is user-supplied unless ``source`` says otherwise."""

    __tablename__ = "competitors"

    name: Mapped[str] = mapped_column(String(200))
    website: Mapped[str | None] = mapped_column(String(500))
    maps_url: Mapped[str | None] = mapped_column(String(1000))
    area: Mapped[str | None] = mapped_column(String(120))
    distance_km: Mapped[float | None] = mapped_column(Float)
    categories: Mapped[list] = mapped_column(JSON, default=list)
    services: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str | None] = mapped_column(Text)
    rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    reviews_last_90_days: Mapped[int | None] = mapped_column(Integer)
    price_notes: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="user_supplied")
    observed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    notes: Mapped[str | None] = mapped_column(Text)


class AiVisibilityQuery(IdMixin, TimestampMixin, TenantMixin, Base):
    """An owner-approved question to monitor, e.g. "best gyms in Gotri, Vadodara"."""

    __tablename__ = "ai_visibility_queries"

    question: Mapped[str] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AiVisibilityResult(IdMixin, TenantMixin, Base):
    """One observed answer. ``method`` says how it was obtained (manual_research | <provider>)."""

    __tablename__ = "ai_visibility_results"

    query_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_visibility_queries.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(64))             # chatgpt | gemini | perplexity | google_ai_overview
    method: Mapped[str] = mapped_column(String(32), default="manual_research")
    mentioned: Mapped[bool] = mapped_column(Boolean, default=False)
    position: Mapped[int | None] = mapped_column(Integer)
    citation_urls: Mapped[list] = mapped_column(JSON, default=list)
    competitors_mentioned: Mapped[list] = mapped_column(JSON, default=list)
    excerpt: Mapped[str | None] = mapped_column(Text)
    recorded_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AiReadinessCheck(IdMixin, TenantMixin, Base):
    """Result of the transparent AI-search readiness checklist (not a Google/OpenAI score)."""

    __tablename__ = "ai_readiness_checks"

    score: Mapped[int] = mapped_column(Integer)
    checklist: Mapped[list] = mapped_column(JSON, default=list)      # [{"key","label","passed","evidence","weight"}]
    inconsistencies: Mapped[list] = mapped_column(JSON, default=list)
    content_gaps: Mapped[list] = mapped_column(JSON, default=list)
    audit_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("seo_audits.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

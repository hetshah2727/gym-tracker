import uuid
from datetime import datetime

from datetime import date

from sqlalchemy import JSON, Boolean, Date, DateTime, ForeignKey, Index, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column
from app.database.models.enums import LeadStatus, Priority
from app.database.session import Base


class Website(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "websites"

    name: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    template: Mapped[str] = mapped_column(String(64), default="classic")
    # {"primaryColor": "#16a34a", "font": "Inter", "logoUrl": ...}
    theme: Mapped[dict] = mapped_column(JSON, default=dict)
    # Ordered blocks from the drag-and-drop editor:
    # [{"id": "...", "type": "hero" | "plans" | "trainers" | "gallery" | "contact" | ..., "props": {...}}]
    blocks: Mapped[list] = mapped_column(JSON, default=list)
    seo: Mapped[dict] = mapped_column(JSON, default=dict)
    custom_domain: Mapped[str | None] = mapped_column(String(255), unique=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Snapshot served to visitors; drafts in `blocks` don't go live until published.
    published_blocks: Mapped[list] = mapped_column(JSON, default=list)


class Lead(IdMixin, TimestampMixin, TenantMixin, Base):
    """Every enquiry, whatever the channel. Shared by the CRM, AI sales agent, trials and analytics."""

    __tablename__ = "leads"
    __table_args__ = (
        Index("ix_leads_gym_status", "gym_id", "status"),
        Index("ix_leads_gym_phone_key", "gym_id", "phone_key"),
    )

    website_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("websites.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    # Last 10 digits of the phone, used for duplicate detection.
    phone_key: Mapped[str | None] = mapped_column(String(16))
    email: Mapped[str | None] = mapped_column(String(255), index=True)
    message: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), default="website")
    status: Mapped[LeadStatus] = mapped_column(enum_column(LeadStatus), default=LeadStatus.NEW)

    # Attribution: how we know the source (utm | referrer | declared | staff | unknown) and the raw evidence.
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("campaigns.id", ondelete="SET NULL"))
    landing_page_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("landing_pages.id", ondelete="SET NULL"))
    attribution: Mapped[dict] = mapped_column(JSON, default=dict)

    # Qualification (no health data is collected on purpose).
    fitness_interest: Mapped[str | None] = mapped_column(String(120))
    interested_plan_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("membership_plans.id", ondelete="SET NULL"))
    preferred_location: Mapped[str | None] = mapped_column(String(120))
    preferred_joining_date: Mapped[date | None] = mapped_column(Date)
    wants_trial: Mapped[bool] = mapped_column(Boolean, default=False)

    # Sales workflow
    assigned_to_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    priority: Mapped[Priority] = mapped_column(enum_column(Priority), default=Priority.MEDIUM)
    score: Mapped[int] = mapped_column(Integer, default=0)
    score_reasons: Mapped[list] = mapped_column(JSON, default=list)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_contacted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    lost_reason: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    # Conversion: only set when an actual member + membership exist.
    existing_member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("members.id", ondelete="SET NULL"))
    converted_member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("members.id", ondelete="SET NULL"))
    converted_membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("memberships.id", ondelete="SET NULL"))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Messaging consent (WhatsApp business-initiated messages need opt-in; STOP opts out).
    whatsapp_opt_in: Mapped[bool] = mapped_column(Boolean, default=False)
    opted_out: Mapped[bool] = mapped_column(Boolean, default=False)
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

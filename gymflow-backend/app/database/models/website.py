import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column
from app.database.models.enums import LeadStatus
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
    __tablename__ = "leads"

    website_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("websites.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    email: Mapped[str | None] = mapped_column(String(255))
    message: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(64), default="website")
    status: Mapped[LeadStatus] = mapped_column(enum_column(LeadStatus), default=LeadStatus.NEW)

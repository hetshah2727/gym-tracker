import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from app.database.models.enums import AutomationTrigger, Channel, NotificationStatus
from app.database.session import Base


class AutomationRule(IdMixin, TimestampMixin, TenantMixin, Base):
    """e.g. "WhatsApp members 3 days before their membership expires"."""

    __tablename__ = "automation_rules"

    name: Mapped[str] = mapped_column(String(200))
    trigger: Mapped[AutomationTrigger] = mapped_column(enum_column(AutomationTrigger))
    offset_days: Mapped[int] = mapped_column(Integer, default=0)
    channel: Mapped[Channel] = mapped_column(enum_column(Channel), default=Channel.WHATSAPP)
    # Python str.format template, e.g. "Hi {name}, your plan ends on {end_date}."
    template: Mapped[str] = mapped_column(Text)
    n8n_workflow: Mapped[str | None] = mapped_column(String(200))  # optional n8n webhook name
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Notification(IdMixin, TimestampMixin, TenantMixin, Base):
    """Outbound message log and queue (WhatsApp, voice call, SMS, email)."""

    __tablename__ = "notifications"

    member_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("members.id", ondelete="SET NULL"), index=True
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("automation_rules.id", ondelete="SET NULL")
    )
    channel: Mapped[Channel] = mapped_column(enum_column(Channel))
    recipient: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(64), default="general")
    # Prevents the same automated reminder being queued twice (e.g. "rule:<id>:membership:<id>").
    dedup_key: Mapped[str | None] = mapped_column(String(200), index=True)
    status: Mapped[NotificationStatus] = mapped_column(
        enum_column(NotificationStatus), default=NotificationStatus.QUEUED, index=True
    )
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    provider_message_id: Mapped[str | None] = mapped_column(String(200))
    error: Mapped[str | None] = mapped_column(Text)

"""Integration connections, webhook de-duplication, usage metering and subscription history."""
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from app.database.models.enums import ConnectionStatus
from app.database.session import Base


class IntegrationConnection(IdMixin, TimestampMixin, TenantMixin, Base):
    """A gym's authorised connection to an external service. Tokens are encrypted at rest."""

    __tablename__ = "integration_connections"
    __table_args__ = (UniqueConstraint("gym_id", "provider", name="uq_integrations_gym_provider"),)

    provider: Mapped[str] = mapped_column(String(48))  # google_search_console | google_business_profile | whatsapp
    status: Mapped[ConnectionStatus] = mapped_column(
        enum_column(ConnectionStatus), default=ConnectionStatus.NOT_CONNECTED)
    account_label: Mapped[str | None] = mapped_column(String(255))
    # GSC property ("sc-domain:example.com"), GBP location ("accounts/1/locations/2"), WA phone number id
    external_id: Mapped[str | None] = mapped_column(String(255), index=True)
    scopes: Mapped[list] = mapped_column(JSON, default=list)
    encrypted_tokens: Mapped[str | None] = mapped_column(Text)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    connected_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)  # e.g. available locations/properties to choose


class WebhookEvent(IdMixin, Base):
    """Seen provider event ids - a redelivered webhook is acknowledged but not processed twice."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),)

    provider: Mapped[str] = mapped_column(String(32))
    event_id: Mapped[str] = mapped_column(String(255))
    gym_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("gyms.id", ondelete="CASCADE"))
    event_type: Mapped[str | None] = mapped_column(String(64))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UsageCounter(IdMixin, TenantMixin, Base):
    """Monthly usage per metered feature (ai_messages, seo_audits, ...)."""

    __tablename__ = "usage_counters"
    __table_args__ = (UniqueConstraint("gym_id", "metric", "period", name="uq_usage_gym_metric_period"),)

    metric: Mapped[str] = mapped_column(String(48))
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    count: Mapped[int] = mapped_column(Integer, default=0)


class SubscriptionEvent(IdMixin, TenantMixin, Base):
    __tablename__ = "subscription_events"

    event: Mapped[str] = mapped_column(String(32))  # trial_started | plan_changed | status_changed
    from_plan: Mapped[str | None] = mapped_column(String(32))
    to_plan: Mapped[str | None] = mapped_column(String(32))
    status: Mapped[str | None] = mapped_column(String(32))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

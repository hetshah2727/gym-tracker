import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column
from app.database.models.enums import SubscriptionStatus, TicketPriority, TicketStatus
from app.database.session import Base


class SubscriptionPlan(IdMixin, TimestampMixin, Base):
    """GymFlow's own SaaS plans that gyms subscribe to."""

    __tablename__ = "subscription_plans"

    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    price_monthly: Mapped[float] = mapped_column(Numeric(10, 2))
    max_members: Mapped[int | None] = mapped_column(Integer)  # None = unlimited
    # {"automation": true, "ai_diet": true, "affiliate": true, "website_builder": true, "voice_calls": false}
    features: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class GymSubscription(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "gym_subscriptions"

    plan_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("subscription_plans.id"))
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_column(SubscriptionStatus), default=SubscriptionStatus.TRIALING
    )
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    gateway_subscription_id: Mapped[str | None] = mapped_column(String(120))


class SupportTicket(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "support_tickets"

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    subject: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[TicketStatus] = mapped_column(enum_column(TicketStatus), default=TicketStatus.OPEN)
    priority: Mapped[TicketPriority] = mapped_column(enum_column(TicketPriority), default=TicketPriority.MEDIUM)

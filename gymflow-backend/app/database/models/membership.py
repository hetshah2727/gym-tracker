import uuid
from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from app.database.models.enums import MembershipStatus, PaymentMethod, PaymentStatus
from app.database.session import Base


class MembershipPlan(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "membership_plans"

    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    duration_days: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Numeric(10, 2))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "memberships"

    member_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), index=True)
    plan_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("membership_plans.id", ondelete="SET NULL"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date, index=True)
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[MembershipStatus] = mapped_column(
        enum_column(MembershipStatus), default=MembershipStatus.ACTIVE, index=True
    )
    auto_renew: Mapped[bool] = mapped_column(Boolean, default=False)


class Payment(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "payments"

    member_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), index=True)
    membership_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("memberships.id", ondelete="SET NULL")
    )
    amount: Mapped[float] = mapped_column(Numeric(10, 2))
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus), default=PaymentStatus.PENDING, index=True
    )
    method: Mapped[PaymentMethod | None] = mapped_column(enum_column(PaymentMethod))
    due_date: Mapped[date | None] = mapped_column(Date)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reference: Mapped[str | None] = mapped_column(String(120))
    gateway_order_id: Mapped[str | None] = mapped_column(String(120), index=True)
    gateway_payment_id: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(String(255))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # "manual" (staff recorded), "gateway" (verified by a signed provider webhook), "demo"
    verified_by: Mapped[str | None] = mapped_column(String(32))


class Attendance(IdMixin, TenantMixin, Base):
    __tablename__ = "attendance"

    member_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), index=True)
    check_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    check_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(32), default="manual")  # manual | qr | biometric

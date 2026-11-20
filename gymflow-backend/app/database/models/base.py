"""Shared column mixins."""
import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Uuid
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enum_column(enum_cls: type[enum.Enum]) -> Enum:
    """Portable enum stored as its string value (works on PostgreSQL and SQLite)."""
    return Enum(enum_cls, native_enum=False, length=32,
                values_callable=lambda e: [m.value for m in e])


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class TenantMixin:
    """Marks a table as gym-scoped. TenantRepository filters on this column."""

    @declared_attr
    def gym_id(cls) -> Mapped[uuid.UUID]:
        return mapped_column(Uuid, ForeignKey("gyms.id", ondelete="CASCADE"), index=True)

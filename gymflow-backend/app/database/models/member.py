import uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column
from app.database.models.enums import DietPreference, FitnessGoal, Gender, MemberStatus
from app.database.session import Base


class Trainer(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "trainers"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str | None] = mapped_column(String(32))
    specialization: Mapped[str | None] = mapped_column(String(200))
    bio: Mapped[str | None] = mapped_column(Text)
    photo_url: Mapped[str | None] = mapped_column(String(500))
    is_active: Mapped[bool] = mapped_column(default=True)


class Member(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "members"

    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    trainer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("trainers.id", ondelete="SET NULL"))
    full_name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str | None] = mapped_column(String(255))
    phone: Mapped[str] = mapped_column(String(32))
    gender: Mapped[Gender | None] = mapped_column(enum_column(Gender))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)
    fitness_goal: Mapped[FitnessGoal | None] = mapped_column(enum_column(FitnessGoal))
    diet_preference: Mapped[DietPreference | None] = mapped_column(enum_column(DietPreference))
    dietary_restrictions: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MemberStatus] = mapped_column(enum_column(MemberStatus), default=MemberStatus.ACTIVE)
    joined_on: Mapped[date] = mapped_column(Date, default=date.today)
    notes: Mapped[str | None] = mapped_column(Text)

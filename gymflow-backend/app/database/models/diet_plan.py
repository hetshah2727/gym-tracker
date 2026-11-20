import uuid

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column
from app.database.models.enums import DietPlanStatus, DietPreference, FitnessGoal
from app.database.session import Base


class DietPlan(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "diet_plans"

    member_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("members.id", ondelete="CASCADE"), index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    goal: Mapped[FitnessGoal] = mapped_column(enum_column(FitnessGoal))
    diet_type: Mapped[DietPreference] = mapped_column(enum_column(DietPreference))
    daily_calories: Mapped[int] = mapped_column(Integer)
    # {"protein_g": 140, "carbs_g": 220, "fat_g": 60}
    macros: Mapped[dict] = mapped_column(JSON, default=dict)
    # [{"name": "Breakfast", "time": "08:00", "items": [{"food": ..., "quantity": ..., "calories": ...}]}]
    meals: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[DietPlanStatus] = mapped_column(enum_column(DietPlanStatus), default=DietPlanStatus.DRAFT)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)

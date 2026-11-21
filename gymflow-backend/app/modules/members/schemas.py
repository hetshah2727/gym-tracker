import uuid
from datetime import date, datetime

from pydantic import BaseModel, EmailStr, Field

from app.database.models.enums import DietPreference, FitnessGoal, Gender, MemberStatus
from app.modules.common import ORMModel


class MemberBase(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)
    phone: str = Field(min_length=6, max_length=32)
    email: EmailStr | None = None
    gender: Gender | None = None
    date_of_birth: date | None = None
    height_cm: float | None = Field(default=None, gt=50, lt=260)
    weight_kg: float | None = Field(default=None, gt=20, lt=350)
    fitness_goal: FitnessGoal | None = None
    diet_preference: DietPreference | None = None
    dietary_restrictions: str | None = None
    trainer_id: uuid.UUID | None = None
    notes: str | None = None


class MemberCreate(MemberBase):
    joined_on: date | None = None


class MemberUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    gender: Gender | None = None
    date_of_birth: date | None = None
    height_cm: float | None = None
    weight_kg: float | None = None
    fitness_goal: FitnessGoal | None = None
    diet_preference: DietPreference | None = None
    dietary_restrictions: str | None = None
    trainer_id: uuid.UUID | None = None
    status: MemberStatus | None = None
    notes: str | None = None


class MemberOut(MemberBase, ORMModel):
    id: uuid.UUID
    gym_id: uuid.UUID
    user_id: uuid.UUID | None
    status: MemberStatus
    joined_on: date
    created_at: datetime
    # Filled in by the list endpoint so the owner sees what matters at a glance.
    plan_name: str | None = None
    end_date: date | None = None
    days_left: int | None = None
    due_amount: float = 0
    last_visit_at: datetime | None = None


class PortalAccessRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)

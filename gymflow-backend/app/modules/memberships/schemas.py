import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field

from app.database.models.enums import MembershipStatus, PaymentMethod
from app.modules.common import ORMModel


class PlanIn(BaseModel):
    name: str
    description: str | None = None
    duration_days: int = Field(gt=0)
    price: float = Field(ge=0)
    is_active: bool = True


class PlanUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    duration_days: int | None = Field(default=None, gt=0)
    price: float | None = Field(default=None, ge=0)
    is_active: bool | None = None


class PlanOut(ORMModel):
    id: uuid.UUID
    name: str
    description: str | None
    duration_days: int
    price: float
    is_active: bool


class AssignMembershipRequest(BaseModel):
    member_id: uuid.UUID
    plan_id: uuid.UUID
    start_date: date | None = None
    amount: float | None = Field(default=None, ge=0, description="Override the plan price (discounts)")
    paid: bool = False
    payment_method: PaymentMethod | None = None
    auto_renew: bool = False


class RenewRequest(BaseModel):
    plan_id: uuid.UUID | None = None
    paid: bool = False
    payment_method: PaymentMethod | None = None


class MembershipOut(ORMModel):
    id: uuid.UUID
    member_id: uuid.UUID
    plan_id: uuid.UUID | None
    start_date: date
    end_date: date
    amount: float
    status: MembershipStatus
    auto_renew: bool
    created_at: datetime
    days_left: int | None = None

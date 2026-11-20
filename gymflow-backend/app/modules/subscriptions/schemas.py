import uuid
from datetime import datetime

from pydantic import BaseModel

from app.database.models.enums import SubscriptionStatus
from app.modules.common import ORMModel


class SubscriptionPlanIn(BaseModel):
    code: str
    name: str
    price_monthly: float
    max_members: int | None = None
    features: dict = {}
    is_active: bool = True


class SubscriptionPlanUpdate(BaseModel):
    name: str | None = None
    price_monthly: float | None = None
    max_members: int | None = None
    features: dict | None = None
    is_active: bool | None = None


class SubscriptionPlanOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    price_monthly: float
    max_members: int | None
    features: dict
    is_active: bool


class GymSubscriptionOut(ORMModel):
    id: uuid.UUID
    gym_id: uuid.UUID
    plan_id: uuid.UUID
    status: SubscriptionStatus
    current_period_end: datetime
    plan: SubscriptionPlanOut | None = None


class ChangePlanRequest(BaseModel):
    plan_code: str

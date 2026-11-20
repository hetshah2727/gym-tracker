import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.modules.common import ORMModel


class GymOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    email: str | None
    phone: str | None
    address: str | None
    city: str | None
    timezone: str
    currency: str
    logo_url: str | None
    settings: dict
    is_active: bool
    created_at: datetime


class GymUpdate(BaseModel):
    name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    address: str | None = None
    city: str | None = None
    timezone: str | None = None
    currency: str | None = None
    logo_url: str | None = None
    settings: dict | None = None

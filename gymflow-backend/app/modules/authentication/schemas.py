import uuid

from pydantic import BaseModel, EmailStr, Field

from app.database.models.enums import Role
from app.modules.common import ORMModel


class RegisterGymRequest(BaseModel):
    gym_name: str = Field(min_length=2, max_length=200)
    owner_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    phone: str | None = None
    city: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class UserOut(ORMModel):
    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    role: Role
    gym_id: uuid.UUID | None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut

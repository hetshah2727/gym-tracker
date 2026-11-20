"""Gym staff accounts (managers and trainers) managed by the gym owner."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import tenant_user
from app.core.security import hash_password
from app.database.models import Trainer, User
from app.database.models.enums import Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.authentication.schemas import UserOut
from app.modules.common import get_or_404

router = APIRouter(prefix="/users", tags=["Staff users"])

STAFF_ROLES = (Role.GYM_MANAGER, Role.TRAINER)


class StaffCreate(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(min_length=8)
    phone: str | None = None
    role: Role = Role.TRAINER


class StaffUpdate(BaseModel):
    full_name: str | None = None
    phone: str | None = None
    is_active: bool | None = None


@router.get("", response_model=list[UserOut])
def list_staff(db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER, Role.GYM_MANAGER))):
    return TenantRepository(User, db).list(User.role != Role.MEMBER, limit=500)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create_staff(data: StaffCreate, db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    if data.role not in STAFF_ROLES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Role must be gym_manager or trainer")
    if db.scalar(select(User.id).where(User.email == data.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use")
    user = TenantRepository(User, db).create(
        email=data.email.lower(), hashed_password=hash_password(data.password),
        full_name=data.full_name, phone=data.phone, role=data.role,
    )
    if data.role == Role.TRAINER:  # every trainer login gets a trainer profile
        TenantRepository(Trainer, db).create(user_id=user.id, full_name=data.full_name,
                                             email=user.email, phone=data.phone)
    return user


@router.patch("/{user_id}", response_model=UserOut)
def update_staff(user_id: uuid.UUID, data: StaffUpdate, db: Session = Depends(get_db),
                 current: User = Depends(tenant_user(Role.GYM_OWNER))):
    repo = TenantRepository(User, db)
    user = get_or_404(repo, user_id, "User")
    if user.id == current.id and data.is_active is False:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "You cannot deactivate yourself")
    return repo.update(user, data.model_dump(exclude_unset=True))

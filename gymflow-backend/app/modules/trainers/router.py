import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF, GYM_STAFF_AND_TRAINERS, tenant_user
from app.database.models import Member, Trainer
from app.database.models.enums import Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, get_or_404
from app.modules.members.schemas import MemberOut

router = APIRouter(prefix="/trainers", tags=["Trainers"])


class TrainerIn(BaseModel):
    full_name: str
    email: EmailStr | None = None
    phone: str | None = None
    specialization: str | None = None
    bio: str | None = None
    photo_url: str | None = None


class TrainerUpdate(BaseModel):
    full_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    specialization: str | None = None
    bio: str | None = None
    photo_url: str | None = None
    is_active: bool | None = None


class TrainerOut(ORMModel):
    id: uuid.UUID
    user_id: uuid.UUID | None
    full_name: str
    email: str | None
    phone: str | None
    specialization: str | None
    bio: str | None
    photo_url: str | None
    is_active: bool


@router.get("", response_model=list[TrainerOut])
def list_trainers(db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    return TenantRepository(Trainer, db).list(limit=500, order_by=Trainer.full_name)


@router.post("", response_model=TrainerOut, status_code=status.HTTP_201_CREATED)
def create_trainer(data: TrainerIn, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    """Trainer profile without a login. Use POST /users with role=trainer to create one with a login."""
    return TenantRepository(Trainer, db).create(**data.model_dump())


@router.patch("/{trainer_id}", response_model=TrainerOut)
def update_trainer(trainer_id: uuid.UUID, data: TrainerUpdate, db: Session = Depends(get_db),
                   _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(Trainer, db)
    return repo.update(get_or_404(repo, trainer_id, "Trainer"), data.model_dump(exclude_unset=True))


@router.delete("/{trainer_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_trainer(trainer_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    repo = TenantRepository(Trainer, db)
    repo.delete(get_or_404(repo, trainer_id, "Trainer"))


@router.get("/{trainer_id}/members", response_model=list[MemberOut])
def trainer_members(trainer_id: uuid.UUID, db: Session = Depends(get_db),
                    _=Depends(tenant_user(*GYM_STAFF))):
    get_or_404(TenantRepository(Trainer, db), trainer_id, "Trainer")
    return TenantRepository(Member, db).list(Member.trainer_id == trainer_id, limit=1000)

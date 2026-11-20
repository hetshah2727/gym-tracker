import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF, GYM_STAFF_AND_TRAINERS, tenant_user
from app.core.security import hash_password
from app.database.models import Member, Trainer, User
from app.database.models.enums import MemberStatus, Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.integrations.n8n import client as n8n
from app.modules.authentication.schemas import UserOut
from app.modules.common import Page, get_or_404
from app.modules.members.schemas import MemberCreate, MemberOut, MemberUpdate, PortalAccessRequest

router = APIRouter(prefix="/members", tags=["Members"])


def trainer_profile_id(db: Session, user: User) -> uuid.UUID | None:
    if user.role != Role.TRAINER:
        return None
    trainer = TenantRepository(Trainer, db).list(Trainer.user_id == user.id, limit=1)
    if not trainer:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No trainer profile for this user")
    return trainer[0].id


def _ensure_trainer(db: Session, trainer_id: uuid.UUID | None) -> None:
    if trainer_id and TenantRepository(Trainer, db).get(trainer_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trainer not found in this gym")


@router.get("", response_model=Page[MemberOut])
def list_members(
    status_: MemberStatus | None = Query(None, alias="status"),
    search: str | None = None,
    trainer_id: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS)),
):
    filters = []
    # Trainers only ever see the members assigned to them.
    own = trainer_profile_id(db, user)
    if own:
        trainer_id = own
    if trainer_id:
        filters.append(Member.trainer_id == trainer_id)
    if status_:
        filters.append(Member.status == status_)
    if search:
        like = f"%{search}%"
        filters.append(or_(Member.full_name.ilike(like), Member.phone.ilike(like), Member.email.ilike(like)))
    repo = TenantRepository(Member, db)
    return Page(items=repo.list(*filters, offset=offset, limit=limit), total=repo.count(*filters),
                offset=offset, limit=limit)


@router.post("", response_model=MemberOut, status_code=status.HTTP_201_CREATED)
def create_member(data: MemberCreate, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    _ensure_trainer(db, data.trainer_id)
    payload = data.model_dump(exclude_none=True)
    member = TenantRepository(Member, db).create(**payload)
    n8n.trigger("member.created", {"member_id": str(member.id), "gym_id": str(member.gym_id),
                                   "name": member.full_name, "phone": member.phone})
    return member


@router.get("/{member_id}", response_model=MemberOut)
def get_member(member_id: uuid.UUID, db: Session = Depends(get_db),
               user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    member = get_or_404(TenantRepository(Member, db), member_id, "Member")
    own = trainer_profile_id(db, user)
    if own and member.trainer_id != own:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Member not found")
    return member


@router.patch("/{member_id}", response_model=MemberOut)
def update_member(member_id: uuid.UUID, data: MemberUpdate, db: Session = Depends(get_db),
                  _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(Member, db)
    member = get_or_404(repo, member_id, "Member")
    updates = data.model_dump(exclude_unset=True)
    if "trainer_id" in updates:
        _ensure_trainer(db, updates["trainer_id"])
    return repo.update(member, updates)


@router.delete("/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_member(member_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(Role.GYM_OWNER))):
    repo = TenantRepository(Member, db)
    repo.delete(get_or_404(repo, member_id, "Member"))


@router.post("/{member_id}/portal-access", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def grant_portal_access(member_id: uuid.UUID, data: PortalAccessRequest, db: Session = Depends(get_db),
                        _=Depends(tenant_user(*GYM_STAFF))):
    """Create a member-app login so the member can see their plan, diet and products."""
    repo = TenantRepository(Member, db)
    member = get_or_404(repo, member_id, "Member")
    if member.user_id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Member already has portal access")
    if db.scalar(select(User.id).where(User.email == data.email.lower())):
        raise HTTPException(status.HTTP_409_CONFLICT, "Email already in use")
    user = TenantRepository(User, db).create(
        email=data.email.lower(), hashed_password=hash_password(data.password),
        full_name=member.full_name, phone=member.phone, role=Role.MEMBER,
    )
    repo.update(member, {"user_id": user.id, "email": member.email or user.email})
    return user

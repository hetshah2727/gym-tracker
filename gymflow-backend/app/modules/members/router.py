import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF, GYM_STAFF_AND_TRAINERS, tenant_user
from app.core.security import hash_password
from app.database.models import Attendance, Member, Membership, MembershipPlan, Payment, Trainer, User
from app.database.models.enums import MemberStatus, PaymentStatus, Role
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
    members = repo.list(*filters, offset=offset, limit=limit)
    return Page(items=_with_status(db, members), total=repo.count(*filters), offset=offset, limit=limit)


def _with_status(db: Session, members: list[Member]) -> list[MemberOut]:
    """Attach current plan, days left, unpaid dues and last visit (one query each, not per member)."""
    ids = [m.id for m in members]
    if not ids:
        return []
    latest: dict = {}
    for ms in TenantRepository(Membership, db).list(Membership.member_id.in_(ids), limit=len(ids) * 20,
                                                     order_by=Membership.end_date):
        latest[ms.member_id] = ms  # ordered by end date, so the last one wins
    plans = {p.id: p.name for p in TenantRepository(MembershipPlan, db).list(limit=500)}
    dues: dict = {}
    for p in TenantRepository(Payment, db).list(Payment.member_id.in_(ids), Payment.status.in_(
            [PaymentStatus.PENDING, PaymentStatus.OVERDUE, PaymentStatus.FAILED]), limit=len(ids) * 20):
        dues[p.member_id] = dues.get(p.member_id, 0) + float(p.amount)
    visits = dict(db.execute(select(Attendance.member_id, func.max(Attendance.check_in_at))
                             .where(Attendance.member_id.in_(ids)).group_by(Attendance.member_id)).all())
    today = date.today()
    out = []
    for m in members:
        row = MemberOut.model_validate(m)
        ms = latest.get(m.id)
        if ms:
            row.plan_name = plans.get(ms.plan_id)
            row.end_date = ms.end_date
            row.days_left = (ms.end_date - today).days
        row.due_amount = round(dues.get(m.id, 0), 2)
        row.last_visit_at = visits.get(m.id)
        out.append(row)
    return out


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


# ---------------------------------------------------------------- import from Excel / CSV

IMPORT_TEMPLATE = ("Name,Phone,Email,Gender,Plan,Joining date,Expiry date,Paid\n"
                   "Amit Shah,9824012345,amit@example.com,Male,Monthly,01/11/2026,30/11/2026,Yes\n"
                   "Priya Kapoor,9824098765,,Female,Quarterly,15/09/2026,13/12/2026,No\n")


@router.get("/import/template.csv")
def import_template(_=Depends(tenant_user(*GYM_STAFF))):
    from fastapi.responses import Response

    return Response(IMPORT_TEMPLATE, media_type="text/csv",
                    headers={"Content-Disposition": 'attachment; filename="gymflow-members-template.csv"'})


@router.post("/import")
async def import_members(file: UploadFile = File(...), preview: bool = Query(True),
                         db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    """Preview (default) or import members from an Excel/CSV file. Re-running never duplicates a phone number."""
    from app.modules.members import importer

    data = await file.read()
    if len(data) > 5_000_000:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File is too large (max 5 MB)")
    try:
        rows = importer.read_rows(file.filename or "", data)
    except importer.ImportError_ as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc))
    return {"preview": preview, **importer.run(db, rows, commit=not preview)}


@router.get("/{member_id}/timeline")
def member_timeline(member_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    """Everything about one member on one screen: current plan, money, visits and history."""
    from datetime import datetime, timedelta, timezone

    member = get_or_404(TenantRepository(Member, db), member_id, "Member")
    plans = {p.id: p.name for p in TenantRepository(MembershipPlan, db).list(limit=500)}
    memberships = TenantRepository(Membership, db).list(Membership.member_id == member.id, limit=50,
                                                        order_by=Membership.end_date.desc())
    payments = TenantRepository(Payment, db).list(Payment.member_id == member.id, limit=50,
                                                  order_by=Payment.created_at.desc())
    since = datetime.now(timezone.utc) - timedelta(days=30)
    visits = TenantRepository(Attendance, db).list(Attendance.member_id == member.id, limit=60,
                                                   order_by=Attendance.check_in_at.desc())
    return {
        "member": _with_status(db, [member])[0].model_dump(mode="json"),
        "memberships": [{"id": str(m.id), "plan": plans.get(m.plan_id), "plan_id": str(m.plan_id) if m.plan_id else None,
                         "start_date": m.start_date.isoformat(), "end_date": m.end_date.isoformat(),
                         "amount": float(m.amount), "status": m.status.value} for m in memberships],
        "payments": [{"id": str(p.id), "amount": float(p.amount), "status": p.status.value,
                      "method": p.method.value if p.method else None,
                      "due_date": p.due_date.isoformat() if p.due_date else None,
                      "paid_at": p.paid_at.isoformat() if p.paid_at else None} for p in payments],
        "visits": {"last_30_days": sum(1 for v in visits if (v.check_in_at if v.check_in_at.tzinfo else
                                                              v.check_in_at.replace(tzinfo=timezone.utc)) >= since),
                   "recent": [v.check_in_at.isoformat() for v in visits[:10]]},
    }

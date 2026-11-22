import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF_AND_TRAINERS, tenant_user
from app.database.models import Attendance, Member
from app.database.models.enums import MemberStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, get_or_404

router = APIRouter(prefix="/attendance", tags=["Attendance"])


class CheckInRequest(BaseModel):
    member_id: uuid.UUID
    source: str = "manual"


class AttendanceOut(ORMModel):
    id: uuid.UUID
    member_id: uuid.UUID
    check_in_at: datetime
    check_out_at: datetime | None
    source: str


@router.post("/check-in", response_model=AttendanceOut, status_code=status.HTTP_201_CREATED)
def check_in(data: CheckInRequest, db: Session = Depends(get_db),
             _=Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    member = get_or_404(TenantRepository(Member, db), data.member_id, "Member")
    if member.status != MemberStatus.ACTIVE:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Member is {member.status.value}; renew to check in")
    return TenantRepository(Attendance, db).create(member_id=member.id, source=data.source)


@router.post("/{attendance_id}/check-out", response_model=AttendanceOut)
def check_out(attendance_id: uuid.UUID, db: Session = Depends(get_db),
              _=Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    repo = TenantRepository(Attendance, db)
    return repo.update(get_or_404(repo, attendance_id, "Attendance"),
                       {"check_out_at": datetime.now(timezone.utc)})


@router.get("", response_model=list[AttendanceOut])
def list_attendance(
    on: date | None = Query(None, description="Defaults to today"),
    member_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    _=Depends(tenant_user(*GYM_STAFF_AND_TRAINERS)),
):
    filters = []
    if member_id:
        filters.append(Attendance.member_id == member_id)
    else:
        # "Today" is the gym's local day (e.g. IST), not the UTC day - otherwise early-morning check-ins
        # (before 05:30 IST) would land on the previous day.
        from zoneinfo import ZoneInfo

        from app.core.tenant_context import get_current_gym_id
        from app.database.models import Gym

        gym = db.get(Gym, get_current_gym_id())
        tz = ZoneInfo(gym.timezone if gym and gym.timezone else "Asia/Kolkata")
        day = on or datetime.now(tz).date()
        start = datetime.combine(day, datetime.min.time(), tzinfo=tz).astimezone(timezone.utc)
        filters += [Attendance.check_in_at >= start, Attendance.check_in_at < start + timedelta(days=1)]
    return TenantRepository(Attendance, db).list(*filters, limit=1000, order_by=Attendance.check_in_at.desc())

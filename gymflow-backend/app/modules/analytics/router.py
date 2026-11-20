"""Dashboard KPIs and the daily / monthly reports gym owners receive."""
from calendar import monthrange
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF, tenant_user
from app.database.models import Attendance, Lead, Member, Membership, Payment
from app.database.models.enums import LeadStatus, MembershipStatus, MemberStatus, PaymentStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db

router = APIRouter(prefix="/analytics", tags=["Analytics & reports"], dependencies=[Depends(tenant_user(*GYM_STAFF))])


def _start(d: date) -> datetime:
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def _sum(db: Session, column, *where) -> float:
    stmt = TenantRepository(Payment, db).query().with_only_columns(func.coalesce(func.sum(column), 0)).where(*where)
    return float(db.scalar(stmt) or 0)


class Overview(BaseModel):
    total_members: int
    active_members: int
    expired_members: int
    new_members_this_month: int
    expiring_in_7_days: int
    revenue_this_month: float
    revenue_last_month: float
    pending_amount: float
    pending_count: int
    checkins_today: int
    new_leads: int


class PeriodReport(BaseModel):
    period_start: date
    period_end: date
    new_members: int
    active_members: int
    memberships_expired: int
    memberships_expiring_next_7_days: int
    revenue_collected: float
    payments_collected: int
    pending_amount: float
    pending_count: int
    checkins: int
    new_leads: int


@router.get("/overview", response_model=Overview)
def overview(db: Session = Depends(get_db)):
    today = date.today()
    month_start = today.replace(day=1)
    last_month_start = (month_start - timedelta(days=1)).replace(day=1)
    members = TenantRepository(Member, db)
    payments = TenantRepository(Payment, db)
    pending = [Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.OVERDUE])]
    return Overview(
        total_members=members.count(),
        active_members=members.count(Member.status == MemberStatus.ACTIVE),
        expired_members=members.count(Member.status == MemberStatus.EXPIRED),
        new_members_this_month=members.count(Member.joined_on >= month_start),
        expiring_in_7_days=TenantRepository(Membership, db).count(
            Membership.status == MembershipStatus.ACTIVE, Membership.end_date <= today + timedelta(days=7)),
        revenue_this_month=_sum(db, Payment.amount, Payment.status == PaymentStatus.PAID,
                                Payment.paid_at >= _start(month_start)),
        revenue_last_month=_sum(db, Payment.amount, Payment.status == PaymentStatus.PAID,
                                Payment.paid_at >= _start(last_month_start), Payment.paid_at < _start(month_start)),
        pending_amount=_sum(db, Payment.amount, *pending),
        pending_count=payments.count(*pending),
        checkins_today=TenantRepository(Attendance, db).count(Attendance.check_in_at >= _start(today)),
        new_leads=TenantRepository(Lead, db).count(Lead.status == LeadStatus.NEW),
    )


@router.get("/revenue")
def revenue_series(months: int = Query(6, ge=1, le=24), db: Session = Depends(get_db)):
    """Monthly collected revenue for the last N months (oldest first)."""
    first = date.today().replace(day=1)
    for _ in range(months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    totals: dict[str, float] = defaultdict(float)
    for p in TenantRepository(Payment, db).list(Payment.status == PaymentStatus.PAID,
                                                Payment.paid_at >= _start(first), limit=1_000_000):
        totals[p.paid_at.strftime("%Y-%m")] += float(p.amount)
    series, cursor = [], first
    for _ in range(months):
        key = cursor.strftime("%Y-%m")
        series.append({"month": key, "revenue": round(totals.get(key, 0), 2)})
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return series


def build_report(db: Session, start: date, end: date) -> PeriodReport:
    """Report for the inclusive date range [start, end]."""
    lo, hi = _start(start), _start(end + timedelta(days=1))
    pending = [Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.OVERDUE])]
    paid = [Payment.status == PaymentStatus.PAID, Payment.paid_at >= lo, Payment.paid_at < hi]
    return PeriodReport(
        period_start=start, period_end=end,
        new_members=TenantRepository(Member, db).count(Member.joined_on >= start, Member.joined_on <= end),
        active_members=TenantRepository(Member, db).count(Member.status == MemberStatus.ACTIVE),
        memberships_expired=TenantRepository(Membership, db).count(
            Membership.end_date >= start - timedelta(days=1), Membership.end_date < end,
            Membership.status == MembershipStatus.EXPIRED),
        memberships_expiring_next_7_days=TenantRepository(Membership, db).count(
            Membership.status == MembershipStatus.ACTIVE, Membership.end_date > end,
            Membership.end_date <= end + timedelta(days=7)),
        revenue_collected=_sum(db, Payment.amount, *paid),
        payments_collected=TenantRepository(Payment, db).count(*paid),
        pending_amount=_sum(db, Payment.amount, *pending),
        pending_count=TenantRepository(Payment, db).count(*pending),
        checkins=TenantRepository(Attendance, db).count(Attendance.check_in_at >= lo, Attendance.check_in_at < hi),
        new_leads=TenantRepository(Lead, db).count(Lead.created_at >= lo, Lead.created_at < hi),
    )


@router.get("/reports/daily", response_model=PeriodReport)
def daily_report(on: date | None = None, db: Session = Depends(get_db)):
    day = on or date.today()
    return build_report(db, day, day)


@router.get("/reports/monthly", response_model=PeriodReport)
def monthly_report(year: int | None = None, month: int | None = Query(None, ge=1, le=12),
                   db: Session = Depends(get_db)):
    today = date.today()
    year, month = year or today.year, month or today.month
    return build_report(db, date(year, month, 1), date(year, month, monthrange(year, month)[1]))

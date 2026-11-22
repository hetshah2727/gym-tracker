"""The monthly owner report: one short, shareable summary of what happened and what GymFlow brought back.

Built only from recorded data (payments, memberships, check-ins, enquiries). Sent by email on the 1st of every
month (when email is configured) and shareable on WhatsApp / printable from the Reports page.
"""
import calendar
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import Attendance, Gym, Lead, Membership, SubscriptionPlan, User
from app.database.models.enums import LeadStatus, Role
from app.database.repositories.base import TenantRepository
from app.modules.growth import metrics

logger = logging.getLogger(__name__)


def month_bounds(month: str | None = None, today: date | None = None) -> tuple[date, date]:
    """'2026-10' -> (1 Oct, 31 Oct). Default: the previous full month."""
    if month:
        y, m = (int(x) for x in month.split("-"))
    else:
        first = (today or date.today()).replace(day=1)
        prev = first - timedelta(days=1)
        y, m = prev.year, prev.month
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def _inr(v: float) -> str:
    # Indian digit grouping without depending on the OS locale
    n = int(round(v))
    s = str(abs(n))
    if len(s) > 3:
        head, tail = s[:-3], s[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        s = ",".join(([head] if head else []) + groups) + "," + tail
    return ("-" if n < 0 else "") + "₹" + s


def build(db: Session, month: str | None = None) -> dict:
    from app.core import entitlements

    start, end = month_bounds(month)
    gym = db.get(Gym, get_current_gym_id())
    lo = datetime.combine(start, datetime.min.time(), tzinfo=timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc)
    rev = metrics.revenue(db, start, end)
    biz = metrics.business_overview(db, start, end)
    ms = TenantRepository(Membership, db)
    new_memberships = ms.count(Membership.created_at >= lo, Membership.created_at < hi)
    checkins = TenantRepository(Attendance, db).count(Attendance.check_in_at >= lo, Attendance.check_in_at < hi)
    leads = TenantRepository(Lead, db)
    enquiries = leads.count(Lead.created_at >= lo, Lead.created_at < hi)
    joined = leads.count(Lead.created_at >= lo, Lead.created_at < hi, Lead.status == LeadStatus.CONVERTED)
    ent = entitlements.resolve(db, gym.id)
    plan = db.scalar(select(SubscriptionPlan).where(SubscriptionPlan.code == ent.plan_code)) if ent.plan_code else None
    price = float(plan.price_monthly) if plan else None
    multiple = round(rev["recovered"] / price, 1) if price and rev["recovered"] else None
    label = start.strftime("%B %Y")

    lines = [f"*{gym.name} – {label}*", "",
             f"💰 Collected: {_inr(rev['collected'])} ({rev['payments_collected']} payments)",
             f"🔁 Brought back by GymFlow: {_inr(rev['recovered'])}"
             + (f" – {multiple}× your GymFlow plan" if multiple and multiple >= 1 else ""),
             f"🧾 Still unpaid today: {_inr(rev['outstanding'])}",
             f"🏋️ Active members: {biz['active_members']} · new memberships & renewals: {new_memberships}",
             f"📅 Check-ins: {checkins}",
             f"📨 Enquiries: {enquiries} · joined: {joined}"]
    return {
        "gym": gym.name, "month": start.strftime("%Y-%m"), "label": label,
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "collected": rev["collected"], "payments": rev["payments_collected"], "recovered": rev["recovered"],
        "outstanding": rev["outstanding"], "active_members": biz["active_members"],
        "new_memberships": new_memberships, "checkins": checkins, "enquiries": enquiries, "joined": joined,
        "plan_price": price, "roi_multiple": multiple, "text": "\n".join(lines),
    }


def email_owners(db: Session, report: dict) -> int:
    """Email the report to the gym's owners. Returns how many emails were handed to the provider."""
    from app.core.config import settings
    from app.services import email

    owners = TenantRepository(User, db).list(User.role == Role.GYM_OWNER, User.is_active.is_(True), limit=5)
    body = report["text"].replace("*", "") + f"\n\nSee more in GymFlow: {settings.FRONTEND_URL.rstrip('/')}/dashboard/revenue"
    return sum(email.send(u.email, f"Your {report['label']} gym report", body) for u in owners)

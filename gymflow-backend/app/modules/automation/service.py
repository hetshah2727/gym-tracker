"""Rule engine: turns gym events (expiring memberships, dues, birthdays...) into notifications.

Each rule run is idempotent: notifications carry a dedup key, so running the
engine several times a day never messages a member twice for the same event.
"""
import logging
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import extract, select
from sqlalchemy.orm import Session

from app.core.tenant_context import tenant_scope
from app.database.models import Attendance, AutomationRule, Gym, Member, Membership, Payment
from app.database.models.enums import AutomationTrigger, MembershipStatus, MemberStatus, PaymentStatus
from app.database.repositories.base import TenantRepository
from app.integrations.n8n import client as n8n
from app.modules.common import render_template
from app.modules.notifications import service as notifications

logger = logging.getLogger(__name__)


def _context(gym: Gym, member: Member, **extra) -> dict:
    return {"name": member.full_name.split()[0], "full_name": member.full_name, "gym": gym.name,
            "phone": gym.phone or "", "currency": gym.currency, **extra}


def _targets(db: Session, rule: AutomationRule, today: date):
    """Yield (member, context, dedup_suffix) for everyone the rule applies to today."""
    members = TenantRepository(Member, db)
    if rule.trigger == AutomationTrigger.MEMBERSHIP_EXPIRING:
        target = today + timedelta(days=rule.offset_days)
        for ms in TenantRepository(Membership, db).list(
                Membership.status == MembershipStatus.ACTIVE, Membership.end_date == target, limit=10_000):
            if member := members.get(ms.member_id):
                yield member, {"end_date": ms.end_date.strftime("%d %b %Y"),
                               "days_left": rule.offset_days}, f"membership:{ms.id}"

    elif rule.trigger == AutomationTrigger.MEMBERSHIP_EXPIRED:
        target = today - timedelta(days=rule.offset_days + 1)
        for ms in TenantRepository(Membership, db).list(
                Membership.status == MembershipStatus.EXPIRED, Membership.end_date == target, limit=10_000):
            if member := members.get(ms.member_id):
                yield member, {"end_date": ms.end_date.strftime("%d %b %Y")}, f"membership:{ms.id}"

    elif rule.trigger == AutomationTrigger.PAYMENT_DUE:
        target = today + timedelta(days=rule.offset_days)
        for p in TenantRepository(Payment, db).list(
                Payment.status.in_([PaymentStatus.PENDING, PaymentStatus.OVERDUE]),
                Payment.due_date == target, limit=10_000):
            if member := members.get(p.member_id):
                yield member, {"amount": f"{float(p.amount):,.0f}",
                               "due_date": p.due_date.strftime("%d %b %Y")}, f"payment:{p.id}"

    elif rule.trigger == AutomationTrigger.BIRTHDAY:
        for member in members.list(Member.status == MemberStatus.ACTIVE,
                                   extract("month", Member.date_of_birth) == today.month,
                                   extract("day", Member.date_of_birth) == today.day, limit=10_000):
            yield member, {}, f"birthday:{member.id}:{today.year}"

    elif rule.trigger == AutomationTrigger.INACTIVE_MEMBER:
        days = rule.offset_days or 7
        since = datetime.combine(today - timedelta(days=days), datetime.min.time(), tzinfo=timezone.utc)
        recent = select(Attendance.member_id).where(Attendance.gym_id == Member.gym_id,
                                                    Attendance.check_in_at >= since)
        week = today.isocalendar()
        for member in members.list(Member.status == MemberStatus.ACTIVE, Member.id.not_in(recent),
                                   Member.joined_on <= today - timedelta(days=days), limit=10_000):
            yield member, {"days": days}, f"inactive:{member.id}:{week[0]}-{week[1]}"


def run_rule(db: Session, gym: Gym, rule: AutomationRule, today: date | None = None) -> int:
    """Run one rule for the current tenant. Returns how many notifications were queued."""
    today = today or date.today()
    queued = 0
    for member, extra, suffix in _targets(db, rule, today):
        context = _context(gym, member, **extra)
        message = render_template(rule.template, **context)
        notification = notifications.enqueue(
            db, member, rule.channel, message, category=rule.trigger.value,
            rule_id=rule.id, dedup_key=f"rule:{rule.id}:{suffix}",
        )
        if notification:
            queued += 1
            if rule.n8n_workflow:
                n8n.trigger(rule.trigger.value, {"gym_id": str(gym.id), "member_id": str(member.id),
                                                 "message": message, **{k: str(v) for k, v in extra.items()}},
                            workflow=rule.n8n_workflow)
    return queued


def run_gym_rules(db: Session, gym: Gym, triggers: set[AutomationTrigger] | None = None,
                  today: date | None = None) -> dict[str, int]:
    """Run all active rules for one gym (caller must have set the tenant)."""
    results: dict[str, int] = {}
    for rule in TenantRepository(AutomationRule, db).list(AutomationRule.is_active.is_(True), limit=500):
        if triggers and rule.trigger not in triggers:
            continue
        results[rule.name] = run_rule(db, gym, rule, today)
    return results


def run_all_gyms(db: Session, triggers: set[AutomationTrigger] | None = None,
                 today: date | None = None) -> int:
    total = 0
    for gym in db.scalars(select(Gym).where(Gym.is_active.is_(True))).all():
        with tenant_scope(gym.id):
            try:
                total += sum(run_gym_rules(db, gym, triggers, today).values())
            except Exception:  # one gym's bad template must not stop the others
                db.rollback()
                logger.exception("Automation failed for gym %s", gym.id)
    return total

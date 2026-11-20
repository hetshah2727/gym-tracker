"""Daily job: expire lapsed memberships and queue expiry reminders.

Run on a schedule (ENABLE_SCHEDULER=true, cron, or an n8n Cron node):
    python -m app.workers.expiry_worker
"""
import logging
from datetime import date

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.database.models import Member, Membership
from app.database.models.enums import AutomationTrigger, MembershipStatus, MemberStatus
from app.database.session import SessionLocal
from app.modules.automation.service import run_all_gyms

logger = logging.getLogger(__name__)


def expire_memberships(db: Session, today: date | None = None) -> int:
    today = today or date.today()
    lapsed = db.scalars(select(Membership).where(Membership.status == MembershipStatus.ACTIVE,
                                                 Membership.end_date < today)).all()
    member_ids = {m.member_id for m in lapsed}
    for membership in lapsed:
        membership.status = MembershipStatus.EXPIRED
    db.flush()
    # A member is only "expired" if they have no other active membership (e.g. an early renewal).
    still_active = set(db.scalars(select(Membership.member_id).where(
        Membership.member_id.in_(member_ids), Membership.status == MembershipStatus.ACTIVE)).all())
    to_expire = member_ids - still_active
    if to_expire:
        db.execute(update(Member).where(Member.id.in_(to_expire)).values(status=MemberStatus.EXPIRED))
    db.commit()
    return len(lapsed)


def run(today: date | None = None) -> dict:
    with SessionLocal() as db:
        expired = expire_memberships(db, today)
        queued = run_all_gyms(db, {AutomationTrigger.MEMBERSHIP_EXPIRING, AutomationTrigger.MEMBERSHIP_EXPIRED,
                                   AutomationTrigger.BIRTHDAY, AutomationTrigger.INACTIVE_MEMBER}, today)
    logger.info("expiry_worker: expired=%s reminders_queued=%s", expired, queued)
    return {"expired": expired, "queued": queued}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())

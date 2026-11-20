"""Daily job: mark unpaid fees overdue and queue payment reminders.

    python -m app.workers.payment_worker
"""
import logging
from datetime import date

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.database.models import Payment
from app.database.models.enums import AutomationTrigger, PaymentStatus
from app.database.session import SessionLocal
from app.modules.automation.service import run_all_gyms

logger = logging.getLogger(__name__)


def mark_overdue(db: Session, today: date | None = None) -> int:
    today = today or date.today()
    result = db.execute(update(Payment).where(Payment.status == PaymentStatus.PENDING, Payment.due_date < today)
                        .values(status=PaymentStatus.OVERDUE))
    db.commit()
    return result.rowcount or 0


def run(today: date | None = None) -> dict:
    with SessionLocal() as db:
        overdue = mark_overdue(db, today)
        queued = run_all_gyms(db, {AutomationTrigger.PAYMENT_DUE}, today)
    logger.info("payment_worker: overdue=%s reminders_queued=%s", overdue, queued)
    return {"overdue": overdue, "queued": queued}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())

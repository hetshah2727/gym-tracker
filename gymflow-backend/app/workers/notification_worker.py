"""Frequent job (every minute or so): deliver queued notifications.

    python -m app.workers.notification_worker
"""
import logging

from app.database.session import SessionLocal
from app.modules.notifications.service import send_due

logger = logging.getLogger(__name__)


def run() -> int:
    with SessionLocal() as db:
        sent = send_due(db)
    if sent:
        logger.info("notification_worker: processed=%s", sent)
    return sent


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())

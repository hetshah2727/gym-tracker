"""1st of every month: email each gym owner last month's report (idempotent per gym and month).

    python -m app.workers.monthly_worker
"""
import logging

from sqlalchemy import select

from app.core import entitlements
from app.core.tenant_context import tenant_scope
from app.database.models import Gym
from app.database.session import SessionLocal
from app.modules.growth import owner_report

logger = logging.getLogger(__name__)


def run(month: str | None = None) -> dict:
    totals = {"gyms": 0, "emailed": 0, "failed": 0}
    with SessionLocal() as db:
        for gym in db.scalars(select(Gym).where(Gym.is_active.is_(True))).all():
            with tenant_scope(gym.id):
                try:
                    if (gym.settings or {}).get("is_demo") or not entitlements.resolve(db, gym.id).has("basic_reports"):
                        continue
                    report = owner_report.build(db, month)
                    sent_key = f"owner_report_sent_{report['month']}"
                    if (gym.settings or {}).get(sent_key):
                        continue
                    sent = owner_report.email_owners(db, report)
                    if sent:
                        gym.settings = {**(gym.settings or {}), sent_key: True}
                        db.commit()
                    totals["gyms"] += 1
                    totals["emailed"] += sent
                except Exception:  # one gym's failure must not stop the others
                    db.rollback()
                    totals["failed"] += 1
                    logger.exception("monthly_worker failed for gym %s", gym.id)
    logger.info("monthly_worker: %s", totals)
    return totals


def reset_demo() -> None:
    """Nightly: put the public demo gym back to its starting state so every visitor sees the same story."""
    from app.demo import ironcore

    with SessionLocal() as db:
        try:
            ironcore.reset(db)
        except Exception:
            db.rollback()
            logger.exception("demo reset failed")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())

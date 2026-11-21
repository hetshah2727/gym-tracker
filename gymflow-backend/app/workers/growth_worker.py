"""Daily growth job for every gym (idempotent - safe to re-run):

* Workflow 4: past trials with no attendance -> pending review + task (never auto no-show)
* Workflow 5/6: renewal, expired, outstanding/failed payment and lead opportunities
* Workflow 9: daily growth summary report (one per gym per day)

    python -m app.workers.growth_worker
"""
import logging
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import entitlements
from app.core.tenant_context import tenant_scope
from app.database.models import Gym
from app.database.session import SessionLocal
from app.modules.growth.reports import build_report
from app.modules.recovery.service import sync_all
from app.modules.trials.service import flag_pending_reviews
from app.services import events

logger = logging.getLogger(__name__)


def run_for_gym(db: Session, gym: Gym, today: date | None = None) -> dict:
    today = today or date.today()
    result = {"pending_trial_reviews": flag_pending_reviews(db)}
    result.update(sync_all(db, today))
    if entitlements.resolve(db, gym.id).has("basic_reports"):
        report = build_report(db, "daily_growth", generated_by="system", today=today, dedup=True)
        result["daily_report"] = str(report.id)
    events.emit(db, "worker.growth_daily", actor="system", payload={k: v for k, v in result.items()})
    return result


def run(today: date | None = None) -> dict:
    totals = {"gyms": 0, "failed": 0}
    with SessionLocal() as db:
        for gym in db.scalars(select(Gym).where(Gym.is_active.is_(True))).all():
            with tenant_scope(gym.id):
                try:
                    run_for_gym(db, gym, today)
                    totals["gyms"] += 1
                except Exception:  # one gym's failure must not stop the others
                    db.rollback()
                    totals["failed"] += 1
                    logger.exception("growth_worker failed for gym %s", gym.id)
    logger.info("growth_worker: %s", totals)
    return totals


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print(run())

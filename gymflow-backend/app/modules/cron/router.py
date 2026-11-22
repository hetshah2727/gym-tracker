"""Scheduled jobs over HTTP, for hosts without a long-running process (e.g. Vercel Cron).

Vercel calls these with ``Authorization: Bearer $CRON_SECRET``. Every job is idempotent, so a retry or a manual
run never double-messages anyone. ``/cron/setup`` runs the database migrations (and optionally seeds the demo)
once after the first deploy.
"""
import hmac
import logging
from datetime import date

from fastapi import APIRouter, Header, HTTPException, Query, status

from app.core.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/cron", tags=["Scheduled jobs"], include_in_schema=False)


def _authorize(authorization: str | None) -> None:
    expected = f"Bearer {settings.CRON_SECRET}" if settings.CRON_SECRET else None
    if not expected or not authorization or not hmac.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Not Found")  # don't advertise the endpoint


@router.get("/daily")
def daily(authorization: str | None = Header(None)):
    """Once a day: expire memberships, mark overdue fees, sync recovery, send queued messages; monthly report
    on the 1st; nightly demo reset when the public demo is on."""
    _authorize(authorization)
    from app.workers import expiry_worker, growth_worker, monthly_worker, notification_worker, payment_worker

    out: dict = {}
    for name, job in (("expiry", expiry_worker.run), ("payments", payment_worker.run), ("growth", growth_worker.run),
                      ("notifications", notification_worker.run)):
        try:
            out[name] = job()
        except Exception as exc:  # noqa: BLE001 - keep going; each job logs its own details
            logger.exception("cron job %s failed", name)
            out[name] = f"failed: {type(exc).__name__}"
    if date.today().day == 1:
        out["owner_report"] = monthly_worker.run()
    if settings.DEMO_LOGIN_ENABLED:
        monthly_worker.reset_demo()
        out["demo_reset"] = True
    return out


@router.get("/notifications")
def notifications(authorization: str | None = Header(None)):
    """Deliver queued WhatsApp/SMS/email notifications (schedule as often as your plan allows)."""
    _authorize(authorization)
    from app.workers import notification_worker

    return {"sent": notification_worker.run()}


@router.get("/setup")
def setup(authorization: str | None = Header(None), seed: bool = Query(False)):
    """Run database migrations to the latest version; ``?seed=true`` also creates the admin + demo gym."""
    _authorize(authorization)
    from pathlib import Path

    from alembic import command
    from alembic.config import Config

    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "migrations"))
    cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    command.upgrade(cfg, "head")
    result: dict = {"migrated": True}
    if seed:
        from app import seed as seed_module

        seed_module.main()
        result["seeded"] = True
    return result

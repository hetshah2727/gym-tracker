"""In-process scheduler (enable with ENABLE_SCHEDULER=true on exactly one API instance)."""
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.workers import expiry_worker, growth_worker, monthly_worker, notification_worker, payment_worker


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(expiry_worker.run, "cron", hour=9, minute=0, id="expiry")
    scheduler.add_job(payment_worker.run, "cron", hour=10, minute=0, id="payments")
    # After expiry/payment jobs so their status changes feed the recovery sync and daily report.
    scheduler.add_job(growth_worker.run, "cron", hour=10, minute=30, id="growth")
    scheduler.add_job(notification_worker.run, "interval", minutes=1, id="notifications")
    scheduler.add_job(monthly_worker.run, "cron", day=1, hour=9, minute=15, id="owner_report")
    if settings.DEMO_LOGIN_ENABLED:  # keep the public demo gym fresh for every visitor
        scheduler.add_job(monthly_worker.reset_demo, "cron", hour=3, minute=0, id="demo_reset")
    return scheduler

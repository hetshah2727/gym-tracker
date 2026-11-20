"""In-process scheduler (enable with ENABLE_SCHEDULER=true on exactly one API instance)."""
from apscheduler.schedulers.background import BackgroundScheduler

from app.workers import expiry_worker, notification_worker, payment_worker


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(expiry_worker.run, "cron", hour=9, minute=0, id="expiry")
    scheduler.add_job(payment_worker.run, "cron", hour=10, minute=0, id="payments")
    scheduler.add_job(notification_worker.run, "interval", minutes=1, id="notifications")
    return scheduler

"""Queue and deliver member notifications over WhatsApp / voice / SMS / email."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.models import Member, Notification
from app.database.models.enums import Channel, NotificationStatus
from app.database.repositories.base import TenantRepository
from app.integrations.base import SendResult
from app.integrations.voice import client as voice
from app.integrations.whatsapp import client as whatsapp

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 3


def recipient_for(member: Member, channel: Channel) -> str | None:
    return member.email if channel == Channel.EMAIL else member.phone


def enqueue(db: Session, member: Member, channel: Channel, message: str, *, category: str = "general",
            rule_id: uuid.UUID | None = None, dedup_key: str | None = None,
            scheduled_for: datetime | None = None) -> Notification | None:
    """Queue a message for the current gym. Returns None if it is a duplicate or undeliverable."""
    repo = TenantRepository(Notification, db)
    if dedup_key and repo.count(Notification.dedup_key == dedup_key):
        return None
    recipient = recipient_for(member, channel)
    if not recipient:
        return None
    return repo.create(
        member_id=member.id, rule_id=rule_id, channel=channel, recipient=recipient, message=message,
        category=category, dedup_key=dedup_key, scheduled_for=scheduled_for or datetime.now(timezone.utc),
    )


def _deliver(notification: Notification) -> SendResult:
    if notification.channel == Channel.WHATSAPP:
        return whatsapp.send_text(notification.recipient, notification.message)
    if notification.channel == Channel.VOICE:
        return voice.place_call(notification.recipient, notification.message,
                                {"notification_id": str(notification.id)})
    # SMS / email providers are not wired up yet; log so flows can be tested.
    logger.info("[%s:dev] to %s: %s", notification.channel.value, notification.recipient, notification.message)
    return SendResult(ok=True, provider_message_id=f"dev-{uuid.uuid4()}")


def dispatch(db: Session, notification: Notification) -> Notification:
    result = _deliver(notification)
    notification.attempts += 1
    if result.ok:
        notification.status = NotificationStatus.SENT
        notification.sent_at = datetime.now(timezone.utc)
        notification.provider_message_id = result.provider_message_id
        notification.error = None
    else:
        notification.error = result.error
        if notification.attempts >= MAX_ATTEMPTS:
            notification.status = NotificationStatus.FAILED
    db.commit()
    return notification


def send_due(db: Session, limit: int = 200) -> int:
    """Deliver queued notifications across all gyms (used by the notification worker)."""
    due = db.scalars(
        select(Notification)
        .where(Notification.status == NotificationStatus.QUEUED,
               Notification.scheduled_for <= datetime.now(timezone.utc))
        .order_by(Notification.scheduled_for)
        .limit(limit)
    ).all()
    for notification in due:
        dispatch(db, notification)
    return len(due)

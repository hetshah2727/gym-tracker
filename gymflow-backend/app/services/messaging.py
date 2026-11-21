"""Policy-aware outbound messaging to leads.

WhatsApp rules enforced here (so no workflow or agent can bypass them):
* a lead who opted out (replied STOP) is never messaged;
* inside the 24-hour customer-service window (lead messaged us recently) a free-form reply is allowed;
* outside it, a business-initiated message needs the lead's opt-in AND an approved template configured
  for that message category in ``gym.settings["whatsapp_templates"]``;
* otherwise nothing is sent: a follow-up task with the drafted message is created for staff.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import FollowUpTask, Gym, Lead, Notification
from app.database.models.enums import Channel, Priority, TaskKind
from app.database.repositories.base import TenantRepository
from app.modules.notifications import service as notifications

SESSION_WINDOW = timedelta(hours=24)


@dataclass
class Outcome:
    status: str            # queued | drafted | blocked | duplicate
    reason: str
    notification: Notification | None = None
    task: FollowUpTask | None = None


def _aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def in_session_window(lead: Lead, now: datetime | None = None) -> bool:
    last = _aware(lead.last_inbound_at)
    return bool(last and (now or datetime.now(timezone.utc)) - last <= SESSION_WINDOW)


def send_to_lead(db: Session, lead: Lead, text: str, *, category: str, template_params: list[str] | None = None,
                 scheduled_for: datetime | None = None, dedup_key: str | None = None,
                 draft_title: str | None = None, due_at: datetime | None = None) -> Outcome:
    """Send (queue) a WhatsApp message to a lead if policy allows, else draft it for staff. Flushes only."""
    from app.modules.crm.service import create_task  # local import: crm depends on this module

    if lead.opted_out:
        return Outcome("blocked", "Lead opted out of messages")
    if not lead.phone:
        return Outcome("blocked", "Lead has no phone number")

    gym = db.get(Gym, get_current_gym_id())
    template = ((gym.settings or {}).get("whatsapp_templates") or {}).get(category)
    send_time = scheduled_for or datetime.now(timezone.utc)
    if in_session_window(lead, send_time) and scheduled_for is None:
        n = notifications.enqueue_raw(db, lead.phone, Channel.WHATSAPP, text, category=category,
                                      lead_id=lead.id, dedup_key=dedup_key)
        return Outcome("queued" if n else "duplicate", "Within the 24-hour session window", n)
    if lead.whatsapp_opt_in and template:
        n = notifications.enqueue_raw(db, lead.phone, Channel.WHATSAPP, text, category=category, lead_id=lead.id,
                                      dedup_key=dedup_key, scheduled_for=scheduled_for,
                                      template_name=template, template_params=template_params or [lead.name])
        return Outcome("queued" if n else "duplicate", f"Approved template '{template}'", n)

    reason = ("No WhatsApp opt-in from this lead" if not lead.whatsapp_opt_in
              else f"No approved WhatsApp template configured for '{category}'")
    task = create_task(db, title=draft_title or f"Send message to {lead.name}", kind=TaskKind.FOLLOW_UP,
                       lead_id=lead.id, priority=Priority.MEDIUM, due_at=due_at or send_time, source="workflow",
                       description=f"Not sent automatically: {reason}. Send it yourself (call/WhatsApp).",
                       draft_message=text, dedup_key=f"draft:{dedup_key}" if dedup_key else None)
    return Outcome("drafted", reason, task=task)


__all__ = ["Outcome", "in_session_window", "send_to_lead", "TenantRepository"]

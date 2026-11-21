"""WhatsApp Cloud API webhooks: verification, inbound messages (-> AI sales agent), delivery receipts.

* Every POST must carry a valid X-Hub-Signature-256 (HMAC-SHA256 of the body with WHATSAPP_APP_SECRET).
* The gym is identified by the receiving phone_number_id, mapped in IntegrationConnection(provider="whatsapp").
* Message ids are de-duplicated (Meta retries deliveries).
* "STOP" / "UNSUBSCRIBE" opts the contact out; "START" opts back in.
"""
import hashlib
import hmac
import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.agents import runtime
from app.core import entitlements
from app.core.config import settings
from app.core.tenant_context import tenant_scope
from app.database.models import IntegrationConnection, Lead, Notification, WebhookEvent
from app.database.models.enums import ConnectionStatus, ConversationStatus, LeadSource, NotificationStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.integrations.whatsapp import client as whatsapp
from app.modules.crm import service as crm

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/webhooks/whatsapp", tags=["WhatsApp webhooks"])

STOP_WORDS = {"stop", "unsubscribe", "stop all", "cancel"}
START_WORDS = {"start", "subscribe"}


def verify_signature(raw: bytes, signature: str | None) -> bool:
    if not settings.WHATSAPP_APP_SECRET or not signature or not signature.startswith("sha256="):
        return False
    expected = hmac.new(settings.WHATSAPP_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.split("=", 1)[1])


@router.get("", response_class=PlainTextResponse)
def verify(mode: str = Query(None, alias="hub.mode"), token: str = Query(None, alias="hub.verify_token"),
           challenge: str = Query(None, alias="hub.challenge")):
    if mode == "subscribe" and settings.WHATSAPP_VERIFY_TOKEN and token and \
            hmac.compare_digest(token, settings.WHATSAPP_VERIFY_TOKEN):
        return challenge or ""
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Verification failed")


@router.post("")
async def receive(request: Request, x_hub_signature_256: str | None = Header(None), db: Session = Depends(get_db)):
    raw = await request.body()
    if not verify_signature(raw, x_hub_signature_256):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid signature")
    body = json.loads(raw or b"{}")
    handled = 0
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value") or {}
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id")
            conn = db.scalar(select(IntegrationConnection).where(
                IntegrationConnection.provider == "whatsapp", IntegrationConnection.external_id == phone_number_id,
                IntegrationConnection.status == ConnectionStatus.CONNECTED))
            if conn is None:
                logger.info("WhatsApp webhook for unmapped number %s ignored", phone_number_id)
                continue
            with tenant_scope(conn.gym_id):
                for st in value.get("statuses", []):
                    _status_update(db, st)
                contacts = {c.get("wa_id"): (c.get("profile") or {}).get("name") for c in value.get("contacts", [])}
                for msg in value.get("messages", []):
                    handled += _inbound(db, conn, msg, contacts.get(msg.get("from")))
    return {"status": "ok", "handled": handled}


def _seen(db: Session, gym_id, event_id: str, kind: str) -> bool:
    try:
        db.add(WebhookEvent(provider="whatsapp", event_id=event_id, gym_id=gym_id, event_type=kind))
        db.commit()
        return False
    except IntegrityError:
        db.rollback()
        return True


def _status_update(db: Session, st: dict) -> None:
    n = TenantRepository(Notification, db).first(Notification.provider_message_id == st.get("id"))
    if n is None:
        return
    n.delivery_status = st.get("status")
    if st.get("status") == "failed":
        n.status = NotificationStatus.FAILED
        n.error = json.dumps(st.get("errors", []))[:500]
    db.commit()


def _inbound(db: Session, conn: IntegrationConnection, msg: dict, profile_name: str | None) -> int:
    msg_id, sender = msg.get("id"), msg.get("from")
    if not msg_id or not sender or _seen(db, conn.gym_id, msg_id, "message"):
        return 0
    text = ((msg.get("text") or {}).get("body") or (msg.get("button") or {}).get("text")
            or ((msg.get("interactive") or {}).get("button_reply") or {}).get("title") or "").strip()
    key = crm.phone_key(sender)
    lead = TenantRepository(Lead, db).first(Lead.phone_key == key, order_by=Lead.created_at.desc())
    lowered = text.lower()
    if lowered in STOP_WORDS:
        if lead:
            lead.opted_out = True
            crm.record_interaction(db, lead, "whatsapp", text, direction="in", data={"opt_out": True})
            db.commit()
        whatsapp.send_text(sender, "You've been unsubscribed. Reply START to receive messages again.")
        return 1
    if lowered in START_WORDS and lead:
        lead.opted_out, lead.whatsapp_opt_in = False, True
        db.commit()
    if not text:
        text = f"[{msg.get('type', 'message')} received]"

    conv = runtime.get_or_create_conversation(db, agent_key="lead_conversion", channel="whatsapp", external_ref=sender)
    if lead and not conv.lead_id:
        conv.lead_id = lead.id
        db.commit()
    if lead is None:
        attribution = crm.Attribution(source=LeadSource.WHATSAPP.value, method="declared",
                                      evidence={"channel": "whatsapp_inbound"})
        lead, _ = crm.capture_lead(db, crm.LeadInput(name=profile_name or "WhatsApp contact", phone=sender,
                                                     whatsapp_opt_in=True), attribution, actor="webhook",
                                   channel_note="First WhatsApp message received")
        conv.lead_id = lead.id
        db.commit()
    lead.last_inbound_at = datetime.now(timezone.utc)
    db.commit()

    if not entitlements.resolve(db).has("ai_sales_agent"):
        crm.record_interaction(db, lead, "whatsapp", text, direction="in")
        db.commit()
        return 1
    reply = runtime.run_agent(db, agent_key="lead_conversion", message=text, channel="whatsapp", conversation=conv,
                              provider_message_id=msg_id)
    if reply.text and reply.status in ("ok", "limited"):  # includes the hand-off notice on escalation
        result = whatsapp.send_text(sender, reply.text)  # inside the 24h window: they just wrote to us
        if not result.ok:
            logger.warning("WhatsApp reply failed for gym %s: %s", conn.gym_id, result.error)
    return 1

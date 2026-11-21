"""Integration health + connection management (Google, WhatsApp)."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import entitlements
from app.core.config import settings
from app.core.permissions import GYM_STAFF, tenant_user
from app.core.tenant_context import get_current_gym_id, tenant_scope
from app.database.models import Gym, IntegrationConnection, Notification, User
from app.database.models.enums import Channel, ConnectionStatus, NotificationStatus, Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.integrations.ai import claude
from app.integrations.payments import razorpay
from app.integrations.voice import client as voice
from app.integrations.whatsapp import client as whatsapp
from app.modules.integrations import google

router = APIRouter(prefix="/integrations", tags=["Integrations"])
staff = tenant_user(*GYM_STAFF)
owner = tenant_user(Role.GYM_OWNER)

# live_tested | configured_not_tested | simulation | not_configured | not_implemented
def _state(configured: bool, *, connected: bool | None = None, tested: bool = False) -> str:
    if not configured:
        return "simulation" if connected is None else "not_configured"
    if connected is False:
        return "not_configured"
    return "live_tested" if tested else "configured_not_tested"


@router.get("/health")
def health(db: Session = Depends(get_db), _=Depends(staff)):
    gym = db.get(Gym, get_current_gym_id())
    conns = {c.provider: c for c in TenantRepository(IntegrationConnection, db).list(limit=20)}
    sent = TenantRepository(Notification, db)
    wa_sent = sent.count(Notification.channel == Channel.WHATSAPP, Notification.status == NotificationStatus.SENT,
                         Notification.provider_message_id.not_like("dev-%"))
    wa_conn = conns.get("whatsapp")
    items = []
    for key in ("google_search_console", "google_business_profile"):
        c = conns.get(key)
        connected = bool(c and c.status == ConnectionStatus.CONNECTED)
        items.append({
            "key": key, "name": google.PROVIDERS[key]["label"],
            "state": "not_configured" if not google.is_configured() else
            ("live_tested" if connected and c.last_sync_at and not c.last_error else
             "configured_not_tested" if connected else "not_configured"),
            "connection": c.status.value if c else "not_connected", "account": c.account_label if c else None,
            "last_sync_at": c.last_sync_at.isoformat() if c and c.last_sync_at else None,
            "last_error": c.last_error if c else None,
            "detail": "Server OAuth credentials missing (GOOGLE_CLIENT_ID/SECRET)." if not google.is_configured()
            else None, "action": "connect"})
    items += [
        {"key": "whatsapp", "name": "WhatsApp Cloud API",
         "state": ("live_tested" if whatsapp.is_configured() and wa_sent else
                   "configured_not_tested" if whatsapp.is_configured() else "simulation"),
         "connection": wa_conn.status.value if wa_conn else "not_connected",
         "account": wa_conn.account_label if wa_conn else None,
         "detail": ("Outbound messages are only logged (no credentials)." if not whatsapp.is_configured() else
                    f"{wa_sent} messages delivered to the provider.")
         + ("" if wa_conn else " Inbound replies need this gym's phone number id mapped below."),
         "inbound_webhook": f"{settings.PUBLIC_API_URL.rstrip('/')}/webhooks/whatsapp",
         "webhook_ready": bool(settings.WHATSAPP_APP_SECRET and settings.WHATSAPP_VERIFY_TOKEN),
         "templates": (gym.settings or {}).get("whatsapp_templates", {})},
        {"key": "razorpay", "name": "Razorpay payments",
         "state": _state(razorpay.is_configured()),
         "detail": ("Orders get fake ids; online payments can't be confirmed." if not razorpay.is_configured()
                    else "Webhook secret " + ("set" if settings.RAZORPAY_WEBHOOK_SECRET else "MISSING"))
         + " Only signed webhooks mark online payments paid."},
        {"key": "ai", "name": "Claude AI", "state": _state(claude.is_configured()),
         "detail": settings.AI_MODEL if claude.is_configured() else
         "Agents use the rule-based engine; content uses templates."},
        {"key": "n8n", "name": "n8n (optional automations)",
         "state": "configured_not_tested" if settings.N8N_WEBHOOK_BASE_URL else "not_configured",
         "detail": "Core workflows run inside GymFlow; n8n only receives events."},
        {"key": "keyword_provider", "name": "Keyword metrics provider", "state": "not_implemented",
         "detail": "No provider adapter ships yet, so keywords are labelled suggestions with no volume data."},
        {"key": "ai_visibility_provider", "name": "AI answer monitoring provider", "state": "not_implemented",
         "detail": "Visibility is tracked by manual research runs, clearly labelled."},
        {"key": "voice", "name": "AI voice calls (deprioritised)", "state": _state(voice.is_configured())},
        {"key": "email_sms", "name": "Email / SMS delivery", "state": "not_implemented",
         "detail": "Messages on these channels are logged only."},
    ]
    return {"integrations": items, "legend": {
        "live_tested": "Connected and has completed real calls", "configured_not_tested": "Credentials set, no successful sync yet",
        "simulation": "Runs in dev mode - actions are logged, not sent", "not_configured": "Needs setup",
        "not_implemented": "Not available in this version"}}


# ---------------------------------------------------------------- Google OAuth

class SelectIn(BaseModel):
    external_id: str = Field(min_length=3, max_length=255)


@router.get("/google/{provider}/status")
def google_status(provider: str, db: Session = Depends(get_db), _=Depends(staff)):
    if provider not in google.PROVIDERS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown provider")
    c = google.connection(db, provider)
    return {"provider": provider, "configured": google.is_configured(), "status": c.status.value if c else "not_connected",
            "account": c.account_label, "external_id": c.external_id, "choices": (c.settings or {}).get("available", []),
            "last_sync_at": c.last_sync_at, "last_error": c.last_error} if c else \
        {"provider": provider, "configured": google.is_configured(), "status": "not_connected", "choices": []}


@router.post("/google/{provider}/connect")
def google_connect(provider: str, user: User = Depends(owner)):
    return {"url": google.authorization_url(provider, user.id)}


@router.get("/google/callback", include_in_schema=False)
def google_callback(state: str, code: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    data = google.decode_state(state)
    target = f"{settings.FRONTEND_URL.rstrip('/')}/dashboard/integrations"
    if error or not code:
        return RedirectResponse(f"{target}?google_error={error or 'cancelled'}")
    try:
        user = db.get(User, uuid.UUID(data["user_id"]))
        gym_id = uuid.UUID(data["gym_id"])
    except (KeyError, ValueError):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid OAuth state")
    if user is None or user.gym_id != gym_id or user.role != Role.GYM_OWNER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "OAuth state does not match a gym owner")
    with tenant_scope(gym_id):
        google.exchange_code(db, data["provider"], code, user.id)
    return RedirectResponse(f"{target}?connected={data['provider']}")


@router.post("/google/{provider}/select")
def google_select(provider: str, data: SelectIn, db: Session = Depends(get_db), _=Depends(owner)):
    c = google.select(db, provider, data.external_id)
    return {"status": c.status.value, "account": c.account_label}


@router.delete("/google/{provider}")
def google_disconnect(provider: str, db: Session = Depends(get_db), _=Depends(owner)):
    google.disconnect(db, provider)
    return {"status": "not_connected"}


# ---------------------------------------------------------------- WhatsApp mapping & templates

class WhatsAppIn(BaseModel):
    phone_number_id: str = Field(min_length=5, max_length=64, pattern=r"^\d+$")
    display_number: str | None = Field(None, max_length=32)


class TemplatesIn(BaseModel):
    templates: dict[str, str] = Field(description="category -> approved template name")


@router.put("/whatsapp")
def map_whatsapp(data: WhatsAppIn, db: Session = Depends(get_db), user: User = Depends(owner)):
    taken = db.scalar(select(IntegrationConnection).where(IntegrationConnection.provider == "whatsapp",
                                                          IntegrationConnection.external_id == data.phone_number_id,
                                                          IntegrationConnection.gym_id != get_current_gym_id()))
    if taken:
        raise HTTPException(status.HTTP_409_CONFLICT, "That WhatsApp number is linked to another gym")
    c = google.connection(db, "whatsapp", create=True)
    c.external_id, c.account_label, c.connected_by_id = data.phone_number_id, data.display_number, user.id
    c.status = ConnectionStatus.CONNECTED
    db.commit()
    return {"status": c.status.value, "phone_number_id": c.external_id}


@router.put("/whatsapp/templates")
def whatsapp_templates(data: TemplatesIn, db: Session = Depends(get_db), _=Depends(owner)):
    allowed = {"trial_confirmation", "trial_reminder", "sales_follow_up", "renewal_reminder", "payment_reminder",
               "staff_reply", "lead_acknowledgement"}
    bad = set(data.templates) - allowed
    if bad:
        raise HTTPException(422, f"Unknown categories: {sorted(bad)}")
    gym = db.get(Gym, get_current_gym_id())
    gym.settings = {**(gym.settings or {}), "whatsapp_templates": data.templates}
    db.commit()
    return {"templates": data.templates}


__all__ = ["router", "datetime", "timezone", "entitlements", "Query"]

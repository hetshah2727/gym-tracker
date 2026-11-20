"""WhatsApp Cloud API (Meta) client.

When credentials are not configured (local development) messages are logged
instead of sent, so the rest of the system can be exercised end to end.
"""
import logging
import uuid

import httpx

from app.core.config import settings
from app.integrations.base import SendResult

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.WHATSAPP_PHONE_NUMBER_ID and settings.WHATSAPP_ACCESS_TOKEN)


def normalize_phone(phone: str, default_country_code: str = "91") -> str:
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = default_country_code + digits
    return digits


def _post(payload: dict) -> SendResult:
    if not is_configured():
        logger.info("[whatsapp:dev] %s", payload)
        return SendResult(ok=True, provider_message_id=f"dev-{uuid.uuid4()}")
    url = f"{settings.WHATSAPP_API_URL}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    try:
        resp = httpx.post(
            url,
            json={"messaging_product": "whatsapp", **payload},
            headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}"},
            timeout=15,
        )
        resp.raise_for_status()
        message_id = resp.json().get("messages", [{}])[0].get("id")
        return SendResult(ok=True, provider_message_id=message_id)
    except httpx.HTTPError as exc:
        logger.warning("WhatsApp send failed: %s", exc)
        return SendResult(ok=False, error=str(exc))


def send_text(to: str, body: str) -> SendResult:
    return _post({"to": normalize_phone(to), "type": "text", "text": {"body": body}})


def send_template(to: str, template_name: str, params: list[str], language: str = "en") -> SendResult:
    """Send a pre-approved template (required for business-initiated messages)."""
    components = [{"type": "body", "parameters": [{"type": "text", "text": p} for p in params]}]
    return _post({
        "to": normalize_phone(to),
        "type": "template",
        "template": {"name": template_name, "language": {"code": language}, "components": components},
    })

"""AI voice-calling client.

Provider-agnostic: POSTs a call request (number + script) to the configured
voice provider. Swap the payload shape here for your provider of choice.
"""
import logging
import uuid

import httpx

from app.core.config import settings
from app.integrations.base import SendResult

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.VOICE_API_URL and settings.VOICE_API_KEY)


def place_call(to: str, script: str, metadata: dict | None = None) -> SendResult:
    if not is_configured():
        logger.info("[voice:dev] call %s: %s", to, script)
        return SendResult(ok=True, provider_message_id=f"dev-call-{uuid.uuid4()}")
    try:
        resp = httpx.post(
            f"{settings.VOICE_API_URL.rstrip('/')}/calls",
            json={"to": to, "script": script, "metadata": metadata or {}},
            headers={"Authorization": f"Bearer {settings.VOICE_API_KEY}"},
            timeout=20,
        )
        resp.raise_for_status()
        return SendResult(ok=True, provider_message_id=resp.json().get("id"))
    except httpx.HTTPError as exc:
        logger.warning("Voice call failed: %s", exc)
        return SendResult(ok=False, error=str(exc))

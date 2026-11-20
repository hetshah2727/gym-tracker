"""n8n workflow triggers.

GymFlow emits domain events (member.created, payment.paid, membership.created,
lead.created, ...) to n8n webhook nodes, so gym owners can add automations in
n8n without code changes here. Events are sent on a background thread so a
slow or unreachable n8n never delays an API response.
"""
import logging
from concurrent.futures import Future, ThreadPoolExecutor

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="n8n")


def _send(url: str, body: dict) -> bool:
    try:
        resp = httpx.post(url, json=body, timeout=10)
        resp.raise_for_status()
        return True
    except httpx.HTTPError as exc:
        logger.warning("n8n event %s failed: %s", body.get("event"), exc)
        return False


def trigger(event: str, payload: dict, workflow: str | None = None) -> Future | None:
    """POST ``payload`` to ``{N8N_WEBHOOK_BASE_URL}/{workflow or event}`` in the background."""
    if not settings.N8N_WEBHOOK_BASE_URL:
        logger.debug("[n8n:disabled] %s %s", event, payload)
        return None
    url = f"{settings.N8N_WEBHOOK_BASE_URL.rstrip('/')}/{workflow or event}"
    return _executor.submit(_send, url, {"event": event, "data": payload})

"""Shared business-event bus.

``emit()`` is the single place a business event is recorded. It
1. appends an EventLog row (feeds analytics, the Business Analyst and the audit trail),
2. runs in-process handlers registered with ``@on(...)`` (e.g. a paid payment closes recovery
   opportunities), each inside a savepoint so one failing handler cannot break the caller,
3. forwards the event to n8n (optional, fire-and-forget).

Core flows never depend on n8n: everything that must happen runs in the handlers.
"""
import logging
import uuid
from collections import defaultdict
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.models import EventLog
from app.integrations.n8n import client as n8n

logger = logging.getLogger(__name__)

Handler = Callable[[Session, dict], None]
_handlers: dict[str, list[Handler]] = defaultdict(list)
_loaded = False


def on(event_type: str) -> Callable[[Handler], Handler]:
    def register(fn: Handler) -> Handler:
        if fn not in _handlers[event_type]:
            _handlers[event_type].append(fn)
        return fn

    return register


def _load_handlers() -> None:
    global _loaded
    if not _loaded:
        _loaded = True
        import app.services.handlers  # noqa: F401  (registers @on handlers)


def emit(db: Session, event_type: str, *, entity_type: str | None = None, entity_id: uuid.UUID | None = None,
         payload: dict[str, Any] | None = None, actor: str = "user", actor_user_id: uuid.UUID | None = None,
         commit: bool = True) -> EventLog:
    _load_handlers()
    gym_id = get_current_gym_id()
    data = {k: (str(v) if isinstance(v, uuid.UUID) else v) for k, v in (payload or {}).items()}
    event = EventLog(gym_id=gym_id, event_type=event_type, entity_type=entity_type, entity_id=entity_id,
                     actor=actor, actor_user_id=actor_user_id, payload=data)
    db.add(event)
    db.flush()
    context = {**data, "gym_id": gym_id, "entity_id": entity_id, "event_id": event.id,
               "actor_user_id": actor_user_id}
    for handler in _handlers.get(event_type, []):
        try:
            with db.begin_nested():
                handler(db, context)
        except Exception:  # noqa: BLE001 - log and continue; the triggering action already succeeded
            logger.exception("Event handler %s failed for %s", handler.__name__, event_type)
    if commit:
        db.commit()
    n8n.trigger(event_type, {"gym_id": str(gym_id), "entity_id": str(entity_id) if entity_id else None, **data})
    return event

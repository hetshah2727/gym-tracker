"""Request-scoped tenant (gym) context.

Every gym is a tenant. The current gym id lives in a ContextVar so that
repositories scope every query to it automatically, keeping each gym's data
isolated from every other gym.
"""
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

_current_gym_id: ContextVar[uuid.UUID | None] = ContextVar("current_gym_id", default=None)


class TenantNotSetError(RuntimeError):
    pass


def set_current_gym_id(gym_id: uuid.UUID | None) -> None:
    _current_gym_id.set(gym_id)


def get_current_gym_id(required: bool = True) -> uuid.UUID | None:
    gym_id = _current_gym_id.get()
    if gym_id is None and required:
        raise TenantNotSetError("No gym (tenant) is set for this request")
    return gym_id


@contextmanager
def tenant_scope(gym_id: uuid.UUID) -> Iterator[None]:
    """Temporarily act as a given gym (used by background workers and webhooks)."""
    token = _current_gym_id.set(gym_id)
    try:
        yield
    finally:
        _current_gym_id.reset(token)

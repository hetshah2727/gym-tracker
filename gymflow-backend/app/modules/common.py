"""Helpers shared by feature modules."""
import re
import secrets
import uuid
from typing import Generic, TypeVar

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    offset: int
    limit: int


def get_or_404(repo, obj_id: uuid.UUID, name: str = "Resource"):
    obj = repo.get(obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{name} not found")
    return obj


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "gym"


def unique_slug(value: str, exists) -> str:
    """``exists(slug) -> bool``; appends a short random suffix until unique."""
    base = slugify(value)[:100]
    slug = base
    while exists(slug):
        slug = f"{base}-{secrets.token_hex(2)}"
    return slug


def render_template(template: str, **context) -> str:
    """str.format that leaves unknown placeholders untouched instead of raising."""

    class _Safe(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    return template.format_map(_Safe(**context))

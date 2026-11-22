"""Authentication dependencies and role-based access control."""
import uuid
from typing import Callable

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.core.tenant_context import set_current_gym_id
from app.database.models.enums import Role
from app.database.models.user import User
from app.database.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)

GYM_STAFF = (Role.GYM_OWNER, Role.GYM_MANAGER)
GYM_STAFF_AND_TRAINERS = (Role.GYM_OWNER, Role.GYM_MANAGER, Role.TRAINER)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        raise unauthorized
    if payload.get("purpose"):  # e.g. password-reset tokens can never be used to log in
        raise unauthorized
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise unauthorized
    return user


def require_roles(*roles: Role) -> Callable[..., User]:
    """Dependency: an authenticated user holding one of ``roles`` (any role if empty)."""

    def dependency(user: User = Depends(get_current_user)) -> User:
        if roles and user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this resource")
        return user

    return dependency


def tenant_user(*roles: Role) -> Callable[..., User]:
    """Dependency: a user acting inside one gym. Sets the tenant context.

    Gym users are always bound to their own gym. A platform admin may act on
    any gym by sending the ``X-Gym-ID`` header.

    This must be ``async``: FastAPI runs sync dependencies in a worker thread
    with a copied context, so a ContextVar set there would never reach the
    endpoint. An async dependency runs in the request's own context, which the
    (sync) endpoint then inherits.
    """

    async def dependency(
        user: User = Depends(get_current_user),
        x_gym_id: str | None = Header(default=None, alias="X-Gym-ID"),
    ) -> User:
        if user.role == Role.PLATFORM_ADMIN:
            if not x_gym_id:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "X-Gym-ID header is required")
            try:
                gym_id = uuid.UUID(x_gym_id)
            except ValueError:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid X-Gym-ID header")
        else:
            if roles and user.role not in roles:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "You do not have access to this resource")
            if user.gym_id is None:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "User is not attached to a gym")
            gym_id = user.gym_id
        set_current_gym_id(gym_id)
        return user

    return dependency


platform_admin = require_roles(Role.PLATFORM_ADMIN)

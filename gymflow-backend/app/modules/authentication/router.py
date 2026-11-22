from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import public_limit
from app.database.models import Gym

from app.core.permissions import get_current_user
from app.database.models import User
from app.database.session import get_db
from app.modules.authentication import service
from app.modules.authentication.schemas import (
    ForgotPasswordRequest, LoginRequest, RegisterGymRequest, ResetPasswordRequest, TokenResponse, UserOut,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_gym(data: RegisterGymRequest, db: Session = Depends(get_db)):
    """Sign up a new gym (tenant) and its owner account."""
    return service.register_gym(db, data)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return service.authenticate(db, data.email, data.password)


@router.post("/demo-login", response_model=TokenResponse)
def demo_login(db: Session = Depends(get_db), _=Depends(public_limit("demo-login", 10))):
    """One-click demo: a token for the IronCore demo owner. Only the flagged demo gym, only when enabled."""
    from app.demo.ironcore import DEMO_SLUG, OWNER

    if not settings.DEMO_LOGIN_ENABLED:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The demo is not available")
    gym = db.scalar(select(Gym).where(Gym.slug == DEMO_SLUG))
    user = db.scalar(select(User).where(User.email == OWNER[0]))
    if gym is None or not (gym.settings or {}).get("is_demo") or user is None or user.gym_id != gym.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "The demo is not available")
    return service.issue_token(user)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED,
             dependencies=[Depends(public_limit("forgot-password", 5))])
def forgot_password(data: ForgotPasswordRequest, db: Session = Depends(get_db)):
    """Emails a 30-minute reset link. Always 202 so the endpoint can't reveal which emails are registered."""
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if user is not None and user.is_active:
        service.send_reset_email(user)
    return {"detail": "If that email is registered, a reset link has been sent."}


@router.post("/reset-password", response_model=TokenResponse)
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db),
                   _=Depends(public_limit("reset-password", 10))):
    """Sets a new password from a valid reset link (each link works once) and logs the user in."""
    return service.reset_password(db, data.token, data.password)

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.permissions import get_current_user
from app.database.models import User
from app.database.session import get_db
from app.modules.authentication import service
from app.modules.authentication.schemas import (
    ForgotPasswordRequest, LoginRequest, RegisterGymRequest, TokenResponse, UserOut,
)

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_gym(data: RegisterGymRequest, db: Session = Depends(get_db)):
    """Sign up a new gym (tenant) and its owner account."""
    return service.register_gym(db, data)


@router.post("/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):
    return service.authenticate(db, data.email, data.password)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.post("/forgot-password", status_code=status.HTTP_202_ACCEPTED)
def forgot_password(data: ForgotPasswordRequest):
    # Always 202 so the endpoint can't be used to discover registered emails.
    # TODO: issue a short-lived reset token and email/WhatsApp it to the user.
    return {"detail": "If that email is registered, a reset link has been sent."}

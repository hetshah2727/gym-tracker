"""Symmetric encryption for secrets stored in the database (OAuth tokens)."""
import base64
import hashlib
import json

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings


def _fernet() -> Fernet:
    material = settings.TOKEN_ENCRYPTION_KEY or f"gymflow-tokens:{settings.SECRET_KEY}"
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest())
    return Fernet(key)


def encrypt_json(data: dict) -> str:
    return _fernet().encrypt(json.dumps(data).encode()).decode()


def decrypt_json(token: str | None) -> dict:
    if not token:
        return {}
    try:
        return json.loads(_fernet().decrypt(token.encode()))
    except (InvalidToken, ValueError):
        return {}

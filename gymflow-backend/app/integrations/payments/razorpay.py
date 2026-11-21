"""Razorpay: create orders for online fee payment and verify webhooks."""
import hashlib
import hmac
import uuid

import httpx

from app.core.config import settings

RAZORPAY_API = "https://api.razorpay.com/v1"


class PaymentGatewayError(RuntimeError):
    pass


def is_configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def create_order(amount: float, receipt: str, currency: str = "INR", notes: dict | None = None) -> dict:
    """Returns the Razorpay order (``id``, ``amount`` in paise, ``currency``)."""
    amount_paise = int(round(amount * 100))
    if not is_configured():
        return {"id": f"order_dev_{uuid.uuid4().hex[:14]}", "amount": amount_paise,
                "currency": currency, "receipt": receipt, "dev": True}
    try:
        resp = httpx.post(
            f"{RAZORPAY_API}/orders",
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            json={"amount": amount_paise, "currency": currency, "receipt": receipt, "notes": notes or {}},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise PaymentGatewayError(str(exc)) from exc


def create_payment_link(amount: float, reference_id: str, description: str, currency: str = "INR",
                        customer: dict | None = None, notes: dict | None = None) -> dict:
    """Hosted payment link (returns ``id`` and ``short_url``). Only call when configured."""
    if not is_configured():
        raise PaymentGatewayError("Razorpay is not configured")
    try:
        resp = httpx.post(
            f"{RAZORPAY_API}/payment_links",
            auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
            json={"amount": int(round(amount * 100)), "currency": currency, "reference_id": reference_id[:40],
                  "description": description[:2048], "customer": customer or {},
                  "notify": {"sms": False, "email": False}, "notes": notes or {}},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPError as exc:
        raise PaymentGatewayError(str(exc)) from exc


def verify_webhook_signature(raw_body: bytes, signature: str | None) -> bool:
    if not settings.RAZORPAY_WEBHOOK_SECRET or not signature:
        return False
    expected = hmac.new(settings.RAZORPAY_WEBHOOK_SECRET.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)

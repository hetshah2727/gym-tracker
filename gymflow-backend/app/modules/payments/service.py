"""Payment state changes shared by staff actions, memberships and verified gateway webhooks."""
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.database.models import Payment
from app.database.models.enums import PaymentMethod, PaymentStatus
from app.services import events


def mark_paid(db: Session, payment: Payment, method: PaymentMethod, reference: str | None = None,
              gateway_payment_id: str | None = None, verified_by: str = "manual",
              actor_user_id: uuid.UUID | None = None) -> Payment:
    """The only way a payment becomes PAID. Emits payment.paid, which closes recovery opportunities."""
    payment.status = PaymentStatus.PAID
    payment.method = method
    payment.paid_at = datetime.now(timezone.utc)
    payment.reference = reference or payment.reference
    payment.gateway_payment_id = gateway_payment_id or payment.gateway_payment_id
    payment.verified_by = verified_by
    payment.failure_reason = None
    events.emit(db, "payment.paid", entity_type="payment", entity_id=payment.id,
                actor="webhook" if verified_by == "gateway" else "user", actor_user_id=actor_user_id,
                payload={"member_id": payment.member_id, "amount": float(payment.amount),
                         "membership_id": payment.membership_id, "verified_by": verified_by})
    db.refresh(payment)
    return payment

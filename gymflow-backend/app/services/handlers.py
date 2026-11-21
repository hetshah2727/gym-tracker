"""In-process reactions to business events - the glue between modules.

Handlers run inside a savepoint (see events.emit) and must only flush, never commit.
"""
from datetime import date

from sqlalchemy.orm import Session

from app.database.models import Member, Payment
from app.database.models.enums import OpportunityType, PaymentStatus, Priority
from app.services.events import on


@on("payment.paid")
def close_recovery_on_payment(db: Session, ctx: dict) -> None:
    from app.modules.recovery.service import on_payment_paid

    payment = db.get(Payment, ctx["entity_id"])
    if payment is not None and payment.status == PaymentStatus.PAID:
        on_payment_paid(db, payment)


@on("payment.failed")
def open_failed_payment_opportunity(db: Session, ctx: dict) -> None:
    from app.modules.recovery.service import upsert_opportunity

    payment = db.get(Payment, ctx["entity_id"])
    member = db.get(Member, payment.member_id) if payment else None
    if payment is None or member is None:
        return
    upsert_opportunity(db, dedup_key=f"payment:{payment.id}", type=OpportunityType.FAILED_PAYMENT,
                       title=f"Failed payment: {member.full_name}",
                       reason=f"Payment attempt failed: {payment.failure_reason or 'unknown reason'}",
                       potential_revenue=float(payment.amount), member_id=member.id, payment_id=payment.id,
                       membership_id=payment.membership_id, priority=Priority.HIGH, due_date=date.today(),
                       next_action="Help member retry payment")

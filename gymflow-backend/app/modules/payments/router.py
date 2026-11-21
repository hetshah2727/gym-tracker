import json
import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import GYM_STAFF, tenant_user
from app.core.tenant_context import tenant_scope
from sqlalchemy.exc import IntegrityError

from app.database.models import Gym, Member, Payment, WebhookEvent
from app.database.models.enums import PaymentMethod, PaymentStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.integrations.payments import razorpay
from app.modules.common import ORMModel, Page, get_or_404
from app.modules.payments.service import mark_paid
from app.services import events

router = APIRouter(prefix="/payments", tags=["Payments"])


class PaymentOut(ORMModel):
    id: uuid.UUID
    member_id: uuid.UUID
    membership_id: uuid.UUID | None
    amount: float
    status: PaymentStatus
    method: PaymentMethod | None
    due_date: date | None
    paid_at: datetime | None
    reference: str | None
    gateway_order_id: str | None
    notes: str | None
    failure_reason: str | None = None
    verified_by: str | None = None
    created_at: datetime


class PaymentCreate(BaseModel):
    member_id: uuid.UUID
    amount: float = Field(gt=0)
    membership_id: uuid.UUID | None = None
    due_date: date | None = None
    paid: bool = True
    method: PaymentMethod | None = PaymentMethod.CASH
    reference: str | None = None
    notes: str | None = None


class MarkPaidRequest(BaseModel):
    method: PaymentMethod = PaymentMethod.CASH
    reference: str | None = None


class CheckoutOut(BaseModel):
    order_id: str
    amount: int
    currency: str
    key_id: str | None


_mark_paid = mark_paid  # backwards-compatible alias


@router.get("", response_model=Page[PaymentOut])
def list_payments(
    status_: PaymentStatus | None = Query(None, alias="status"),
    member_id: uuid.UUID | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    offset: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _=Depends(tenant_user(*GYM_STAFF)),
):
    filters = []
    if status_:
        filters.append(Payment.status == status_)
    if member_id:
        filters.append(Payment.member_id == member_id)
    if date_from:
        filters.append(Payment.created_at >= date_from)
    if date_to:
        filters.append(Payment.created_at < date_to)
    repo = TenantRepository(Payment, db)
    return Page(items=repo.list(*filters, offset=offset, limit=limit), total=repo.count(*filters),
                offset=offset, limit=limit)


@router.post("", response_model=PaymentOut, status_code=status.HTTP_201_CREATED)
def record_payment(data: PaymentCreate, db: Session = Depends(get_db), user=Depends(tenant_user(*GYM_STAFF))):
    get_or_404(TenantRepository(Member, db), data.member_id, "Member")
    payment = TenantRepository(Payment, db).create(
        member_id=data.member_id, membership_id=data.membership_id, amount=data.amount,
        due_date=data.due_date or date.today(), reference=data.reference, notes=data.notes,
        status=PaymentStatus.PENDING,
    )
    if data.paid:
        payment = mark_paid(db, payment, data.method or PaymentMethod.CASH, data.reference, actor_user_id=user.id)
    return payment


@router.post("/{payment_id}/mark-paid", response_model=PaymentOut)
def mark_paid_endpoint(payment_id: uuid.UUID, data: MarkPaidRequest, db: Session = Depends(get_db),
                       user=Depends(tenant_user(*GYM_STAFF))):
    payment = get_or_404(TenantRepository(Payment, db), payment_id, "Payment")
    if payment.status == PaymentStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment is already marked as paid")
    return mark_paid(db, payment, data.method, data.reference, actor_user_id=user.id)


@router.post("/{payment_id}/checkout", response_model=CheckoutOut)
def create_checkout(payment_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user())):
    """Create a Razorpay order so the member can pay online (UPI / card)."""
    repo = TenantRepository(Payment, db)
    payment = get_or_404(repo, payment_id, "Payment")
    if payment.status == PaymentStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment is already paid")
    gym = db.get(Gym, payment.gym_id)
    try:
        order = razorpay.create_order(float(payment.amount), receipt=str(payment.id)[:40],
                                      currency=gym.currency,
                                      notes={"gym_id": str(payment.gym_id), "payment_id": str(payment.id)})
    except razorpay.PaymentGatewayError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Payment gateway error: {exc}")
    repo.update(payment, {"gateway_order_id": order["id"]})
    return CheckoutOut(order_id=order["id"], amount=order["amount"], currency=order["currency"],
                       key_id=settings.RAZORPAY_KEY_ID)


@router.post("/webhooks/razorpay", include_in_schema=False)
async def razorpay_webhook(request: Request, x_razorpay_signature: str | None = Header(None),
                           x_razorpay_event_id: str | None = Header(None), db: Session = Depends(get_db)):
    """Signed webhooks are the only thing that can mark an online payment as paid (or failed)."""
    raw = await request.body()
    if not razorpay.verify_webhook_signature(raw, x_razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")
    event = json.loads(raw)
    kind = event.get("event")
    if kind not in ("payment.captured", "order.paid", "payment.failed", "payment_link.paid"):
        return {"status": "ignored"}
    payload = event.get("payload", {})
    entity = (payload.get("payment") or {}).get("entity") or {}
    payment = None
    if kind == "payment_link.paid":
        ref = ((payload.get("payment_link") or {}).get("entity") or {}).get("reference_id")
        try:
            payment = db.get(Payment, uuid.UUID(ref)) if ref else None
        except ValueError:
            payment = None
    elif entity.get("order_id"):
        # Webhooks arrive without a tenant; look the payment up by order id, then act as its gym.
        payment = db.scalar(select(Payment).where(Payment.gateway_order_id == entity.get("order_id")))
    if payment is None:
        return {"status": "unknown_order"}

    event_id = x_razorpay_event_id or f"{kind}:{entity.get('id')}"
    try:
        db.add(WebhookEvent(provider="razorpay", event_id=event_id, gym_id=payment.gym_id, event_type=kind))
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate"}

    with tenant_scope(payment.gym_id):
        if kind == "payment.failed":
            if payment.status != PaymentStatus.PAID:
                payment.status = PaymentStatus.FAILED
                payment.failed_at = datetime.now(timezone.utc)
                payment.failure_reason = (entity.get("error_description") or entity.get("error_reason")
                                          or "Payment failed")[:255]
                events.emit(db, "payment.failed", entity_type="payment", entity_id=payment.id, actor="webhook",
                            payload={"member_id": payment.member_id, "amount": float(payment.amount),
                                     "reason": payment.failure_reason})
            else:
                db.commit()
        elif payment.status != PaymentStatus.PAID:
            mark_paid(db, payment, PaymentMethod.ONLINE, gateway_payment_id=entity.get("id"), verified_by="gateway")
        else:
            db.commit()
    return {"status": "ok"}

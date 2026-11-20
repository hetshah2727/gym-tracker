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
from app.database.models import Gym, Member, Payment
from app.database.models.enums import PaymentMethod, PaymentStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.integrations.n8n import client as n8n
from app.integrations.payments import razorpay
from app.modules.common import ORMModel, Page, get_or_404

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


def _mark_paid(db: Session, payment: Payment, method: PaymentMethod, reference: str | None = None,
               gateway_payment_id: str | None = None) -> Payment:
    payment.status = PaymentStatus.PAID
    payment.method = method
    payment.paid_at = datetime.now(timezone.utc)
    payment.reference = reference or payment.reference
    payment.gateway_payment_id = gateway_payment_id or payment.gateway_payment_id
    db.commit()
    db.refresh(payment)
    n8n.trigger("payment.paid", {"payment_id": str(payment.id), "gym_id": str(payment.gym_id),
                                 "member_id": str(payment.member_id), "amount": float(payment.amount)})
    return payment


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
def record_payment(data: PaymentCreate, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    get_or_404(TenantRepository(Member, db), data.member_id, "Member")
    return TenantRepository(Payment, db).create(
        member_id=data.member_id, membership_id=data.membership_id, amount=data.amount,
        due_date=data.due_date or date.today(), reference=data.reference, notes=data.notes,
        status=PaymentStatus.PAID if data.paid else PaymentStatus.PENDING,
        method=data.method if data.paid else None,
        paid_at=datetime.now(timezone.utc) if data.paid else None,
    )


@router.post("/{payment_id}/mark-paid", response_model=PaymentOut)
def mark_paid(payment_id: uuid.UUID, data: MarkPaidRequest, db: Session = Depends(get_db),
              _=Depends(tenant_user(*GYM_STAFF))):
    payment = get_or_404(TenantRepository(Payment, db), payment_id, "Payment")
    if payment.status == PaymentStatus.PAID:
        raise HTTPException(status.HTTP_409_CONFLICT, "Payment is already marked as paid")
    return _mark_paid(db, payment, data.method, data.reference)


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
                           db: Session = Depends(get_db)):
    raw = await request.body()
    if not razorpay.verify_webhook_signature(raw, x_razorpay_signature):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid signature")
    event = json.loads(raw)
    if event.get("event") not in ("payment.captured", "order.paid"):
        return {"status": "ignored"}
    entity = event["payload"]["payment"]["entity"]
    # Webhooks arrive without a tenant; look the payment up by order id, then act as its gym.
    payment = db.scalar(select(Payment).where(Payment.gateway_order_id == entity.get("order_id")))
    if payment is None:
        return {"status": "unknown_order"}
    if payment.status != PaymentStatus.PAID:
        with tenant_scope(payment.gym_id):
            _mark_paid(db, payment, PaymentMethod.ONLINE, gateway_payment_id=entity.get("id"))
    return {"status": "ok"}

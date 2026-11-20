"""Platform-admin view of all tenants (gyms) and platform-level metrics."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import platform_admin
from app.database.models import (
    AffiliateConversion, Gym, GymSubscription, Member, Payment, SubscriptionPlan,
)
from app.database.models.enums import MemberStatus, PaymentStatus, SubscriptionStatus
from app.database.repositories.base import Repository
from app.database.session import get_db
from app.modules.common import get_or_404
from app.modules.gyms.schemas import GymOut

router = APIRouter(prefix="/platform", tags=["Platform admin"], dependencies=[Depends(platform_admin)])


class TenantSummary(GymOut):
    member_count: int = 0
    subscription_status: SubscriptionStatus | None = None
    plan_name: str | None = None


class GymStatusUpdate(BaseModel):
    is_active: bool


class PlatformStats(BaseModel):
    total_gyms: int
    active_gyms: int
    total_members: int
    active_members: int
    mrr: float
    subscriptions_by_status: dict[str, int]
    affiliate_platform_earnings: float
    gym_fee_volume_this_month: float


@router.get("/gyms", response_model=list[TenantSummary])
def list_gyms(search: str | None = None, offset: int = 0, limit: int = Query(50, le=200),
              db: Session = Depends(get_db)):
    stmt = select(Gym).order_by(Gym.created_at.desc()).offset(offset).limit(limit)
    if search:
        stmt = stmt.where(Gym.name.ilike(f"%{search}%"))
    gyms = db.scalars(stmt).all()
    counts = dict(db.execute(select(Member.gym_id, func.count()).group_by(Member.gym_id)).all())
    subs = {s.gym_id: s for s in db.scalars(select(GymSubscription)).all()}
    plans = {p.id: p.name for p in db.scalars(select(SubscriptionPlan)).all()}
    result = []
    for gym in gyms:
        item = TenantSummary.model_validate(gym)
        item.member_count = counts.get(gym.id, 0)
        if sub := subs.get(gym.id):
            item.subscription_status = sub.status
            item.plan_name = plans.get(sub.plan_id)
        result.append(item)
    return result


@router.patch("/gyms/{gym_id}", response_model=GymOut)
def set_gym_status(gym_id: uuid.UUID, data: GymStatusUpdate, db: Session = Depends(get_db)):
    """Suspend or reactivate a tenant."""
    repo = Repository(Gym, db)
    return repo.update(get_or_404(repo, gym_id, "Gym"), {"is_active": data.is_active})


@router.get("/integrations")
def integration_status():
    """Which third-party services are configured (never returns the secrets themselves)."""
    from app.core.config import settings
    from app.integrations.ai import diet_generator
    from app.integrations.payments import razorpay
    from app.integrations.voice import client as voice
    from app.integrations.whatsapp import client as whatsapp

    return [
        {"key": "ai", "name": "Claude (AI diet plans)", "configured": diet_generator.is_configured(),
         "detail": settings.AI_MODEL},
        {"key": "whatsapp", "name": "WhatsApp Cloud API", "configured": whatsapp.is_configured(), "detail": None},
        {"key": "voice", "name": "AI voice calling", "configured": voice.is_configured(), "detail": None},
        {"key": "razorpay", "name": "Razorpay payments", "configured": razorpay.is_configured(),
         "detail": "webhook secret set" if settings.RAZORPAY_WEBHOOK_SECRET else "webhook secret missing"},
        {"key": "n8n", "name": "n8n workflows", "configured": bool(settings.N8N_WEBHOOK_BASE_URL),
         "detail": settings.N8N_WEBHOOK_BASE_URL},
        {"key": "amazon", "name": "Amazon Associates", "configured": bool(settings.AMAZON_ASSOCIATE_TAG),
         "detail": settings.AMAZON_MARKETPLACE_DOMAIN},
    ]


@router.get("/stats", response_model=PlatformStats)
def platform_stats(db: Session = Depends(get_db)):
    month_start = date.today().replace(day=1)
    by_status = dict(db.execute(select(GymSubscription.status, func.count())
                                .group_by(GymSubscription.status)).all())
    mrr = db.scalar(
        select(func.coalesce(func.sum(SubscriptionPlan.price_monthly), 0))
        .select_from(GymSubscription).join(SubscriptionPlan, SubscriptionPlan.id == GymSubscription.plan_id)
        .where(GymSubscription.status == SubscriptionStatus.ACTIVE)
    )
    return PlatformStats(
        total_gyms=db.scalar(select(func.count()).select_from(Gym)) or 0,
        active_gyms=db.scalar(select(func.count()).select_from(Gym).where(Gym.is_active.is_(True))) or 0,
        total_members=db.scalar(select(func.count()).select_from(Member)) or 0,
        active_members=db.scalar(select(func.count()).select_from(Member)
                                 .where(Member.status == MemberStatus.ACTIVE)) or 0,
        mrr=float(mrr or 0),
        subscriptions_by_status={(k.value if hasattr(k, "value") else str(k)): v for k, v in by_status.items()},
        affiliate_platform_earnings=float(db.scalar(
            select(func.coalesce(func.sum(AffiliateConversion.platform_share), 0))) or 0),
        gym_fee_volume_this_month=float(db.scalar(
            select(func.coalesce(func.sum(Payment.amount), 0))
            .where(Payment.status == PaymentStatus.PAID, Payment.paid_at >= month_start)) or 0),
    )

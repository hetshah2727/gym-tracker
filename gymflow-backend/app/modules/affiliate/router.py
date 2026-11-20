import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import GYM_STAFF, GYM_STAFF_AND_TRAINERS, get_current_user, platform_admin, tenant_user
from app.core.tenant_context import tenant_scope
from app.database.models import AffiliateConversion, AffiliateLink, AffiliateProduct, Trainer, User
from app.database.models.enums import ConversionStatus, Role
from app.database.repositories.base import Repository, TenantRepository
from app.database.session import get_db
from app.integrations.amazon.affiliate import build_affiliate_url
from app.modules.affiliate.service import split_commission
from app.modules.common import ORMModel, get_or_404
from app.modules.members.router import trainer_profile_id

router = APIRouter(prefix="/affiliate", tags=["Affiliate store"])


class ProductIn(BaseModel):
    name: str
    category: str
    description: str | None = None
    image_url: str | None = None
    price: float | None = None
    source: str = "amazon"
    external_url: str
    asin: str | None = None
    commission_rate_pct: float = Field(0, ge=0, le=100)
    is_active: bool = True


class ProductUpdate(BaseModel):
    name: str | None = None
    category: str | None = None
    description: str | None = None
    image_url: str | None = None
    price: float | None = None
    external_url: str | None = None
    asin: str | None = None
    commission_rate_pct: float | None = Field(None, ge=0, le=100)
    is_active: bool | None = None


class ProductOut(ORMModel):
    id: uuid.UUID
    name: str
    category: str
    description: str | None
    image_url: str | None
    price: float | None
    source: str
    external_url: str
    asin: str | None
    commission_rate_pct: float
    is_active: bool


class LinkCreate(BaseModel):
    product_id: uuid.UUID
    trainer_id: uuid.UUID | None = None


class LinkOut(ORMModel):
    id: uuid.UUID
    product_id: uuid.UUID
    trainer_id: uuid.UUID | None
    code: str
    clicks: int
    created_at: datetime
    share_url: str | None = None


class ConversionIn(BaseModel):
    link_code: str
    order_amount: float = Field(gt=0)
    commission_amount: float | None = Field(None, ge=0, description="Defaults to order x product rate")
    external_order_id: str | None = None


class ConversionOut(ORMModel):
    id: uuid.UUID
    link_id: uuid.UUID
    external_order_id: str | None
    order_amount: float
    commission_amount: float
    platform_share: float
    gym_share: float
    trainer_share: float
    status: ConversionStatus
    created_at: datetime


class EarningsOut(BaseModel):
    total_clicks: int
    total_conversions: int
    total_sales: float
    gym_earnings: float
    trainer_earnings: float
    pending_earnings: float
    by_trainer: list[dict]


def _share_url(code: str) -> str:
    return f"{settings.API_PREFIX}/affiliate/r/{code}"


# ---- Catalogue ----

@router.get("/products", response_model=list[ProductOut])
def list_products(category: str | None = None, search: str | None = None, db: Session = Depends(get_db),
                  _: User = Depends(get_current_user)):
    stmt = select(AffiliateProduct).where(AffiliateProduct.is_active.is_(True)).order_by(AffiliateProduct.name)
    if category:
        stmt = stmt.where(AffiliateProduct.category == category)
    if search:
        stmt = stmt.where(AffiliateProduct.name.ilike(f"%{search}%"))
    return db.scalars(stmt.limit(500)).all()


@router.post("/products", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
def create_product(data: ProductIn, db: Session = Depends(get_db), _=Depends(platform_admin)):
    return Repository(AffiliateProduct, db).create(**data.model_dump())


@router.patch("/products/{product_id}", response_model=ProductOut)
def update_product(product_id: uuid.UUID, data: ProductUpdate, db: Session = Depends(get_db),
                   _=Depends(platform_admin)):
    repo = Repository(AffiliateProduct, db)
    return repo.update(get_or_404(repo, product_id, "Product"), data.model_dump(exclude_unset=True))


# ---- Trackable links ----

@router.post("/links", response_model=LinkOut, status_code=status.HTTP_201_CREATED)
def create_link(data: LinkCreate, db: Session = Depends(get_db),
                user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    product = get_or_404(Repository(AffiliateProduct, db), data.product_id, "Product")
    trainer_id = trainer_profile_id(db, user) or data.trainer_id  # trainers always link as themselves
    if trainer_id and TenantRepository(Trainer, db).get(trainer_id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Trainer not found in this gym")
    repo = TenantRepository(AffiliateLink, db)
    existing = repo.list(AffiliateLink.product_id == product.id, AffiliateLink.trainer_id == trainer_id, limit=1)
    link = existing[0] if existing else repo.create(product_id=product.id, trainer_id=trainer_id,
                                                    code=secrets.token_urlsafe(6))
    out = LinkOut.model_validate(link)
    out.share_url = _share_url(link.code)
    return out


@router.get("/links", response_model=list[LinkOut])
def list_links(db: Session = Depends(get_db), user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    filters = [AffiliateLink.trainer_id == own] if (own := trainer_profile_id(db, user)) else []
    links = TenantRepository(AffiliateLink, db).list(*filters, limit=1000)
    return [LinkOut.model_validate(link).model_copy(update={"share_url": _share_url(link.code)})
            for link in links]


@router.get("/r/{code}", include_in_schema=False)
def redirect(code: str, db: Session = Depends(get_db)):
    """Public tracking redirect: count the click, then send the buyer to the store."""
    link = db.scalar(select(AffiliateLink).where(AffiliateLink.code == code))
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Link not found")
    product = db.get(AffiliateProduct, link.product_id)
    link.clicks += 1
    link.last_clicked_at = datetime.now(timezone.utc)
    db.commit()
    url = (build_affiliate_url(product.external_url, product.asin, sub_tag=link.code)
           if product.source == "amazon" else product.external_url)
    return RedirectResponse(url, status_code=status.HTTP_302_FOUND)


# ---- Conversions & revenue share ----

@router.post("/conversions", response_model=ConversionOut, status_code=status.HTTP_201_CREATED)
def record_conversion(data: ConversionIn, db: Session = Depends(get_db), _=Depends(platform_admin)):
    """Record an eligible purchase (from the affiliate network's report) and split the commission."""
    link = db.scalar(select(AffiliateLink).where(AffiliateLink.code == data.link_code))
    if link is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown link code")
    product = db.get(AffiliateProduct, link.product_id)
    commission = data.commission_amount
    if commission is None:
        commission = data.order_amount * float(product.commission_rate_pct) / 100
    with tenant_scope(link.gym_id):
        return TenantRepository(AffiliateConversion, db).create(
            link_id=link.id, external_order_id=data.external_order_id, order_amount=data.order_amount,
            **split_commission(commission, has_trainer=link.trainer_id is not None),
        )


@router.post("/conversions/{conversion_id}/status", response_model=ConversionOut)
def set_conversion_status(conversion_id: uuid.UUID, new_status: ConversionStatus, db: Session = Depends(get_db),
                          _=Depends(platform_admin)):
    repo = Repository(AffiliateConversion, db)
    return repo.update(get_or_404(repo, conversion_id, "Conversion"), {"status": new_status})


@router.get("/conversions", response_model=list[ConversionOut])
def list_conversions(db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    return TenantRepository(AffiliateConversion, db).list(limit=1000)


@router.get("/earnings", response_model=EarningsOut)
def earnings(db: Session = Depends(get_db), user: User = Depends(tenant_user(*GYM_STAFF_AND_TRAINERS))):
    links = TenantRepository(AffiliateLink, db)
    convs = TenantRepository(AffiliateConversion, db)
    own = trainer_profile_id(db, user)
    link_filter = [AffiliateLink.trainer_id == own] if own else []
    my_links = links.list(*link_filter, limit=10_000)
    link_ids = [link.id for link in my_links]
    rows = convs.list(AffiliateConversion.link_id.in_(link_ids),
                      AffiliateConversion.status != ConversionStatus.REJECTED, limit=100_000) if link_ids else []
    trainer_of = {link.id: link.trainer_id for link in my_links}
    names = {t.id: t.full_name for t in TenantRepository(Trainer, db).list(limit=1000)}
    per_trainer: dict[uuid.UUID, float] = {}
    for c in rows:
        if tid := trainer_of.get(c.link_id):
            per_trainer[tid] = per_trainer.get(tid, 0) + float(c.trainer_share)
    return EarningsOut(
        total_clicks=sum(link.clicks for link in my_links),
        total_conversions=len(rows),
        total_sales=sum(float(c.order_amount) for c in rows),
        gym_earnings=0 if own else sum(float(c.gym_share) for c in rows),
        trainer_earnings=sum(float(c.trainer_share) for c in rows),
        pending_earnings=sum(float(c.trainer_share if own else c.gym_share) for c in rows
                             if c.status == ConversionStatus.PENDING),
        by_trainer=[{"trainer_id": str(t), "name": names.get(t, "Unknown"), "earnings": round(v, 2)}
                    for t, v in sorted(per_trainer.items(), key=lambda kv: -kv[1])],
    )

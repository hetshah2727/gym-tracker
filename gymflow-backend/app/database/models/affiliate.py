import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column
from app.database.models.enums import ConversionStatus
from app.database.session import Base


class AffiliateProduct(IdMixin, TimestampMixin, Base):
    """Platform-wide catalogue (managed by the platform admin, shared by all gyms)."""

    __tablename__ = "affiliate_products"

    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str] = mapped_column(String(100), index=True)  # supplements, equipment, apparel...
    description: Mapped[str | None] = mapped_column(Text)
    image_url: Mapped[str | None] = mapped_column(String(500))
    price: Mapped[float | None] = mapped_column(Numeric(10, 2))
    source: Mapped[str] = mapped_column(String(32), default="amazon")
    external_url: Mapped[str] = mapped_column(String(1000))
    asin: Mapped[str | None] = mapped_column(String(20))
    commission_rate_pct: Mapped[float] = mapped_column(Numeric(5, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class AffiliateLink(IdMixin, TimestampMixin, TenantMixin, Base):
    """A trackable link a trainer (or the gym) shares with members."""

    __tablename__ = "affiliate_links"

    product_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("affiliate_products.id", ondelete="CASCADE"))
    trainer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("trainers.id", ondelete="SET NULL"))
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    last_clicked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AffiliateConversion(IdMixin, TimestampMixin, TenantMixin, Base):
    """An eligible purchase and its commission split (platform / gym / trainer)."""

    __tablename__ = "affiliate_conversions"

    link_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("affiliate_links.id", ondelete="CASCADE"))
    external_order_id: Mapped[str | None] = mapped_column(String(120))
    order_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    commission_amount: Mapped[float] = mapped_column(Numeric(12, 2))
    platform_share: Mapped[float] = mapped_column(Numeric(12, 2))
    gym_share: Mapped[float] = mapped_column(Numeric(12, 2))
    trainer_share: Mapped[float] = mapped_column(Numeric(12, 2))
    status: Mapped[ConversionStatus] = mapped_column(enum_column(ConversionStatus), default=ConversionStatus.PENDING)

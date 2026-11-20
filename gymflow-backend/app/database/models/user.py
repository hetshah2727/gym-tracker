import uuid

from sqlalchemy import Boolean, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TimestampMixin, enum_column
from app.database.models.enums import Role
from app.database.session import Base


class User(IdMixin, TimestampMixin, Base):
    """A login. Platform admins have no gym; everyone else belongs to exactly one."""

    __tablename__ = "users"

    gym_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("gyms.id", ondelete="CASCADE"), index=True, nullable=True
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(200))
    phone: Mapped[str | None] = mapped_column(String(32))
    role: Mapped[Role] = mapped_column(enum_column(Role))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

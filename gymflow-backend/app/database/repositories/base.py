"""Generic repositories.

``TenantRepository`` is the only way module code should touch gym-scoped
tables: every read is filtered by the current gym and every insert is stamped
with it, so cross-tenant access is impossible by construction.
"""
import uuid
from typing import Any, Generic, Sequence, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from app.core.tenant_context import get_current_gym_id
from app.database.session import Base

M = TypeVar("M", bound=Base)


class Repository(Generic[M]):
    def __init__(self, model: type[M], db: Session):
        self.model = model
        self.db = db

    def query(self) -> Select:
        return select(self.model)

    def get(self, obj_id: uuid.UUID) -> M | None:
        return self.db.scalars(self.query().where(self.model.id == obj_id)).first()

    def list(self, *where: Any, offset: int = 0, limit: int = 50, order_by: Any = None) -> Sequence[M]:
        stmt = self.query().where(*where)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        elif hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc())
        return self.db.scalars(stmt.offset(offset).limit(limit)).all()

    def count(self, *where: Any) -> int:
        stmt = select(func.count()).select_from(self.query().where(*where).subquery())
        return self.db.scalar(stmt) or 0

    def create(self, **data: Any) -> M:
        obj = self.model(**data)
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def update(self, obj: M, data: dict[str, Any]) -> M:
        for key, value in data.items():
            setattr(obj, key, value)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def delete(self, obj: M) -> None:
        self.db.delete(obj)
        self.db.commit()


class TenantRepository(Repository[M]):
    @property
    def gym_id(self) -> uuid.UUID:
        return get_current_gym_id()  # type: ignore[return-value]

    def query(self) -> Select:
        return select(self.model).where(self.model.gym_id == self.gym_id)

    def create(self, **data: Any) -> M:
        data["gym_id"] = self.gym_id
        return super().create(**data)

    def add(self, **data: Any) -> M:
        """Insert and flush without committing, so a service can group writes into one transaction."""
        obj = self.model(**{**data, "gym_id": self.gym_id})
        self.db.add(obj)
        self.db.flush()
        return obj

    def first(self, *where: Any, order_by: Any = None) -> M | None:
        stmt = self.query().where(*where)
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        return self.db.scalars(stmt.limit(1)).first()

    def update(self, obj: M, data: dict[str, Any]) -> M:
        data.pop("gym_id", None)
        return super().update(obj, data)

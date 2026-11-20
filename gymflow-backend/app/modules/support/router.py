import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF, platform_admin, tenant_user
from app.database.models import SupportTicket, User
from app.database.models.enums import TicketPriority, TicketStatus
from app.database.repositories.base import Repository, TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, get_or_404

router = APIRouter(prefix="/support", tags=["Support"])


class TicketIn(BaseModel):
    subject: str = Field(min_length=3, max_length=255)
    description: str = Field(min_length=3)
    priority: TicketPriority = TicketPriority.MEDIUM


class TicketOut(ORMModel):
    id: uuid.UUID
    gym_id: uuid.UUID
    created_by_id: uuid.UUID | None
    subject: str
    description: str
    status: TicketStatus
    priority: TicketPriority
    created_at: datetime
    updated_at: datetime


@router.get("/tickets", response_model=list[TicketOut])
def my_tickets(db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    return TenantRepository(SupportTicket, db).list(limit=200)


@router.post("/tickets", response_model=TicketOut, status_code=status.HTTP_201_CREATED)
def open_ticket(data: TicketIn, db: Session = Depends(get_db), user: User = Depends(tenant_user(*GYM_STAFF))):
    return TenantRepository(SupportTicket, db).create(created_by_id=user.id, **data.model_dump())


@router.get("/admin/tickets", response_model=list[TicketOut])
def all_tickets(status_: TicketStatus | None = None, db: Session = Depends(get_db), _=Depends(platform_admin)):
    stmt = select(SupportTicket).order_by(SupportTicket.created_at.desc()).limit(500)
    if status_:
        stmt = stmt.where(SupportTicket.status == status_)
    return db.scalars(stmt).all()


@router.patch("/admin/tickets/{ticket_id}", response_model=TicketOut)
def update_ticket(ticket_id: uuid.UUID, new_status: TicketStatus, db: Session = Depends(get_db),
                  _=Depends(platform_admin)):
    repo = Repository(SupportTicket, db)
    return repo.update(get_or_404(repo, ticket_id, "Ticket"), {"status": new_status})

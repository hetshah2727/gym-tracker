import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.permissions import GYM_STAFF, tenant_user
from app.database.models import Member, Notification
from app.database.models.enums import Channel, MemberStatus, NotificationStatus
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.common import ORMModel, Page, get_or_404
from app.modules.notifications import service

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class NotificationOut(ORMModel):
    id: uuid.UUID
    member_id: uuid.UUID | None
    rule_id: uuid.UUID | None
    channel: Channel
    recipient: str
    message: str
    category: str
    status: NotificationStatus
    scheduled_for: datetime
    sent_at: datetime | None
    attempts: int
    error: str | None
    created_at: datetime


class SendRequest(BaseModel):
    channel: Channel = Channel.WHATSAPP
    message: str = Field(min_length=1, max_length=4000)
    member_ids: list[uuid.UUID] | None = None
    all_active_members: bool = False
    scheduled_for: datetime | None = None


class SendResponse(BaseModel):
    queued: int
    sent: int


@router.get("", response_model=Page[NotificationOut])
def list_notifications(
    status_: NotificationStatus | None = Query(None, alias="status"),
    channel: Channel | None = None,
    member_id: uuid.UUID | None = None,
    offset: int = 0,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    _=Depends(tenant_user(*GYM_STAFF)),
):
    filters = []
    if status_:
        filters.append(Notification.status == status_)
    if channel:
        filters.append(Notification.channel == channel)
    if member_id:
        filters.append(Notification.member_id == member_id)
    repo = TenantRepository(Notification, db)
    return Page(items=repo.list(*filters, offset=offset, limit=limit), total=repo.count(*filters),
                offset=offset, limit=limit)


@router.post("/send", response_model=SendResponse)
def send_message(data: SendRequest, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    """Send (or schedule) a message to selected members or a broadcast to all active members."""
    repo = TenantRepository(Member, db)
    if data.all_active_members:
        members = repo.list(Member.status == MemberStatus.ACTIVE, limit=10_000)
    elif data.member_ids:
        members = repo.list(Member.id.in_(data.member_ids), limit=len(data.member_ids))
    else:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Provide member_ids or all_active_members=true")

    queued = [n for m in members if (n := service.enqueue(
        db, m, data.channel, data.message.replace("{name}", m.full_name.split()[0]),
        category="manual", scheduled_for=data.scheduled_for))]
    sent = 0
    if data.scheduled_for is None:  # immediate: deliver now instead of waiting for the worker
        for notification in queued:
            sent += service.dispatch(db, notification).status == NotificationStatus.SENT
    return SendResponse(queued=len(queued), sent=sent)


@router.post("/{notification_id}/retry", response_model=NotificationOut)
def retry(notification_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    notification = get_or_404(TenantRepository(Notification, db), notification_id, "Notification")
    notification.status = NotificationStatus.QUEUED
    notification.attempts = 0
    return service.dispatch(db, notification)

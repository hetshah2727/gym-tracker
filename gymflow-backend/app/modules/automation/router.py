import hmac
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.permissions import GYM_STAFF, tenant_user
from app.core.tenant_context import get_current_gym_id, tenant_scope
from app.database.models import AutomationRule, Gym, Member
from app.database.models.enums import AutomationTrigger, Channel
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.modules.automation import service
from app.modules.common import ORMModel, get_or_404
from app.modules.notifications import service as notifications

router = APIRouter(prefix="/automation", tags=["Automation"])


class RuleIn(BaseModel):
    name: str
    trigger: AutomationTrigger
    offset_days: int = Field(0, ge=0, le=365)
    channel: Channel = Channel.WHATSAPP
    template: str = Field(min_length=1, max_length=2000)
    n8n_workflow: str | None = None
    is_active: bool = True


class RuleUpdate(BaseModel):
    name: str | None = None
    offset_days: int | None = Field(None, ge=0, le=365)
    channel: Channel | None = None
    template: str | None = None
    n8n_workflow: str | None = None
    is_active: bool | None = None


class RuleOut(ORMModel):
    id: uuid.UUID
    name: str
    trigger: AutomationTrigger
    offset_days: int
    channel: Channel
    template: str
    n8n_workflow: str | None
    is_active: bool
    created_at: datetime


class N8nSendRequest(BaseModel):
    gym_id: uuid.UUID
    member_id: uuid.UUID
    channel: Channel = Channel.WHATSAPP
    message: str


@router.get("/rules", response_model=list[RuleOut])
def list_rules(db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    return TenantRepository(AutomationRule, db).list(limit=500)


@router.post("/rules", response_model=RuleOut, status_code=status.HTTP_201_CREATED)
def create_rule(data: RuleIn, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    return TenantRepository(AutomationRule, db).create(**data.model_dump())


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def update_rule(rule_id: uuid.UUID, data: RuleUpdate, db: Session = Depends(get_db),
                _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(AutomationRule, db)
    return repo.update(get_or_404(repo, rule_id, "Rule"), data.model_dump(exclude_unset=True))


@router.delete("/rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rule(rule_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    repo = TenantRepository(AutomationRule, db)
    repo.delete(get_or_404(repo, rule_id, "Rule"))


@router.post("/run", response_model=dict[str, int])
def run_now(db: Session = Depends(get_db), _=Depends(tenant_user(*GYM_STAFF))):
    """Run every active rule for this gym now. Returns notifications queued per rule."""
    gym = db.get(Gym, get_current_gym_id())
    results = service.run_gym_rules(db, gym)
    notifications.send_due(db)
    return results


@router.post("/n8n/send", status_code=status.HTTP_202_ACCEPTED)
def n8n_send(data: N8nSendRequest, x_n8n_key: str | None = Header(None), db: Session = Depends(get_db)):
    """Callback for n8n workflows to message a member through GymFlow's channels."""
    if not settings.N8N_API_KEY or not x_n8n_key or not hmac.compare_digest(x_n8n_key, settings.N8N_API_KEY):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid n8n key")
    with tenant_scope(data.gym_id):
        member = get_or_404(TenantRepository(Member, db), data.member_id, "Member")
        notification = notifications.enqueue(db, member, data.channel, data.message, category="n8n")
        if notification:
            notifications.dispatch(db, notification)
    return {"status": "accepted"}

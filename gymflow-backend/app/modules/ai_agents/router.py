"""AI agent control center, central assistant, conversations, approvals and usage."""
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.agents import runtime
from app.agents.registry import AGENTS, TOOLS, AgentContext
from app.agents.runtime_exec import execute
from app.core import entitlements
from app.core.entitlements import gym_feature
from app.core.permissions import GYM_STAFF, tenant_user
from app.database.models import AgentConfig, AgentRun, AIConversation, AIMessage, Lead, PendingAction, User
from app.database.models.enums import ActionStatus, Channel, ConversationStatus, Role
from app.database.repositories.base import TenantRepository
from app.database.session import get_db
from app.integrations.ai import llm
from app.modules.common import get_or_404
from app.modules.crm import service as crm
from app.services import messaging

router = APIRouter(prefix="/ai", tags=["AI agents"])
staff = tenant_user(*GYM_STAFF)


class AskIn(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    conversation_id: uuid.UUID | None = None
    agent: str | None = None


class ConfigIn(BaseModel):
    enabled: bool | None = None
    channels: list[str] | None = None
    working_hours: dict | None = None
    escalation_rules: dict | None = None
    daily_message_limit: int | None = Field(None, ge=0, le=100_000)
    settings: dict | None = None


class StaffReplyIn(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


def _reply_out(r: runtime.AgentReply) -> dict:
    return {"reply": r.text, "status": r.status, "engine": r.engine, "conversation_id": r.conversation_id,
            "agent": r.agent_key, "agent_name": AGENTS[r.agent_key].name, "pending_actions": r.pending_actions,
            "tools_called": r.tools_called, "evidence": r.evidence}


@router.post("/assistant")
def assistant(data: AskIn, db: Session = Depends(get_db), user: User = Depends(staff)):
    """Central GymFlow AI Assistant: routes to the specialised agent; every agent runs with your permissions."""
    agent_key = data.agent or runtime.route(data.message)
    if agent_key not in AGENTS or AGENTS[agent_key].public:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Unknown agent")
    ent = entitlements.resolve(db)
    if user.role != Role.PLATFORM_ADMIN and not ent.has(AGENTS[agent_key].feature):
        # An auto-routed question falls back to the Business Analyst when that is included in the plan.
        if data.agent or not ent.has("business_analyst"):
            raise HTTPException(status.HTTP_402_PAYMENT_REQUIRED,
                                f"The {AGENTS[agent_key].name} is not included in your plan.")
        agent_key = "business_analyst"
    conv = runtime.get_or_create_conversation(db, agent_key=agent_key, channel="assistant", user=user,
                                              conversation_id=data.conversation_id)
    if conv.agent_key != agent_key:
        conv.agent_key = agent_key
    return _reply_out(runtime.run_agent(db, agent_key=agent_key, message=data.message, channel="assistant",
                                        user=user, conversation=conv))


@router.post("/sales-agent/test")
def test_sales_agent(data: AskIn, db: Session = Depends(get_db), user: User = Depends(gym_feature("ai_sales_agent", *GYM_STAFF))):
    """Talk to the Lead Conversion Agent as a prospect would (channel "test"; leads are created for real)."""
    conv = runtime.get_or_create_conversation(db, agent_key="lead_conversion", channel="test",
                                              external_ref=f"test:{user.id}", conversation_id=data.conversation_id)
    reply = runtime.run_agent(db, agent_key="lead_conversion", message=data.message, channel="test", user=None,
                              conversation=conv)
    return _reply_out(reply)


@router.post("/sales-agent/test/reset")
def reset_test(db: Session = Depends(get_db), user: User = Depends(staff)):
    for c in TenantRepository(AIConversation, db).list(AIConversation.channel == "test",
                                                       AIConversation.external_ref == f"test:{user.id}", limit=50):
        c.status = ConversationStatus.CLOSED
    db.commit()
    return {"reset": True}


# ---------------------------------------------------------------- agents & config

@router.get("/agents")
def agents(db: Session = Depends(get_db), user: User = Depends(staff)):
    ent = entitlements.resolve(db)
    out = []
    for spec in AGENTS.values():
        cfg = runtime.get_config(db, spec.key)
        out.append({"key": spec.key, "name": spec.name, "purpose": spec.purpose, "public": spec.public,
                    "included_in_plan": ent.has(spec.feature), "feature": spec.feature,
                    "tools": [{"name": t, "description": TOOLS[t].description, "consequential": TOOLS[t].consequential,
                               "roles": list(TOOLS[t].roles)} for t in spec.tools],
                    "config": {"enabled": cfg.enabled, "channels": cfg.channels, "working_hours": cfg.working_hours,
                               "escalation_rules": cfg.escalation_rules, "daily_message_limit": cfg.daily_message_limit,
                               "settings": cfg.settings}})
    return {"engine": llm.engine() or "rules",
            "engine_note": None if llm.is_configured() else
            "No AI provider key is configured: agents use GymFlow's rule-based engine (approved answers only).",
            "agents": out}


@router.put("/agents/{agent_key}")
def update_agent(agent_key: str, data: ConfigIn, db: Session = Depends(get_db),
                 _=Depends(tenant_user(Role.GYM_OWNER))):
    if agent_key not in AGENTS:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown agent")
    cfg = runtime.get_config(db, agent_key)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(cfg, k, v)
    db.commit()
    return {"key": agent_key, "enabled": cfg.enabled, "channels": cfg.channels, "working_hours": cfg.working_hours,
            "escalation_rules": cfg.escalation_rules, "daily_message_limit": cfg.daily_message_limit}


# ---------------------------------------------------------------- conversations

@router.get("/conversations")
def conversations(channel: str | None = None, status_: ConversationStatus | None = Query(None, alias="status"),
                  db: Session = Depends(get_db), user: User = Depends(staff)):
    f = [AIConversation.channel != "assistant"]
    if channel:
        f.append(AIConversation.channel == channel)
    if status_:
        f.append(AIConversation.status == status_)
    rows = TenantRepository(AIConversation, db).list(*f, limit=200, order_by=AIConversation.last_message_at.desc())
    leads = {l.id: l for l in TenantRepository(Lead, db).list(Lead.id.in_([r.lead_id for r in rows if r.lead_id]),
                                                              limit=500)} if rows else {}
    return [{"id": str(c.id), "channel": c.channel, "status": c.status.value, "agent": c.agent_key,
             "lead": {"id": str(leads[c.lead_id].id), "name": leads[c.lead_id].name} if c.lead_id in leads else None,
             "escalation_reason": c.escalation_reason,
             "last_message_at": c.last_message_at.isoformat() if c.last_message_at else None} for c in rows]


@router.get("/conversations/{conversation_id}")
def conversation(conversation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(staff)):
    conv = get_or_404(TenantRepository(AIConversation, db), conversation_id, "Conversation")
    if conv.channel == "assistant" and conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    msgs = TenantRepository(AIMessage, db).list(AIMessage.conversation_id == conv.id, limit=500,
                                                order_by=AIMessage.created_at)
    return {"id": str(conv.id), "channel": conv.channel, "status": conv.status.value, "agent": conv.agent_key,
            "lead_id": str(conv.lead_id) if conv.lead_id else None, "escalation_reason": conv.escalation_reason,
            "messages": [{"role": m.role, "content": m.content, "data": m.data, "at": m.created_at.isoformat()}
                         for m in msgs]}


@router.post("/conversations/{conversation_id}/takeover")
def takeover(conversation_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(staff)):
    conv = runtime.take_over(db, get_or_404(TenantRepository(AIConversation, db), conversation_id, "Conversation"), user)
    return {"status": conv.status.value}


@router.post("/conversations/{conversation_id}/handback")
def handback(conversation_id: uuid.UUID, db: Session = Depends(get_db), _=Depends(staff)):
    conv = runtime.hand_back(db, get_or_404(TenantRepository(AIConversation, db), conversation_id, "Conversation"))
    return {"status": conv.status.value}


@router.post("/conversations/{conversation_id}/reply")
def staff_reply(conversation_id: uuid.UUID, data: StaffReplyIn, db: Session = Depends(get_db),
                user: User = Depends(staff)):
    """Staff reply in a human-handled conversation. WhatsApp replies obey the 24-hour window rules."""
    conv = get_or_404(TenantRepository(AIConversation, db), conversation_id, "Conversation")
    if conv.status != ConversationStatus.HUMAN:
        runtime.take_over(db, conv, user)
    TenantRepository(AIMessage, db).add(conversation_id=conv.id, role="staff", content=data.message,
                                        data={"user_id": str(user.id)}, created_at=datetime.now(timezone.utc))
    delivery = {"status": "shown_in_chat"}
    lead = db.get(Lead, conv.lead_id) if conv.lead_id else None
    if lead:
        if conv.channel == "whatsapp":
            outcome = messaging.send_to_lead(db, lead, data.message, category="staff_reply")
            delivery = {"status": outcome.status, "reason": outcome.reason}
        crm.record_interaction(db, lead, "whatsapp" if conv.channel == "whatsapp" else "chat", data.message,
                               direction="out", user=user, is_contact=True)
    conv.last_message_at = datetime.now(timezone.utc)
    db.commit()
    return {"delivery": delivery}


# ---------------------------------------------------------------- approvals

@router.get("/actions")
def pending(status_: ActionStatus = Query(ActionStatus.PENDING, alias="status"), db: Session = Depends(get_db),
            _=Depends(staff)):
    rows = TenantRepository(PendingAction, db).list(PendingAction.status == status_, limit=100)
    return [{"id": str(a.id), "agent": a.agent_key, "tool": a.tool, "summary": a.summary, "arguments": a.arguments,
             "status": a.status.value, "result": a.result, "created_at": a.created_at.isoformat()} for a in rows]


@router.post("/actions/{action_id}/confirm")
def confirm(action_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(staff)):
    action = get_or_404(TenantRepository(PendingAction, db), action_id, "Action")
    if action.status != ActionStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Action is already {action.status.value}")
    ctx = AgentContext(db=db, agent_key=action.agent_key, user=user, channel="assistant")
    result = execute(ctx, action.tool, action.arguments, confirmed=True)  # permissions re-checked for this user
    action = TenantRepository(PendingAction, db).get(action_id)
    action.status = ActionStatus.FAILED if "error" in result else ActionStatus.EXECUTED
    action.result, action.decided_by_id, action.decided_at = result, user.id, datetime.now(timezone.utc)
    db.commit()
    return {"status": action.status.value, "result": result}


@router.post("/actions/{action_id}/reject")
def reject(action_id: uuid.UUID, db: Session = Depends(get_db), user: User = Depends(staff)):
    action = get_or_404(TenantRepository(PendingAction, db), action_id, "Action")
    if action.status != ActionStatus.PENDING:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Action is already {action.status.value}")
    action.status, action.decided_by_id, action.decided_at = ActionStatus.REJECTED, user.id, datetime.now(timezone.utc)
    db.commit()
    return {"status": "rejected"}


# ---------------------------------------------------------------- usage

@router.get("/usage")
def usage(days: int = Query(30, ge=1, le=366), db: Session = Depends(get_db), _=Depends(staff)):
    since = datetime.combine(date.today() - timedelta(days=days - 1), datetime.min.time(), tzinfo=timezone.utc)
    runs = TenantRepository(AgentRun, db).list(AgentRun.created_at >= since, limit=100_000)
    by_agent = defaultdict(lambda: {"runs": 0, "errors": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0,
                                    "tool_calls": 0, "denied_tool_calls": 0})
    for r in runs:
        row = by_agent[r.agent_key]
        row["runs"] += 1
        row["errors"] += int(r.status == "error")
        row["input_tokens"] += r.input_tokens
        row["output_tokens"] += r.output_tokens
        row["cost_usd"] = round(row["cost_usd"] + r.cost_usd, 4)
        row["tool_calls"] += len(r.tools_called or [])
        row["denied_tool_calls"] += sum(1 for t in r.tools_called or [] if t.get("denied"))
    ent = entitlements.resolve(db)
    return {"days": days, "by_agent": dict(by_agent), "total_cost_usd": round(sum(r.cost_usd for r in runs), 4),
            "engine": llm.engine() or "rules",
            "monthly_usage": {m: {"used": entitlements.usage(db, m), "limit": ent.limits.get(m)}
                              for m in ("ai_messages", "seo_audits", "content_generations")},
            "recent_runs": [{"agent": r.agent_key, "engine": r.engine, "status": r.status, "ms": r.duration_ms,
                             "tools": [t.get("name") for t in r.tools_called or []], "at": r.created_at.isoformat(),
                             "error": r.error} for r in sorted(runs, key=lambda r: r.created_at, reverse=True)[:25]]}


__all__ = ["router", "Channel", "AgentConfig"]

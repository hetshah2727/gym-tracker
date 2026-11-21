"""AI agent configuration, conversations, execution logs and actions awaiting human approval."""
import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import IdMixin, TenantMixin, TimestampMixin, enum_column, utcnow
from app.database.models.enums import ActionStatus, ConversationStatus
from app.database.session import Base


class AgentConfig(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ai_agent_configs"
    __table_args__ = (UniqueConstraint("gym_id", "agent_key", name="uq_agent_configs_gym_agent"),)

    agent_key: Mapped[str] = mapped_column(String(48))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    channels: Mapped[list] = mapped_column(JSON, default=list)          # ["website_chat", "whatsapp"]
    # {"timezone": "Asia/Kolkata", "days": [0..6], "start": "06:00", "end": "22:00"}; empty = always on
    working_hours: Mapped[dict] = mapped_column(JSON, default=dict)
    # {"keywords": ["refund", "injury", ...], "after_messages": 12}
    escalation_rules: Mapped[dict] = mapped_column(JSON, default=dict)
    daily_message_limit: Mapped[int] = mapped_column(Integer, default=300)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)


class AIConversation(IdMixin, TimestampMixin, TenantMixin, Base):
    __tablename__ = "ai_conversations"
    __table_args__ = (Index("ix_conversations_gym_ext", "gym_id", "channel", "external_ref"),)

    agent_key: Mapped[str] = mapped_column(String(48))
    channel: Mapped[str] = mapped_column(String(32))      # website_chat | whatsapp | test | assistant
    # Web chat session token / WhatsApp number - identifies the visitor across messages.
    external_ref: Mapped[str | None] = mapped_column(String(128))
    lead_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("leads.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="CASCADE"))
    status: Mapped[ConversationStatus] = mapped_column(
        enum_column(ConversationStatus), default=ConversationStatus.AI_ACTIVE)
    escalation_reason: Mapped[str | None] = mapped_column(String(255))
    taken_over_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    # Collected so far by the rule-based flow: {"name", "phone", "interest", "awaiting": ...}
    state: Mapped[dict] = mapped_column(JSON, default=dict)
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AIMessage(IdMixin, TenantMixin, Base):
    __tablename__ = "ai_messages"

    conversation_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("ai_conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))         # user | assistant | staff | system
    content: Mapped[str] = mapped_column(Text)
    data: Mapped[dict] = mapped_column(JSON, default=dict)  # tools used, actions, evidence
    provider_message_id: Mapped[str | None] = mapped_column(String(200), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AgentRun(IdMixin, TenantMixin, Base):
    """Execution log: one row per agent invocation (for debugging, usage and cost tracking)."""

    __tablename__ = "ai_agent_runs"
    __table_args__ = (Index("ix_agent_runs_gym_time", "gym_id", "created_at"),)

    agent_key: Mapped[str] = mapped_column(String(48))
    user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_conversations.id", ondelete="SET NULL"))
    engine: Mapped[str] = mapped_column(String(32))       # claude | rules
    model: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(16))       # ok | error | denied | limited
    tools_called: Mapped[list] = mapped_column(JSON, default=list)  # [{"name","ok","ms","denied"?}]
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[float] = mapped_column(Float, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PendingAction(IdMixin, TimestampMixin, TenantMixin, Base):
    """A consequential action an agent proposed; it runs only after an authorised person confirms it."""

    __tablename__ = "ai_pending_actions"

    agent_key: Mapped[str] = mapped_column(String(48))
    tool: Mapped[str] = mapped_column(String(64))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text)
    status: Mapped[ActionStatus] = mapped_column(enum_column(ActionStatus), default=ActionStatus.PENDING)
    requested_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="SET NULL"))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("ai_conversations.id", ondelete="SET NULL"))

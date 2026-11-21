"""Shared agent infrastructure: tool registry, agent definitions, permission checks.

A tool is plain deterministic code with a pydantic input schema. Agents never touch the database
directly - they can only call tools they are authorised for, as the caller they act for:
* staff/owner requests run with that user's role and the gym's plan entitlements;
* public visitors (website chat, WhatsApp) run as ``PUBLIC`` and can only use lead-conversion tools,
  which are bound to the visitor's own conversation/lead (a lead id in the arguments is ignored).
Consequential tools (sending messages, publishing) never run directly from the model: they create a
PendingAction that an authorised person must confirm.
"""
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import entitlements
from app.database.models import AIConversation, User
from app.database.models.enums import Role

PUBLIC = "public"
STAFF = (Role.GYM_OWNER.value, Role.GYM_MANAGER.value)
OWNER = (Role.GYM_OWNER.value,)


@dataclass
class AgentContext:
    db: Session
    agent_key: str
    user: User | None = None              # None = public visitor
    conversation: AIConversation | None = None
    channel: str = "assistant"
    tools_called: list = field(default_factory=list)
    pending_actions: list = field(default_factory=list)
    evidence: list = field(default_factory=list)

    @property
    def role(self) -> str:
        return self.user.role.value if self.user else PUBLIC

    @property
    def gym_id(self) -> uuid.UUID:
        from app.core.tenant_context import get_current_gym_id

        return get_current_gym_id()


@dataclass
class Tool:
    name: str
    description: str
    params: type[BaseModel]
    handler: Callable[[AgentContext, Any], dict]
    roles: tuple[str, ...]
    feature: str | None = None
    consequential: bool = False
    summarize: Callable[[Any], str] | None = None

    def json_schema(self) -> dict:
        schema = self.params.model_json_schema()
        schema.pop("title", None)
        schema.setdefault("properties", {})
        schema["additionalProperties"] = False
        return schema


class ToolDenied(Exception):
    pass


TOOLS: dict[str, Tool] = {}


def tool(name: str, description: str, params: type[BaseModel], roles: tuple[str, ...], *,
         feature: str | None = None, consequential: bool = False, summarize=None):
    def register(fn):
        TOOLS[name] = Tool(name, description, params, fn, roles, feature, consequential, summarize)
        return fn

    return register


@dataclass
class AgentSpec:
    key: str
    name: str
    purpose: str
    tools: list[str]
    feature: str
    public: bool = False


AGENTS: dict[str, AgentSpec] = {}


def define(spec: AgentSpec) -> AgentSpec:
    AGENTS[spec.key] = spec
    return spec


def check_permission(ctx: AgentContext, t: Tool) -> None:
    """Raise ToolDenied unless this caller may run this tool for this agent."""
    spec = AGENTS.get(ctx.agent_key)
    if spec is None or t.name not in spec.tools:
        raise ToolDenied(f"{t.name} is not available to the {ctx.agent_key} agent")
    if ctx.role != Role.PLATFORM_ADMIN.value and ctx.role not in t.roles:
        raise ToolDenied(f"Your role ({ctx.role}) cannot use {t.name}")
    if t.feature and ctx.role != Role.PLATFORM_ADMIN.value and not entitlements.resolve(ctx.db).has(t.feature):
        raise ToolDenied(f"{t.name} needs the {entitlements.FEATURES[t.feature][0]} feature on your plan")


def tools_for(ctx: AgentContext) -> list[Tool]:
    spec = AGENTS[ctx.agent_key]
    out = []
    for name in spec.tools:
        t = TOOLS[name]
        try:
            check_permission(ctx, t)
            out.append(t)
        except ToolDenied:
            continue
    return out

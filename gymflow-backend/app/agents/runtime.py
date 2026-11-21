"""Agent runtime: conversation persistence, limits, routing, Claude tool loop or rule engine, run logs."""
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

import app.agents.tools  # noqa: F401  (registers tools and agents)
from app.agents import rules
from app.agents.registry import AGENTS, AgentContext, tools_for
from app.agents.runtime_exec import execute
from app.core import entitlements
from app.core.config import settings
from app.core.tenant_context import get_current_gym_id
from app.database.models import AgentConfig, AgentRun, AIConversation, AIMessage, Gym, Lead, User
from app.database.models.enums import ConversationStatus
from app.database.repositories.base import TenantRepository
from app.integrations.ai import claude, groq, llm
from app.modules.crm import service as crm
from app.services import content

logger = logging.getLogger(__name__)
MAX_TOOL_ROUNDS = 6
HISTORY = 20

ROUTES = [  # (agent, keywords) - first match wins for the central assistant
    ("seo_growth", ("seo audit", "website audit", "meta description", "sitemap", "page title", "keyword")),
    ("local_seo", ("google business", "maps", "review", "local seo", "gbp", "profile post")),
    ("ai_search", ("chatgpt", "gpt", "ai search", "schema", "structured data", "json-ld", "faq")),
    ("recovery", ("renew", "expir", "outstanding", "dues", "unpaid", "recover", "failed payment")),
    ("trial_conversion", ("trial", "no-show", "no show")),
    ("crm_follow_up", ("lead", "enquir", "follow up", "follow-up", "pipeline", "contact")),
]


def route(question: str) -> str:
    q = question.lower()
    if any(k in q for k in ("perform", "overview", "plan", "today", "grow", "opportunit", "revenue", "analy")):
        return "business_analyst"
    for agent, keys in ROUTES:
        if any(k in q for k in keys):
            return agent
    return "business_analyst"


@dataclass
class AgentReply:
    text: str | None
    status: str                       # ok | human | disabled | limited | error
    engine: str
    conversation_id: str
    agent_key: str
    pending_actions: list = field(default_factory=list)
    evidence: list = field(default_factory=list)
    tools_called: list = field(default_factory=list)


def get_config(db: Session, agent_key: str) -> AgentConfig:
    repo = TenantRepository(AgentConfig, db)
    cfg = repo.first(AgentConfig.agent_key == agent_key)
    if cfg is None:
        cfg = repo.add(agent_key=agent_key, enabled=True,
                       channels=["website_chat", "whatsapp", "test"] if agent_key == "lead_conversion" else ["assistant"],
                       working_hours={}, escalation_rules={"keywords": [], "after_messages": 30},
                       daily_message_limit=300, settings={})
        db.commit()
    return cfg


def within_hours(cfg: AgentConfig, gym: Gym, now: datetime | None = None) -> bool:
    wh = cfg.working_hours or {}
    if not wh.get("start") or not wh.get("end"):
        return True
    local = (now or datetime.now(timezone.utc)).astimezone(ZoneInfo(gym.timezone or "Asia/Kolkata"))
    if wh.get("days") and local.weekday() not in wh["days"]:
        return False
    return wh["start"] <= local.strftime("%H:%M") < wh["end"]


def _messages_today(db: Session, agent_key: str) -> int:
    start = datetime.combine(date.today(), datetime.min.time(), tzinfo=timezone.utc)
    return db.scalar(select(func.count()).select_from(AIMessage).join(
        AIConversation, AIConversation.id == AIMessage.conversation_id).where(
        AIMessage.gym_id == get_current_gym_id(), AIConversation.agent_key == agent_key,
        AIMessage.role == "assistant", AIMessage.created_at >= start)) or 0


def get_or_create_conversation(db: Session, *, agent_key: str, channel: str, external_ref: str | None = None,
                               user: User | None = None, conversation_id=None) -> AIConversation:
    repo = TenantRepository(AIConversation, db)
    conv = None
    if conversation_id:
        conv = repo.get(conversation_id)
        if conv and user and conv.user_id and conv.user_id != user.id:
            conv = None  # never continue someone else's assistant thread
    if conv is None and external_ref:
        conv = repo.first(AIConversation.channel == channel, AIConversation.external_ref == external_ref,
                          AIConversation.status != ConversationStatus.CLOSED,
                          order_by=AIConversation.created_at.desc())
    if conv is None:
        conv = repo.add(agent_key=agent_key, channel=channel, external_ref=external_ref,
                        user_id=user.id if user else None, status=ConversationStatus.AI_ACTIVE, state={})
        db.commit()
    return conv


def _history(db: Session, conv: AIConversation) -> list[dict]:
    rows = TenantRepository(AIMessage, db).list(AIMessage.conversation_id == conv.id, limit=HISTORY,
                                                order_by=AIMessage.created_at.desc())
    msgs = []
    for m in reversed(rows):
        role = "assistant" if m.role in ("assistant", "staff") else "user"
        text = m.content if m.role != "staff" else f"[Staff member replied] {m.content}"
        if msgs and msgs[-1]["role"] == role:
            msgs[-1]["content"] += "\n" + text
        else:
            msgs.append({"role": role, "content": text})
    while msgs and msgs[0]["role"] != "user":
        msgs.pop(0)
    return msgs


def _system_prompt(ctx: AgentContext) -> str:
    gym = ctx.db.get(Gym, ctx.gym_id)
    spec = AGENTS[ctx.agent_key]
    if spec.public:
        facts = content.load_facts(ctx.db)
        faqs = "\n".join(f"Q: {f['q']}\nA: {f['a']}" for f in facts.faqs) or "(none approved)"
        return f"""You are the front-desk assistant of {facts.gym}, chatting with a prospective member on {ctx.channel.replace('_', ' ')}.

Approved gym information (the ONLY facts you may state):
{facts.as_prompt()}

Approved FAQs:
{faqs}

Rules:
- Never invent or estimate prices, discounts, offers, availability, facilities or results. Quote plans only from the information above.
- If something is not covered, say you'll check with the team and call escalate_to_staff with stop_ai=false.
- Call escalate_to_staff with stop_ai=true for complaints, refunds, injuries, medical conditions, pregnancy, or when they ask for a person.
- Do not ask about health conditions or medical history.
- Collect their name and phone naturally and save them with save_lead_details (also save interest, preferred plan, joining date when mentioned).
- To book a trial: find_trial_slots, offer 2-3 options in local time, then book_trial with the exact starts_at they pick.
- Reply in the visitor's language (English, Hindi or Gujarati). Keep it short and friendly (under 80 words)."""
    return f"""You are GymFlow's {spec.name} for {gym.name} (currency {gym.currency}). Today is {date.today():%A %d %B %Y}.
Purpose: {spec.purpose}

Rules:
- Get data with tools. Every number you state must come from a tool result in this conversation. If data is missing, say so.
- "Potential revenue" and forecasts are estimates - never call them revenue. Recovered revenue is always backed by a paid payment.
- Never claim Google rankings, map-pack positions or AI-assistant citations; GymFlow does not measure them.
- Tools that send messages or run audits create a pending action that the user must confirm in GymFlow - tell them.
- Answer first, then up to 5 short bullets with the key figures, then 1-3 next actions with their GymFlow links (href values from tools).
- Links must be plain paths that start with /dashboard/ exactly as tools return them. Never invent URLs or HTML.
- Plain language for a gym owner. Use markdown."""


def _claude_loop(ctx: AgentContext, history: list[dict]) -> tuple[str, claude.Usage]:
    usage = claude.Usage(model=settings.AI_MODEL)
    tools = [{"name": t.name, "description": t.description, "input_schema": t.json_schema()} for t in tools_for(ctx)]
    messages: list = list(history)
    effort = "low" if AGENTS[ctx.agent_key].public else "medium"
    for _ in range(MAX_TOOL_ROUNDS):
        response = claude.create(max_tokens=8000, system=_system_prompt(ctx), tools=tools, messages=messages,
                                 output_config={"effort": effort})
        usage.add(response.usage)
        if response.stop_reason == "refusal":
            return "Sorry, I can't help with that here. A team member can assist you.", usage
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        if response.stop_reason != "tool_use" or not tool_uses:
            return "".join(b.text for b in response.content if b.type == "text").strip(), usage
        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in tool_uses:
            out = execute(ctx, block.name, block.input if isinstance(block.input, dict) else {})
            results.append({"type": "tool_result", "tool_use_id": block.id,
                            "content": json.dumps(out, default=str)[:20_000], "is_error": "error" in out})
        messages.append({"role": "user", "content": results})
    return "I gathered the data but ran out of steps. Please ask a more specific question.", usage


def _groq_loop(ctx: AgentContext, history: list[dict]) -> tuple[str, claude.Usage]:
    """Same tool loop as Claude, in the OpenAI-compatible format Groq uses."""
    usage = claude.Usage(model=settings.GROQ_MODEL)
    tools = [{"type": "function", "function": {"name": t.name, "description": t.description,
                                               "parameters": t.json_schema()}} for t in tools_for(ctx)]
    messages: list = [{"role": "system", "content": _system_prompt(ctx)}, *history]
    for _ in range(MAX_TOOL_ROUNDS):
        response = groq.chat(messages, tools=tools or None, max_tokens=1500)
        groq.add_usage(usage, response)
        msg = response["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        if not calls:
            return (msg.get("content") or "").strip(), usage
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            try:
                args = json.loads(call["function"].get("arguments") or "{}")
            except json.JSONDecodeError:
                args = {}
            out = execute(ctx, call["function"]["name"], args if isinstance(args, dict) else {})
            messages.append({"role": "tool", "tool_call_id": call["id"],
                             "content": json.dumps(out, default=str)[:6_000]})
    return "I gathered the data but ran out of steps. Please ask a more specific question.", usage


def run_agent(db: Session, *, agent_key: str, message: str, channel: str, user: User | None = None,
              conversation: AIConversation | None = None, provider_message_id: str | None = None) -> AgentReply:
    started = time.monotonic()
    gym = db.get(Gym, get_current_gym_id())
    conv = conversation or get_or_create_conversation(db, agent_key=agent_key, channel=channel, user=user)
    ctx = AgentContext(db=db, agent_key=agent_key, user=user, conversation=conv, channel=channel)
    engine = llm.engine()
    reply = AgentReply(text=None, status="ok", engine=engine or "rules",
                       conversation_id=str(conv.id), agent_key=agent_key)

    TenantRepository(AIMessage, db).add(conversation_id=conv.id, role="user", content=message[:4000], data={},
                                        provider_message_id=provider_message_id, created_at=datetime.now(timezone.utc))
    conv.last_message_at = datetime.now(timezone.utc)
    lead = db.get(Lead, conv.lead_id) if conv.lead_id else None
    if lead:
        crm.record_interaction(db, lead, "chat" if channel != "whatsapp" else "whatsapp", message[:2000], direction="in")
    db.commit()

    cfg = get_config(db, agent_key)
    if conv.status == ConversationStatus.HUMAN:
        reply.status, reply.text = "human", None
        return reply
    if not cfg.enabled or (AGENTS[agent_key].public and channel not in (cfg.channels or []) and channel != "test"):
        reply.status = "disabled"
        return reply
    if not entitlements.within_limit(db, "ai_messages") or _messages_today(db, agent_key) >= cfg.daily_message_limit:
        reply.status = "limited"
        reply.text = ("Thanks! Our team will get back to you shortly." if AGENTS[agent_key].public
                      else "Your plan's AI message limit has been reached for now.")
        _log(db, ctx, reply, started, status="limited")
        return reply

    usage = claude.Usage(model=settings.AI_MODEL)
    error = None
    try:
        if AGENTS[agent_key].public and not within_hours(cfg, gym):
            reply.text = (cfg.settings or {}).get("after_hours_message") or \
                "Thanks for your message! Our team is offline right now and will reply in the morning."
            crm.create_task(db, title="Reply to after-hours chat", lead_id=conv.lead_id, source="agent",
                            dedup_key=f"after_hours:{conv.id}:{date.today()}")
            db.commit()
        elif engine == "groq":
            reply.text, usage = _groq_loop(ctx, _history(db, conv))
        elif engine == "claude":
            reply.text, usage = _claude_loop(ctx, _history(db, conv))
        elif AGENTS[agent_key].public:
            reply.text = rules.sales_reply(ctx, message)
        else:
            reply.text = rules.analyst_reply(ctx, message)
    except claude.AIError as exc:
        error = str(exc)
        reply.engine = "rules"
        reply.text = rules.sales_reply(ctx, message) if AGENTS[agent_key].public else rules.analyst_reply(ctx, message)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Agent %s failed", agent_key)
        db.rollback()
        error, reply.status = str(exc)[:300], "error"
        reply.text = "Sorry, something went wrong. A team member will follow up."

    reply.pending_actions, reply.evidence, reply.tools_called = ctx.pending_actions, ctx.evidence, ctx.tools_called
    db.commit()  # persist conversation state collected by the engine before re-reading lead links
    db.refresh(conv)
    if reply.text:
        TenantRepository(AIMessage, db).add(conversation_id=conv.id, role="assistant", content=reply.text,
                                            data={"engine": reply.engine, "tools": ctx.tools_called,
                                                  "pending_actions": ctx.pending_actions},
                                            created_at=datetime.now(timezone.utc))
        lead = db.get(Lead, conv.lead_id) if conv.lead_id else None
        if lead:
            crm.record_interaction(db, lead, "chat" if channel != "whatsapp" else "whatsapp", reply.text[:2000],
                                   direction="out", is_contact=False, data={"by": "ai_agent"})
    db.commit()
    entitlements.record_usage(db, "ai_messages")
    _log(db, ctx, reply, started, status="error" if reply.status == "error" else "ok", usage=usage, error=error)
    return reply


def _log(db: Session, ctx: AgentContext, reply: AgentReply, started: float, *, status: str,
         usage: claude.Usage | None = None, error: str | None = None) -> None:
    usage = usage or claude.Usage(model=settings.AI_MODEL)
    TenantRepository(AgentRun, db).add(
        agent_key=ctx.agent_key, user_id=ctx.user.id if ctx.user else None, conversation_id=ctx.conversation.id
        if ctx.conversation else None, engine=reply.engine, model=llm.model_name(reply.engine) if reply.engine != "rules" else None,
        status=status, tools_called=ctx.tools_called, input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens, cost_usd=usage.cost_usd if reply.engine != "rules" else 0,
        duration_ms=int((time.monotonic() - started) * 1000), error=error, created_at=datetime.now(timezone.utc))
    db.commit()


def take_over(db: Session, conv: AIConversation, user: User) -> AIConversation:
    conv.status, conv.taken_over_by_id = ConversationStatus.HUMAN, user.id
    db.commit()
    return conv


def hand_back(db: Session, conv: AIConversation) -> AIConversation:
    conv.status = ConversationStatus.AI_ACTIVE
    db.commit()
    return conv


__all__ = ["AgentReply", "get_config", "get_or_create_conversation", "hand_back", "route", "run_agent", "take_over",
           "timedelta"]

"""Execute one tool call on behalf of an agent: permission check, validation, approval gate, logging."""
import json
import logging
import time

from fastapi import HTTPException
from pydantic import ValidationError

from app.agents.registry import TOOLS, AgentContext, ToolDenied, check_permission
from app.database.models import PendingAction
from app.database.repositories.base import TenantRepository

logger = logging.getLogger(__name__)
MAX_RESULT_CHARS = 12_000


def execute(ctx: AgentContext, name: str, raw_args: dict | None, *, confirmed: bool = False) -> dict:
    started = time.monotonic()
    record = {"name": name, "ok": False}
    try:
        t = TOOLS.get(name)
        if t is None:
            raise ToolDenied(f"Unknown tool {name}")
        check_permission(ctx, t)
        args = t.params.model_validate(raw_args or {})
        if t.consequential and not confirmed:
            action = TenantRepository(PendingAction, ctx.db).add(
                agent_key=ctx.agent_key, tool=name, arguments=json.loads(args.model_dump_json()),
                summary=t.summarize(args) if t.summarize else f"Run {name}",
                requested_by_id=ctx.user.id if ctx.user else None,
                conversation_id=ctx.conversation.id if ctx.conversation else None, result={})
            ctx.db.commit()
            ctx.pending_actions.append({"id": str(action.id), "summary": action.summary, "tool": name})
            record.update(ok=True, pending=True)
            return {"status": "pending_confirmation", "action_id": str(action.id),
                    "message": "This action needs the user's confirmation in GymFlow before it runs."}
        result = t.handler(ctx, args)
        record["ok"] = "error" not in result
        ctx.evidence.append({"tool": name, "result": _truncate(result)})
        return result
    except ToolDenied as exc:
        record["denied"] = True
        return {"error": str(exc), "denied": True}
    except ValidationError as exc:
        return {"error": f"Invalid arguments: {exc.errors()[0].get('msg')}"}
    except HTTPException as exc:
        ctx.db.rollback()
        return {"error": str(exc.detail)}
    except Exception:  # noqa: BLE001
        logger.exception("Tool %s failed", name)
        ctx.db.rollback()
        return {"error": "The tool failed unexpectedly"}
    finally:
        record["ms"] = int((time.monotonic() - started) * 1000)
        ctx.tools_called.append(record)


def _truncate(result: dict) -> dict:
    text = json.dumps(result, default=str)
    if len(text) <= MAX_RESULT_CHARS:
        return json.loads(text)
    return {"truncated": True, "preview": text[:MAX_RESULT_CHARS]}

"""Which AI provider handles what.

* Text, structured drafts and the agents' tool loop -> ``LLM_PROVIDER`` (auto: Groq if its key is set, else Claude).
* Posts (Google / social), images and live web search -> Gemini, when ``GEMINI_API_KEY`` is set.
Everything falls back to GymFlow's templates/rule engine when no provider is configured.
"""
from typing import TypeVar

from pydantic import BaseModel

from app.core.config import settings
from app.integrations.ai import claude, gemini, groq
from app.integrations.ai.claude import AIError, Usage

T = TypeVar("T", bound=BaseModel)
__all__ = ["AIError", "Usage", "engine", "is_configured", "parse", "parse_post", "model_name"]


def engine() -> str | None:
    """'groq' | 'claude' | None for text generation and agents."""
    choice = (settings.LLM_PROVIDER or "auto").lower()
    if choice == "groq":
        return "groq" if groq.is_configured() else None
    if choice == "claude":
        return "claude" if claude.is_configured() else None
    if groq.is_configured():
        return "groq"
    if claude.is_configured():
        return "claude"
    return None


def is_configured() -> bool:
    return engine() is not None


def model_name(name: str | None = None) -> str | None:
    name = name or engine()
    return {"groq": settings.GROQ_MODEL, "claude": settings.AI_MODEL, "gemini": settings.GEMINI_MODEL}.get(name or "")


def parse(system: str, user: str, schema: type[T], *, effort: str = "low") -> tuple[T, Usage]:
    match engine():
        case "groq":
            return groq.parse(system, user, schema)
        case "claude":
            return claude.parse(system, user, schema, effort=effort)
    raise AIError("No AI provider is configured")


def parse_post(system: str, user: str, schema: type[T]) -> tuple[T, Usage, str]:
    """Posts go to Gemini when available, otherwise the main text model. Returns the engine used too."""
    if gemini.is_configured():
        try:
            result, usage = gemini.parse(system, user, schema)
            return result, usage, "gemini"
        except AIError:
            if not is_configured():
                raise
    result, usage = parse(system, user, schema)
    return result, usage, engine() or "template"

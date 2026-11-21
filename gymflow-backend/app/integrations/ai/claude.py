"""Thin Claude provider used by GymFlow agents and content generation.

Credentials stay on the backend. Server-side refusal fallbacks are enabled (``fallbacks="default"``), so if a
safety classifier declines a request the API retries on a fallback model in the same call.
"""
import logging
from dataclasses import dataclass
from typing import TypeVar

import anthropic
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)

FALLBACK_BETAS = ["server-side-fallback-2026-07-01"]
# USD per million tokens (input, output) - used for the usage/cost dashboard only.
PRICING = {
    "claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50),
    "claude-fable-5-2": (8.0, 40.0),
}


class AIError(RuntimeError):
    pass


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""

    @property
    def cost_usd(self) -> float:
        inp, out = PRICING.get(self.model, PRICING["claude-opus-5-5"])
        return round((self.input_tokens * inp + self.output_tokens * out) / 1_000_000, 6)

    def add(self, usage) -> None:
        if usage is None:
            return
        self.input_tokens += getattr(usage, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage, "output_tokens", 0) or 0


def is_configured() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


def client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY, max_retries=2, timeout=120)


def _wrap(exc: Exception) -> AIError:
    if isinstance(exc, anthropic.RateLimitError):
        return AIError("The AI service is busy, please try again shortly")
    if isinstance(exc, anthropic.APIStatusError):
        logger.error("Claude API error %s: %s", exc.status_code, exc.message)
        return AIError("The AI service returned an error")
    if isinstance(exc, anthropic.APIConnectionError):
        return AIError("Could not reach the AI service")
    return AIError(str(exc))


def parse(system: str, user: str, schema: type[T], *, effort: str = "low",
          max_tokens: int = 8000) -> tuple[T, Usage]:
    """Single structured-output call. Raises AIError on refusal or failure."""
    usage = Usage(model=settings.AI_MODEL)
    try:
        response = client().beta.messages.parse(
            model=settings.AI_MODEL, max_tokens=max_tokens, betas=FALLBACK_BETAS, fallbacks="default",
            output_config={"effort": effort}, system=system,
            messages=[{"role": "user", "content": user}], output_format=schema,
        )
    except (anthropic.APIError, anthropic.APIConnectionError) as exc:
        raise _wrap(exc) from exc
    usage.add(response.usage)
    if response.stop_reason == "refusal":
        raise AIError("The AI declined this request")
    if response.stop_reason == "max_tokens" or response.parsed_output is None:
        raise AIError("The AI response was incomplete")
    return response.parsed_output, usage


def create(**kwargs):
    """Raw Messages call for the agent tool loop (fallbacks enabled)."""
    try:
        return client().beta.messages.create(model=settings.AI_MODEL, betas=FALLBACK_BETAS, fallbacks="default",
                                             **kwargs)
    except (anthropic.APIError, anthropic.APIConnectionError) as exc:
        raise _wrap(exc) from exc

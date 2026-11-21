"""Groq provider (OpenAI-compatible Chat Completions) - GymFlow's default LLM for text and agent tool calls.

Only plain HTTP via httpx, so there is no extra SDK to install. Structured output uses JSON mode plus pydantic
validation (with one corrective retry), which works across Groq's models.
"""
import json
import logging
import time
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.integrations.ai.claude import AIError, Usage

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
URL = "https://api.groq.com/openai/v1/chat/completions"


def is_configured() -> bool:
    return bool(settings.GROQ_API_KEY)


def chat(messages: list[dict], *, tools: list[dict] | None = None, max_tokens: int = 1500,
         json_mode: bool = False, temperature: float = 0.3) -> dict:
    """One Chat Completions call. Returns the raw response JSON. Raises AIError on failure.

    ``max_tokens`` counts against Groq's tokens-per-minute limit (8K/min on smaller accounts), so keep it modest.
    """
    body: dict[str, Any] = {"model": settings.GROQ_MODEL, "messages": messages, "max_tokens": max_tokens,
                            "temperature": temperature}
    if settings.GROQ_MODEL.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"  # fewer hidden reasoning tokens -> faster and within rate limits
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    for attempt in range(2):
        try:
            r = httpx.post(URL, json=body, timeout=90,
                           headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"})
        except httpx.HTTPError as exc:
            raise AIError("Could not reach the AI service") from exc
        if r.status_code != 429 or attempt:
            break
        # Rate limited: wait once if Groq says it's a short wait, otherwise give up (caller falls back).
        try:
            wait = float(r.headers.get("retry-after", "0"))
        except ValueError:
            wait = 0
        if not 0 < wait <= 20:
            break
        time.sleep(wait)
    if r.status_code == 429:
        logger.warning("Groq rate limit: %s", r.text[:300])
        raise AIError("The AI service is busy, please try again shortly")
    if r.status_code >= 400:
        logger.error("Groq API error %s: %s", r.status_code, r.text[:500])
        raise AIError("The AI service returned an error")
    return r.json()


def add_usage(usage: Usage, response: dict) -> None:
    u = response.get("usage") or {}
    usage.input_tokens += u.get("prompt_tokens", 0) or 0
    usage.output_tokens += u.get("completion_tokens", 0) or 0


def parse(system: str, user: str, schema: type[T], *, max_tokens: int = 3000) -> tuple[T, Usage]:
    """Structured output: JSON mode + schema in the prompt + pydantic validation (one retry on a bad shape)."""
    usage = Usage(model=settings.GROQ_MODEL)
    shape = json.dumps(schema.model_json_schema())
    messages = [
        {"role": "system", "content": f"{system}\n\nReply with ONLY a JSON object matching this JSON schema:\n{shape}"},
        {"role": "user", "content": user},
    ]
    for attempt in range(2):
        response = chat(messages, max_tokens=max_tokens, json_mode=True)
        add_usage(usage, response)
        text = (response["choices"][0]["message"].get("content") or "").strip()
        try:
            return schema.model_validate_json(text), usage
        except ValidationError as exc:
            if attempt:
                raise AIError("The AI response was incomplete") from exc
            messages += [{"role": "assistant", "content": text},
                         {"role": "user", "content": f"That JSON did not match the schema ({exc.errors()[:3]}). "
                                                     "Reply again with corrected JSON only."}]
    raise AIError("The AI response was incomplete")

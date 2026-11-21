"""Google Gemini provider - used for social/Google posts, images and live Google Search answers.

REST via httpx (no SDK). Search results come from Gemini's built-in Google Search grounding, and every answer is
returned together with the web sources it was grounded on.
"""
import base64
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from app.core.config import settings
from app.integrations.ai.claude import AIError, Usage

logger = logging.getLogger(__name__)
T = TypeVar("T", bound=BaseModel)
BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def is_configured() -> bool:
    return bool(settings.GEMINI_API_KEY)


def _call(model: str, body: dict, timeout: float = 90) -> dict:
    for attempt in range(2):
        try:
            r = httpx.post(f"{BASE}/{model}:generateContent", json=body, timeout=timeout,
                           headers={"x-goog-api-key": settings.GEMINI_API_KEY or ""})
        except httpx.HTTPError as exc:
            raise AIError("Could not reach the AI service") from exc
        if r.status_code != 503 or attempt:
            break
        time.sleep(2)  # "model overloaded" spikes are usually brief
    if r.status_code == 429:
        logger.warning("Gemini quota/rate limit on %s: %s", model, r.text[:300])
        if "quota" in r.text.lower():
            raise AIError("This needs a paid Gemini plan (quota reached). Turn on billing in Google AI Studio.")
        raise AIError("The AI service is busy, please try again shortly")
    if r.status_code == 503:
        raise AIError("The AI service is busy, please try again shortly")
    if r.status_code >= 400:
        logger.error("Gemini API error %s: %s", r.status_code, r.text[:500])
        raise AIError("The AI service returned an error")
    data = r.json()
    if not data.get("candidates"):
        raise AIError("The AI declined this request")
    return data


def _usage(model: str, data: dict) -> Usage:
    meta = data.get("usageMetadata") or {}
    return Usage(input_tokens=meta.get("promptTokenCount", 0) or 0,
                 output_tokens=meta.get("candidatesTokenCount", 0) or 0, model=model)


def _text(data: dict) -> str:
    parts = data["candidates"][0].get("content", {}).get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


def parse(system: str, user: str, schema: type[T]) -> tuple[T, Usage]:
    """Structured output in JSON mode, validated with pydantic (one corrective retry)."""
    model = settings.GEMINI_MODEL
    prompt = f"{user}\n\nReply with ONLY a JSON object matching this JSON schema:\n{json.dumps(schema.model_json_schema())}"
    contents = [{"role": "user", "parts": [{"text": prompt}]}]
    for attempt in range(2):
        data = _call(model, {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
                             "generationConfig": {"responseMimeType": "application/json", "temperature": 0.6}})
        text = _text(data)
        try:
            return schema.model_validate_json(text), _usage(model, data)
        except ValidationError as exc:
            if attempt:
                raise AIError("The AI response was incomplete") from exc
            contents += [{"role": "model", "parts": [{"text": text}]},
                         {"role": "user", "parts": [{"text": "That JSON did not match the schema. Reply with corrected JSON only."}]}]
    raise AIError("The AI response was incomplete")


@dataclass
class SearchAnswer:
    text: str
    sources: list[dict] = field(default_factory=list)   # [{"title", "url"}]
    queries: list[str] = field(default_factory=list)


def search(question: str, *, system: str | None = None) -> SearchAnswer:
    """Answer a question using live Google Search results (grounded), with the sources it used."""
    body: dict = {"contents": [{"role": "user", "parts": [{"text": question}]}], "tools": [{"google_search": {}}]}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    data = _call(settings.GEMINI_MODEL, body)
    meta = data["candidates"][0].get("groundingMetadata") or {}
    sources, seen = [], set()
    for chunk in meta.get("groundingChunks", []):
        web = chunk.get("web") or {}
        if web.get("uri") and web["uri"] not in seen:
            seen.add(web["uri"])
            sources.append({"title": web.get("title") or web.get("domain") or "", "url": web["uri"]})
    return SearchAnswer(text=_text(data), sources=sources, queries=meta.get("webSearchQueries", []))


@dataclass
class Image:
    mime_type: str
    data: bytes

    @property
    def data_url(self) -> str:
        return f"data:{self.mime_type};base64,{base64.b64encode(self.data).decode()}"


def image(prompt: str) -> Image:
    """Generate one image (e.g. for a Google Business Profile or Instagram post)."""
    data = _call(settings.GEMINI_IMAGE_MODEL, {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }, timeout=120)
    for part in data["candidates"][0].get("content", {}).get("parts", []):
        inline = part.get("inlineData") or part.get("inline_data")
        if inline and inline.get("data"):
            return Image(mime_type=inline.get("mimeType") or inline.get("mime_type") or "image/png",
                         data=base64.b64decode(inline["data"]))
    raise AIError("The AI did not return an image")

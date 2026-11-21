"""Small in-memory sliding-window rate limiter for public endpoints.

Per process: with several API replicas put a shared limiter (e.g. Redis or the
reverse proxy) in front; this still stops casual abuse of a single instance.
"""
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import settings

_hits: dict[str, deque] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check(key: str, limit: int, window_seconds: float = 60.0) -> None:
    now = time.monotonic()
    with _lock:
        hits = _hits[key]
        while hits and now - hits[0] > window_seconds:
            hits.popleft()
        if len(hits) >= limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, please slow down")
        hits.append(now)


def public_limit(bucket: str, limit: int | None = None):
    """FastAPI dependency: limit requests per client IP for one bucket."""

    def dependency(request: Request) -> None:
        check(f"{bucket}:{client_ip(request)}", limit or settings.PUBLIC_RATE_LIMIT_PER_MINUTE)

    return dependency


def reset() -> None:
    with _lock:
        _hits.clear()

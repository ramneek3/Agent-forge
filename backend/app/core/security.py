"""Security helpers: auth dependency and rate limiting abstraction."""

from collections import defaultdict, deque
from time import time
from typing import Deque

from fastapi import Header, HTTPException, Request, status

from app.core.config import get_settings


class RateLimiter:
    """Simple in-memory sliding-window rate limiter (per-process)."""

    def __init__(self, limit: int, window_seconds: int = 60):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, Deque[float]] = defaultdict(deque)

    def check(self, key: str) -> bool:
        now = time()
        q = self._hits[key]
        while q and now - q[0] > self.window:
            q.popleft()
        if len(q) >= self.limit:
            return False
        q.append(now)
        return True


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        settings = get_settings()
        _rate_limiter = RateLimiter(settings.rate_limit_per_minute)
    return _rate_limiter


async def require_admin(
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    settings = get_settings()
    if not settings.auth_enabled:
        return
    if not x_api_key or x_api_key != settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key",
        )


async def rate_limit_dependency(request: Request) -> None:
    client = request.client.host if request.client else "unknown"
    limiter = get_rate_limiter()
    if not limiter.check(client):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded",
        )

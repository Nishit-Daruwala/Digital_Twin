"""Tiny in-memory sliding-window rate limiter.

Protects the OpenAI budget from runaway clients and the login from password guessing.
Per process only, which is enough for a single instance; swap for Redis if the backend is
ever scaled out.
"""

import threading
import time
import weakref
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

_registry: "weakref.WeakSet[RateLimiter]" = weakref.WeakSet()


class RateLimiter:
    def __init__(self, limit: int, window_s: float = 60.0):
        self.limit = limit
        self.window = window_s
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        _registry.add(self)

    def allow(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, seconds_until_next_slot)."""
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] >= self.window:
                q.popleft()
            if len(q) >= self.limit:
                return False, max(1, int(self.window - (now - q[0])) + 1)
            q.append(now)
            if len(self._hits) > 10_000:  # forget idle keys so memory stays bounded
                for k in [k for k, v in self._hits.items() if not v]:
                    del self._hits[k]
            return True, 0

    def enforce(self, key: str, message: str = "Too many requests.") -> None:
        """Raise 429 (with a Retry-After header) when `key` is over the limit."""
        allowed, retry_after = self.allow(key)
        if not allowed:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS,
                f"{message} Try again in {retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()


def reset_all() -> None:
    """Clear every limiter (tests)."""
    for limiter in list(_registry):
        limiter.reset()


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"

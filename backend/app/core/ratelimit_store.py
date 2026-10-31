"""Rate-limit storage.

Two implementations behind one interface:

* `InMemoryStore` — correct for a single process, and the default.
* `RedisStore` — correct across workers, used when `POTENCIA_REDIS_URL` is set.

The interface exists because the failure it prevents is silent: with four
workers and an in-memory limiter, a client gets four times the configured budget
and nothing anywhere reports it. Choosing a shared store is a deployment
decision, not a code change.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Protocol

logger = logging.getLogger(__name__)


class LimitStore(Protocol):
    def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        """Record a hit.

        Returns `(allowed, remaining, retry_after_seconds)`. `retry_after` is 0
        when the request is allowed.
        """
        ...


class InMemoryStore:
    """Sliding window in process memory. One budget per worker, not per cluster."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def reset(self) -> None:
        self._hits.clear()

    def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        now = time.monotonic()
        window = self._hits[key]

        while window and now - window[0] > window_seconds:
            window.popleft()

        if len(window) >= limit:
            retry_after = max(1, int(window_seconds - (now - window[0])))
            return False, 0, retry_after

        window.append(now)
        return True, max(0, limit - len(window)), 0


class RedisStore:
    """Fixed window in Redis, incremented atomically.

    `INCR` + `EXPIRE` in one pipeline is the standard approach: the counter is
    shared by every worker and disappears on its own, so no cleanup job is
    needed. It is a fixed window rather than a sliding one, which permits a
    short burst across a boundary — acceptable for abuse control, and stated
    here rather than discovered later.
    """

    def __init__(self, client, *, prefix: str = "potencia:rl:") -> None:
        self._client = client
        self._prefix = prefix

    def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        bucket = f"{self._prefix}{key}"
        pipe = self._client.pipeline()
        pipe.incr(bucket)
        # NX keeps an existing TTL: a later hit must not extend the window.
        pipe.expire(bucket, window_seconds, nx=True)
        count, _ = pipe.execute()

        if int(count) > limit:
            ttl = int(self._client.ttl(bucket) or window_seconds)
            return False, 0, max(1, ttl)
        return True, max(0, limit - int(count)), 0


def build_store(redis_url: str | None) -> LimitStore:
    """Pick a store from configuration, degrading loudly, never silently."""
    if not redis_url:
        return InMemoryStore()

    try:
        import redis  # imported lazily: the dependency is optional

        client = redis.Redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
    except Exception as exc:  # noqa: BLE001 - any failure means "no shared store"
        # Falling back keeps the API serving; the log line is what stops the
        # fallback from being invisible.
        logger.error(
            "rate limiting is falling back to per-process memory: Redis unavailable",
            extra={"error": type(exc).__name__},
        )
        return InMemoryStore()

    logger.info("rate limiting is using Redis")
    return RedisStore(client)

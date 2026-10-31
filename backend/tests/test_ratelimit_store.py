"""Rate-limit storage: the seam that lets one limiter work per process or shared."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.ratelimit import RateLimitMiddleware
from app.core.ratelimit_store import InMemoryStore, RedisStore, build_store


class DenyStore:
    """A store that always refuses, to prove the middleware delegates."""

    def __init__(self) -> None:
        self.seen: list[tuple[str, int, int]] = []

    def hit(self, key: str, *, limit: int, window_seconds: int) -> tuple[bool, int, int]:
        self.seen.append((key, limit, window_seconds))
        return False, 0, 42


class FakePipeline:
    def __init__(self, redis: "FakeRedis") -> None:
        self._redis = redis
        self._ops: list[tuple[str, tuple]] = []

    def incr(self, key: str) -> None:
        self._ops.append(("incr", (key,)))

    def expire(self, key: str, seconds: int, nx: bool = False) -> None:
        self._ops.append(("expire", (key, seconds, nx)))

    def execute(self) -> list:
        results: list = []
        for name, args in self._ops:
            if name == "incr":
                self._redis.counters[args[0]] = self._redis.counters.get(args[0], 0) + 1
                results.append(self._redis.counters[args[0]])
            else:
                key, seconds, nx = args
                self._redis.expires.append((key, seconds, nx))
                results.append(True)
        return results


class FakeRedis:
    def __init__(self) -> None:
        self.counters: dict[str, int] = {}
        self.expires: list[tuple[str, int, bool]] = []

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)

    def ttl(self, key: str) -> int:
        return 900


def _app(store) -> FastAPI:
    application = FastAPI()
    application.add_middleware(RateLimitMiddleware, store=store)

    @application.post("/api/v1/auth/login")
    def login() -> dict[str, bool]:
        return {"ok": True}

    return application


def test_the_middleware_honours_the_store_it_is_given() -> None:
    store = DenyStore()
    with TestClient(_app(store)) as client:
        response = client.post("/api/v1/auth/login")

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"
    assert store.seen and store.seen[0][1] == 5  # the login rule, not a default


def test_the_in_memory_store_enforces_its_window() -> None:
    store = InMemoryStore()
    with TestClient(_app(store)) as client:
        statuses = [client.post("/api/v1/auth/login").status_code for _ in range(6)]

    assert statuses[:5] == [200] * 5
    assert statuses[5] == 429


def test_redis_store_counts_and_expires_atomically() -> None:
    redis = FakeRedis()
    store = RedisStore(redis)

    allowed = [store.hit("user:1|POST /x", limit=5, window_seconds=900) for _ in range(5)]
    refused = store.hit("user:1|POST /x", limit=5, window_seconds=900)

    assert all(result[0] for result in allowed)
    assert allowed[0][1] == 4  # remaining after the first hit
    assert refused[0] is False
    assert refused[2] > 0

    # NX is essential: a later hit must not extend the window.
    assert all(nx is True for _, _, nx in redis.expires)
    assert redis.counters["potencia:rl:user:1|POST /x"] == 6


def test_no_redis_url_means_the_in_memory_store() -> None:
    assert isinstance(build_store(None), InMemoryStore)


def test_an_unreachable_redis_degrades_to_memory_rather_than_failing_requests() -> None:
    # Port 1 refuses immediately; the point is that construction does not raise.
    assert isinstance(build_store("redis://127.0.0.1:1/0"), InMemoryStore)

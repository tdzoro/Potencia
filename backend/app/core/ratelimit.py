"""Per-identity rate limiting (docs/API.md §4).

The limits themselves live here; the counters live behind `LimitStore`, so the
same middleware works for one process (memory) or many (Redis). See
`ratelimit_store.py` for why that distinction is not cosmetic.

The identity is the authenticated account when a valid token is presented,
otherwise the client IP. IP alone is a poor identity behind NAT, which is why an
authenticated request is counted against the account.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, Response

from app.core.config import get_settings
from app.core.logging import get_request_id
from app.core.ratelimit_store import InMemoryStore, LimitStore, build_store

WINDOW_SECONDS = 3600


@dataclass(frozen=True)
class Limit:
    limit: int
    window_seconds: int = WINDOW_SECONDS


# Ordered most specific first: the first rule whose method and prefix match wins.
_RULES: tuple[tuple[str, str, Limit], ...] = (
    ("POST", "/api/v1/auth/login", Limit(5, 900)),
    ("POST", "/api/v1/auth/register", Limit(5, 900)),
    ("POST", "/api/v1/resumes", Limit(10)),
    ("POST", "/api/v1/analyses", Limit(20)),
    ("POST", "/api/v1/matches", Limit(20)),
    ("POST", "/api/v1/exports", Limit(30)),
    ("", "/api/v1/", Limit(300)),
)


def limit_for(method: str, path: str) -> Limit | None:
    for rule_method, prefix, limit in _RULES:
        if path.startswith(prefix) and (rule_method == "" or rule_method == method.upper()):
            return limit
    return None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # The first entry is the original client; proxies append to the right.
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _identity(request: Request) -> str:
    """The account when the request carries a valid token, else the client IP.

    Counting an authenticated request against the account means a shared office
    IP does not throttle an entire building, and a single client rotating tokens
    cannot escape its own limit.
    """
    authorization = request.headers.get("authorization", "")
    token = authorization[7:] if authorization.lower().startswith("bearer ") else ""
    if token:
        try:
            from app.core.security import decode_token

            payload = decode_token(token)
            subject = payload.get("sub")
            if isinstance(subject, str) and subject:
                return f"user:{subject}"
        except Exception:  # noqa: BLE001 - an invalid token is simply not an identity
            pass
    return f"ip:{_client_ip(request)}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Counts hits per (identity, rule) and returns `429` with `Retry-After`."""

    def __init__(self, app, *, enabled: bool = True, store: LimitStore | None = None) -> None:
        super().__init__(app)
        self.enabled = enabled
        self.store = store or build_store(get_settings().redis_url)

    def reset(self) -> None:
        if isinstance(self.store, InMemoryStore):
            self.store.reset()
        else:  # pragma: no cover - Redis is only used in deployment
            raise RuntimeError("reset() is only meaningful for the in-memory store")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not self.enabled:
            return await call_next(request)

        limit = limit_for(request.method, request.url.path)
        if limit is None:
            return await call_next(request)

        key = f"{_identity(request)}|{request.method} {request.url.path}"
        allowed, remaining, retry_after = self.store.hit(
            key, limit=limit.limit, window_seconds=limit.window_seconds
        )

        if not allowed:
            return JSONResponse(
                status_code=429,
                headers={"Retry-After": str(retry_after)},
                content={
                    "error": {
                        "code": "rate_limited",
                        "message": "Too many requests. Try again later.",
                        "details": [
                            {
                                "field": "request",
                                "issue": "rate_limited",
                                "meta": {
                                    "limit": limit.limit,
                                    "window_seconds": limit.window_seconds,
                                },
                            }
                        ],
                        "request_id": get_request_id(),
                    }
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

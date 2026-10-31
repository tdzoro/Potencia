"""Idempotent create endpoints (docs/API.md §1.5).

Supplying `X-Idempotency-Key` makes a POST replayable: the first call performs
the work and stores its response, a repeat within 24 hours returns that stored
response with `200` and `Idempotency-Replayed: true`.

Two failure modes are refused rather than papered over:

* the same key used for a different endpoint is a `409`, because replaying
  another resource's body would be a lie;
* an unrecognisable key is a `422`, because silently ignoring it would let the
  client believe it was protected when it was not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import PotenciaError
from app.models.idempotency import IdempotencyKey
from app.models.user import User

HEADER = "X-Idempotency-Key"
REPLAY_HEADER = "Idempotency-Replayed"
WINDOW = timedelta(hours=24)
MIN_KEY_LENGTH = 8
MAX_KEY_LENGTH = 200


@dataclass(frozen=True)
class Replay:
    status: int
    body: dict
    original_path: str


def _key_from(request: Request) -> str | None:
    raw = request.headers.get(HEADER)
    if raw is None:
        return None
    key = raw.strip()
    if not (MIN_KEY_LENGTH <= len(key) <= MAX_KEY_LENGTH):
        raise PotenciaError(
            "validation_error",
            422,
            f"{HEADER} must be between {MIN_KEY_LENGTH} and {MAX_KEY_LENGTH} characters.",
            [{"field": HEADER, "issue": "invalid_length"}],
        )
    return key


def find(db: Session, user: User, symbol: str) -> IdempotencyKey | None:
    return db.scalar(
        select(IdempotencyKey).where(
            IdempotencyKey.user_id == user.id,
            IdempotencyKey.key == symbol,
        )
    )


def replay_or_refuse(db: Session, user: User, request: Request) -> Response | None:
    """Return the stored response for a repeat, or None to proceed."""
    key = _key_from(request)
    if key is None:
        return None

    stored = find(db, user, key)
    if stored is None:
        return None

    created = stored.created_at
    if created.tzinfo is None:  # SQLite returns naive datetimes
        created = created.replace(tzinfo=timezone.utc)
    if datetime.now(timezone.utc) - created > WINDOW:
        # Expired: the key may be used for fresh work, so drop the stale record.
        db.delete(stored)
        db.commit()
        return None

    if stored.path != request.url.path:
        raise PotenciaError(
            "conflict",
            409,
            "This idempotency key was already used for a different request.",
            [{"field": HEADER, "issue": "key_reused_across_endpoints"}],
        )

    return JSONResponse(
        content=stored.response_body,
        status_code=200,
        # The header name is part of the published contract (docs/API.md §1.5).
        headers={REPLAY_HEADER: "true"},
    )


def remember(
    db: Session,
    user: User,
    request: Request,
    payload: BaseModel | dict,
    *,
    status: int,
) -> None:
    """Store the response for this key. Safe under a concurrent duplicate."""
    key = _key_from(request)
    if key is None:
        return

    body = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
    record = IdempotencyKey(
        user_id=user.id,
        key=key,
        method=request.method,
        path=request.url.path,
        response_status=status,
        response_body=body,
    )
    db.add(record)
    try:
        db.commit()
    except IntegrityError:
        # Another request with the same key won the race. Its response is the
        # canonical one; this one still completed, which is harmless.
        db.rollback()

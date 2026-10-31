"""Signed download tokens for exported files.

A download URL is a capability, not a session: it must work without the access
token (so a browser can follow it) yet must not be guessable, must expire, and
must be bound to exactly one file and one owner. An HMAC over
`(export_id, user_id, expiry)` satisfies all three.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import datetime, timedelta, timezone

from app.core.config import get_settings
from app.core.errors import PotenciaError

DOWNLOAD_TOKEN_TTL = timedelta(minutes=15)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def _sign(payload: str) -> str:
    secret = get_settings().secret_key.encode("utf-8")
    return _b64(hmac.new(secret, payload.encode("utf-8"), hashlib.sha256).digest())


def issue_download_token(
    export_id: uuid.UUID, user_id: uuid.UUID, *, expires_at: datetime | None = None
) -> tuple[str, datetime]:
    expiry = expires_at or (datetime.now(timezone.utc) + DOWNLOAD_TOKEN_TTL)
    payload = f"{export_id}.{user_id}.{int(expiry.timestamp())}"
    return f"{payload}.{_sign(payload)}", expiry


def verify_download_token(token: str, *, export_id: uuid.UUID) -> uuid.UUID:
    """Return the bound user id, or raise the same 404 as a missing export.

    The error is deliberately indistinguishable from "no such export": a
    distinguishable failure tells an attacker that an id exists.
    """
    invalid = PotenciaError("not_found", 404, "Export not found.")
    try:
        raw_export, raw_user, raw_expiry, signature = token.split(".")
        expected = _sign(f"{raw_export}.{raw_user}.{raw_expiry}")
    except ValueError:
        raise invalid from None

    if not hmac.compare_digest(signature, expected):
        raise invalid
    if raw_export != str(export_id):
        raise invalid
    if datetime.now(timezone.utc).timestamp() > int(raw_expiry):
        raise invalid
    try:
        return uuid.UUID(raw_user)
    except ValueError:
        raise invalid from None


__all__ = ["DOWNLOAD_TOKEN_TTL", "issue_download_token", "verify_download_token"]

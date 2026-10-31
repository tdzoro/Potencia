"""Password hashing and token handling.

Two deliberate choices:

1. Passwords are SHA-256 pre-hashed before bcrypt. bcrypt silently truncates at
   72 bytes, so a long passphrase would be partially ignored — pre-hashing makes
   the whole input significant without changing the stored format's strength.
2. Access tokens are short-lived and carry only an identifier. Nothing about the
   user's data is embedded, so revoking an account does not require rotating a
   secret that other sessions depend on.
"""

from __future__ import annotations

import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

from app.core.config import get_settings

ACCESS_TOKEN_TTL = timedelta(minutes=15)
REFRESH_TOKEN_TTL = timedelta(days=14)
ALGORITHM = "HS256"

# bcrypt only reads the first 72 bytes; pre-hash so length never truncates.
_MAX_BCRYPT_BYTES = 72


def _prehash(password: str) -> bytes:
    digest = hashlib.sha256(password.encode("utf-8")).digest()
    return base64.b64encode(digest)[:_MAX_BCRYPT_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_prehash(password), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time comparison; malformed hashes are a failed login, not a 500."""
    try:
        return bcrypt.checkpw(_prehash(password), password_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False


def _encode(subject: str, token_type: str, ttl: timedelta, extra: dict | None = None) -> str:
    now = datetime.now(timezone.utc)
    payload: dict = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: str) -> str:
    return _encode(user_id, "access", ACCESS_TOKEN_TTL)


def create_refresh_token(user_id: str, token_version: int = 0) -> str:
    # `ver` lets a password change invalidate every outstanding refresh token
    # without a per-token table.
    return _encode(user_id, "refresh", REFRESH_TOKEN_TTL, {"ver": token_version})


def decode_token(token: str, expected_type: str) -> dict:
    """Decode and validate. Raises `jwt.PyJWTError` on any failure."""
    payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("unexpected token type")
    if not payload.get("sub"):
        raise jwt.InvalidTokenError("missing subject")
    return payload


def refresh_token_fingerprint(token: str) -> str:
    """Stored value for a refresh token, so the raw token is never persisted."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

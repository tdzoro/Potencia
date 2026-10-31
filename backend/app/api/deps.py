"""Request dependencies.

`get_current_user` is the single gate for authenticated routes. Every failure —
absent header, malformed token, expired token, wrong token type, deleted account
— becomes the same `401 unauthenticated`, so no detail about why a credential
failed is disclosed.
"""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.errors import PotenciaError
from app.core.security import decode_token
from app.models.user import User
from app.repositories import users as users_repo

# auto_error=False so a missing header reaches our handler and gets the
# documented envelope instead of FastAPI's default {"detail": ...}.
_bearer_scheme = HTTPBearer(auto_error=False)

_UNAUTHENTICATED_MESSAGE = "Authentication is required."


def _unauthenticated() -> PotenciaError:
    return PotenciaError("unauthenticated", 401, _UNAUTHENTICATED_MESSAGE)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise _unauthenticated()

    try:
        claims = decode_token(credentials.credentials, "access")
        user_id = uuid.UUID(str(claims["sub"]))
    except (jwt.PyJWTError, KeyError, TypeError, ValueError) as exc:
        raise _unauthenticated() from exc

    user = users_repo.get_active_by_id(session, user_id)
    if user is None:
        raise _unauthenticated()

    return user

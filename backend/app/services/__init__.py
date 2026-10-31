"""Application services.

A service owns a business rule and its transaction boundary. Routes translate
HTTP to calls; they do not contain policy.
"""

from __future__ import annotations

from app.services import auth_service

__all__ = ["auth_service"]

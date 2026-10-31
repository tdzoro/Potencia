"""Data access layer.

Repositories are the only place that builds queries. Route handlers and services
call them with an explicit `Session`, which keeps every read scoped by the
caller rather than filtered after the fact.
"""

from __future__ import annotations

from app.repositories import users

__all__ = ["users"]

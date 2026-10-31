"""Model package.

Importing this module is what registers every table on `Base.metadata`, which is
what Alembic autogenerate and the test fixtures both read. A model that is not
imported here is invisible to migrations — the failure mode is a table that
silently never gets created.
"""

from __future__ import annotations

from app.models.analysis import Analysis, Export, Match, Recommendation
from app.models.base import Base
from app.models.content import Job, Resume, ResumeRevision
from app.models.idempotency import IdempotencyKey
from app.models.user import User

__all__ = [
    "Analysis",
    "Base",
    "Export",
    "IdempotencyKey",
    "Job",
    "Match",
    "Recommendation",
    "Resume",
    "ResumeRevision",
    "User",
]

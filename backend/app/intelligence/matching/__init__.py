"""Job-description matching package."""

from __future__ import annotations

from app.intelligence.matching.engine import match_resume
from app.intelligence.matching.requirements import extract_requirements

__all__ = ["extract_requirements", "match_resume"]

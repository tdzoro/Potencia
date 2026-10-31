"""Deterministic scoring package.

Import the public entry point from here:

    from app.intelligence.scoring.engine import score_resume

The submodules are imported explicitly rather than star-exported so that the
dependency direction stays readable: criteria modules depend on `aggregate`,
and only `engine` depends on all of them.
"""

from __future__ import annotations

from app.intelligence.scoring.aggregate import (
    CATEGORY_WEIGHTS,
    ScoreResult,
    band_for,
)
from app.intelligence.scoring.engine import score_resume

__all__ = ["CATEGORY_WEIGHTS", "ScoreResult", "band_for", "score_resume"]

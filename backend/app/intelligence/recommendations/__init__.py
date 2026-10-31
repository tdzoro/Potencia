"""Recommendation generators.

`rules` is the deterministic source of every recommendation produced today. It
is the only generator wired in, so nothing here can invent a fact the resume
does not contain.
"""

from __future__ import annotations

from app.intelligence.recommendations.rules import generate, summarise_skill_gaps

__all__ = ["generate", "summarise_skill_gaps"]

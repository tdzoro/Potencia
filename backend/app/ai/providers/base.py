"""Provider-independent rewrite interface.

The seam exists so a model can be added later without touching business logic.
Two rules make that safe:

1. A provider may only return *rewrites of text the user already wrote*. It never
   receives the score, and its output never changes one.
2. A proposal is validated against a schema before use. A malformed response is
   discarded, not repaired with a guess.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class RewriteRequest(BaseModel):
    original_text: str
    reason: str
    context: str = ""


class RewriteProposal(BaseModel):
    proposed_text: str = Field(min_length=1, max_length=2000)
    confidence: str = "medium"
    provider: str


class RewriteProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def propose(self, request: RewriteRequest) -> RewriteProposal | None: ...


class NullRewriteProvider:
    """Used when no provider is configured.

    It proposes nothing rather than pretending: the deterministic rules still
    produce useful, factual recommendations without it.
    """

    name = "none"

    def available(self) -> bool:
        return False

    def propose(self, request: RewriteRequest) -> RewriteProposal | None:  # noqa: ARG002
        return None

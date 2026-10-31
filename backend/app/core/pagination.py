"""Opaque list cursors.

A cursor is the id of the last row returned. Primary keys are UUIDv7, which are
ordered by creation time, so `order by id desc` *is* `order by newest first` —
and keyset pagination on it stays correct while new rows arrive.

An offset would not: rows inserted between two page requests shift the window,
which silently skips or repeats records. Comparison is always done in SQL against
the id column, so the cursor is correct whether the database sorts UUIDs as bytes
or as text.
"""

from __future__ import annotations

import base64
import binascii
import uuid

from app.core.errors import PotenciaError


def encode_cursor(row_id: uuid.UUID) -> str:
    return base64.urlsafe_b64encode(str(row_id).encode("ascii")).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> uuid.UUID:
    try:
        padded = value + "=" * (-len(value) % 4)
        return uuid.UUID(base64.urlsafe_b64decode(padded).decode("ascii"))
    except (ValueError, binascii.Error, UnicodeDecodeError):
        raise PotenciaError(
            "validation_error",
            422,
            "The pagination cursor is not valid.",
            [{"field": "cursor", "issue": "invalid_cursor"}],
        ) from None

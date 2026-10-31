"""Identifier generation.

UUIDv7 is used instead of v4 because it is time-ordered: new rows append to the
end of an index rather than scattering across it, which matters once a resume
history table grows. The values stay opaque to clients (docs/API.md §1.1).
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7() -> uuid.UUID:
    """Return a UUIDv7.

    Layout (RFC 9562): 48-bit unix timestamp in milliseconds, 4-bit version,
    12-bit random, 2-bit variant, 62-bit random. Time-ordered and opaque.
    """
    timestamp_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand_a = int.from_bytes(os.urandom(2), "big") & 0x0FFF
    rand_b = int.from_bytes(os.urandom(8), "big") & 0x3FFF_FFFF_FFFF_FFFF

    value = timestamp_ms << 80
    value |= 0x7 << 76
    value |= rand_a << 64
    value |= 0b10 << 62
    value |= rand_b
    return uuid.UUID(int=value)


def new_id() -> uuid.UUID:
    return uuid7()


def request_id(prefix: str = "req") -> str:
    """Human-scannable id used for log correlation."""
    return f"{prefix}_{uuid.uuid4().hex[:20]}"

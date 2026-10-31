"""Local object storage.

Documents are never stored in the database and never served from a guessable
path. A key is the SHA-256 of the content plus the resolved extension, so two
uploads of the same file collapse to one object and a caller cannot influence
where the bytes land.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache
from pathlib import Path

from app.core.config import get_settings

_EXTENSION_BY_MEDIA_TYPE = {
    "application/pdf": ".pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
}


class LocalObjectStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

    def _safe_path(self, key: str) -> Path:
        candidate = (self.root / key).resolve()
        # Defence in depth: a key that escapes the root is a traversal attempt.
        if self.root not in candidate.parents and candidate != self.root:
            raise ValueError("refusing to access a path outside the store")
        return candidate

    def put(self, data: bytes, media_type: str, *, prefix: str = "") -> tuple[str, str]:
        """Store bytes and return `(key, sha256)`.

        `prefix` keeps collections apart — deleting an export must never unlink
        an uploaded document that happens to hash to the same bytes.
        """
        suffix = _EXTENSION_BY_MEDIA_TYPE.get(media_type)
        if suffix is None:
            raise ValueError(f"unsupported media type for storage: {media_type}")
        digest = hashlib.sha256(data).hexdigest()
        key = f"{prefix}{digest[:2]}/{digest}{suffix}"
        path = self._safe_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key, digest

    def get(self, key: str) -> bytes:
        return self._safe_path(key).read_bytes()

    def delete(self, key: str) -> None:
        try:
            self._safe_path(key).unlink()
        except FileNotFoundError:
            pass


@lru_cache
def get_store() -> LocalObjectStore:
    return LocalObjectStore(get_settings().storage_root)

"""Resume ingestion orchestration.

Order is fixed and deliberate:
1. Validate bytes (size, extension, signature, container structure)
2. Scan for malware (ClamAV / test engine)
3. Store approved bytes in isolated storage
4. Extract document text
5. Parse and populate revision 0
If extraction or persistence fails, the stored object is immediately cleaned up.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PotenciaError
from app.core.pagination import decode_cursor, encode_cursor
from app.core.storage import get_store
from app.document.extraction import extract
from app.document.validation import sanitize_filename, validate_upload
from app.intelligence.parser import parse_document
from app.models.content import Resume, ResumeRevision
from app.models.user import User
from app.services.malware_scanner import get_malware_scanner


def create_resume(
    db: Session,
    user: User,
    *,
    filename: str,
    declared_content_type: str | None,
    data: bytes,
) -> Resume:
    # Step 1: Sanitize user-provided filename
    safe_filename = sanitize_filename(filename)

    # Step 2: Validate file extension, signature, and internal container structure
    media_type = validate_upload(safe_filename, declared_content_type, data)

    # Step 3: Malware scanning (ClamAV integration / test scanner)
    scanner = get_malware_scanner()
    scan_result = scanner.scan_bytes(data, safe_filename)
    if scan_result.is_malicious:
        raise PotenciaError(
            "file_rejected",
            422,
            f"Malicious content detected: {scan_result.virus_name or 'threat detected'}.",
            [{"issue": "malware_detected", "virus": scan_result.virus_name}],
        )

    # Step 4: Secure storage of approved bytes
    store = get_store()
    key, digest = store.put(data, media_type)

    try:
        try:
            extraction = extract(data, media_type)
        except Exception as exc:  # a corrupt file must not surface as a 500
            raise PotenciaError(
                "file_rejected", 422, "The document could not be read."
            ) from exc

        resume = Resume(
            user_id=user.id,
            original_filename=safe_filename[:255],
            media_type=media_type,
            size_bytes=len(data),
            checksum_sha256=digest,
            storage_key=key,
            page_count=extraction.page_count,
            status="completed" if extraction.text.strip() else "failed",
        )

        structure = None
        if extraction.text.strip():
            structure = parse_document(extraction)
            resume.structure = structure.model_dump(mode="json")
            resume.extraction = {
                "confidence": extraction.confidence,
                "method": extraction.method,
                "ocr_used": extraction.ocr_used,
                "text_chars": len(extraction.text),
                "warnings": extraction.warnings,
            }
        else:
            resume.extraction = {
                "confidence": extraction.confidence,
                "method": extraction.method,
                "ocr_used": extraction.ocr_used,
                "text_chars": 0,
                "warnings": extraction.warnings,
            }
            resume.failure = {
                "code": "extraction_empty",
                "message": "No text layer was found. The document may be a scanned image.",
                "retryable": False,
            }

        db.add(resume)
        # Flush to obtain the generated id before the revision references it.
        db.flush()

        if structure is not None:
            # Revision 0 is the untouched parse; later edits are new nodes.
            db.add(
                ResumeRevision(
                    resume_id=resume.id,
                    user_id=user.id,
                    parent_id=None,
                    content=structure.model_dump(mode="json"),
                    applied_recommendations=[],
                    created_at=datetime.now(timezone.utc),
                )
            )

        db.commit()
        db.refresh(resume)
        return resume
    except Exception:
        # Clean up stored file if extraction or persistence fails
        store.delete(key)
        raise


def get_resume(db: Session, user: User, resume_id: uuid.UUID) -> Resume:
    """Ownership is part of the query: another user's id is simply not found."""
    resume = db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    if resume is None:
        raise PotenciaError("not_found", 404, "Resume not found.")
    return resume


def list_resumes(
    db: Session, user: User, limit: int = 20, cursor: str | None = None
) -> tuple[list[Resume], str | None]:
    """Newest first, keyset-paginated by id (UUIDv7 is time-ordered)."""
    statement = select(Resume).where(Resume.user_id == user.id)
    if cursor:
        statement = statement.where(Resume.id < decode_cursor(cursor))

    rows = list(db.scalars(statement.order_by(Resume.id.desc()).limit(limit + 1)))
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = encode_cursor(rows[-1].id) if has_more and rows else None
    return rows, next_cursor


def delete_resume(db: Session, user: User, resume_id: uuid.UUID) -> None:
    resume = get_resume(db, user, resume_id)
    get_store().delete(resume.storage_key)
    db.delete(resume)
    db.commit()

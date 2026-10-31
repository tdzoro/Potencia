"""Resume ingestion orchestration.

Order is fixed and deliberate: validate bytes → store → extract → parse. A
document that fails validation never reaches the store, and a document whose
extraction fails is still stored and recorded as `failed` so the user can see
what happened rather than wondering why nothing appeared.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import PotenciaError
from app.core.storage import get_store
from app.document.extraction import extract
from app.document.validation import validate_upload
from app.intelligence.parser import parse_document
from app.models.content import Resume
from app.models.user import User


def create_resume(
    db: Session,
    user: User,
    *,
    filename: str,
    declared_content_type: str | None,
    data: bytes,
) -> Resume:
    media_type = validate_upload(filename, declared_content_type, data)
    key, digest = get_store().put(data, media_type)

    try:
        extraction = extract(data, media_type)
    except Exception as exc:  # a corrupt file must not surface as a 500
        raise PotenciaError(
            "file_rejected", 422, "The document could not be read."
        ) from exc

    resume = Resume(
        user_id=user.id,
        original_filename=filename[:255],
        media_type=media_type,
        size_bytes=len(data),
        checksum_sha256=digest,
        storage_key=key,
        page_count=extraction.page_count,
        status="completed" if extraction.text.strip() else "failed",
    )

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
    db.commit()
    db.refresh(resume)
    return resume


def get_resume(db: Session, user: User, resume_id: uuid.UUID) -> Resume:
    """Ownership is part of the query: another user's id is simply not found."""
    resume = db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    if resume is None:
        raise PotenciaError("not_found", 404, "Resume not found.")
    return resume


def list_resumes(db: Session, user: User, limit: int = 20) -> list[Resume]:
    return list(
        db.scalars(
            select(Resume)
            .where(Resume.user_id == user.id)
            .order_by(Resume.created_at.desc())
            .limit(limit)
        )
    )


def delete_resume(db: Session, user: User, resume_id: uuid.UUID) -> None:
    resume = get_resume(db, user, resume_id)
    get_store().delete(resume.storage_key)
    db.delete(resume)
    db.commit()

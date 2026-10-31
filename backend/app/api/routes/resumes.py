"""Resume upload, listing, retrieval and deletion (docs/API.md §3.3)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import PotenciaError
from app.models.content import Resume
from app.models.user import User
from app.schemas.resume import ResumeStructure
from app.schemas.resumes import (
    ExtractionOut,
    ResumeListOut,
    ResumeOut,
    ResumeSummaryOut,
)
from app.services import resume_service

router = APIRouter(prefix="/resumes", tags=["resumes"])


def _extraction_out(resume: Resume) -> ExtractionOut | None:
    if not resume.extraction:
        return None
    raw = resume.extraction
    return ExtractionOut(
        confidence=float(raw.get("confidence", 0.0)),
        method=str(raw.get("method", "unknown")),
        ocr_used=bool(raw.get("ocr_used", False)),
        text_chars=int(raw.get("text_chars", 0)),
        warnings=list(raw.get("warnings", [])),
    )


def _to_out(resume: Resume, *, include_structure: bool = True) -> ResumeOut:
    structure = (
        ResumeStructure.model_validate(resume.structure)
        if include_structure and resume.structure
        else None
    )
    return ResumeOut(
        id=str(resume.id),
        original_filename=resume.original_filename,
        media_type=resume.media_type,
        size_bytes=resume.size_bytes,
        page_count=resume.page_count,
        status=resume.status,
        created_at=resume.created_at,
        extraction=_extraction_out(resume),
        structure=structure,
        failure=resume.failure,
    )


async def _read_limited(upload: UploadFile) -> bytes:
    """Read at most the configured limit, then reject.

    Reading the whole body before checking length would let a large upload be
    buffered in memory — the limit is enforced while reading, not after.
    """
    limit = get_settings().max_upload_bytes
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await upload.read(64 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > limit:
            raise PotenciaError(
                "payload_too_large",
                413,
                "The file exceeds the 5 MiB upload limit.",
                [{"field": "file", "issue": "exceeds_max_size", "meta": {"max_bytes": limit}}],
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("", status_code=201, response_model=ResumeOut)
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ResumeOut:
    data = await _read_limited(file)
    resume = resume_service.create_resume(
        db,
        user,
        filename=file.filename or "resume",
        declared_content_type=file.content_type,
        data=data,
    )
    return _to_out(resume)


@router.get("", response_model=ResumeListOut)
def list_resumes(
    limit: int = 20, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ResumeListOut:
    rows = resume_service.list_resumes(db, user, limit=min(limit, 100))
    return ResumeListOut(
        items=[
            ResumeSummaryOut(
                id=str(resume.id),
                original_filename=resume.original_filename,
                page_count=resume.page_count,
                status=resume.status,
                created_at=resume.created_at,
                extraction=_extraction_out(resume),
            )
            for resume in rows
        ],
        next_cursor=None,
        has_more=False,
    )


@router.get("/{resume_id}", response_model=ResumeOut)
def read_resume(
    resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> ResumeOut:
    return _to_out(resume_service.get_resume(db, user, resume_id))


@router.delete("/{resume_id}", status_code=204)
def delete_resume(
    resume_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    resume_service.delete_resume(db, user, resume_id)

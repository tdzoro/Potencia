"""Export creation, retrieval and signed download (docs/API.md §3.8).

Rendering happens synchronously and the row is only marked `completed` once the
bytes are on disk and the file has been re-opened to prove it is valid. A file
that exists but cannot be parsed is a failed export, not a successful one.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import signing
from app.core.errors import PotenciaError
from app.core.storage import get_store
from app.document.export import (
    render_analysis_report,
    render_resume_docx,
    render_resume_pdf,
)
from app.models.analysis import Analysis, Export
from app.models.content import Resume, ResumeRevision
from app.models.user import User
from app.schemas.resume import ResumeStructure
from app.services import analysis_service

MEDIA_TYPES = {
    "pdf": "application/pdf",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
# The file itself outlives the link, but not indefinitely (§ privacy retention).
FILE_RETENTION = timedelta(hours=24)


def _report_payload(analysis: Analysis) -> dict:
    return {
        "scores": analysis.scores or {},
        "ats": analysis.ats or {},
        "findings": analysis.findings or [],
        "strengths": analysis.strengths or [],
        "priority_actions": analysis.priority_actions or [],
    }


def _latest_structure(db: Session, user: User, resume: Resume) -> ResumeStructure:
    """The most recent user-approved revision, falling back to the parse.

    An "improved resume" must be the version the user actually approved, so the
    newest revision wins; revision 0 is the untouched parse.
    """
    revision = db.scalar(
        select(ResumeRevision)
        .where(ResumeRevision.resume_id == resume.id, ResumeRevision.user_id == user.id)
        # IDs are UUIDv7, so the tie-break keeps "newest" deterministic even when
        # two revisions land in the same clock tick.
        .order_by(ResumeRevision.created_at.desc(), ResumeRevision.id.desc())
        .limit(1)
    )
    if revision is not None and revision.content:
        return ResumeStructure.model_validate(revision.content)
    if resume.structure:
        return ResumeStructure.model_validate(resume.structure)
    raise PotenciaError("unprocessable", 422, "The resume has no usable structure to export.")


def _verify_render(data: bytes, fmt: str) -> None:
    """Re-open the rendered bytes; a produced file is not a valid file."""
    if not data:
        raise PotenciaError("internal_error", 500, "Export rendering produced no content.")
    if fmt == "pdf":
        import pymupdf

        with pymupdf.open(stream=data, filetype="pdf") as document:
            if document.page_count == 0 or not document.load_page(0).get_text().strip():
                raise PotenciaError("internal_error", 500, "The rendered PDF is not readable.")
    else:
        from docx import Document as DocxDocument

        document = DocxDocument(io.BytesIO(data))
        if not any(paragraph.text.strip() for paragraph in document.paragraphs):
            raise PotenciaError("internal_error", 500, "The rendered DOCX is not readable.")


def create_export(
    db: Session, user: User, *, analysis_id: uuid.UUID, kind: str, fmt: str
) -> Export:
    analysis = analysis_service.get_analysis(db, user, analysis_id)
    if analysis.status != "completed":
        raise PotenciaError(
            "conflict", 409, "The analysis must complete before it can be exported."
        )
    resume = db.get(Resume, analysis.resume_id)
    if resume is None:
        raise PotenciaError("not_found", 404, "Resume not found.")

    record = Export(
        user_id=user.id,
        analysis_id=analysis.id,
        kind=kind,
        format=fmt,
        status="queued",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    try:
        if kind == "analysis_report":
            data = render_analysis_report(
                _report_payload(analysis),
                filename=resume.original_filename,
                generated_at=datetime.now(timezone.utc),
            )
        else:
            structure = _latest_structure(db, user, resume)
            data = render_resume_pdf(structure) if fmt == "pdf" else render_resume_docx(structure)
        _verify_render(data, fmt)
        key, _digest = get_store().put(data, MEDIA_TYPES[fmt], prefix="exports/")
    except PotenciaError:
        record.status = "failed"
        db.commit()
        raise
    except Exception as exc:  # noqa: BLE001 - rendered failure is recorded, not hidden
        record.status = "failed"
        record.failure = {"message": str(exc)[:300]}
        db.commit()
        raise PotenciaError("internal_error", 500, "The export could not be generated.") from exc

    record.storage_key = key
    record.size_bytes = len(data)
    record.status = "completed"
    record.expires_at = datetime.now(timezone.utc) + FILE_RETENTION
    db.commit()
    db.refresh(record)
    return record


def get_export(db: Session, user: User, export_id: uuid.UUID) -> Export:
    record = db.scalar(
        select(Export).where(Export.id == export_id, Export.user_id == user.id)
    )
    if record is None:
        raise PotenciaError("not_found", 404, "Export not found.")
    return record


def list_exports(db: Session, user: User, analysis_id: uuid.UUID) -> list[Export]:
    analysis = analysis_service.get_analysis(db, user, analysis_id)
    return list(
        db.scalars(
            select(Export)
            .where(Export.analysis_id == analysis.id, Export.user_id == user.id)
            .order_by(Export.created_at.desc())
        )
    )


def download_token(record: Export) -> tuple[str, datetime]:
    return signing.issue_download_token(record.id, record.user_id)


def read_download(db: Session, export_id: uuid.UUID, token: str) -> tuple[bytes, str, str]:
    """Return `(bytes, media_type, filename)` for a valid signed request."""
    user_id = signing.verify_download_token(token, export_id=export_id)
    record = db.scalar(
        select(Export).where(Export.id == export_id, Export.user_id == user_id)
    )
    if record is None or record.status != "completed" or not record.storage_key:
        raise PotenciaError("not_found", 404, "Export not found.")

    filename = (
        "potencia-analysis-report.pdf"
        if record.kind == "analysis_report"
        else f"potencia-resume.{record.format}"
    )
    return get_store().get(record.storage_key), MEDIA_TYPES[record.format], filename


def delete_export(db: Session, user: User, export_id: uuid.UUID) -> None:
    record = get_export(db, user, export_id)
    if record.storage_key:
        get_store().delete(record.storage_key)
    db.delete(record)
    db.commit()


def to_payload(record: Export, download_url: str | None) -> dict:
    return {
        "id": str(record.id),
        "analysis_id": str(record.analysis_id),
        "kind": record.kind,
        "format": record.format,
        "status": record.status,
        "size_bytes": record.size_bytes,
        "download_url": download_url,
        "expires_at": record.expires_at,
        "failure": record.failure,
    }

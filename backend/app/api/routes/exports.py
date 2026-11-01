"""Export endpoints (docs/API.md §3.8).

Creation requires an access token. Download does not: it is authorised by the
signed, short-lived token in the URL, so the browser can follow it directly
without the file ever being public.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Request, Response
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import idempotency
from app.core.database import get_db
from app.core.errors import PotenciaError
from app.models.analysis import Export
from app.models.user import User
from app.schemas.resumes import CreateExportRequest, ExportOut
from app.services import export_service

router = APIRouter(prefix="/exports", tags=["exports"])


def _download_url(request: Request, record: Export) -> str | None:
    if record.status != "completed":
        return None
    token, _expiry = export_service.download_token(record)
    base = str(request.url_for("download_export", export_id=str(record.id)))
    return f"{base}?token={token}"


def to_api_out(request: Request, record: Export) -> ExportOut:
    """The public shape of an export, including its signed download URL."""
    return ExportOut.model_validate(export_service.to_payload(record, _download_url(request, record)))


@router.post("", status_code=202, response_model=ExportOut)
def create_export(
    payload: CreateExportRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExportOut | Response:
    replayed = idempotency.replay_or_refuse(db, user, request)
    if replayed is not None:
        return replayed

    if payload.kind == "analysis_report" and payload.format != "pdf":
        raise PotenciaError(
            "validation_error",
            422,
            "An analysis report is exported as PDF only.",
            [{"field": "format", "issue": "unsupported_pairing"}],
        )
    if payload.kind == "analysis_report" and payload.revision_id is not None:
        raise PotenciaError(
            "validation_error",
            422,
            "An analysis report describes the analysis, not a resume version.",
            [{"field": "revision_id", "issue": "unsupported_pairing"}],
        )
    record = export_service.create_export(
        db,
        user,
        analysis_id=payload.analysis_id,
        kind=payload.kind,
        fmt=payload.format,
        revision_id=payload.revision_id,
    )
    out = to_api_out(request, record)
    idempotency.remember(db, user, request, out, status=202)
    return out


@router.get("/{export_id}", response_model=ExportOut)
def read_export(
    export_id: uuid.UUID,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExportOut:
    return to_api_out(request, export_service.get_export(db, user, export_id))


@router.get("/{export_id}/download", name="download_export")
def download_export(
    export_id: uuid.UUID,
    token: str = Query(..., min_length=8),
    db: Session = Depends(get_db),
) -> Response:
    data, media_type, filename = export_service.read_download(db, export_id, token)
    return Response(
        content=data,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
            # The file is user content; never let a browser sniff a type into it.
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete("/{export_id}", status_code=204)
def delete_export(
    export_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> None:
    export_service.delete_export(db, user, export_id)

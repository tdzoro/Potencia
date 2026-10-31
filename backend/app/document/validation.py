"""Upload validation.

Order matters and follows docs/API.md §3.3: cheapest and safest checks first, so
an oversized or mislabelled file is rejected before any parser allocates memory
for it. The extension is treated as a *claim*, never as evidence — a file named
`resume.pdf` that is really a PNG is rejected, and so is a DOCX carrying macros
or an archive bomb.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath

import fitz  # PyMuPDF

from app.core.errors import PotenciaError

PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

MAX_BYTES = 5 * 1024 * 1024  # 5 MiB

EXTENSION_TO_MEDIA_TYPE: dict[str, str] = {
    ".pdf": PDF_MEDIA_TYPE,
    ".docx": DOCX_MEDIA_TYPE,
}

# A DOCX is a ZIP container; refuse anything that expands to more than this.
_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 250


def _reject(status: int, code: str, message: str, **meta: object) -> PotenciaError:
    return PotenciaError(code, status, message, [{"issue": code, "meta": meta}])


def _check_pdf_structure(data: bytes) -> None:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # corrupt container, bad xref, truncated file
        raise _reject(422, "file_rejected", "The PDF could not be opened.") from exc

    try:
        if document.needs_pass:
            raise _reject(422, "file_rejected", "Encrypted PDFs are not supported.")
        if document.page_count < 1:
            raise _reject(422, "file_rejected", "The PDF contains no pages.")
    finally:
        document.close()


def _check_docx_structure(data: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()

            if "word/document.xml" not in names:
                raise _reject(422, "file_rejected", "The file is a ZIP archive but not a DOCX.")

            if any(name.lower().endswith("vbaproject.bin") for name in names):
                raise _reject(
                    422,
                    "file_rejected",
                    "DOCX files containing macros are not accepted.",
                )

            total = sum(info.file_size for info in archive.infolist())
            if total > _MAX_UNCOMPRESSED_BYTES:
                raise _reject(422, "file_rejected", "The document expands to an unsafe size.")

            compressed = max(1, len(data))
            if total / compressed > _MAX_COMPRESSION_RATIO:
                raise _reject(422, "file_rejected", "The document has an unsafe compression ratio.")

            if archive.testzip() is not None:
                raise _reject(422, "file_rejected", "The DOCX archive is corrupted.")
    except zipfile.BadZipFile as exc:
        raise _reject(422, "file_rejected", "The file is not a valid DOCX container.") from exc


def validate_upload(
    filename: str | None,
    declared_content_type: str | None,
    data: bytes,
) -> str:
    """Validate an upload and return its resolved media type.

    `declared_content_type` is accepted for logging/telemetry only; it is never
    trusted, because the browser copies it from the file extension.
    """
    del declared_content_type  # intentionally unused: never a security signal

    if not data:
        raise _reject(422, "file_rejected", "The uploaded file is empty.")

    if len(data) > MAX_BYTES:
        raise _reject(
            413,
            "payload_too_large",
            f"Files must be {MAX_BYTES // (1024 * 1024)} MiB or smaller.",
            max_bytes=MAX_BYTES,
        )

    suffix = PurePosixPath(filename or "").suffix.lower()
    media_type = EXTENSION_TO_MEDIA_TYPE.get(suffix)
    if media_type is None:
        raise _reject(
            415,
            "unsupported_media_type",
            "Only PDF and DOCX files are accepted.",
            allowed=sorted(EXTENSION_TO_MEDIA_TYPE),
        )

    if media_type == PDF_MEDIA_TYPE:
        # A PDF header may sit a little past byte 0 in files produced by some
        # scanners, but it must appear in the first KiB.
        if b"%PDF-" not in data[:1024]:
            raise _reject(
                415,
                "unsupported_media_type",
                "The file does not contain a PDF header.",
                detected="not_pdf",
            )
        _check_pdf_structure(data)
    else:
        if not data.startswith(b"PK\x03\x04"):
            raise _reject(
                415,
                "unsupported_media_type",
                "The file does not contain a DOCX (ZIP) header.",
                detected="not_zip",
            )
        _check_docx_structure(data)

    return media_type

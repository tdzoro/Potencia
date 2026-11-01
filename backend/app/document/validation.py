"""Upload validation.

Order matters and follows docs/API.md §3.3: cheapest and safest checks first, so
an oversized or mislabelled file is rejected before any parser allocates memory
for it. The extension is treated as a *claim*, never as evidence — a file named
`resume.pdf` that is really a PNG is rejected, and so is a DOCX carrying macros
or an archive bomb.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import PurePosixPath

import fitz  # PyMuPDF

from app.core.config import get_settings
from app.core.errors import PotenciaError

PDF_MEDIA_TYPE = "application/pdf"
DOCX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

MAX_BYTES = 5 * 1024 * 1024  # 5 MiB fallback

EXTENSION_TO_MEDIA_TYPE: dict[str, str] = {
    ".pdf": PDF_MEDIA_TYPE,
    ".docx": DOCX_MEDIA_TYPE,
}

# A DOCX is a ZIP container; refuse anything that expands to more than this.
_MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 100

_DISALLOWED_CHARS = re.compile(r'[\x00-\x1f\x7f-\x9f<>:"/\\|?*]')
_RESERVED_DEVICE_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}

_DISALLOWED_ARCHIVE_EXTENSIONS = {
    ".exe", ".dll", ".bat", ".cmd", ".vbs", ".js", ".scr",
    ".bin", ".msi", ".ps1", ".sh", ".com", ".pif", ".jar",
}


def sanitize_filename(filename: str | None, default_stem: str = "uploaded_resume") -> str:
    """Sanitize an untrusted user-supplied filename.

    - Strips path components (directory traversal).
    - Removes control characters and illegal filesystem characters.
    - Resolves reserved device names.
    - Enforces maximum length of 255 characters while preserving the extension.
    - Falls back to a safe default if the result is empty.
    """
    if not filename or not filename.strip():
        return f"{default_stem}.pdf"

    # Take only the basename, stripping any directory separators (\ or /)
    clean = filename.replace("\\", "/")
    clean = clean.split("/")[-1]

    # Remove null bytes, control chars, and forbidden filename characters
    clean = _DISALLOWED_CHARS.sub("_", clean)

    # Strip leading/trailing spaces and dots
    clean = clean.strip(". ")

    if not clean:
        return f"{default_stem}.pdf"

    # Extract stem and extension
    if "." in clean:
        parts = clean.rsplit(".", 1)
        stem, ext = parts[0].strip(". "), f".{parts[1].strip('. ')}"
    else:
        stem, ext = clean, ""

    # Check for reserved Windows device names or empty stem
    if stem.upper() in _RESERVED_DEVICE_NAMES or not stem:
        stem = default_stem

    if not ext:
        ext = ".pdf"

    # Truncate length so stem + ext <= 255
    max_stem_len = max(1, 255 - len(ext))
    stem = stem[:max_stem_len]

    return f"{stem}{ext}"


def _reject(status: int, code: str, message: str, **meta: object) -> PotenciaError:
    return PotenciaError(code, status, message, [{"issue": code, "meta": meta}])


def _check_pdf_structure(data: bytes) -> None:
    settings = get_settings()
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # corrupt container, bad xref, truncated file
        raise _reject(422, "file_rejected", "The PDF could not be opened.") from exc

    try:
        if document.needs_pass or document.is_encrypted:
            raise _reject(422, "file_rejected", "Encrypted PDFs are not supported.")
        if document.page_count < 1:
            raise _reject(422, "file_rejected", "The PDF contains no pages.")
        if document.page_count > settings.max_pdf_pages:
            raise _reject(
                422,
                "file_rejected",
                f"The PDF exceeds the maximum allowed page count of {settings.max_pdf_pages}.",
                max_pages=settings.max_pdf_pages,
                page_count=document.page_count,
            )

        # Inspect embedded attachments for executable/script content
        emb_count = document.embfile_count()
        if emb_count > 0:
            for name in document.embfile_names():
                suffix = PurePosixPath(name.lower()).suffix
                if suffix in _DISALLOWED_ARCHIVE_EXTENSIONS:
                    raise _reject(
                        422,
                        "file_rejected",
                        f"The PDF contains an unsafe embedded attachment: {name}.",
                    )
    finally:
        document.close()


def _check_docx_structure(data: bytes) -> None:
    settings = get_settings()
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()

            if len(names) > settings.max_docx_entries:
                raise _reject(
                    422,
                    "file_rejected",
                    f"The DOCX container has too many archive entries ({len(names)} > {settings.max_docx_entries}).",
                    max_entries=settings.max_docx_entries,
                    entry_count=len(names),
                )

            # Check for path traversal or absolute paths in ZIP entries
            for name in names:
                normalized = name.replace("\\", "/")
                parts = normalized.split("/")
                if ".." in parts or normalized.startswith("/") or ":" in normalized:
                    raise _reject(
                        422,
                        "file_rejected",
                        "DOCX archive contains suspicious path traversal entries.",
                        entry=name,
                    )
                suffix = PurePosixPath(normalized.lower()).suffix
                if suffix in _DISALLOWED_ARCHIVE_EXTENSIONS and not normalized.lower().endswith("vbaproject.bin"):
                    raise _reject(
                        422,
                        "file_rejected",
                        f"DOCX archive contains unsafe embedded file: {name}.",
                    )

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

    settings = get_settings()
    max_bytes = settings.max_upload_bytes

    if len(data) > max_bytes:
        raise _reject(
            413,
            "payload_too_large",
            f"Files must be {max_bytes // (1024 * 1024)} MiB or smaller.",
            max_bytes=max_bytes,
        )

    safe_name = sanitize_filename(filename)
    suffix = PurePosixPath(safe_name).suffix.lower()
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

"""Document validation and extraction contract tests (docs/API.md §3.3).

Fixtures are generated at runtime with the same libraries the application uses,
so the tests exercise the real parsers rather than hand-written mocks, and no
binary blobs need to live in the repository.
"""

from __future__ import annotations

import io
import zipfile

import fitz
import pytest
from docx import Document as DocxDocument

from app.core.errors import PotenciaError
from app.document.extraction import extract
from app.document.validation import (
    DOCX_MEDIA_TYPE,
    MAX_BYTES,
    PDF_MEDIA_TYPE,
    validate_upload,
)

RESUME_TEXT: tuple[str, ...] = (
    "ARJUN MEHTA",
    "arjun.mehta@example.com",
    "SUMMARY",
    "Backend engineer with four years of experience.",
    "TECHNICAL SKILLS",
    "Python, Django, PostgreSQL",
    "WORK EXPERIENCE",
    "Backend Engineer",
    "Acme Payments | Mar 2022 - Present",
    "Built a ledger service handling 2M daily transactions",
)


def _pdf_bytes(lines: tuple[str, ...] = RESUME_TEXT) -> bytes:
    document = fitz.open()
    page = document.new_page()
    y = 60.0
    for line in lines:
        page.insert_text((60, y), line, fontsize=9)
        y += 14
    data = document.tobytes()
    document.close()
    return data


def _docx_bytes(paragraphs: tuple[str, ...] = RESUME_TEXT) -> bytes:
    document = DocxDocument()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _error_status(excinfo: pytest.ExceptionInfo[PotenciaError]) -> int:
    return excinfo.value.status_code


# --- Validation -------------------------------------------------------------


def test_valid_pdf_is_accepted() -> None:
    media_type = validate_upload("resume.pdf", "application/pdf", _pdf_bytes())
    assert media_type == PDF_MEDIA_TYPE


def test_valid_docx_is_accepted() -> None:
    media_type = validate_upload(
        "resume.docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        _docx_bytes(),
    )
    assert media_type == DOCX_MEDIA_TYPE


def test_declared_content_type_is_not_trusted() -> None:
    """A correct PDF is accepted even when the client mislabels it."""
    media_type = validate_upload("resume.pdf", "text/plain", _pdf_bytes())
    assert media_type == PDF_MEDIA_TYPE


def test_empty_file_is_rejected() -> None:
    with pytest.raises(PotenciaError) as excinfo:
        validate_upload("resume.pdf", "application/pdf", b"")
    assert _error_status(excinfo) == 422
    assert excinfo.value.code == "file_rejected"


def test_oversize_file_is_rejected_before_parsing() -> None:
    with pytest.raises(PotenciaError) as excinfo:
        validate_upload("resume.pdf", "application/pdf", b"x" * (MAX_BYTES + 1))
    assert _error_status(excinfo) == 413
    assert excinfo.value.code == "payload_too_large"


def test_png_renamed_as_pdf_is_rejected() -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 128
    with pytest.raises(PotenciaError) as excinfo:
        validate_upload("resume.pdf", "application/pdf", png)
    assert _error_status(excinfo) == 415
    assert excinfo.value.code == "unsupported_media_type"


def test_unsupported_extension_is_rejected() -> None:
    with pytest.raises(PotenciaError) as excinfo:
        validate_upload("resume.txt", "text/plain", b"hello")
    assert _error_status(excinfo) == 415


def test_docx_with_macros_is_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", "<w:document/>")
        archive.writestr("word/vbaProject.bin", b"\x00" * 32)

    with pytest.raises(PotenciaError) as excinfo:
        validate_upload("resume.docx", "application/zip", buffer.getvalue())
    assert _error_status(excinfo) == 422


def test_zip_that_is_not_a_docx_is_rejected() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("notes.txt", "not a document")

    with pytest.raises(PotenciaError) as excinfo:
        validate_upload("resume.docx", "application/zip", buffer.getvalue())
    assert _error_status(excinfo) == 422


# --- Extraction -------------------------------------------------------------


def test_pdf_text_is_extracted_with_confidence() -> None:
    result = extract(_pdf_bytes(), PDF_MEDIA_TYPE)

    assert result.method == "text_layer"
    assert result.ocr_used is False
    assert "ARJUN MEHTA" in result.text
    assert "2M daily transactions" in result.text
    assert result.page_count == 1
    assert 0.0 < result.confidence <= 1.0


def test_low_text_pdf_is_flagged_partial_and_never_claims_ocr() -> None:
    result = extract(_pdf_bytes(("Hi",)), PDF_MEDIA_TYPE)

    assert result.method == "partial"
    assert result.confidence < 0.5
    assert "low_text_density" in result.warnings
    assert "ocr_not_performed" in result.warnings
    # The OCR fallback is not installed, so it must not be reported as used.
    assert result.ocr_used is False


def test_pdf_without_text_reports_failure_not_a_guess() -> None:
    empty_page = fitz.open()
    empty_page.new_page()
    data = empty_page.tobytes()
    empty_page.close()

    result = extract(data, PDF_MEDIA_TYPE)

    assert result.method == "failed"
    assert result.text == ""
    assert result.confidence == 0.0
    assert "no_text_layer" in result.warnings


def test_docx_paragraph_order_is_preserved() -> None:
    result = extract(_docx_bytes(), DOCX_MEDIA_TYPE)

    assert result.method == "text_layer"
    assert result.page_count >= 1
    assert "page_count_estimated" in result.warnings
    positions = [result.text.index(token) for token in ("ARJUN MEHTA", "SUMMARY", "WORK EXPERIENCE")]
    assert positions == sorted(positions)


def test_docx_tables_are_flagged_rather_than_silently_flattened() -> None:
    document = DocxDocument()
    document.add_paragraph("ARJUN MEHTA")
    table = document.add_table(rows=1, cols=2)
    table.rows[0].cells[0].text = "Skills"
    table.rows[0].cells[1].text = "Python"
    buffer = io.BytesIO()
    document.save(buffer)

    result = extract(buffer.getvalue(), DOCX_MEDIA_TYPE)

    assert any(warning.startswith("tables_present") for warning in result.warnings)
    assert "Python" in result.text


def test_unknown_media_type_fails_closed() -> None:
    result = extract(b"anything", "text/plain")

    assert result.method == "failed"
    assert result.confidence == 0.0

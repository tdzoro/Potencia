"""Text extraction from PDF and DOCX.

The goal is not "some text" but *trustworthy* text: page boundaries, paragraph
order and a confidence figure the scoring engine can act on. Where extraction is
weak the result says so, because a low-confidence parse that reports itself as
clean produces confidently wrong advice downstream.

For PDFs with insufficient or missing native text layers (scanned documents or
image-dominant pages), the extractor automatically engages the OCR engine
(Tesseract + OpenCV preprocessing) while leaving ordinary text-based PDFs untouched.
"""

from __future__ import annotations

import io
import math

import pymupdf as fitz
from docx import Document as load_docx

from app.core.config import get_settings
from app.document.ocr import ocr_pdf
from app.document.validation import DOCX_MEDIA_TYPE, PDF_MEDIA_TYPE
from app.intelligence.normalization import normalize_whitespace
from app.schemas.resume import ExtractionResult

# Below this many characters per page a PDF is treated as image-dominant / scanned.
_LOW_TEXT_PER_PAGE = 120
# Characters per page at which extraction is considered fully confident.
_GOOD_TEXT_PER_PAGE = 600
# DOCX has no fixed page count; assume a conservative digits-per-page figure.
_WORDS_PER_PAGE = 500


def _confidence(text_chars: int, page_count: int) -> float:
    if text_chars <= 0:
        return 0.0
    per_page = text_chars / max(1, page_count)
    return round(min(1.0, per_page / _GOOD_TEXT_PER_PAGE), 2)


def _extract_pdf(data: bytes) -> ExtractionResult:
    warnings: list[str] = []
    settings = get_settings()

    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception:
        return ExtractionResult(
            text="",
            page_count=0,
            method="failed",
            confidence=0.0,
            ocr_used=False,
            warnings=["pdf_unreadable"],
        )

    try:
        page_count = document.page_count
        pages: list[str] = []
        image_only_pages = 0

        for page in document:
            page_text = page.get_text("text")
            pages.append(page_text)
            if len(page_text.strip()) < _LOW_TEXT_PER_PAGE:
                # Only worth flagging if the page also contains an image, which
                # is the actual signal for "this was scanned".
                if page.get_images(full=True):
                    image_only_pages += 1

        text = normalize_whitespace("\n\n".join(pages))
    finally:
        document.close()

    text_chars = len(text.strip())
    per_page = text_chars / max(1, page_count)

    # Scanned document detection: either completely empty native layer or
    # sparse text on image-dominant pages.
    is_scanned_candidate = (text_chars == 0) or (per_page < _LOW_TEXT_PER_PAGE and image_only_pages > 0)

    if is_scanned_candidate and settings.ocr_enabled:
        ocr_res = ocr_pdf(data)
        ocr_chars = len(ocr_res.text.strip())

        # If OCR recovered text (or more text than native extraction), use OCR result
        if ocr_chars > 0 and ocr_chars >= text_chars:
            return ExtractionResult(
                text=normalize_whitespace(ocr_res.text),
                page_count=page_count,
                method="ocr",
                confidence=ocr_res.confidence,
                ocr_used=True,
                warnings=ocr_res.warnings,
            )
        elif text_chars == 0:
            # OCR failed or returned no text
            combined_warnings = ["no_text_layer"]
            for w in ocr_res.warnings:
                if w not in combined_warnings:
                    combined_warnings.append(w)
            return ExtractionResult(
                text="",
                page_count=page_count,
                method="failed",
                confidence=0.0,
                ocr_used=ocr_res.ocr_used,
                warnings=combined_warnings,
            )

    confidence = _confidence(text_chars, page_count)

    if text_chars == 0:
        return ExtractionResult(
            text="",
            page_count=page_count,
            method="failed",
            confidence=0.0,
            ocr_used=False,
            warnings=["no_text_layer", "ocr_disabled" if not settings.ocr_enabled else "ocr_not_performed"],
        )

    method: str = "text_layer"
    if per_page < _LOW_TEXT_PER_PAGE:
        method = "partial"
        warnings.append("low_text_density")
    if image_only_pages:
        method = "partial"
        warnings.append(f"image_only_pages:{image_only_pages}")
    if method == "partial":
        warnings.append("ocr_not_performed")

    return ExtractionResult(
        text=text,
        page_count=page_count,
        method=method,  # type: ignore[arg-type]
        confidence=confidence,
        ocr_used=False,
        warnings=warnings,
    )


def _extract_docx(data: bytes) -> ExtractionResult:
    warnings: list[str] = []
    try:
        document = load_docx(io.BytesIO(data))
    except Exception:
        return ExtractionResult(
            text="",
            page_count=0,
            method="failed",
            confidence=0.0,
            ocr_used=False,
            warnings=["docx_unreadable"],
        )

    lines: list[str] = []
    for paragraph in document.paragraphs:
        # Blank paragraphs are preserved: they are the only section boundary
        # signal a DOCX gives us.
        lines.append(paragraph.text)

    # Tables are a documented ATS hazard, so their presence is recorded rather
    # than silently flattened into prose.
    table_rows = 0
    for table in document.tables:
        table_rows += len(table.rows)
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            if any(cells):
                lines.append(" | ".join(cells))

    header_text = ""
    for section in document.sections:
        for paragraph in section.header.paragraphs:
            header_text += paragraph.text
        for paragraph in section.footer.paragraphs:
            header_text += paragraph.text
    if header_text.strip():
        warnings.append("header_footer_content")

    if table_rows:
        warnings.append(f"tables_present:{table_rows}")

    text = normalize_whitespace("\n".join(lines))
    text_chars = len(text.strip())

    if text_chars == 0:
        return ExtractionResult(
            text="",
            page_count=1,
            method="failed",
            confidence=0.0,
            ocr_used=False,
            warnings=["no_text_extracted"],
        )

    words = len(text.split())
    page_count = max(1, math.ceil(words / _WORDS_PER_PAGE))
    warnings.append("page_count_estimated")

    return ExtractionResult(
        text=text,
        page_count=page_count,
        method="text_layer",
        confidence=_confidence(text_chars, page_count),
        ocr_used=False,
        warnings=warnings,
    )


def extract(data: bytes, media_type: str) -> ExtractionResult:
    """Extract text from an already-validated document."""
    if media_type == PDF_MEDIA_TYPE:
        return _extract_pdf(data)
    if media_type == DOCX_MEDIA_TYPE:
        return _extract_docx(data)

    return ExtractionResult(
        text="",
        page_count=0,
        method="failed",
        confidence=0.0,
        ocr_used=False,
        warnings=["unsupported_media_type"],
    )

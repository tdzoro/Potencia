"""OCR application service facade.

Exposes document and image OCR capabilities to application services and extraction routines.
"""

from __future__ import annotations

from app.document.ocr import (
    OcrDocumentResult,
    OcrPageResult,
    configure_tesseract_cmd,
    deskew_image,
    is_tesseract_available,
    ocr_image,
    ocr_pdf,
    preprocess_image,
    render_pdf_page_as_image,
)

__all__ = [
    "OcrDocumentResult",
    "OcrPageResult",
    "configure_tesseract_cmd",
    "deskew_image",
    "is_tesseract_available",
    "ocr_image",
    "ocr_pdf",
    "preprocess_image",
    "render_pdf_page_as_image",
]


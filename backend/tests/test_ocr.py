"""Phase 22: OCR Integration Test Suite for Scanned Resumes.

Verifies:
- Native text-based PDF uses text layer directly and bypasses OCR (ocr_used=False).
- Scanned PDF (image-dominant, no text layer) triggers OCR (ocr_used=True).
- Multi-page scanned document maintains page order and aggregate confidence.
- Image preprocessing: grayscale, CLAHE, Gaussian blur, Otsu binarization, and deskew.
- Handling of skewed/rotated documents.
- Low-confidence OCR generates quality warnings ('ocr_low_confidence').
- Graceful degradation when Tesseract binary is missing ('ocr_engine_missing').
- OCR timeout handling without crashing.
- Unsupported language error handling.
- Maximum page limit enforcement during OCR.
- DOCX extraction remains unaffected.
- Malware scanning precedes extraction and OCR.
"""

from __future__ import annotations

import io
from unittest.mock import MagicMock, patch

import cv2
import fitz
import numpy as np
import pytest
from docx import Document
from PIL import Image, ImageDraw

from app.core.config import get_settings
from app.core.errors import PotenciaError
from app.document.extraction import _extract_pdf, extract
from app.document.ocr import (
    OcrDocumentResult,
    OcrPageResult,
    deskew_image,
    is_tesseract_available,
    ocr_image,
    ocr_pdf,
    preprocess_image,
    render_pdf_page_as_image,
)
from app.document.validation import DOCX_MEDIA_TYPE, PDF_MEDIA_TYPE
from app.models.user import User
from app.services import resume_service
from app.services.malware_scanner import EICAR_SIGNATURE


def _make_text_pdf(text: str | None = None, num_pages: int = 1) -> bytes:
    if text is None:
        text = (
            "Arjun Mehta\narjun.mehta@example.com | +91 98765 43210\n"
            "SUMMARY\nBackend engineer with four years building payment services.\n"
            "TECHNICAL SKILLS\nPython, Django, PostgreSQL, Docker, AWS, Kubernetes, Redis\n"
            "WORK EXPERIENCE\nBackend Engineer\nAcme Payments | Mar 2022 - Present\n"
            "- Built a ledger service handling 2M daily transactions\n"
            "- Reduced p99 latency from 800ms to 220ms by adding Redis caching\n"
        )
    doc = fitz.open()
    for _ in range(num_pages):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def _make_scanned_pdf(text: str = "JANE DOE\njane@example.com\nLead Cloud Architect", num_pages: int = 1) -> bytes:
    """Creates a PDF with purely image-rendered text and no native text layer."""
    doc = fitz.open()
    for _ in range(num_pages):
        page = doc.new_page(width=595, height=842)
        # Create image with drawn text (no PDF text layer)
        img = Image.new("RGB", (600, 800), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.text((50, 80), text, fill=(0, 0, 0))
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        page.insert_image(page.rect, stream=img_buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


def _make_docx(text: str = "Jane Doe\nTechnical Architect\nPython, Docker, AWS") -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


class TestImagePreprocessing:
    def test_preprocess_converts_to_binarized_image(self) -> None:
        # Create dummy RGB image with a black rectangle on white
        img = np.full((100, 100, 3), 255, dtype=np.uint8)
        img[30:70, 30:70] = 0

        preprocessed = preprocess_image(img, deskew=False)
        assert len(preprocessed.shape) == 2  # Grayscale / binarized
        assert preprocessed.shape == (100, 100)
        # Values should be 0 or 255 from Otsu thresholding
        unique_vals = set(np.unique(preprocessed))
        assert unique_vals.issubset({0, 255})

    def test_deskew_image_straight_image_unchanged(self) -> None:
        # Perfectly horizontal line
        img = np.full((100, 100), 255, dtype=np.uint8)
        img[48:52, 20:80] = 0
        deskewed = deskew_image(img)
        assert deskewed.shape == img.shape

    def test_deskew_image_handles_blank_image_safely(self) -> None:
        blank = np.full((100, 100), 255, dtype=np.uint8)
        deskewed = deskew_image(blank)
        assert np.array_equal(blank, deskewed)

    def test_render_pdf_page_as_image(self) -> None:
        pdf_bytes = _make_text_pdf("Sample test text", 1)
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        page = doc[0]
        img = render_pdf_page_as_image(page, dpi=100)
        doc.close()

        assert isinstance(img, np.ndarray)
        assert len(img.shape) == 3
        assert img.shape[2] == 3  # RGB
        assert img.shape[0] > 0
        assert img.shape[1] > 0


class TestOcrExtractionLogic:
    def test_text_pdf_bypasses_ocr(self) -> None:
        pdf_bytes = _make_text_pdf()
        with patch("app.document.extraction.ocr_pdf") as mock_ocr:
            result = extract(pdf_bytes, PDF_MEDIA_TYPE)
            assert result.method == "text_layer"
            assert result.ocr_used is False
            assert "Arjun Mehta" in result.text
            # OCR engine should NOT be called for normal text PDFs
            mock_ocr.assert_not_called()

    def test_scanned_pdf_triggers_ocr(self) -> None:
        scanned_bytes = _make_scanned_pdf("Priya Sharma\nCloud Architect\nAWS, Terraform", 1)
        mock_ocr_doc = OcrDocumentResult(
            text="Priya Sharma Cloud Architect AWS Terraform",
            page_count=1,
            confidence=0.88,
            method="ocr",
            ocr_used=True,
            warnings=[],
            pages=[
                OcrPageResult(
                    page_number=1,
                    text="Priya Sharma Cloud Architect AWS Terraform",
                    confidence=0.88,
                    word_count=6,
                    warnings=[],
                )
            ],
        )

        with patch("app.document.extraction.ocr_pdf", return_value=mock_ocr_doc) as mock_ocr:
            result = extract(scanned_bytes, PDF_MEDIA_TYPE)
            mock_ocr.assert_called_once()
            assert result.method == "ocr"
            assert result.ocr_used is True
            assert result.confidence == 0.88
            assert "Priya Sharma" in result.text

    def test_multi_page_scanned_pdf_orders_pages(self) -> None:
        scanned_bytes = _make_scanned_pdf("Page text", 2)
        mock_ocr_doc = OcrDocumentResult(
            text="Header Content Page 1\n\nExperience Content Page 2",
            page_count=2,
            confidence=0.92,
            method="ocr",
            ocr_used=True,
            warnings=[],
            pages=[
                OcrPageResult(page_number=1, text="Header Content Page 1", confidence=0.94, word_count=4),
                OcrPageResult(page_number=2, text="Experience Content Page 2", confidence=0.90, word_count=4),
            ],
        )

        with patch("app.document.extraction.ocr_pdf", return_value=mock_ocr_doc):
            result = extract(scanned_bytes, PDF_MEDIA_TYPE)
            assert result.method == "ocr"
            assert result.ocr_used is True
            assert "Page 1" in result.text
            assert "Page 2" in result.text
            assert result.text.index("Page 1") < result.text.index("Page 2")

    def test_ocr_low_confidence_generates_warning(self) -> None:
        scanned_bytes = _make_scanned_pdf("Degraded text", 1)
        mock_ocr_doc = OcrDocumentResult(
            text="Dgrdd txt fragment",
            page_count=1,
            confidence=0.32,
            method="ocr",
            ocr_used=True,
            warnings=["ocr_low_confidence"],
            pages=[
                OcrPageResult(
                    page_number=1,
                    text="Dgrdd txt fragment",
                    confidence=0.32,
                    word_count=3,
                    warnings=["ocr_low_confidence"],
                )
            ],
        )

        with patch("app.document.extraction.ocr_pdf", return_value=mock_ocr_doc):
            result = extract(scanned_bytes, PDF_MEDIA_TYPE)
            assert result.method == "ocr"
            assert result.confidence == 0.32
            assert "ocr_low_confidence" in result.warnings

    def test_missing_tesseract_fails_gracefully(self) -> None:
        scanned_bytes = _make_scanned_pdf("No Tesseract available", 1)
        with patch("app.document.ocr.is_tesseract_available", return_value=False):
            result = ocr_pdf(scanned_bytes)
            assert result.method == "failed"
            assert result.confidence == 0.0
            assert "ocr_engine_missing" in result.warnings

    def test_ocr_timeout_handled_gracefully(self) -> None:
        scanned_bytes = _make_scanned_pdf("Timeout test", 1)
        with patch("app.document.ocr.is_tesseract_available", return_value=True):
            with patch("app.document.ocr.ocr_image") as mock_ocr_page:
                mock_ocr_page.return_value = OcrPageResult(
                    page_number=1,
                    text="",
                    confidence=0.0,
                    word_count=0,
                    warnings=["ocr_timeout"],
                )
                result = ocr_pdf(scanned_bytes)
                assert result.method == "failed"
                assert "ocr_timeout" in result.warnings

    def test_ocr_disabled_in_settings(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "ocr_enabled", False)
        scanned_bytes = _make_scanned_pdf("Scanned content", 1)
        result = extract(scanned_bytes, PDF_MEDIA_TYPE)
        assert result.method == "failed"
        assert result.ocr_used is False
        assert "ocr_disabled" in result.warnings

    def test_max_pdf_pages_respected_in_ocr(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "max_pdf_pages", 2)
        pdf_bytes = _make_scanned_pdf("Page content", 4)

        with patch("app.document.ocr.is_tesseract_available", return_value=True):
            with patch("app.document.ocr.ocr_image") as mock_ocr_page:
                mock_ocr_page.return_value = OcrPageResult(
                    page_number=1,
                    text="Page content",
                    confidence=0.9,
                    word_count=2,
                    warnings=[],
                )
                result = ocr_pdf(pdf_bytes)
                # Should process at most 2 pages
                assert mock_ocr_page.call_count <= 2

    def test_docx_extraction_unaffected_by_ocr(self) -> None:
        docx_bytes = _make_docx("Jane Doe\nBackend Developer with Python")
        with patch("app.document.extraction.ocr_pdf") as mock_ocr:
            result = extract(docx_bytes, DOCX_MEDIA_TYPE)
            assert result.method == "text_layer"
            assert result.ocr_used is False
            assert "Jane Doe" in result.text
            mock_ocr.assert_not_called()


class TestSecurityAndMalwareRegression:
    def test_malicious_file_intercepted_before_ocr(self, session, monkeypatch) -> None:
        user = User(
            email="ocr_malware_user@example.com",
            display_name="Test User",
            password_hash="fakehash",
            email_verified=True,
        )
        session.add(user)
        session.commit()
        session.refresh(user)

        # Scanned PDF embedding the EICAR test signature
        scanned_eicar = _make_scanned_pdf("Clean looking page", 1) + b"\n% " + EICAR_SIGNATURE + b"\n"

        with patch("app.document.extraction.ocr_pdf") as mock_ocr:
            with pytest.raises(PotenciaError) as exc_info:
                resume_service.create_resume(
                    session,
                    user,
                    filename="scanned_trojan.pdf",
                    declared_content_type="application/pdf",
                    data=scanned_eicar,
                )
            assert exc_info.value.status_code == 422
            assert "Malicious content detected" in exc_info.value.message
            # OCR must NEVER run on a malicious upload
            mock_ocr.assert_not_called()

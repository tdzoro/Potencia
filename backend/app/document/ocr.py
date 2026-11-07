"""Optical Character Recognition (OCR) engine for scanned resumes.

Uses:
- PyMuPDF (fitz) for high-fidelity page rasterization at configurable DPI.
- OpenCV for document image preprocessing (grayscale, noise reduction, CLAHE,
  safe deskewing, and adaptive binarization).
- pytesseract for Tesseract OCR execution, capturing text and word/page confidences.

Designed to fail safely: if Tesseract is missing or times out, the engine
degrades gracefully with documented warnings rather than raising an unhandled exception.
"""

from __future__ import annotations

import logging
import math
import shutil
import time
from dataclasses import dataclass, field

import cv2
import pymupdf as fitz
import numpy as np
import pytesseract

from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OcrPageResult:
    page_number: int
    text: str
    confidence: float  # 0.0 to 1.0
    word_count: int
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OcrDocumentResult:
    text: str
    page_count: int
    confidence: float  # 0.0 to 1.0
    method: str  # "ocr" or "failed"
    ocr_used: bool
    warnings: list[str] = field(default_factory=list)
    pages: list[OcrPageResult] = field(default_factory=list)


def configure_tesseract_cmd() -> str | None:
    """Configure and return the path to the Tesseract executable."""
    settings = get_settings()
    custom_cmd = settings.ocr_tesseract_cmd
    if custom_cmd:
        pytesseract.pytesseract.tesseract_cmd = custom_cmd
        return custom_cmd

    # Check if tesseract is in PATH
    which_cmd = shutil.which("tesseract")
    if which_cmd:
        pytesseract.pytesseract.tesseract_cmd = which_cmd
        return which_cmd

    return None


def is_tesseract_available() -> bool:
    """Check if Tesseract OCR binary is installed and executable."""
    configure_tesseract_cmd()
    try:
        version = pytesseract.get_tesseract_version()
        return bool(version)
    except Exception as exc:
        logger.debug("Tesseract OCR is not available: %s", exc)
        return False


def deskew_image(image: np.ndarray) -> np.ndarray:
    """Detect and correct document skew using contour analysis.

    Only corrects realistic skew angles (between 0.5° and 45.0°).
    Extreme or near-zero angles are left untouched to prevent distortion.
    """
    try:
        # Create inverted binary image to find text regions
        if len(image.shape) == 3:
            gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
        else:
            gray = image

        thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(thresh > 0))
        if len(coords) < 100:
            return image

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45.0:
            angle = -(90.0 + angle)
        elif angle > 45.0:
            angle = angle - 90.0
        else:
            angle = -angle

        # Only deskew if the detected angle is meaningful
        if abs(angle) < 0.5 or abs(angle) > 45.0:
            return image

        (h, w) = image.shape[:2]
        center = (w // 2, h // 2)
        rot_mat = cv2.getRotationMatrix2D(center, angle, 1.0)
        deskewed = cv2.warpAffine(
            image,
            rot_mat,
            (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(255, 255, 255) if len(image.shape) == 3 else 255,
        )
        return deskewed
    except Exception as exc:
        logger.warning("Deskew processing failed, proceeding with original image: %s", exc)
        return image


def preprocess_image(image: np.ndarray, *, deskew: bool = True) -> np.ndarray:
    """Preprocess a document image for optimal character recognition.

    1. Convert to RGB / Grayscale.
    2. Enhance contrast using CLAHE (Contrast Limited Adaptive Histogram Equalization).
    3. Noise reduction using Gaussian blur.
    4. Optional deskewing to align text lines.
    5. Adaptive Otsu binarization.
    """
    # Ensure 3-channel RGB or 1-channel Grayscale
    if len(image.shape) == 3 and image.shape[2] == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)

    if deskew:
        image = deskew_image(image)

    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    else:
        gray = image

    # Contrast Limited Adaptive Histogram Equalization (CLAHE)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    contrast_enhanced = clahe.apply(gray)

    # Mild Gaussian blur to reduce high-frequency scanner noise
    blurred = cv2.GaussianBlur(contrast_enhanced, (3, 3), 0)

    # Otsu thresholding for clean black-on-white text
    _, binarized = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binarized


def render_pdf_page_as_image(page: fitz.Page, dpi: int = 200) -> np.ndarray:
    """Render a PyMuPDF page as an RGB numpy array at the given DPI."""
    pix = page.get_pixmap(dpi=dpi)
    try:
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
        if pix.n == 4:
            return cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)
        if pix.n == 1:
            return cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        return img.copy()
    finally:
        del pix


def _assemble_ocr_lines(data: dict[str, list]) -> tuple[list[str], str]:
    """Return recognized words and text with Tesseract's original line breaks."""
    words: list[str] = []
    lines: dict[tuple[int, ...], list[str]] = {}
    has_line_data = all(key in data for key in ("page_num", "block_num", "par_num", "line_num"))

    for i, raw_text in enumerate(data.get("text", [])):
        text = str(raw_text).strip()
        if not text:
            continue
        words.append(text)
        if has_line_data:
            try:
                key = tuple(
                    int(data[column][i])
                    for column in ("page_num", "block_num", "par_num", "line_num")
                )
            except (IndexError, TypeError, ValueError):
                key = (0, 0, 0, i)
        else:
            key = (0, 0, 0, 0)
        lines.setdefault(key, []).append(text)

    return words, "\n".join(" ".join(line) for line in lines.values()).strip()


def ocr_image(
    image: np.ndarray,
    page_number: int = 1,
    *,
    lang: str = "eng",
    timeout: float = 30.0,
    min_confidence: float = 40.0,
    deskew: bool = True,
) -> OcrPageResult:
    """Process a single image through preprocessing and Tesseract OCR."""
    warnings: list[str] = []
    if not is_tesseract_available():
        return OcrPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            word_count=0,
            warnings=["ocr_engine_missing"],
        )

    preprocessed = preprocess_image(image, deskew=deskew)

    try:
        data = pytesseract.image_to_data(
            preprocessed,
            lang=lang,
            timeout=timeout,
            output_type=pytesseract.Output.DICT,
        )
    except pytesseract.TesseractNotFoundError:
        return OcrPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            word_count=0,
            warnings=["ocr_engine_missing"],
        )
    except pytesseract.pytesseract.TesseractError as exc:
        logger.error("Tesseract execution error on page %d: %s", page_number, exc)
        return OcrPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            word_count=0,
            warnings=["ocr_execution_failed"],
        )
    except Exception as exc:  # Timeout, subprocess termination, etc.
        logger.error("OCR failed on page %d: %s", page_number, exc)
        return OcrPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            word_count=0,
            warnings=["ocr_timeout" if "timeout" in str(exc).lower() else "ocr_failed"],
        )

    # Preserve Tesseract's line geometry so downstream section parsing can
    # distinguish headings and resume entries rather than receiving one long line.
    words, page_text = _assemble_ocr_lines(data)
    confidences = [
        float(conf)
        for text, conf in zip(data.get("text", []), data.get("conf", []))
        if str(text).strip() and float(conf) >= 0
    ]
    word_count = len(words)

    if not confidences or word_count == 0:
        return OcrPageResult(
            page_number=page_number,
            text="",
            confidence=0.0,
            word_count=0,
            warnings=["ocr_empty_page"],
        )

    # Calculate average confidence normalized to 0.0 - 1.0
    avg_confidence = round(sum(confidences) / len(confidences) / 100.0, 2)

    if avg_confidence * 100.0 < min_confidence:
        warnings.append("ocr_low_confidence")

    return OcrPageResult(
        page_number=page_number,
        text=page_text,
        confidence=avg_confidence,
        word_count=word_count,
        warnings=warnings,
    )


def ocr_pdf(data: bytes) -> OcrDocumentResult:
    """Run OCR across all pages of a PDF document."""
    settings = get_settings()

    if not settings.ocr_enabled:
        return OcrDocumentResult(
            text="",
            page_count=0,
            confidence=0.0,
            method="failed",
            ocr_used=False,
            warnings=["ocr_disabled"],
        )

    if not is_tesseract_available():
        return OcrDocumentResult(
            text="",
            page_count=0,
            confidence=0.0,
            method="failed",
            ocr_used=False,
            warnings=["ocr_engine_missing"],
        )

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        return OcrDocumentResult(
            text="",
            page_count=0,
            confidence=0.0,
            method="failed",
            ocr_used=False,
            warnings=["pdf_unreadable"],
        )

    try:
        page_count = doc.page_count
        if page_count < 1:
            return OcrDocumentResult(
                text="",
                page_count=0,
                confidence=0.0,
                method="failed",
                ocr_used=False,
                warnings=["pdf_empty"],
            )

        pages_to_process = min(page_count, settings.max_pdf_pages)
        page_results: list[OcrPageResult] = []
        overall_warnings: list[str] = []

        start_time = time.monotonic()
        per_page_timeout = max(5.0, settings.ocr_timeout_seconds / max(1, pages_to_process))

        for idx in range(pages_to_process):
            # Enforce overall timeout
            elapsed = time.monotonic() - start_time
            if elapsed > settings.ocr_timeout_seconds:
                overall_warnings.append("ocr_timeout")
                break

            page = doc[idx]
            img = render_pdf_page_as_image(page, dpi=settings.ocr_dpi)
            try:
                page_res = ocr_image(
                    img,
                    page_number=idx + 1,
                    lang=settings.ocr_language,
                    timeout=per_page_timeout,
                    min_confidence=settings.ocr_min_confidence,
                    deskew=settings.ocr_deskew_enabled,
                )
                page_results.append(page_res)
                for w in page_res.warnings:
                    if w not in overall_warnings:
                        overall_warnings.append(w)
            finally:
                del img

        combined_text = "\n\n".join(res.text for res in page_results if res.text.strip())
        total_chars = len(combined_text.strip())

        if total_chars == 0:
            return OcrDocumentResult(
                text="",
                page_count=page_count,
                confidence=0.0,
                method="failed",
                ocr_used=True,
                warnings=overall_warnings or ["ocr_no_text_recovered"],
                pages=page_results,
            )

        # Compute weighted overall confidence
        weights = [res.word_count for res in page_results]
        total_words = sum(weights)
        if total_words > 0:
            overall_confidence = round(
                sum(res.confidence * res.word_count for res in page_results) / total_words, 2
            )
        else:
            overall_confidence = 0.0

        if overall_confidence * 100.0 < settings.ocr_min_confidence and "ocr_low_confidence" not in overall_warnings:
            overall_warnings.append("ocr_low_confidence")

        return OcrDocumentResult(
            text=combined_text,
            page_count=page_count,
            confidence=overall_confidence,
            method="ocr",
            ocr_used=True,
            warnings=overall_warnings,
            pages=page_results,
        )
    finally:
        doc.close()


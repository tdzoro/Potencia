"""Measure the OCR fallback on a scanned resume.

    PYTHONPATH=backend backend/.venv/bin/python scripts/measure_ocr.py

Tesseract and OpenCV only run for scanned documents, so the engine profile
never touches them and the README had no number for the fallback. This script
builds a scan from a text resume — rasterised at 200 DPI, rotated, noised and
JPEG-compressed, then wrapped in a PDF with no text layer — and runs the real
`extract()` entry point on it. It records what the fallback costs, how much of
the text it recovers, and whether the score survives the round trip.

Writes `assets/readme/ocr_profile.json`; prints a table.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np
import pymupdf as fitz
import pytesseract

from app.document.extraction import extract
from app.document.ocr import (
    is_tesseract_available,
    ocr_image,
    ocr_pdf,
    preprocess_image,
    render_pdf_page_as_image,
)
from app.document.validation import PDF_MEDIA_TYPE
from app.intelligence.parser import parse_document
from app.intelligence.scoring.engine import score_resume

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "assets" / "readme" / "ocr_profile.json"

DPI = 200
SKEW_DEGREES = 1.3
NOISE_SIGMA = 7.0
JPEG_QUALITY = 65

# A deliberately imperfect resume: the score is interesting, and the text is
# long enough that OCR errors at the margins cannot hide behind a short page.
RESUME = """ARJUN MEHTA
arjun.mehta@example.com | +91 98765 43210 | Bengaluru, India
linkedin.com/in/arjunmehta | github.com/arjunmehta

SUMMARY
Backend engineer with four years building payment and ledger services in Python.
Comfortable owning a service from schema design through on-call.

TECHNICAL SKILLS
Python, Django, PostgreSQL, Docker, AWS, Kubernetes, Redis, Terraform

WORK EXPERIENCE

Backend Engineer
Acme Payments | Mar 2022 - Present
- Built a double-entry ledger service handling 2M daily transactions
- Reduced p99 settlement latency from 840 ms to 210 ms by batching writes
- Worked on latency improvements across the payments team
- Responsible for mentoring two interns and reviewing their pull requests

Software Engineer
Northwind Systems | Jul 2020 - Feb 2022
- Automated reconciliation reports with Python and Pandas, saving 12 hours weekly
- Migrated 40 services from virtual machines to Docker without downtime

PROJECTS
Ledger Replay - rebuilt historical ledger state from an event log in PostgreSQL
Rate Limiter - Redis-backed sliding window limiter, 8k requests per second

EDUCATION
B.Tech in Computer Science
National Institute of Technology | 2016 - 2020
"""


def _percentiles(samples: list[float]) -> dict[str, float]:
    ordered = sorted(samples)
    return {
        "p50": round(statistics.median(ordered), 2),
        "p95": round(ordered[max(0, int(len(ordered) * 0.95) - 1)], 2),
        "max": round(ordered[-1], 2),
        "mean": round(statistics.fmean(ordered), 2),
    }


def _timed(fn, runs: int) -> list[float]:
    samples: list[float] = []
    for _ in range(runs):
        started = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - started) * 1000)
    return samples


def _text_pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page(width=595, height=842)
    page.insert_textbox(fitz.Rect(48, 48, 547, 794), text, fontsize=9.5, fontname="helv")
    data = document.tobytes()
    document.close()
    return data


def _scanned_pdf() -> bytes:
    """A text page photographed: rasterised, skewed, noised, JPEG-compressed."""
    source = fitz.open()
    page = source.new_page(width=595, height=842)
    page.insert_textbox(fitz.Rect(48, 48, 547, 794), RESUME, fontsize=9.5, fontname="helv")
    pix = page.get_pixmap(dpi=DPI)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape((pix.height, pix.width, pix.n))
    if pix.n == 4:
        image = cv2.cvtColor(image, cv2.COLOR_RGBA2RGB)
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    height, width = gray.shape
    source.close()

    rotation = cv2.getRotationMatrix2D((width / 2, height / 2), SKEW_DEGREES, 1.0)
    gray = cv2.warpAffine(
        gray,
        rotation,
        (width, height),
        flags=cv2.INTER_LINEAR,
        borderMode=cv2.BORDER_CONSTANT,
        borderValue=255,
    )

    rng = np.random.default_rng(7)
    noisy = np.clip(gray.astype(np.int16) + rng.normal(0, NOISE_SIGMA, gray.shape), 0, 255)
    encoded, buffer = cv2.imencode(
        ".jpg", noisy.astype(np.uint8), [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
    )
    if not encoded:
        raise RuntimeError("JPEG encoding failed")

    scanned = fitz.open()
    scanned_page = scanned.new_page(width=595, height=842)
    scanned_page.insert_image(scanned_page.rect, stream=buffer.tobytes())
    data = scanned.tobytes()
    scanned.close()

    # The whole point is that this document has no text layer to fall back to.
    probe = fitz.open(stream=data, filetype="pdf")
    try:
        if probe[0].get_text("text").strip():
            raise AssertionError("the scan fixture still contains a text layer")
    finally:
        probe.close()

    return data


def _words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9+#.]+", text.lower())


def _accuracy(truth: str, recovered: str) -> dict[str, float]:
    expected, actual = _words(truth), _words(recovered)
    overlap = sum((Counter(actual) & Counter(expected)).values())
    recall = overlap / len(expected) if expected else 0.0
    precision = overlap / len(actual) if actual else 0.0
    f1 = 2 * recall * precision / (recall + precision) if recall + precision else 0.0
    character_ratio = difflib.SequenceMatcher(
        None, " ".join(expected), " ".join(actual), autojunk=False
    ).ratio()
    return {
        "word_recall": round(recall, 3),
        "word_precision": round(precision, 3),
        "word_f1": round(f1, 3),
        "character_similarity": round(character_ratio, 3),
        "truth_words": len(expected),
        "recovered_words": len(actual),
    }


def _score(extraction) -> dict[str, float | int | str | None]:
    structure = parse_document(extraction)
    result = score_resume(structure, extraction_confidence=extraction.confidence)
    return {
        "overall": round(result.bundle.overall, 2),
        "band": result.bundle.band,
        "ats": round(result.ats.estimate, 2) if result.ats else None,
        "findings": len(result.findings),
        "word_count": structure.word_count,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--baseline-runs", type=int, default=30)
    args = parser.parse_args()

    if not is_tesseract_available():
        print("Tesseract is not installed; the OCR path cannot be measured.")
        raise SystemExit(2)

    text_pdf = _text_pdf(RESUME)
    scan_pdf = _scanned_pdf()

    baseline = extract(text_pdf, PDF_MEDIA_TYPE)
    scanned = extract(scan_pdf, PDF_MEDIA_TYPE)
    if not scanned.ocr_used:
        print(f"OCR was not engaged: {scanned.warnings}")
        raise SystemExit(1)

    accuracy = _accuracy(RESUME, scanned.text)

    document = fitz.open(stream=scan_pdf, filetype="pdf")
    page_image = render_pdf_page_as_image(document[0], dpi=DPI)
    document.close()

    timings = {
        "text_layer_extract": _percentiles(
            _timed(lambda: extract(text_pdf, PDF_MEDIA_TYPE), args.baseline_runs)
        ),
        "scan_detect_and_ocr": _percentiles(
            _timed(lambda: extract(scan_pdf, PDF_MEDIA_TYPE), args.runs)
        ),
        "ocr_document": _percentiles(_timed(lambda: ocr_pdf(scan_pdf), args.runs)),
        "render_page": _percentiles(
            _timed(lambda: render_pdf_page_as_image(fitz.open(stream=scan_pdf, filetype="pdf")[0], dpi=DPI), args.runs)
        ),
        "preprocess": _percentiles(_timed(lambda: preprocess_image(page_image), args.runs)),
        "tesseract": _percentiles(_timed(lambda: ocr_image(page_image), args.runs)),
    }

    text_score = _score(baseline)
    ocr_score = _score(scanned)

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "python": sys.version.split()[0],
        "tesseract": str(pytesseract.get_tesseract_version()),
        "dpi": DPI,
        "language": "eng",
        "scan": {
            "pages": 1,
            "skew_degrees": SKEW_DEGREES,
            "gaussian_noise_sigma": NOISE_SIGMA,
            "jpeg_quality": JPEG_QUALITY,
        },
        "accuracy": accuracy,
        "timing_ms": {key: value for key, value in timings.items()},
        "score": {
            "text_layer": text_score,
            "ocr": ocr_score,
            "overall_delta": round((ocr_score["overall"] or 0) - (text_score["overall"] or 0), 2),
            "ats_delta": round((ocr_score["ats"] or 0) - (text_score["ats"] or 0), 2),
        },
        "extraction": {
            "method": scanned.method,
            "ocr_used": scanned.ocr_used,
            "confidence": scanned.confidence,
            "warnings": scanned.warnings,
        },
        "note": (
            "One synthetic scan of one resume on one machine: it shows the shape and "
            "the cost of the fallback, not a benchmark across scanners. The fixture "
            "and its defects are reproducible by re-running this script."
        ),
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    cost = timings["scan_detect_and_ocr"]
    base = timings["text_layer_extract"]
    print(f"tesseract {report['tesseract']}, {DPI} DPI, 1 page\n")
    print(
        f"recovery  {accuracy['word_recall'] * 100:.1f}% of words recalled, "
        f"F1 {accuracy['word_f1']:.3f}, character similarity {accuracy['character_similarity']:.3f}"
    )
    print(
        f"cost      text layer {base['p50']:.2f} ms p50 -> scanned {cost['p50']:.0f} ms p50 "
        f"({cost['p95']:.0f} ms p95, {cost['max']:.0f} ms max)"
    )
    print(
        f"          render {timings['render_page']['p50']:.0f} ms · "
        f"preprocess {timings['preprocess']['p50']:.1f} ms · "
        f"tesseract {timings['tesseract']['p50']:.0f} ms"
    )
    print(
        f"score     {text_score['overall']:.1f} ({text_score['band']}) -> "
        f"{ocr_score['overall']:.1f} ({ocr_score['band']}), "
        f"ATS {text_score['ats']:.1f} -> {ocr_score['ats']:.1f}, "
        f"confidence {scanned.confidence:.2f}"
    )
    print(f"\nwrote {OUTPUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

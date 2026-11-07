"""Checks against a real clamd, not a stub.

The rest of the suite is hermetic: ClamAV is disabled and the socket protocol,
the signature database and the daemon's own verdict are never exercised. These
tests are skipped unless ``POTENCIA_TEST_CLAMAV=1`` is set, and expect a clamd
on ``POTENCIA_CLAMAV_HOST:POTENCIA_CLAMAV_PORT``. CI starts one and runs this
file alone; locally, ``docker compose up -d clamav`` is enough once it is
healthy.
"""

from __future__ import annotations

import os

import pymupdf as fitz
import pytest
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.user import User
from app.services import resume_service
from app.services.malware_scanner import EICAR_SIGNATURE, _scan_stream_socket, scan_bytes

pytestmark = pytest.mark.skipif(
    os.environ.get("POTENCIA_TEST_CLAMAV") != "1",
    reason="set POTENCIA_TEST_CLAMAV=1 with a clamd running to run the scanner integration tests",
)

HOST = os.environ.get("POTENCIA_CLAMAV_HOST", "127.0.0.1")
PORT = int(os.environ.get("POTENCIA_CLAMAV_PORT", "3310"))


def _clean_pdf() -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_text((50, 72), "Arjun Mehta - Backend Engineer - four years of Python")
    data = document.tobytes()
    document.close()
    return data


def _user(session: Session) -> User:
    user = User(
        email="clamav-integration@example.com",
        display_name="ClamAV Integration",
        password_hash="fakehash_for_testing",
        email_verified=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def test_settings_point_at_the_running_daemon() -> None:
    settings = get_settings()
    assert settings.clamav_enabled is True, "POTENCIA_CLAMAV_ENABLED must be true for these tests"
    assert settings.clamav_host == HOST
    assert settings.clamav_port == PORT


def test_daemon_accepts_a_clean_document() -> None:
    result = scan_bytes(_clean_pdf(), "clean.pdf")

    # `scanned` is the point: an unreachable daemon would report scanned=False.
    assert result.scanned is True
    assert result.is_malicious is False
    assert result.details == "ok"


def test_daemon_detects_eicar_when_the_fast_path_is_bypassed() -> None:
    # scan_bytes short-circuits on the EICAR signature, so it proves nothing
    # about the daemon. Sending the same bytes over INSTREAM proves the socket
    # protocol and a loaded signature database, not just our own string match.
    result = _scan_stream_socket(EICAR_SIGNATURE, HOST, PORT, 15.0)

    assert result.is_malicious is True
    assert "eicar" in (result.virus_name or "").lower()


def test_upload_pipeline_survives_a_real_scan(session: Session) -> None:
    resume = resume_service.create_resume(
        session,
        _user(session),
        filename="clean_resume.pdf",
        declared_content_type="application/pdf",
        data=_clean_pdf(),
    )

    assert resume.status == "completed"
    assert resume.extraction is not None
    assert resume.extraction["ocr_used"] is False

"""Retention: the file really goes away, and only when it should.

The product tells users a generated file is removed after 24 hours. These tests
assert the bytes and the row both disappear, that an unexpired export survives,
and that the previously working link stops serving anything.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone

import fitz
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.storage import get_store
from app.models.analysis import Export
from app.tasks.retention import purge_expired_exports

RESUME_TEXT = """PRIYA NAIR
priya.nair@example.com | +91 90000 11111

SUMMARY
Data engineer focused on streaming pipelines and warehouse reliability.

TECHNICAL SKILLS
Python, SQL, Airflow, dbt, Snowflake, Kafka

WORK EXPERIENCE
Data Engineer
Orbit Analytics | Jan 2021 - Present
- Rebuilt the nightly pipeline, cutting cost by 38%
- Maintained 140 dbt models with automated tests

EDUCATION
B.E. in Information Science
PES University | 2016 - 2020
"""


def _pdf(text: str) -> bytes:
    document = fitz.open()
    page = document.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 555, 800), text, fontsize=9)
    buffer = io.BytesIO()
    document.save(buffer)
    document.close()
    return buffer.getvalue()


def _prepare(client: TestClient, email: str) -> tuple[dict[str, str], str]:
    """Register, upload and analyse. Returns the auth headers and analysis id."""
    headers = {
        "Authorization": "Bearer "
        + client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "a-long-enough-password", "display_name": "Test"},
        ).json()["tokens"]["access_token"]
    }
    resume = client.post(
        "/api/v1/resumes",
        headers=headers,
        files={"file": ("priya.pdf", _pdf(RESUME_TEXT), "application/pdf")},
    ).json()
    analysis = client.post(
        "/api/v1/analyses", headers=headers, json={"resume_id": resume["id"]}
    ).json()
    return headers, analysis["id"]


def _export(client: TestClient, headers: dict[str, str], analysis_id: str) -> dict:
    response = client.post(
        "/api/v1/exports",
        headers=headers,
        json={"analysis_id": analysis_id, "kind": "analysis_report", "format": "pdf"},
    )
    assert response.status_code == 202, response.text
    return response.json()


def test_expired_export_is_removed_with_its_file(client: TestClient, session: Session) -> None:
    headers, analysis_id = _prepare(client, "retention@example.com")
    expired = _export(client, headers, analysis_id)
    kept = _export(client, headers, analysis_id)

    row = session.get(Export, uuid.UUID(expired["id"]))
    assert row is not None
    key = row.storage_key
    assert key
    # Prove the bytes are there before the purge, or the test proves nothing.
    assert len(get_store().get(key)) > 1000

    row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    session.commit()

    assert purge_expired_exports(session) == 1

    assert session.get(Export, uuid.UUID(expired["id"])) is None
    assert session.get(Export, uuid.UUID(kept["id"])) is not None

    # The deleted file is gone from disk and its signing link serves nothing.
    try:
        get_store().get(key)
    except FileNotFoundError:
        pass
    else:  # pragma: no cover - only reached when deletion is broken
        raise AssertionError("the expired file still exists on disk")

    assert client.get(expired["download_url"]).status_code == 404
    # The unexpired export is still downloadable.
    download = client.get(kept["download_url"])
    assert download.status_code == 200
    assert download.headers["content-type"] == "application/pdf"


def test_purge_is_a_no_op_when_nothing_has_expired(client: TestClient, session: Session) -> None:
    headers, analysis_id = _prepare(client, "retention-fresh@example.com")
    _export(client, headers, analysis_id)
    assert purge_expired_exports(session) == 0


def test_expired_export_without_a_file_still_removes_the_row(
    client: TestClient, session: Session
) -> None:
    """A failed export has no bytes but still carries an expiry; it must not linger."""
    headers, analysis_id = _prepare(client, "retention-orphan@example.com")
    record = _export(client, headers, analysis_id)

    row = session.get(Export, uuid.UUID(record["id"]))
    assert row is not None
    get_store().delete(row.storage_key or "")
    row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
    session.commit()

    assert purge_expired_exports(session) == 1
    assert session.get(Export, uuid.UUID(record["id"])) is None

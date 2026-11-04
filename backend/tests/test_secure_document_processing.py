"""Phase 21: Security Hardening & Secure Document Processing Test Suite.

Verifies:
- File extension and file signature validation (magic bytes).
- Executable disguised as PDF or DOCX rejection.
- Empty file and oversized upload rejection.
- Malicious file detection via ClamAV / EICAR signature.
- Scanner fail-safe behavior:
  - Mock/fallback in development mode.
  - Fail-closed (503 Service Unavailable) in production / required mode.
  - Scanner timeout handling.
- PDF security:
  - Malformed and corrupted PDF handling.
  - Encrypted / password-protected PDF rejection.
  - Maximum page count enforcement.
  - Suspicious attachment detection.
- DOCX security:
  - Archive entry count limits.
  - Path traversal in ZIP archive entries.
  - ZIP bomb / excessive compression ratio rejection.
  - Macro-enabled DOCX rejection.
- File storage security:
  - Filename sanitization and directory traversal stripping.
  - Strict user ownership and access control (isolated tenants).
  - Internal storage paths never exposed in API responses.
  - Cleanup of stored objects upon extraction/processing failure.
"""

from __future__ import annotations

import io
import socket
import zipfile
from unittest.mock import patch
import pymupdf as fitz
import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import PotenciaError
from app.core.storage import get_store
from app.document.validation import sanitize_filename, validate_upload
from app.models.user import User
from app.services import resume_service
from app.services.malware_scanner import EICAR_SIGNATURE, scan_bytes


def _make_minimal_pdf(num_pages: int = 1) -> bytes:
    doc = fitz.open()
    for _ in range(num_pages):
        page = doc.new_page()
        page.insert_text((50, 72), "POTENCIA Verified Test Resume Content")
    data = doc.tobytes()
    doc.close()
    return data


def _make_minimal_docx(text: str = "POTENCIA Verified Test Resume Content") -> bytes:
    doc = Document()
    doc.add_paragraph(text)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _register(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "a-long-enough-password", "display_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    return {"Authorization": f"Bearer {response.json()['tokens']['access_token']}"}


def _create_user(session: Session, email: str) -> User:
    user = User(
        email=email,
        display_name="Test User",
        password_hash="fakehash_for_testing",
        email_verified=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


class TestFilenameSanitization:
    def test_strips_unix_directory_traversal(self) -> None:
        assert sanitize_filename("../../../etc/passwd.pdf") == "passwd.pdf"

    def test_strips_windows_directory_traversal(self) -> None:
        assert sanitize_filename(r"..\..\..\Windows\System32\cmd.exe.pdf") == "cmd.exe.pdf"

    def test_strips_null_bytes_and_control_chars(self) -> None:
        sanitized = sanitize_filename("resume\x00_test\r\n.pdf")
        assert "\x00" not in sanitized
        assert "\r" not in sanitized
        assert "\n" not in sanitized
        assert sanitized.endswith(".pdf")

    def test_replaces_windows_reserved_names(self) -> None:
        assert sanitize_filename("CON.pdf") == "uploaded_resume.pdf"
        assert sanitize_filename("NUL.docx") == "uploaded_resume.docx"

    def test_truncates_oversized_filename(self) -> None:
        long_stem = "a" * 300
        sanitized = sanitize_filename(f"{long_stem}.pdf")
        assert len(sanitized) <= 255
        assert sanitized.endswith(".pdf")

    def test_empty_or_whitespace_fallback(self) -> None:
        assert sanitize_filename("") == "uploaded_resume.pdf"
        assert sanitize_filename("   ") == "uploaded_resume.pdf"
        assert sanitize_filename("...") == "uploaded_resume.pdf"


class TestFileValidationAndSignatures:
    def test_valid_pdf_accepted(self) -> None:
        pdf_data = _make_minimal_pdf(1)
        media_type = validate_upload("my_resume.pdf", "application/pdf", pdf_data)
        assert media_type == "application/pdf"

    def test_valid_docx_accepted(self) -> None:
        docx_data = _make_minimal_docx("Candidate Experience")
        media_type = validate_upload("my_resume.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", docx_data)
        assert "openxmlformats" in media_type

    def test_empty_file_rejected(self) -> None:
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("empty.pdf", "application/pdf", b"")
        assert exc_info.value.status_code == 422
        assert "empty" in exc_info.value.message.lower()

    def test_oversized_file_rejected(self) -> None:
        big_data = b"A" * (6 * 1024 * 1024)
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("large.pdf", "application/pdf", big_data)
        assert exc_info.value.status_code == 413

    def test_unsupported_extension_rejected(self) -> None:
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("script.sh", "text/plain", b"echo hello")
        assert exc_info.value.status_code == 415

    def test_executable_disguised_as_pdf_rejected(self) -> None:
        fake_pdf = b"MZ\x90\x00\x03\x00\x00\x00FakeWindowsExecutable"
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("trojan.pdf", "application/pdf", fake_pdf)
        assert exc_info.value.status_code == 415
        assert "PDF header" in exc_info.value.message

    def test_executable_disguised_as_docx_rejected(self) -> None:
        fake_docx = b"MZ\x90\x00\x03\x00\x00\x00FakeWindowsExecutable"
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("trojan.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", fake_docx)
        assert exc_info.value.status_code == 415
        assert "DOCX" in exc_info.value.message


class TestPDFSecurity:
    def test_corrupted_pdf_rejected(self) -> None:
        corrupted = b"%PDF-1.4\ncorrupted bytes that fail fitz parsing\n%%EOF"
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("corrupt.pdf", "application/pdf", corrupted)
        assert exc_info.value.status_code == 422
        assert "could not be opened" in exc_info.value.message

    def test_encrypted_pdf_rejected(self) -> None:
        doc = fitz.open()
        doc.new_page().insert_text((50, 72), "Secret encrypted resume")
        buf = io.BytesIO()
        doc.save(
            buf,
            encryption=fitz.PDF_ENCRYPT_AES_256,
            user_pw="password123",
            owner_pw="owner123",
        )
        encrypted_bytes = buf.getvalue()
        doc.close()

        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("encrypted.pdf", "application/pdf", encrypted_bytes)
        assert exc_info.value.status_code == 422
        assert "encrypted" in exc_info.value.message.lower()

    def test_exceeds_maximum_pdf_pages_rejected(self) -> None:
        large_pdf = _make_minimal_pdf(51)
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("huge.pdf", "application/pdf", large_pdf)
        assert exc_info.value.status_code == 422
        assert "maximum allowed page count" in exc_info.value.message.lower()

    def test_embedded_executable_attachment_rejected(self) -> None:
        doc = fitz.open()
        doc.new_page().insert_text((50, 72), "Resume with payload")
        doc.embfile_add("payload.exe", b"binary_executable_data", filename="payload.exe")
        buf = io.BytesIO()
        doc.save(buf)
        data = buf.getvalue()
        doc.close()

        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("attached.pdf", "application/pdf", data)
        assert exc_info.value.status_code == 422
        assert "unsafe embedded attachment" in exc_info.value.message.lower()


class TestDOCXSecurity:
    def test_zip_without_document_xml_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("test.txt", "just a zip file, not docx")
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("not_docx.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buf.getvalue())
        assert exc_info.value.status_code == 422
        assert "not a docx" in exc_info.value.message.lower()

    def test_macro_enabled_docx_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:document/>")
            z.writestr("word/vbaProject.bin", b"evil_vba_macros")
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("macro.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buf.getvalue())
        assert exc_info.value.status_code == 422
        assert "macros" in exc_info.value.message.lower()

    def test_docx_path_traversal_archive_entry_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:document/>")
            z.writestr("../../etc/cron.d/evil", "malicious cron")
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("traversal.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buf.getvalue())
        assert exc_info.value.status_code == 422
        assert "path traversal" in exc_info.value.message.lower()

    def test_docx_excessive_archive_entries_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("word/document.xml", "<w:document/>")
            for i in range(1001):
                z.writestr(f"word/media/image{i}.png", b"fakeimg")
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("many_files.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buf.getvalue())
        assert exc_info.value.status_code == 422
        assert "too many archive entries" in exc_info.value.message.lower()

    def test_docx_compression_ratio_zip_bomb_rejected(self) -> None:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr("word/document.xml", "<w:document/>" + (" " * (5 * 1024 * 1024)))
        with pytest.raises(PotenciaError) as exc_info:
            validate_upload("zipbomb.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", buf.getvalue())
        assert exc_info.value.status_code == 422
        assert "unsafe compression ratio" in exc_info.value.message.lower()


class TestMalwareScanning:
    def test_detects_eicar_test_signature(self) -> None:
        data = b"%PDF-1.4\n" + EICAR_SIGNATURE + b"\n%%EOF"
        result = scan_bytes(data, "eicar.pdf")
        assert result.is_malicious is True
        assert result.virus_name == "Eicar-Test-Signature"

    def test_eicar_upload_rejected_by_service(self, session: Session) -> None:
        user = _create_user(session, "malware_test_user@example.com")
        # Valid PDF with EICAR test signature present in document bytes
        pdf_bytes = _make_minimal_pdf(1) + b"\n% " + EICAR_SIGNATURE + b"\n"

        with pytest.raises(PotenciaError) as exc_info:
            resume_service.create_resume(
                session,
                user,
                filename="eicar_resume.pdf",
                declared_content_type="application/pdf",
                data=pdf_bytes,
            )
        assert exc_info.value.status_code == 422
        assert "Malicious content detected" in exc_info.value.message

    def test_clamav_unreachable_in_dev_falls_back(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "clamav_enabled", True)
        monkeypatch.setattr(get_settings(), "clamav_required", False)
        monkeypatch.setattr(get_settings(), "environment", "development")
        monkeypatch.setattr(get_settings(), "clamav_port", 65530)  # Unbound port

        result = scan_bytes(b"%PDF-1.4\nClean file\n%%EOF", "resume.pdf")
        assert result.is_malicious is False
        assert result.details == "scanner_unreachable"

    def test_clamav_unreachable_in_production_fails_closed(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "clamav_enabled", True)
        monkeypatch.setattr(get_settings(), "clamav_required", False)
        monkeypatch.setattr(get_settings(), "environment", "production")
        monkeypatch.setattr(get_settings(), "clamav_port", 65530)

        with pytest.raises(PotenciaError) as exc_info:
            scan_bytes(b"%PDF-1.4\nClean file\n%%EOF", "resume.pdf")
        assert exc_info.value.status_code == 503
        assert "unreachable" in exc_info.value.message.lower()

    def test_clamav_timeout_fails_closed_when_required(self, monkeypatch) -> None:
        monkeypatch.setattr(get_settings(), "clamav_enabled", True)
        monkeypatch.setattr(get_settings(), "clamav_required", True)

        with patch("socket.socket.connect", side_effect=socket.timeout("timed out")):
            with pytest.raises(PotenciaError) as exc_info:
                scan_bytes(b"%PDF-1.4\nClean file\n%%EOF", "resume.pdf")
            assert exc_info.value.status_code == 503
            assert "timed out" in exc_info.value.message.lower()


class TestSecureStorageAndTenantIsolation:
    def test_unauthorized_user_cannot_access_resume(
        self, client: TestClient, session: Session
    ) -> None:
        user1 = _create_user(session, "user1@example.com")
        user2_headers = _register(client, "user2@example.com")

        pdf_bytes = _make_minimal_pdf(1)
        resume = resume_service.create_resume(
            session,
            user1,
            filename="user1_resume.pdf",
            declared_content_type="application/pdf",
            data=pdf_bytes,
        )

        # Attempt to access user1's resume with user2's credentials
        response = client.get(
            f"/api/v1/resumes/{resume.id}",
            headers=user2_headers,
        )
        assert response.status_code == 404

    def test_api_never_exposes_storage_path(self, client: TestClient) -> None:
        headers = _register(client, "storage_path_test@example.com")
        pdf_bytes = _make_minimal_pdf(1)
        response = client.post(
            "/api/v1/resumes",
            headers=headers,
            files={"file": ("sanitized_resume.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 201
        data = response.json()
        assert "storage_key" not in data
        assert "path" not in data
        assert "storage" not in data

    def test_failed_processing_cleans_up_stored_object(
        self, session: Session, monkeypatch
    ) -> None:
        user = _create_user(session, "cleanup_user@example.com")
        pdf_bytes = _make_minimal_pdf(1)
        store = get_store()

        # Monkeypatch extract to simulate unhandled catastrophic failure during text extraction
        def broken_extract(data, media_type):
            raise RuntimeError("Catastrophic parsing failure")

        monkeypatch.setattr("app.services.resume_service.extract", broken_extract)

        with pytest.raises(PotenciaError) as exc_info:
            resume_service.create_resume(
                session,
                user,
                filename="cleanup_test.pdf",
                declared_content_type="application/pdf",
                data=pdf_bytes,
            )
        assert exc_info.value.status_code == 422

        # Verify that no orphaned file exists in storage for this digest
        import hashlib
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        key = f"{digest[:2]}/{digest}.pdf"
        with pytest.raises(FileNotFoundError):
            store.get(key)

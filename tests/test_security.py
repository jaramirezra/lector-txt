"""Apertura de PDF y DOCX protegidos con contraseña."""

from __future__ import annotations

from pathlib import Path

import pytest

from lector.docx import extract_docx
from lector.pdf import extract_pdf
from lector.security import LockedDocument, WrongPassword


def test_pdf_requires_password(tmp_path: Path, encrypted_pdf_bytes: bytes):
    path = tmp_path / "locked.pdf"
    path.write_bytes(encrypted_pdf_bytes)

    with pytest.raises(LockedDocument) as error:
        extract_pdf(path)

    assert error.value.page_count == 3
    assert error.value.info["kind"] == "pdf"
    assert error.value.info["level"] == "user"


def test_pdf_wrong_password(tmp_path: Path, encrypted_pdf_bytes: bytes):
    path = tmp_path / "locked.pdf"
    path.write_bytes(encrypted_pdf_bytes)

    with pytest.raises(WrongPassword):
        extract_pdf(path, password="incorrecta")


def test_pdf_correct_password(tmp_path: Path, encrypted_pdf_bytes: bytes):
    path = tmp_path / "locked.pdf"
    path.write_bytes(encrypted_pdf_bytes)

    analysis = extract_pdf(path, password="clave")

    assert analysis.status == "ready"
    assert analysis.encryption is not None
    assert analysis.encryption["level"] == "user"
    assert any("Contenido de la pagina 1." in block.text for block in analysis.blocks)


def test_owner_only_pdf_opens_without_password(tmp_path: Path, owner_only_pdf_bytes: bytes):
    path = tmp_path / "owner.pdf"
    path.write_bytes(owner_only_pdf_bytes)

    analysis = extract_pdf(path)

    assert analysis.status == "ready"
    assert analysis.encryption is not None
    assert analysis.encryption["level"] == "owner"
    assert analysis.encryption["can_copy"] is False
    assert any("permiso" in warning for warning in analysis.warnings)


def test_encrypted_docx_flow(tmp_path: Path, encrypted_docx_bytes: bytes):
    path = tmp_path / "locked.docx"
    path.write_bytes(encrypted_docx_bytes)

    with pytest.raises(LockedDocument) as error:
        extract_docx(path)
    assert error.value.info["kind"] == "docx"

    with pytest.raises(WrongPassword):
        extract_docx(path, password="incorrecta")

    analysis = extract_docx(path, password="clave")
    assert analysis.status == "ready"
    assert analysis.encryption is not None
    assert any(block.text == "Titulo del documento" for block in analysis.blocks)

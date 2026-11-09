"""Fixtures compartidas: documentos de prueba generados al vuelo."""

from __future__ import annotations

import io

import msoffcrypto
import pymupdf
import pytest
from docx import Document


def _pdf_document() -> pymupdf.Document:
    document = pymupdf.open()
    for index in range(3):
        page = document.new_page(width=595, height=842)
        page.insert_text((72, 55), "Informe confidencial", fontsize=9)
        page.insert_text((72, 130), f"Seccion {index + 1}", fontsize=20)
        page.insert_text((72, 170), f"Contenido de la pagina {index + 1}.", fontsize=11)
        page.insert_text((72, 205), "Segunda linea del parrafo.", fontsize=11)
        page.insert_text((280, 805), f"Pagina {index + 1} de 3", fontsize=9)
    return document


@pytest.fixture(scope="session")
def sample_pdf_bytes() -> bytes:
    document = _pdf_document()
    try:
        return document.tobytes()
    finally:
        document.close()


@pytest.fixture(scope="session")
def encrypted_pdf_bytes() -> bytes:
    document = _pdf_document()
    try:
        return document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="dueno",
            user_pw="clave",
        )
    finally:
        document.close()


@pytest.fixture(scope="session")
def owner_only_pdf_bytes() -> bytes:
    document = _pdf_document()
    try:
        return document.tobytes(
            encryption=pymupdf.PDF_ENCRYPT_AES_256,
            owner_pw="dueno",
            user_pw="",
            permissions=pymupdf.PDF_PERM_PRINT,
        )
    finally:
        document.close()


@pytest.fixture(scope="session")
def rotated_pdf_bytes() -> bytes:
    document = pymupdf.open()
    try:
        page = document.new_page(width=400, height=600)
        page.insert_text((50, 80), "Texto rotado", fontsize=14)
        page.set_rotation(90)
        return document.tobytes()
    finally:
        document.close()


@pytest.fixture(scope="session")
def sample_docx_bytes() -> bytes:
    document = Document()
    document.add_heading("Titulo del documento", level=1)
    paragraph = document.add_paragraph("Primer parrafo con ")
    run = paragraph.add_run("negrita")
    run.bold = True
    document.add_paragraph("Elemento uno", style="List Bullet")
    document.add_paragraph("Elemento dos", style="List Bullet")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "Nombre"
    table.cell(0, 1).text = "Valor"
    table.cell(1, 0).text = "Total"
    table.cell(1, 1).text = "10"
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


@pytest.fixture(scope="session")
def encrypted_docx_bytes(sample_docx_bytes: bytes) -> bytes:
    source = io.BytesIO(sample_docx_bytes)
    target = io.BytesIO()
    office = msoffcrypto.OfficeFile(source)
    office.encrypt("clave", target)
    return target.getvalue()

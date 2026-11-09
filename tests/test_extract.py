"""Extracción de bloques de PDF y DOCX."""

from __future__ import annotations

from pathlib import Path

from lector.docx import extract_docx
from lector.pdf import extract_pdf


def test_extract_pdf_blocks_and_suggestions(tmp_path: Path, sample_pdf_bytes: bytes):
    path = tmp_path / "sample.pdf"
    path.write_bytes(sample_pdf_bytes)

    analysis = extract_pdf(path)

    assert analysis.status == "ready"
    assert analysis.page_count == 3
    assert len(analysis.pages) == 3
    assert any("Contenido de la pagina 1." in block.text for block in analysis.blocks)
    assert any(block.kind == "heading" for block in analysis.blocks)

    headers = [block for block in analysis.blocks if block.meta.get("margin") == "header"]
    assert headers and all(block.suggested for block in headers)
    page_numbers = [block for block in analysis.blocks if block.reason == "número de página"]
    assert len(page_numbers) == 3


def test_extract_pdf_rotated_page(tmp_path: Path, rotated_pdf_bytes: bytes):
    path = tmp_path / "rotated.pdf"
    path.write_bytes(rotated_pdf_bytes)

    analysis = extract_pdf(path)

    assert analysis.page_count == 1
    page = analysis.pages[0]
    assert (page.width, page.height) == (600.0, 400.0)

    block = next(block for block in analysis.blocks if "Texto rotado" in block.text)
    assert block.bbox is not None
    assert 0.0 <= block.bbox[0] < block.bbox[2] <= 1.0
    assert 0.0 <= block.bbox[1] < block.bbox[3] <= 1.0
    # El texto se insertó arriba a la izquierda en la página sin rotar y, al
    # girar 90 grados, debe aparecer en la parte derecha de la página visible.
    assert block.bbox[0] > 0.5


def test_extract_docx_styles_lists_and_tables(tmp_path: Path, sample_docx_bytes: bytes):
    path = tmp_path / "sample.docx"
    path.write_bytes(sample_docx_bytes)

    analysis = extract_docx(path)

    assert analysis.status == "ready"
    assert analysis.page_count == 0
    assert analysis.preview_html and "data-block-id" in analysis.preview_html
    assert [block.kind for block in analysis.blocks] == [
        "heading",
        "paragraph",
        "list",
        "list",
        "table",
    ]
    assert analysis.blocks[0].meta["level"] == 1
    assert analysis.blocks[2].meta["needs_bullet"] is True
    assert "Nombre\tValor" in analysis.blocks[4].text
    assert "negrita" in analysis.blocks[1].text

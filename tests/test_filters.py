"""Detección de encabezados, pies y números de página."""

from __future__ import annotations

from lector.filters import suggest_exclusions
from lector.models import Block, Page

PAGES = [Page(number=index, width=595, height=842) for index in range(1, 6)]


def _block(block_id: str, page: int, text: str, margin: str | None) -> Block:
    return Block(
        id=block_id,
        order=0,
        page=page,
        kind="paragraph",
        text=text,
        bbox=(0.1, 0.02, 0.9, 0.05) if margin == "header" else (0.1, 0.95, 0.9, 0.98),
        meta={"margin": margin},
    )


def test_page_number_and_repeated_header():
    blocks = [
        _block("h1", 1, "Informe interno", "header"),
        _block("h2", 2, "Informe interno", "header"),
        _block("h3", 3, "Informe interno", "header"),
        _block("f1", 1, "Página 1 de 5", "footer"),
        _block("f2", 2, "Página 2 de 5", "footer"),
        _block("b1", 1, "Contenido real", None),
    ]
    pages = PAGES[:3]

    suggest_exclusions(blocks, pages)

    assert all(block.suggested for block in blocks[:3])
    assert blocks[0].reason == "encabezado repetido"
    assert all(block.suggested for block in blocks[3:5])
    assert blocks[3].reason == "número de página"
    assert not blocks[5].suggested


def test_repeated_header_requires_half_of_pages():
    blocks = [
        _block("h1", 1, "Informe interno", "header"),
        _block("h2", 2, "Informe interno", "header"),
        _block("h3", 3, "Otro texto", "header"),
    ]

    suggest_exclusions(blocks, PAGES)

    # 2 de 5 páginas no alcanza el umbral (3).
    assert not any(block.suggested for block in blocks)


def test_short_document_threshold():
    blocks = [
        _block("h1", 1, "Cabecera", "header"),
        _block("h2", 2, "Cabecera", "header"),
    ]

    suggest_exclusions(blocks, PAGES[:2])

    assert all(block.suggested for block in blocks)

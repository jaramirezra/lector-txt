"""Extracción de párrafos, estilos, listas y tablas de un DOCX."""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

from docx import Document
from docx.document import Document as DocxDocument
from docx.oxml.ns import qn
from docx.table import Table
from docx.text.paragraph import Paragraph
from docx.text.run import Run

from .models import Analysis, Block
from .security import (
    DocumentError,
    LockedDocument,
    WrongPassword,
    decrypt_docx,
    docx_encryption_info,
    is_ole,
)

LIST_RE = re.compile(r"^\s*(?:[•◦▪‣·∙]\s*|[-–—*]\s+|\d{1,3}[.)]\s+)")


def _paragraph_text(paragraph: Paragraph) -> str:
    pieces: list[str] = []
    for node in paragraph._p.iter():
        if node.tag == qn("w:t"):
            pieces.append(node.text or "")
        elif node.tag == qn("w:tab"):
            pieces.append("\t")
        elif node.tag in {qn("w:br"), qn("w:cr")}:
            pieces.append("\n")
        elif node.tag == qn("w:noBreakHyphen"):
            pieces.append("-")
    return "".join(pieces)


def _paragraph_html(paragraph: Paragraph) -> str:
    pieces: list[str] = []
    try:
        items = list(paragraph.iter_inner_content())
    except Exception:
        items = list(paragraph.runs)

    for item in items:
        if isinstance(item, Run):
            text = item.text
            if not text:
                continue
            fragment = escape(text).replace("\n", "<br>").replace("\t", "&#9;")
            if item.bold:
                fragment = f"<strong>{fragment}</strong>"
            if item.italic:
                fragment = f"<em>{fragment}</em>"
            if item.underline:
                fragment = f"<u>{fragment}</u>"
            pieces.append(fragment)
        else:
            text = getattr(item, "text", "") or ""
            if text:
                pieces.append(f'<span class="docx-link">{escape(text)}</span>')

    if not pieces:
        pieces.append(escape(paragraph.text).replace("\n", "<br>"))
    return "".join(pieces)


def _classify(paragraph: Paragraph) -> tuple[str, int]:
    style_name = (paragraph.style.name if paragraph.style is not None else "") or ""
    lower = style_name.strip().lower()
    has_numbering = paragraph._p.pPr is not None and paragraph._p.pPr.numPr is not None

    if lower.startswith("heading") or lower.startswith("título") or lower in {"title", "subtitle"}:
        digits = re.findall(r"\d+", style_name)
        if digits:
            level = int(digits[0])
        elif lower == "subtitle":
            level = 2
        else:
            level = 1
        return "heading", max(1, min(level, 6))

    if "list" in lower or "lista" in lower or has_numbering:
        return "list", 0

    if "quote" in lower or "cita" in lower:
        return "quote", 0

    return "paragraph", 0


def _table_data(table: Table) -> tuple[str, str]:
    text_rows: list[str] = []
    html_rows: list[str] = []

    for row in table.rows:
        text_cells: list[str] = []
        html_cells: list[str] = []
        for cell in row.cells:
            text_cells.append(" ".join(cell.text.split()))
            inner = "<br>".join(
                _paragraph_html(paragraph)
                for paragraph in cell.paragraphs
                if _paragraph_text(paragraph).strip()
            )
            html_cells.append(f"<td>{inner}</td>")
        text_rows.append("\t".join(text_cells))
        html_rows.append("<tr>" + "".join(html_cells) + "</tr>")

    text = "\n".join(text_rows).strip()
    html = f'<table class="docx-table"><tbody>{"".join(html_rows)}</tbody></table>'
    return text, html


def _iter_body_items(document: DocxDocument):
    for child in document.element.body.iterchildren():
        if child.tag == qn("w:p"):
            yield Paragraph(child, document)
        elif child.tag == qn("w:tbl"):
            yield Table(child, document)


def _preview_html(blocks: list[Block]) -> str:
    parts = ['<div class="docx-doc">']
    for block in blocks:
        classes = ["docx-block", f"kind-{block.kind}"]
        if block.kind == "heading":
            classes.append(f"level-{block.meta.get('level') or 2}")
        if block.kind == "list" and block.meta.get("needs_bullet"):
            classes.append("needs-bullet")
        inner = block.meta.get("html") or escape(block.text).replace("\n", "<br>")
        parts.append(
            f'<div class="{" ".join(classes)}" data-block-id="{block.id}" '
            f'role="button" tabindex="0" aria-pressed="true">{inner}</div>'
        )
    parts.append("</div>")
    return "".join(parts)


def _open_document(path: Path, password: str | None) -> DocxDocument:
    if is_ole(path):
        info = docx_encryption_info(path)
        if info is None:
            raise DocumentError(
                "El archivo parece un .doc antiguo o está dañado. Guarda el documento como DOCX.",
                code="legacy_doc",
            )
        if password is None:
            raise LockedDocument(info)
        stream = decrypt_docx(path, password, info)
        try:
            return Document(stream)
        except Exception as exc:
            raise DocumentError(
                "El documento se descifró, pero no se pudo leer como DOCX.",
                code="invalid_docx",
            ) from exc

    try:
        return Document(str(path))
    except Exception as exc:
        raise DocumentError(
            "El archivo no es un DOCX válido o está dañado.",
            code="invalid_docx",
        ) from exc


def extract_docx(path: Path, password: str | None = None, max_pages: int = 300) -> Analysis:
    document = _open_document(path, password)

    blocks: list[Block] = []
    for item in _iter_body_items(document):
        if isinstance(item, Paragraph):
            text = _paragraph_text(item).strip("\n")
            if not text.strip():
                continue
            kind, level = _classify(item)
            needs_bullet = kind == "list" and not LIST_RE.match(text)
            blocks.append(
                Block(
                    id=f"b{len(blocks) + 1}",
                    order=len(blocks),
                    page=0,
                    kind=kind,
                    text=text,
                    meta={
                        "level": level or None,
                        "needs_bullet": needs_bullet,
                        "style": item.style.name if item.style is not None else "",
                        "html": _paragraph_html(item),
                    },
                )
            )
        elif isinstance(item, Table):
            text, html = _table_data(item)
            if not text.strip():
                continue
            blocks.append(
                Block(
                    id=f"b{len(blocks) + 1}",
                    order=len(blocks),
                    page=0,
                    kind="table",
                    text=text,
                    meta={"html": html},
                )
            )

    warnings: list[str] = []
    if not blocks:
        warnings.append("El documento no contiene texto que se pueda convertir a TXT.")

    return Analysis(
        kind="docx",
        status="ready",
        page_count=0,
        pages=[],
        blocks=blocks,
        warnings=warnings,
        encryption=docx_encryption_info(path) if is_ole(path) else None,
        preview_html=_preview_html(blocks) if blocks else None,
    )

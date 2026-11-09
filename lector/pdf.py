"""Extracción de texto, coordenadas y renderizado de PDF con PyMuPDF."""

from __future__ import annotations

import re
import statistics
from pathlib import Path

import pymupdf

from .filters import suggest_exclusions
from .models import Analysis, Block, Page
from .security import (
    DocumentError,
    LockedDocument,
    PageLimitError,
    WrongPassword,
    authenticate_pdf,
    level_from_code,
    pdf_encryption_info,
    pdf_is_encrypted,
)

LIST_RE = re.compile(r"^\s*(?:[•◦▪‣·∙]\s*|[-–—*]\s+|\d{1,3}[.)]\s+)")
MARGIN_RATIO = 0.13


def open_pdf(path: Path) -> pymupdf.Document:
    try:
        return pymupdf.open(str(path))
    except Exception as exc:
        raise DocumentError(
            "El archivo no es un PDF válido o está dañado.",
            code="invalid_pdf",
        ) from exc


def _normalized_bbox(bbox, page: pymupdf.Page) -> tuple[float, float, float, float] | None:
    try:
        rect = page.rect
        if rect.width <= 0 or rect.height <= 0:
            return None
        rotated = pymupdf.Rect(bbox) * page.rotation_matrix
        x0 = max(0.0, min(1.0, rotated.x0 / rect.width))
        y0 = max(0.0, min(1.0, rotated.y0 / rect.height))
        x1 = max(0.0, min(1.0, rotated.x1 / rect.width))
        y1 = max(0.0, min(1.0, rotated.y1 / rect.height))
    except Exception:
        return None
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1, y1)


def _block_payload(raw: dict) -> tuple[str, float, bool, int, list[str]]:
    lines: list[str] = []
    sizes: list[float] = []
    bold_spans = 0
    total_spans = 0

    for line in raw.get("lines", []):
        pieces: list[str] = []
        for span in line.get("spans", []):
            pieces.append(span.get("text", ""))
            size = span.get("size")
            if size:
                sizes.append(float(size))
            if span.get("text", "").strip():
                total_spans += 1
                if int(span.get("flags", 0)) & 16:
                    bold_spans += 1
        line_text = "".join(pieces)
        if line_text:
            lines.append(line_text)

    text = "\n".join(lines).strip()
    max_size = max(sizes) if sizes else 0.0
    is_bold = total_spans > 0 and (bold_spans / total_spans) >= 0.6
    return text, max_size, is_bold, total_spans, lines


def _classify(
    text: str,
    lines: list[str],
    max_size: float,
    median_size: float,
    bold: bool,
    margin: str | None,
) -> tuple[str, int]:
    nonempty = [line for line in lines if line.strip()]
    is_list = bool(nonempty) and all(LIST_RE.match(line) for line in nonempty)

    if margin:
        return "paragraph", 0
    if is_list:
        return "list", 0
    if len(text) <= 170 and len(nonempty) <= 3:
        if median_size > 0 and max_size >= median_size * 1.3:
            ratio = max_size / median_size
            level = 1 if ratio >= 1.9 else 2 if ratio >= 1.5 else 3
            return "heading", level
        if bold and len(text) <= 100:
            return "heading", 2
    return "paragraph", 0


def extract_pdf(path: Path, password: str | None = None, max_pages: int = 300) -> Analysis:
    doc = open_pdf(path)
    try:
        if doc.needs_pass:
            if doc.page_count > max_pages:
                raise PageLimitError(max_pages)
            if password is None:
                raise LockedDocument(
                    pdf_encryption_info(doc, "user", False),
                    page_count=doc.page_count,
                )
            code = authenticate_pdf(doc, password)
            if not code:
                raise WrongPassword(pdf_encryption_info(doc, "user", False))
            level = level_from_code(code)
            encryption = pdf_encryption_info(doc, level, True)
        else:
            code = doc.authenticate("")
            encrypted = pdf_is_encrypted(doc)
            if encrypted:
                # Si el PDF se abre sin contraseña, la contraseña de usuario es
                # vacía: para el usuario el documento está protegido por el
                # propietario, aunque PyMuPDF devuelva el código de usuario (2).
                level = "owner" if code in {2, 4} else level_from_code(code)
                encryption = pdf_encryption_info(doc, level, True)
            else:
                encryption = None

        if doc.page_count <= 0:
            raise DocumentError("El PDF no tiene páginas.", code="empty_document")
        if doc.page_count > max_pages:
            raise PageLimitError(max_pages)

        pages = [
            Page(number=page.number + 1, width=page.rect.width, height=page.rect.height)
            for page in doc
        ]

        raw_pages: list[tuple[pymupdf.Page, dict]] = []
        for page in doc:
            pages_data = page.get_text("dict", sort=True)
            raw_pages.append((page, pages_data))

        sizes: list[float] = []
        for _, data in raw_pages:
            for raw in data.get("blocks", []):
                if raw.get("type") != 0:
                    continue
                for line in raw.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("text", "").strip() and span.get("size"):
                            sizes.append(float(span["size"]))
        median_size = statistics.median(sizes) if sizes else 0.0

        blocks: list[Block] = []
        for page, data in raw_pages:
            for raw in data.get("blocks", []):
                if raw.get("type") != 0:
                    continue
                text, max_size, bold, _, lines = _block_payload(raw)
                if not text.strip():
                    continue
                bbox = _normalized_bbox(raw.get("bbox"), page)
                if bbox is None:
                    continue

                margin = None
                if bbox[3] <= MARGIN_RATIO:
                    margin = "header"
                elif bbox[1] >= 1.0 - MARGIN_RATIO:
                    margin = "footer"

                kind, level = _classify(text, lines, max_size, median_size, bold, margin)
                needs_bullet = kind == "list" and not LIST_RE.match(text)
                block = Block(
                    id=f"b{len(blocks) + 1}",
                    order=len(blocks),
                    page=page.number + 1,
                    kind=kind,
                    text=text,
                    bbox=bbox,
                    meta={
                        "font_size": round(max_size, 1),
                        "bold": bold,
                        "margin": margin,
                        "level": level or None,
                        "needs_bullet": needs_bullet,
                    },
                )
                blocks.append(block)

        suggest_exclusions(blocks, pages)

        total_text = "".join(block.text for block in blocks)
        warnings: list[str] = []
        if encryption:
            if encryption.get("level") == "owner":
                warnings.append(
                    "El PDF está protegido con contraseña de propietario: se abrió sin contraseña."
                )
            elif encryption.get("level") in {"user", "user-owner"}:
                warnings.append(
                    "Documento desbloqueado solo para esta sesión; la contraseña no se guarda."
                )
            if encryption.get("can_copy") is False:
                warnings.append(
                    "El autor del PDF restringe la copia de texto. Comprueba que tengas permiso para reutilizarlo."
                )
        if len(total_text.strip()) < 10 and len(pages) > 0:
            warnings.append(
                "El PDF no contiene texto seleccionable (parece escaneado). Para convertirlo haría falta OCR."
            )

        return Analysis(
            kind="pdf",
            status="ready",
            page_count=len(pages),
            pages=pages,
            blocks=blocks,
            warnings=warnings,
            encryption=encryption,
        )
    finally:
        doc.close()


def render_pdf_page(
    path: Path,
    password: str | None,
    number: int,
    dpi: int = 120,
) -> bytes:
    doc = open_pdf(path)
    try:
        if doc.needs_pass:
            if not password or not authenticate_pdf(doc, password):
                raise WrongPassword(pdf_encryption_info(doc, "user", False))
        if number < 1 or number > doc.page_count:
            raise DocumentError("Página fuera de rango.", code="page_not_found", status=404)
        page = doc.load_page(number - 1)
        pixmap = page.get_pixmap(dpi=dpi, alpha=False)
        return pixmap.tobytes("png")
    finally:
        doc.close()

"""Detección del tipo de archivo y punto de entrada de la extracción."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

from .docx import extract_docx
from .models import Analysis
from .pdf import extract_pdf
from .security import OLE_MAGIC, ZIP_MAGIC


def _zip_has_word_document(data: bytes) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            return "word/document.xml" in archive.namelist()
    except Exception:
        return False


def sniff_kind(data: bytes, filename: str) -> str | None:
    extension = Path(filename).suffix.lower()

    if data.startswith(b"%PDF-"):
        return "pdf"
    if data.startswith(ZIP_MAGIC):
        return "docx" if _zip_has_word_document(data) else None
    if data.startswith(OLE_MAGIC):
        # Puede ser un DOCX cifrado o un .doc antiguo; se decide al analizarlo.
        return "docx"
    if extension == ".pdf":
        return "pdf"
    if extension == ".docx":
        return "docx"
    return None


def analyze(
    path: Path,
    kind: str,
    password: str | None = None,
    max_pages: int = 300,
) -> Analysis:
    if kind == "pdf":
        return extract_pdf(path, password=password, max_pages=max_pages)
    if kind == "docx":
        return extract_docx(path, password=password, max_pages=max_pages)
    raise ValueError(f"Tipo de documento no soportado: {kind}")

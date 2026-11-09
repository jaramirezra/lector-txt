"""Detección de cifrado, desbloqueo de PDF y descifrado de DOCX en memoria.

Regla de oro de este módulo: la contraseña nunca se escribe en disco ni aparece
en mensajes, URLs o registros. Solo vive en memoria mientras dura el trabajo.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import msoffcrypto
import pymupdf

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
ZIP_MAGIC = b"PK\x03\x04"

PERMISSION_LABELS: dict[int, str] = {
    pymupdf.PDF_PERM_PRINT: "imprimir",
    pymupdf.PDF_PERM_MODIFY: "modificar",
    pymupdf.PDF_PERM_COPY: "copiar texto",
    pymupdf.PDF_PERM_ANNOTATE: "anotar",
    pymupdf.PDF_PERM_FORM: "rellenar formularios",
    pymupdf.PDF_PERM_ACCESSIBILITY: "accesibilidad",
    pymupdf.PDF_PERM_ASSEMBLE: "ensamblar",
    pymupdf.PDF_PERM_PRINT_HQ: "imprimir en alta calidad",
}


class DocumentError(Exception):
    """El archivo no se puede procesar."""

    def __init__(self, message: str, code: str = "invalid_document", status: int = 422):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


class PageLimitError(DocumentError):
    def __init__(self, limit: int):
        super().__init__(
            f"El documento supera el límite de {limit} páginas.",
            code="page_limit",
            status=413,
        )


class LockedDocument(Exception):
    """El documento necesita contraseña para poder leerse."""

    def __init__(self, info: dict[str, Any], page_count: int = 0):
        super().__init__("Documento protegido con contraseña")
        self.info = info
        self.page_count = page_count


class WrongPassword(Exception):
    def __init__(self, info: dict[str, Any]):
        super().__init__("Contraseña incorrecta")
        self.info = info


def level_from_code(code: int) -> str:
    return {
        1: "none",
        2: "user",
        4: "owner",
        6: "user-owner",
    }.get(code, "unknown")


def permission_labels(doc: pymupdf.Document) -> list[str]:
    try:
        permissions = doc.permissions
    except Exception:  # pragma: no cover - documentos dañados
        return []
    return [label for bit, label in PERMISSION_LABELS.items() if permissions & bit]


def _can(doc: pymupdf.Document, bit: int) -> bool | None:
    try:
        return bool(doc.permissions & bit)
    except Exception:  # pragma: no cover
        return None


def pdf_is_encrypted(doc: pymupdf.Document) -> bool:
    """Detecta cifrado incluso cuando solo hay contraseña de propietario.

    En ese caso ``needs_pass`` es 0 e ``is_encrypted`` puede ser False, pero el
    metadato ``encryption`` sigue presente.
    """

    try:
        if doc.needs_pass:
            return True
    except Exception:  # pragma: no cover
        pass
    try:
        metadata = doc.metadata or {}
        return bool(metadata.get("encryption"))
    except Exception:  # pragma: no cover
        return False


def pdf_encryption_info(
    doc: pymupdf.Document,
    level: str,
    authenticated: bool,
) -> dict[str, Any]:
    method = "PDF cifrado"
    try:
        metadata = doc.metadata or {}
        method = metadata.get("encryption") or method
    except Exception:  # pragma: no cover
        pass

    labels: list[str] = []
    can_copy: bool | None = None
    can_print: bool | None = None
    if authenticated or not doc.needs_pass:
        labels = permission_labels(doc)
        can_copy = _can(doc, pymupdf.PDF_PERM_COPY)
        can_print = _can(doc, pymupdf.PDF_PERM_PRINT)

    return {
        "kind": "pdf",
        "method": method,
        "level": level,
        "permissions": labels,
        "can_copy": can_copy,
        "can_print": can_print,
    }


def authenticate_pdf(doc: pymupdf.Document, password: str) -> int:
    """Prueba la contraseña y variantes de codificación habituales.

    Los PDF antiguos guardan la contraseña como bytes en PDFDocEncoding, mientras
    que los modernos (AES-256) usan UTF-8. Si la contraseña tiene acentos, probar
    ambas interpretaciones evita fallos difíciles de explicar al usuario.
    """

    candidates = [password]
    if any(ord(char) > 127 for char in password):
        for encode, decode in (("utf-8", "latin-1"), ("latin-1", "utf-8")):
            try:
                candidate = password.encode(encode).decode(decode)
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            if candidate not in candidates:
                candidates.append(candidate)

    for candidate in candidates:
        try:
            code = doc.authenticate(candidate)
        except Exception:
            code = 0
        if code:
            return code
    return 0


def is_ole(path: Path) -> bool:
    try:
        with open(path, "rb") as handle:
            return handle.read(8) == OLE_MAGIC
    except OSError:
        return False


def docx_encryption_info(path: Path) -> dict[str, Any] | None:
    """Devuelve información de cifrado si el DOCX está protegido."""

    try:
        with open(path, "rb") as handle:
            office = msoffcrypto.OfficeFile(handle)
            if not office.is_encrypted():
                return None
    except Exception:
        return None

    return {
        "kind": "docx",
        "method": "Cifrado de Office (OOXML)",
        "level": "user",
        "permissions": [],
        "can_copy": None,
        "can_print": None,
    }


def decrypt_docx(path: Path, password: str, info: dict[str, Any]) -> io.BytesIO:
    """Descifra un DOCX a memoria; nunca escribe una copia en claro."""

    try:
        with open(path, "rb") as handle:
            office = msoffcrypto.OfficeFile(handle)
            if not office.is_encrypted():
                raise DocumentError(
                    "El archivo parece un .doc antiguo o está dañado; no es un DOCX válido."
                )
            office.load_key(password=password, verify_password=True)
            output = io.BytesIO()
            office.decrypt(output)
    except msoffcrypto.exceptions.InvalidKeyError as exc:
        raise WrongPassword(info) from exc
    except DocumentError:
        raise
    except Exception as exc:
        raise DocumentError(
            "No se pudo descifrar el documento. Comprueba que sea un DOCX de Office válido."
        ) from exc

    output.seek(0)
    return output

"""Modelos compartidos entre extracción, filtros y exportación."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

WORD_RE = re.compile(r"[^\s]+")


@dataclass(slots=True)
class Page:
    """Página visible del documento (solo PDF)."""

    number: int
    width: float
    height: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "number": self.number,
            "width": round(self.width, 2),
            "height": round(self.height, 2),
        }


@dataclass(slots=True)
class Block:
    """Unidad de contenido que el usuario puede incluir o excluir."""

    id: str
    order: int
    page: int
    kind: str
    text: str
    bbox: tuple[float, float, float, float] | None = None
    suggested: bool = False
    reason: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        # ``html`` es solo para la vista previa del DOCX; no se envía en los bloques.
        meta = {key: value for key, value in self.meta.items() if key != "html"}
        return {
            "id": self.id,
            "order": self.order,
            "page": self.page,
            "kind": self.kind,
            "text": self.text,
            "bbox": [round(value, 6) for value in self.bbox] if self.bbox else None,
            "suggested": self.suggested,
            "reason": self.reason,
            "meta": meta,
        }


@dataclass(slots=True)
class Analysis:
    """Resultado normalizado de analizar un documento."""

    kind: str
    status: str
    page_count: int
    pages: list[Page] = field(default_factory=list)
    blocks: list[Block] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    encryption: dict[str, Any] | None = None
    preview_html: str | None = None


def count_words(text: str) -> int:
    return len(WORD_RE.findall(text or ""))

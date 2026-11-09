"""Sugerencias de exclusión: encabezados, pies y números de página."""

from __future__ import annotations

import math
import re
from collections import defaultdict

from .models import Block, Page

PAGE_NUMBER_RE = re.compile(
    r"^\s*(?:(?:p[áa]g(?:ina)?|page|p\.)\s*)?[-–—]?\s*"
    r"(?:\d{1,4}|[ivxlcdm]{1,7})"
    r"(?:\s*(?:de|/|of)\s*(?:\d{1,4}|[ivxlcdm]{1,7}))?"
    r"\s*[-–—]?\s*$",
    re.IGNORECASE,
)

MARGIN_RATIO = 0.13
MAX_REPEATED_LENGTH = 160


def _normalize(text: str) -> str:
    text = re.sub(r"\d+", "#", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def _in_margin(block: Block) -> bool:
    return block.meta.get("margin") in {"header", "footer"}


def _is_page_number(block: Block) -> bool:
    if not _in_margin(block):
        return False
    text = block.text.strip()
    return 0 < len(text) <= 24 and bool(PAGE_NUMBER_RE.match(text))


def suggest_exclusions(blocks: list[Block], pages: list[Page]) -> None:
    """Marca bloques que probablemente sobran, sin excluirlos automáticamente."""

    page_count = len(pages)
    for block in blocks:
        if _is_page_number(block):
            block.suggested = True
            block.reason = "número de página"

    if page_count < 2:
        return

    groups: dict[tuple[str, str], list[Block]] = defaultdict(list)
    for block in blocks:
        if not _in_margin(block) or block.reason == "número de página":
            continue
        text = block.text.strip()
        if not text or len(text) > MAX_REPEATED_LENGTH:
            continue
        key = (_normalize(text), str(block.meta.get("margin")))
        groups[key].append(block)

    threshold = max(2, math.ceil(page_count * 0.5))
    for items in groups.values():
        repeated_pages = {block.page for block in items if block.page > 0}
        if len(repeated_pages) < threshold:
            continue
        for block in items:
            block.suggested = True
            block.reason = "encabezado repetido" if block.meta.get("margin") == "header" else "pie repetido"

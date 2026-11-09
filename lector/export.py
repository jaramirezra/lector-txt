"""Ensamblado del TXT final a partir de los bloques incluidos."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .models import Block

LIST_RE = re.compile(r"^\s*(?:[•◦▪‣·∙]\s*|[-–—*]\s+|\d{1,3}[.)]\s+)")
HYPHEN_JOIN_RE = re.compile(r"(?<=[^\W\d_])-\n(?=[^\W\d_])")

PARAGRAPH_SEPARATORS = {
    "none": "\n",
    "single": "\n\n",
    "double": "\n\n\n",
}

LIST_PREFIXES = {"keep", "dash", "none"}
TABLE_SEPARATORS = {"tab", "pipe", "newline"}
HEADING_STYLES = {"none", "upper", "markdown"}
ENCODINGS = {"utf-8", "utf-8-sig"}
NEWLINES = {"lf", "crlf"}


def _choice(value: Any, allowed: set[str], default: str) -> str:
    return value if isinstance(value, str) and value in allowed else default


@dataclass(slots=True)
class ExportOptions:
    paragraph_sep: str = "single"
    list_prefix: str = "keep"
    table_sep: str = "tab"
    heading_style: str = "none"
    join_hyphenated: bool = False
    encoding: str = "utf-8"
    newline: str = "lf"

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ExportOptions":
        data = data or {}
        return cls(
            paragraph_sep=_choice(data.get("paragraph_sep"), set(PARAGRAPH_SEPARATORS), "single"),
            list_prefix=_choice(data.get("list_prefix"), LIST_PREFIXES, "keep"),
            table_sep=_choice(data.get("table_sep"), TABLE_SEPARATORS, "tab"),
            heading_style=_choice(data.get("heading_style"), HEADING_STYLES, "none"),
            join_hyphenated=bool(data.get("join_hyphenated", False)),
            encoding=_choice(data.get("encoding"), ENCODINGS, "utf-8"),
            newline=_choice(data.get("newline"), NEWLINES, "lf"),
        )

    def encode(self, text: str) -> bytes:
        return text.encode(self.encoding)


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).strip()


def _format_block(block: Block, text: str, options: ExportOptions) -> str:
    text = _normalize(text)
    if not text:
        return ""

    if options.join_hyphenated:
        text = HYPHEN_JOIN_RE.sub("", text)

    if block.kind == "heading":
        if options.heading_style == "upper":
            text = text.upper()
        elif options.heading_style == "markdown":
            try:
                level = int(block.meta.get("level") or 1)
            except (TypeError, ValueError):
                level = 1
            text = "#" * max(1, min(level, 6)) + " " + text

    elif block.kind == "list":
        has_bullet = bool(LIST_RE.match(text))
        plain = LIST_RE.sub("", text, count=1).lstrip()
        if options.list_prefix == "none":
            text = plain
        elif options.list_prefix == "dash":
            text = "- " + plain if plain else ""
        elif not has_bullet and block.meta.get("needs_bullet"):
            text = "- " + text

    elif block.kind == "table":
        if options.table_sep == "pipe":
            text = text.replace("\t", " | ")
        elif options.table_sep == "newline":
            text = text.replace("\t", "\n")

    return text.strip()


def build_text(
    blocks: list[Block],
    included_ids: set[str],
    edits: dict[str, str] | None = None,
    options: ExportOptions | None = None,
    text_override: str | None = None,
) -> str:
    """Construye el texto final. ``text_override`` respeta la edición manual."""

    options = options or ExportOptions()
    edits = edits or {}

    if text_override is not None:
        text = _normalize(text_override)
    else:
        separator = PARAGRAPH_SEPARATORS[options.paragraph_sep]
        chunks: list[str] = []
        previous_kind: str | None = None
        for block in blocks:
            if block.id not in included_ids:
                continue
            raw = edits.get(block.id, block.text)
            piece = _format_block(block, str(raw), options)
            if not piece:
                continue
            joiner = "\n" if previous_kind == "list" and block.kind == "list" else separator
            if chunks:
                chunks.append(joiner)
            chunks.append(piece)
            previous_kind = block.kind
        text = _normalize("".join(chunks))
        text = re.sub(r"\n{4,}", "\n\n\n", text)

    if text:
        text += "\n"
    if options.newline == "crlf":
        text = text.replace("\n", "\r\n")
    return text

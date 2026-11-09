"""Ensamblado del TXT y opciones de exportación."""

from __future__ import annotations

from lector.export import ExportOptions, build_text
from lector.models import Block


def _blocks() -> list[Block]:
    return [
        Block(id="b1", order=0, page=1, kind="heading", text="Titulo", meta={"level": 2}),
        Block(id="b2", order=1, page=1, kind="paragraph", text="Primer parrafo."),
        Block(id="b3", order=2, page=1, kind="list", text="Uno", meta={"needs_bullet": True}),
        Block(id="b4", order=3, page=1, kind="list", text="Dos", meta={"needs_bullet": True}),
        Block(id="b5", order=4, page=0, kind="table", text="A\tB\nC\tD"),
    ]


def test_default_export_joins_list_items():
    text = build_text(_blocks(), {block.id for block in _blocks()})

    assert "Titulo" in text
    assert "Primer parrafo." in text
    assert "- Uno\n- Dos" in text
    assert "A\tB" in text
    assert text.endswith("\n")


def test_excluded_blocks_and_edits():
    blocks = _blocks()
    text = build_text(
        blocks,
        {"b1", "b2"},
        edits={"b2": "Parrafo corregido."},
    )

    assert "Titulo" in text
    assert "Parrafo corregido." in text
    assert "Uno" not in text
    assert "A\tB" not in text


def test_heading_and_table_options():
    text = build_text(
        _blocks(),
        {block.id for block in _blocks()},
        options=ExportOptions(heading_style="markdown", table_sep="pipe"),
    )

    assert "## Titulo" in text
    assert "A | B" in text


def test_no_list_prefix():
    text = build_text(
        _blocks(),
        {block.id for block in _blocks()},
        options=ExportOptions(list_prefix="none"),
    )

    assert "Uno" in text
    assert "- Uno" not in text


def test_text_override_respects_manual_editing():
    text = build_text(
        _blocks(),
        set(),
        options=ExportOptions(),
        text_override="Linea uno\r\nLinea dos\r\n",
    )

    assert text == "Linea uno\nLinea dos\n"


def test_crlf_and_bom_encoding():
    options = ExportOptions(newline="crlf", encoding="utf-8-sig")
    text = build_text(_blocks(), {"b2"}, options=options)

    assert text == "Primer parrafo.\r\n"
    assert options.encode(text).startswith(b"\xef\xbb\xbf")


def test_join_hyphenated_words():
    blocks = [Block(id="b1", order=0, page=1, kind="paragraph", text="docu-\nmento")]
    text = build_text(blocks, {"b1"}, options=ExportOptions(join_hyphenated=True))

    assert text == "documento\n"


def test_unknown_options_fall_back_to_defaults():
    options = ExportOptions.from_dict(
        {"paragraph_sep": "raro", "list_prefix": "raro", "encoding": "latin-1"}
    )

    assert options.paragraph_sep == "single"
    assert options.list_prefix == "keep"
    assert options.encoding == "utf-8"

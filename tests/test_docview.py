"""Tests for the large-document query helper."""

from __future__ import annotations

import io
import json

import pytest

from tinyassets.docview import (
    extract_markdown_section,
    extract_text_lines,
    list_markdown_headings,
    render_json_keys,
    render_json_value,
    run_docview,
    search_text,
    write_output,
)


def test_list_markdown_headings_skips_fenced_code() -> None:
    text = """# Top

## Real Section

```md
## Not a heading
```

### Deep Section
"""

    headings = list_markdown_headings(text)

    assert [(heading.level, heading.title, heading.line_number) for heading in headings] == [
        (1, "Top", 1),
        (2, "Real Section", 3),
        (3, "Deep Section", 9),
    ]


def test_extract_markdown_section_stops_at_next_peer_heading() -> None:
    text = """# Top

Intro

## Alpha
alpha line 1
alpha line 2

### Alpha Child
child line

## Beta
beta line
"""

    section = extract_markdown_section(text, "Alpha")

    assert "## Alpha" in section
    assert "alpha line 2" in section
    assert "### Alpha Child" in section
    assert "## Beta" not in section


def test_extract_text_lines_clamps_to_file_bounds() -> None:
    text = "one\ntwo\nthree\n"

    excerpt = extract_text_lines(text, start_line=-10, end_line=99)

    assert excerpt == "one\ntwo\nthree"


def test_search_text_returns_bounded_context() -> None:
    text = "\n".join(
        [
            "line 1",
            "line 2",
            "target hit here",
            "line 4",
            "line 5",
        ]
    )

    matches = search_text(text, pattern="target", context_lines=1)

    assert len(matches) == 1
    match = matches[0]
    assert match.match_line == 3
    assert match.start_line == 2
    assert match.end_line == 4
    assert "line 2" in match.excerpt
    assert "line 5" not in match.excerpt


def test_render_json_keys_lists_object_keys_at_pointer() -> None:
    payload = {
        "universes": {
            "sporemarch": {
                "notes": [{"id": 1}, {"id": 2}],
                "status": {"active": True},
            }
        }
    }

    rendered = render_json_keys(payload, pointer="/universes/sporemarch")

    assert "notes" in rendered
    assert "status" in rendered


def test_render_json_value_slices_lists() -> None:
    payload = {
        "items": [
            {"id": 1, "name": "one"},
            {"id": 2, "name": "two"},
            {"id": 3, "name": "three"},
        ]
    }

    rendered = render_json_value(payload, pointer="/items", start=1, end=3)
    parsed = json.loads(rendered)

    assert [item["id"] for item in parsed] == [2, 3]


def test_render_json_value_raises_when_result_is_still_too_large() -> None:
    payload = {"items": ["x" * 5000]}

    with pytest.raises(ValueError, match="Result too large"):
        render_json_value(payload, pointer="/items/0", max_chars=100)


def test_run_docview_accepts_max_chars_after_subcommand(tmp_path) -> None:
    path = tmp_path / "sample.md"
    path.write_text("# Title\n\n## Alpha\nBody\n", encoding="utf-8")

    rendered = run_docview(["headings", str(path), "--max-chars", "1000"])

    assert "Alpha" in rendered


def test_write_output_falls_back_when_console_encoding_cannot_render_text() -> None:
    class BrokenTextStream:
        encoding = "cp1252"

        def write(self, text: str) -> int:
            raise UnicodeEncodeError("charmap", text, 0, 1, "boom")

    binary = io.BytesIO()

    write_output("alpha → beta", stream=BrokenTextStream(), binary_stream=binary)

    assert binary.getvalue().decode("cp1252") == "alpha ? beta\n"

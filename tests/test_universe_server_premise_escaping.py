"""Tests for set_premise / read_premise escape-normalization (task #13).

Some MCP clients transmit multi-line strings as JSON string literals,
and the server receives the escape sequences verbatim. This corrupts the
stored PROGRAM.md so later `read_premise` returns literal ``\\n`` in
place of real newlines. The server now normalizes at write time and
provides a read-time fallback for already-corrupted files.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest


@pytest.fixture
def us(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    base = tmp_path / "output"
    base.mkdir()
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(base))
    import workflow.api.universe as module

    importlib.reload(module)
    yield module
    importlib.reload(module)


def _mkuniverse(base: Path, uid: str) -> Path:
    udir = base / uid
    udir.mkdir(parents=True, exist_ok=True)
    return udir


def test_normalize_leaves_already_newlined_text_alone(us):
    already = "Line one\nLine two\nLine three"
    assert us._normalize_escaped_text(already) is already or \
        us._normalize_escaped_text(already) == already


def test_normalize_converts_backslash_n_to_real_newline(us):
    corrupt = "Line one\\nLine two\\nLine three"
    assert us._normalize_escaped_text(corrupt) == "Line one\nLine two\nLine three"


def test_normalize_handles_escaped_crlf_pair(us):
    corrupt = "A\\r\\nB\\r\\nC"
    assert us._normalize_escaped_text(corrupt) == "A\nB\nC"


def test_normalize_decodes_even_with_trailing_newline(us):
    """Real-world case: file was written with literal \\n and has a
    trailing real newline at EOF. Still need to decode because the
    literal \\n sequences are the bug, not the intent."""
    corrupt = "# Title\\n\\nParagraph.\n"
    assert us._normalize_escaped_text(corrupt) == "# Title\n\nParagraph.\n"


def test_normalize_noop_on_empty_string(us):
    assert us._normalize_escaped_text("") == ""


def test_set_premise_normalizes_on_write(us, tmp_path):
    base = Path(us._base_path())
    _mkuniverse(base, "u1")
    corrupt = "# Title\\n\\nParagraph one.\\n\\nParagraph two."

    result = json.loads(us._action_set_premise(universe_id="u1", text=corrupt))
    assert result["status"] == "updated"

    on_disk = (base / "u1" / "PROGRAM.md").read_text(encoding="utf-8")
    assert on_disk == "# Title\n\nParagraph one.\n\nParagraph two."


def test_set_premise_preserves_intentional_newlines(us):
    base = Path(us._base_path())
    _mkuniverse(base, "u1")
    already = "# Title\n\nA normal paragraph.\n\nAnother one."

    us._action_set_premise(universe_id="u1", text=already)
    on_disk = (base / "u1" / "PROGRAM.md").read_text(encoding="utf-8")
    assert on_disk == already


def test_read_premise_decodes_pre_existing_corrupt_file(us):
    """Files written by a buggy client before the fix still render cleanly."""
    base = Path(us._base_path())
    udir = _mkuniverse(base, "corrupt-u")
    (udir / "PROGRAM.md").write_text(
        "# Ashwater Chronicles\\n\\nA dark fantasy.",
        encoding="utf-8",
    )

    result = json.loads(us._action_read_premise(universe_id="corrupt-u"))
    assert result["premise"] == "# Ashwater Chronicles\n\nA dark fantasy."
    assert "\\n" not in result["premise"]


def test_read_premise_passes_through_healthy_file(us):
    base = Path(us._base_path())
    udir = _mkuniverse(base, "healthy-u")
    (udir / "PROGRAM.md").write_text(
        "# Sporemarch\n\nCharacters seed fungal memory.\n",
        encoding="utf-8",
    )

    result = json.loads(us._action_read_premise(universe_id="healthy-u"))
    assert result["premise"] == "# Sporemarch\n\nCharacters seed fungal memory.\n"


def test_read_premise_reports_missing_premise(us):
    base = Path(us._base_path())
    _mkuniverse(base, "empty-u")
    result = json.loads(us._action_read_premise(universe_id="empty-u"))
    assert result["premise"] is None
    assert "no premise set" in result["note"].lower()


def test_create_universe_normalizes_embedded_premise(us):
    from workflow.api.universe import _action_create_universe

    base = Path(us._base_path())
    corrupt = "# New Universe\\n\\nFirst premise line."
    result = json.loads(_action_create_universe(
        universe_id="newverse", text=corrupt,
    ))
    assert result["status"] == "created"
    on_disk = (base / "newverse" / "PROGRAM.md").read_text(encoding="utf-8")
    assert on_disk == "# New Universe\n\nFirst premise line."


def test_create_universe_rejects_confidential_tier_on_legacy_surface(us):
    from workflow.api.universe import _action_create_universe

    base = Path(us._base_path())
    result = json.loads(_action_create_universe(
        universe_id="private-draft",
        text="A public-scope premise.",
        tier="confidential",
    ))

    assert result["status"] == "rejected"
    assert result["error"] == "unsupported_tier"
    assert "get_status" in result["hint"]
    assert not (base / "private-draft").exists()

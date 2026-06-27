"""Tests for the tinyassets.author_server import pre-commit invariant."""
from __future__ import annotations

import pytest

from scripts.pre_commit_invariant_author_server import check_diff

# ── helpers ──────────────────────────────────────────────────────────────────


def _make_diff(added_lines: list[str], filename: str = "tinyassets/foo.py") -> str:
    """Build a minimal unified diff that adds the given lines to filename."""
    lines = [
        f"diff --git a/{filename} b/{filename}",
        f"--- a/{filename}",
        f"+++ b/{filename}",
        f"@@ -1,0 +1,{len(added_lines)} @@",
    ]
    for line in added_lines:
        lines.append(f"+{line}")
    return "\n".join(lines) + "\n"


# ── no-hit cases ─────────────────────────────────────────────────────────────


def test_empty_diff_returns_no_hits():
    assert check_diff("") == []


def test_clean_import_no_hit():
    diff = _make_diff(["from tinyassets.daemon_server import execute_branch"])
    assert check_diff(diff) == []


def test_existing_file_content_not_in_diff_ignored():
    # Context lines (no "+" prefix) are never flagged.
    raw = "\n".join([
        "diff --git a/tinyassets/foo.py b/tinyassets/foo.py",
        "--- a/tinyassets/foo.py",
        "+++ b/tinyassets/foo.py",
        "@@ -1,1 +1,2 @@",
        " from tinyassets.author_server import x",  # context line — NOT new
        "+good_line = 1",
    ]) + "\n"
    assert check_diff(raw) == []


def test_comment_line_not_flagged():
    diff = _make_diff(["# from tinyassets.author_server import old_thing"])
    assert check_diff(diff) == []


def test_non_python_file_ignored():
    diff = _make_diff(
        ["from tinyassets.author_server import x"],
        filename="docs/notes.md",
    )
    assert check_diff(diff) == []


def test_string_literal_not_flagged():
    diff = _make_diff(['msg = "from tinyassets.author_server import x"'])
    assert check_diff(diff) == []


# ── hit cases ────────────────────────────────────────────────────────────────


def test_from_import_flagged():
    diff = _make_diff(["from tinyassets.author_server import foo"])
    hits = check_diff(diff)
    assert len(hits) == 1
    filename, lineno, line = hits[0]
    assert "tinyassets/foo.py" in filename
    assert lineno == 1
    assert "tinyassets.author_server" in line


def test_bare_import_flagged():
    diff = _make_diff(["import tinyassets.author_server"])
    hits = check_diff(diff)
    assert len(hits) == 1
    assert "tinyassets.author_server" in hits[0][2]


def test_indented_deferred_import_flagged():
    diff = _make_diff(["    from tinyassets.author_server import bar"])
    hits = check_diff(diff)
    assert len(hits) == 1


def test_multiple_hits_in_one_diff():
    diff = _make_diff([
        "from tinyassets.author_server import a",
        "x = 1",
        "from tinyassets.author_server import b",
    ])
    hits = check_diff(diff)
    assert len(hits) == 2
    assert hits[0][1] == 1
    assert hits[1][1] == 3


def test_mixed_hits_and_clean_lines():
    diff = _make_diff([
        "from tinyassets.daemon_server import good",
        "from tinyassets.author_server import bad",
        "from tinyassets.daemon_server import also_good",
    ])
    hits = check_diff(diff)
    assert len(hits) == 1
    assert hits[0][1] == 2


def test_line_number_tracking_with_context():
    """Context lines in the diff advance the new-file line counter."""
    raw = "\n".join([
        "diff --git a/tinyassets/bar.py b/tinyassets/bar.py",
        "--- a/tinyassets/bar.py",
        "+++ b/tinyassets/bar.py",
        "@@ -5,1 +5,3 @@",
        " existing_line = 1",         # context line → new lineno advances to 5
        "+from tinyassets.author_server import x",  # new lineno 6
        "+good_line = 2",
    ]) + "\n"
    hits = check_diff(raw)
    assert len(hits) == 1
    assert hits[0][1] == 6  # line 5 (context) advances counter, then +line = 6


def test_returns_correct_shape():
    diff = _make_diff(["from tinyassets.author_server import thing"])
    hits = check_diff(diff)
    assert len(hits) == 1
    filename, lineno, line = hits[0]
    assert isinstance(filename, str)
    assert isinstance(lineno, int)
    assert isinstance(line, str)


# ── edge cases ───────────────────────────────────────────────────────────────


def test_submodule_not_flagged():
    # tinyassets.author_server_utils is NOT the shim — don't over-match.
    diff = _make_diff(["from tinyassets.author_server_utils import helper"])
    assert check_diff(diff) == []


def test_workflow_daemon_server_not_flagged():
    diff = _make_diff(["from tinyassets.daemon_server import execute_branch"])
    assert check_diff(diff) == []


@pytest.mark.parametrize("variant", [
    "from tinyassets.author_server import x",
    "import tinyassets.author_server",
    "    from tinyassets.author_server import (y,)",
])
def test_parametrized_forbidden_forms(variant):
    diff = _make_diff([variant])
    assert len(check_diff(diff)) == 1

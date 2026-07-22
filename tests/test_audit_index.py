"""Tests for scripts/check_audit_index.py.

Each failure mode is exercised on a synthetic tree so the checker is proven to
go RED, not just green — a guard that cannot fail is not a guard.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "check_audit_index.py"


def _load():
    spec = importlib.util.spec_from_file_location("check_audit_index", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


check_audit_index = _load()


def _run(root: Path) -> int:
    argv = sys.argv
    sys.argv = ["check_audit_index.py", "--repo-root", str(root)]
    try:
        return check_audit_index.main()
    finally:
        sys.argv = argv


def _tree(root: Path, audits: dict[str, str], index: str | None) -> Path:
    d = root / "docs" / "audits"
    d.mkdir(parents=True)
    for name, body in audits.items():
        p = d / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    if index is not None:
        (d / "INDEX.md").write_text(index, encoding="utf-8")
    return root


def test_clean_tree_passes(tmp_path):
    _tree(
        tmp_path,
        {"2026-01-01-a.md": "# A", "sub/2026-01-02-b.md": "# B"},
        "# Audits Index\n\n- [`a`](2026-01-01-a.md) — A\n"
        "- [`b`](sub/2026-01-02-b.md) — B\n",
    )
    assert _run(tmp_path) == 0


def test_unindexed_audit_goes_red(tmp_path, capsys):
    """The core case: a new audit lands and nobody adds an index line."""
    _tree(
        tmp_path,
        {"2026-01-01-a.md": "# A", "2026-01-02-orphan.md": "# Orphan"},
        "# Audits Index\n\n- [`a`](2026-01-01-a.md) — A\n",
    )
    assert _run(tmp_path) == 2
    assert "2026-01-02-orphan.md" in capsys.readouterr().err


def test_broken_index_link_goes_red(tmp_path, capsys):
    _tree(
        tmp_path,
        {"2026-01-01-a.md": "# A"},
        "# Audits Index\n\n- [`a`](2026-01-01-a.md) — A\n"
        "- [`gone`](2026-01-09-deleted.md) — was deleted\n",
    )
    assert _run(tmp_path) == 2
    assert "2026-01-09-deleted.md" in capsys.readouterr().err


def test_duplicate_entry_goes_red(tmp_path, capsys):
    _tree(
        tmp_path,
        {"2026-01-01-a.md": "# A"},
        "# Audits Index\n\n- [`a`](2026-01-01-a.md) — A\n"
        "- [`a again`](2026-01-01-a.md) — A\n",
    )
    assert _run(tmp_path) == 2
    assert "2026-01-01-a.md" in capsys.readouterr().err


def test_missing_index_goes_red(tmp_path):
    _tree(tmp_path, {"2026-01-01-a.md": "# A"}, None)
    assert _run(tmp_path) == 2


def test_bare_mention_does_not_count_as_a_link(tmp_path):
    """A filename in prose is a mention, not a link — it must not satisfy the check.

    This is the distinction the 2026-07-22 measurement turned on: the repo cites
    audits as bare code-span paths, which leave them unreachable by navigation.
    """
    _tree(
        tmp_path,
        {"2026-01-01-a.md": "# A"},
        "# Audits Index\n\nSee `2026-01-01-a.md` for details.\n",
    )
    assert _run(tmp_path) == 2


@pytest.mark.skipif(
    not (REPO_ROOT / "docs" / "audits" / "INDEX.md").is_file(),
    reason="docs/audits/INDEX.md not present in this checkout",
)
def test_real_repo_audits_are_fully_indexed():
    assert _run(REPO_ROOT) == 0

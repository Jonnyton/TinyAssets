"""Tests for scripts/check_frontmatter_status.py.

The point of the script is to be a guard that can actually fail — PR #1509
audits ten test groups in this repo that pass even when their code is deleted.
So these tests drive the CLI over purpose-built fixture trees and assert BOTH
directions: a clean tree exits 0, and each individual violation class flips it
to 1. `test_check_goes_red_for_each_violation_class` is the one that matters.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_frontmatter_status.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_frontmatter_status", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cfs = _load_module()


def _write(root: Path, rel: str, text: str) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _clean_tree(root: Path) -> Path:
    """A minimal tree that satisfies every rule."""
    _write(root, "docs/design-notes/2026-01-01-note.md", "---\nstatus: active\n---\n\n# Note\n")
    _write(root, "docs/specs/some-spec.md", "---\nstatus: shipped\n---\n\n# Spec\n")
    return root


# --- frontmatter parsing ------------------------------------------------------


def test_parses_scalar_and_list_fields():
    fields = cfs.parse_frontmatter(
        "---\n"
        "status: superseded\n"
        "superseded_by:\n"
        "  - a.md\n"
        "  - b.md\n"
        "title: Thing\n"
        "---\n\n# Body\n"
    )
    assert fields == {"status": "superseded", "superseded_by": ["a.md", "b.md"], "title": "Thing"}


def test_no_frontmatter_returns_none():
    assert cfs.parse_frontmatter("# Title\n\nstatus: active\n") is None


def test_unterminated_frontmatter_returns_none():
    assert cfs.parse_frontmatter("---\nstatus: active\n\n# Body\n") is None


def test_body_status_line_is_not_frontmatter(tmp_path):
    """The old head-grep measurement counted these; a real parse must not.

    Eleven real docs in this repo have a prose `Status: proposal` line near the
    top and no frontmatter at all — that is what made the earlier count wrong.
    """
    _clean_tree(tmp_path)
    _write(tmp_path, "docs/specs/prose.md", "# Spec\n\nStatus: proposal\n")
    required, _ = cfs.scan(tmp_path)
    specs = next(r for r in required if r.rel == "docs/specs")
    assert [f.path.name for f in specs.problems("no-status")] == ["prose.md"]


def test_status_inside_fenced_block_is_not_frontmatter(tmp_path):
    _clean_tree(tmp_path)
    _write(tmp_path, "docs/specs/fenced.md", "# Spec\n\n```yaml\nstatus: active\n```\n")
    required, _ = cfs.scan(tmp_path)
    specs = next(r for r in required if r.rel == "docs/specs")
    assert [f.path.name for f in specs.problems("no-status")] == ["fenced.md"]


# --- scanning semantics -------------------------------------------------------


def test_index_md_is_excluded_from_the_count(tmp_path):
    _clean_tree(tmp_path)
    _write(tmp_path, "docs/specs/INDEX.md", "# Index\n")
    required, _ = cfs.scan(tmp_path)
    specs = next(r for r in required if r.rel == "docs/specs")
    assert specs.total == 1
    assert cfs.main(["--root", str(tmp_path), "--check"]) == 0


def test_subdirectories_are_not_swept_into_the_parent(tmp_path):
    """`docs/design-notes/*.md` is a top-level glob — `proposed/` is separate."""
    _clean_tree(tmp_path)
    _write(tmp_path, "docs/design-notes/proposed/draft.md", "# Draft, no status\n")
    required, informational = cfs.scan(tmp_path)
    notes = next(r for r in required if r.rel == "docs/design-notes")
    proposed = next(r for r in informational if r.rel == "docs/design-notes/proposed")
    assert notes.total == 1  # the subdirectory file is not counted here
    assert proposed.total == 1
    assert cfs.main(["--root", str(tmp_path), "--check"]) == 0  # informational never gates


def test_informational_violations_do_not_gate(tmp_path):
    _clean_tree(tmp_path)
    _write(tmp_path, "docs/audits/2026-01-01-audit.md", "# Audit with no status\n")
    assert cfs.main(["--root", str(tmp_path), "--check"]) == 0


def test_missing_directory_is_reported_not_crashed(tmp_path):
    result = cfs.scan_dir(tmp_path, "docs/design-notes")
    assert result.exists is False
    assert result.total == 0


# --- the guard can go green ---------------------------------------------------


def test_check_is_green_on_a_clean_tree(tmp_path, capsys):
    _clean_tree(tmp_path)
    assert cfs.main(["--root", str(tmp_path), "--check"]) == 0
    assert "No violations in required directories." in capsys.readouterr().out


def test_superseded_with_resolving_list_is_green(tmp_path):
    _clean_tree(tmp_path)
    _write(tmp_path, "docs/design-notes/a.md", "---\nstatus: active\n---\n")
    _write(tmp_path, "docs/design-notes/b.md", "---\nstatus: active\n---\n")
    _write(
        tmp_path,
        "docs/specs/gone.md",
        "---\nstatus: superseded\nsuperseded_by:\n"
        "  - docs/design-notes/a.md\n  - docs/design-notes/b.md\n---\n",
    )
    assert cfs.main(["--root", str(tmp_path), "--check"]) == 0


@pytest.mark.parametrize("value", cfs.LIFECYCLE_VALUES)
def test_every_documented_lifecycle_value_is_accepted(tmp_path, value):
    body = f"---\nstatus: {value}\n"
    if value == "superseded":
        body += "superseded_by: docs/specs/other.md\n"
    body += "---\n"
    _write(tmp_path, "docs/specs/other.md", "---\nstatus: active\n---\n")
    _write(tmp_path, "docs/specs/doc.md", body)
    assert cfs.main(["--root", str(tmp_path), "--check"]) == 0


# --- the guard can go red -----------------------------------------------------


@pytest.mark.parametrize(
    ("case", "content", "expected_problem"),
    [
        ("no-frontmatter", "# Just a heading\n", "no-status"),
        ("empty-status", "---\nstatus:\n---\n", "no-status"),
        ("undocumented-value", "---\nstatus: proposed\n---\n", "bad-value"),
        ("superseded-no-target", "---\nstatus: superseded\n---\n", "bad-superseded-by"),
        (
            "superseded-dangling",
            "---\nstatus: superseded\nsuperseded_by: docs/specs/nope.md\n---\n",
            "bad-superseded-by",
        ),
        (
            "superseded-dangling-in-list",
            "---\nstatus: superseded\nsuperseded_by:\n"
            "  - docs/specs/ok.md\n  - docs/specs/nope.md\n---\n",
            "bad-superseded-by",
        ),
    ],
)
def test_check_goes_red_for_each_violation_class(tmp_path, case, content, expected_problem):
    """A guard that cannot fail is not a guard. Each class must flip the exit code."""
    _clean_tree(tmp_path)
    _write(tmp_path, "docs/specs/ok.md", "---\nstatus: active\n---\n")
    offender = _write(tmp_path, f"docs/specs/{case}.md", content)

    assert cfs.check_file(offender, tmp_path).problem == expected_problem
    assert cfs.main(["--root", str(tmp_path), "--check"]) == 1, f"{case} should fail --check"


def test_report_mode_stays_green_but_names_the_violation(tmp_path, capsys):
    """Report mode is for the doc's numbers; only --check gates."""
    _clean_tree(tmp_path)
    _write(tmp_path, "docs/specs/broken.md", "# no status\n")

    assert cfs.main(["--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "broken.md" in out
    assert "1 violation(s) in required directories." in out


def test_bad_root_exits_2(tmp_path, capsys):
    assert cfs.main(["--root", str(tmp_path / "nope"), "--check"]) == 2
    assert "not a directory" in capsys.readouterr().err


# --- the real tree ------------------------------------------------------------


def test_real_repo_is_measurable_and_currently_noncompliant():
    """Pins today's reality: the required dirs are NOT clean, and the script says so.

    Deliberately asserts the *shape* (violations exist, counts are plausible) and
    not a hardcoded total — hardcoding the number here would recreate the exact
    rot this script was written to eliminate. When the backlog of undocumented
    files is cleared, this test flips to asserting zero and stays honest either way.
    """
    root = _SCRIPT.resolve().parent.parent
    required, informational = cfs.scan(root)
    by_rel = {r.rel: r for r in required}

    assert set(by_rel) == {"docs/design-notes", "docs/specs"}
    for rel, result in by_rel.items():
        assert result.exists, f"{rel} should exist in the real repo"
        assert result.total > 0
        assert result.with_status <= result.total
    assert all(r.exists for r in informational)

    total_violations = sum(
        len(r.problems(kind)) for r in required for kind, _ in cfs._PROBLEM_LABELS
    )
    assert total_violations > 0, (
        "The required directories are now clean — good. Update this test to assert "
        "zero violations and propose wiring --check into CI."
    )

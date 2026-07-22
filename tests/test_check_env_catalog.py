"""Tests for `scripts/check_env_catalog.py`.

Two jobs. The behavioural tests pin the extractor + the catalog parser against
the real patterns in this codebase. The last two are the ones that matter for
trust: the guard is actually wired to the real repo (`test_repo_catalog_is_complete`)
AND it can actually go red (`test_guard_can_fail`). A guard that only ever passes
is worse than no guard — see `.claude/agent-memory` on floor guards wired to
nothing.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_env_catalog.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_env_catalog", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load_module()


# --------------------------------------------------------------------------
# extractor — direct reads
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "source, expected",
    [
        ('os.environ.get("TINYASSETS_A")', {"TINYASSETS_A"}),
        ('os.environ["TINYASSETS_B"]', {"TINYASSETS_B"}),
        ('os.getenv("TINYASSETS_C")', {"TINYASSETS_C"}),
        ('os.environ.pop("TINYASSETS_D", None)', {"TINYASSETS_D"}),
        ('os.environ.setdefault("TINYASSETS_E", "1")', {"TINYASSETS_E"}),
        # bare `from os import environ, getenv` forms
        ('environ.get("TINYASSETS_F")', {"TINYASSETS_F"}),
        ('getenv("TINYASSETS_G")', {"TINYASSETS_G"}),
    ],
)
def test_direct_reads(source, expected):
    assert mod.extract_from_source(source) == expected


def test_unprefixed_direct_reads_are_caught():
    """Non-TINYASSETS_ names are real config too (GITHUB_TOKEN, SUPABASE_URL)."""
    src = 'token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")'
    assert mod.extract_from_source(src) == {"GITHUB_TOKEN", "GH_TOKEN"}


# --------------------------------------------------------------------------
# extractor — indirect binding (the pattern that hid 67 vars)
# --------------------------------------------------------------------------


def test_module_constant_binding():
    """`_ENABLE_ENV = "TINYASSETS_EXTERNAL_WRITE_ENABLED"` — tinyassets/effectors/github_pr.py."""
    src = '_ENABLE_ENV = "TINYASSETS_EXTERNAL_WRITE_ENABLED"'
    assert "TINYASSETS_EXTERNAL_WRITE_ENABLED" in mod.extract_from_source(src)


def test_dict_value_binding():
    """`{"logs": "TINYASSETS_CAP_LOGS_BYTES"}` — tinyassets/storage/caps.py."""
    src = '_CAP_ENVS = {"logs": "TINYASSETS_CAP_LOGS_BYTES"}'
    assert "TINYASSETS_CAP_LOGS_BYTES" in mod.extract_from_source(src)


def test_env_helper_first_arg():
    """`_int_env("X", default)` — tinyassets/effectors/github_read.py."""
    src = 'max_files = _int_env("GITHUB_READ_MAX_FILES", 20)'
    assert "GITHUB_READ_MAX_FILES" in mod.extract_from_source(src)


# --------------------------------------------------------------------------
# extractor — false positives a naive `grep -oE 'TINYASSETS_[A-Z_]+'` reports
# --------------------------------------------------------------------------


def test_python_identifier_is_not_an_env_var():
    """`_TINYASSETS_ENV_PATH = Path(...)` is a module constant, not an env var.

    A bare grep over the source reports it as an undocumented env var. It is not.
    """
    src = '_TINYASSETS_ENV_PATH = Path("/etc/tinyassets/env")'
    assert mod.extract_from_source(src) == set()


def test_docstring_mention_is_not_a_read():
    """Prose naming a var does not make the module read it.

    A docstring is one big string Constant, so full-literal matching excludes it.
    """
    src = '"""Caps configured via ``TINYASSETS_CAP_CHECKPOINTS_BYTES`` and friends."""'
    assert mod.extract_from_source(src) == set()


def test_superseded_scheme_in_comment_is_not_a_read():
    """github_pr.py documents a *retired* suffix-encoded var family in a comment."""
    src = '# round-1 TINYASSETS_GITHUB_PR_CAPABILITY_REPO_<OWNER>_<REPO> suffix encoding\nx = 1'
    assert mod.extract_from_source(src) == set()


def test_syntax_error_does_not_crash():
    assert mod.extract_from_source("def broken(:\n") == set()


# --------------------------------------------------------------------------
# catalog parser
# --------------------------------------------------------------------------


def test_only_first_cell_counts_as_documented(tmp_path):
    """A var must have its own row; a cross-reference in a purpose cell doesn't count.

    This is the stricter rule that caught `CODEX_HOME` — mentioned inside another
    var's purpose text, so it looked documented while carrying no purpose+default
    of its own.
    """
    catalog = tmp_path / "catalog.md"
    catalog.write_text(
        "| Var | Purpose | Default |\n"
        "|-----|---------|---------|\n"
        "| `TINYASSETS_REAL` | Cross-refs `TINYASSETS_MENTIONED_ONLY` here. | `1`. |\n",
        encoding="utf-8",
    )
    documented = mod.scan_catalog(catalog)
    assert "TINYASSETS_REAL" in documented
    assert "TINYASSETS_MENTIONED_ONLY" not in documented


def test_multi_var_row_documents_every_name(tmp_path):
    """`| `GITHUB_TOKEN` / `GH_TOKEN` |` documents both."""
    catalog = tmp_path / "catalog.md"
    catalog.write_text(
        "| `GITHUB_TOKEN` / `GH_TOKEN` | Bearer token. | Unset. |\n", encoding="utf-8"
    )
    assert mod.scan_catalog(catalog) == {"GITHUB_TOKEN", "GH_TOKEN"}


def test_prose_backticks_are_not_entries(tmp_path):
    """The catalog backticks Python identifiers in prose; those aren't vars."""
    catalog = tmp_path / "catalog.md"
    catalog.write_text(
        "Soft cap fires at `SOFT_RATIO` (0.80) of the hard cap.\n", encoding="utf-8"
    )
    assert mod.scan_catalog(catalog) == set()


# --------------------------------------------------------------------------
# the guard, end to end
# --------------------------------------------------------------------------


def test_repo_catalog_is_complete():
    """The real repo passes. This is what makes the guard non-vacuous."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "docs/reference/environment-variables.md is missing env vars the daemon "
        f"reads:\n{result.stdout}\n{result.stderr}"
    )


def test_guard_can_fail(tmp_path):
    """Prove red is reachable: drop a real entry, expect exit 2 naming that var.

    Without this, a checker that silently matched everything would still pass
    `test_repo_catalog_is_complete` and look like working coverage.
    """
    catalog = REPO_ROOT / "docs" / "reference" / "environment-variables.md"
    original = catalog.read_text(encoding="utf-8")
    trimmed = "\n".join(
        line
        for line in original.splitlines()
        if not line.startswith("| `TINYASSETS_EXTERNAL_WRITE_ENABLED`")
    )
    assert trimmed != original, "expected a TINYASSETS_EXTERNAL_WRITE_ENABLED row to drop"

    # Write to a temp copy rather than mutating the repo file — a crashing test
    # must not leave the catalog truncated.
    damaged = tmp_path / "environment-variables.md"
    damaged.write_text(trimmed, encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--catalog", str(damaged)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    assert "TINYASSETS_EXTERNAL_WRITE_ENABLED" in result.stderr


def test_missing_catalog_exits_3(tmp_path):
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--catalog", str(tmp_path / "nope.md")],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 3

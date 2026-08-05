"""Tests for scripts/pre_commit_invariant_worker.py.

Covers:
  (a) check() passes when both required reads are present
  (b) check() fails when one or both required reads are absent
  (c) main() with explicit path: passes/fails correctly
  (d) main() with no args + not staged: no-op (exit 0)
  (e) main() with no args + staged but content missing: exit 1
  (f) main() with no args + staged and content present: exit 0
  (g) pre-commit hook source-of-truth contains the invariant section
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import pre_commit_invariant_worker as inv  # noqa: E402

_REPO = Path(__file__).resolve().parent.parent
_WORKER = _REPO / "deploy" / "cloudflare-worker" / "worker.js"
_HOOK_SOURCE = _REPO / "scripts" / "git-hooks" / "pre-commit"

# ---------------------------------------------------------------------------
# (a) check() passes when both required reads are present
# ---------------------------------------------------------------------------

FULL_CONTENT = """
export default {
  async fetch(request, env) {
    const clientId = env.CF_ACCESS_CLIENT_ID;
    const clientSecret = env.CF_ACCESS_CLIENT_SECRET;
    return new Response('ok');
  }
}
"""

MISSING_ONE = """
export default {
  async fetch(request, env) {
    const clientId = env.CF_ACCESS_CLIENT_ID;
    return new Response('ok');
  }
}
"""

MISSING_BOTH = """
export default {
  async fetch(request, env) {
    return new Response('ok');
  }
}
"""


def test_check_passes_when_both_present():
    assert inv.check(FULL_CONTENT) == []


def test_check_fails_missing_secret():
    missing = inv.check(MISSING_ONE)
    assert missing == ["env.CF_ACCESS_CLIENT_SECRET"]


def test_check_fails_missing_both():
    missing = inv.check(MISSING_BOTH)
    assert set(missing) == {"env.CF_ACCESS_CLIENT_ID", "env.CF_ACCESS_CLIENT_SECRET"}


def test_check_fails_on_empty_content():
    missing = inv.check("")
    assert len(missing) == 2


# ---------------------------------------------------------------------------
# (b) Partial presence: only ID present
# ---------------------------------------------------------------------------

def test_check_fails_missing_id_only():
    content = "env.CF_ACCESS_CLIENT_SECRET present but not id"
    missing = inv.check(content)
    assert "env.CF_ACCESS_CLIENT_ID" in missing
    assert "env.CF_ACCESS_CLIENT_SECRET" not in missing


# ---------------------------------------------------------------------------
# (c) main() with explicit path
# ---------------------------------------------------------------------------


def test_main_explicit_path_passes(tmp_path):
    worker = tmp_path / "worker.js"
    worker.write_text(FULL_CONTENT, encoding="utf-8")
    assert inv.main([str(worker)]) == 0


def test_main_explicit_path_fails_missing_both(tmp_path):
    worker = tmp_path / "worker.js"
    worker.write_text(MISSING_BOTH, encoding="utf-8")
    assert inv.main([str(worker)]) == 2


def test_main_explicit_path_fails_missing_one(tmp_path):
    worker = tmp_path / "worker.js"
    worker.write_text(MISSING_ONE, encoding="utf-8")
    assert inv.main([str(worker)]) == 2


def test_main_explicit_path_nonexistent(tmp_path):
    """Non-existent explicit path → skip (exit 0)."""
    assert inv.main([str(tmp_path / "does-not-exist.js")]) == 0


# ---------------------------------------------------------------------------
# (d) main() no args + worker.js NOT staged → no-op
# ---------------------------------------------------------------------------


def test_main_no_args_not_staged():
    with patch.object(inv, "_is_worker_staged", return_value=False):
        assert inv.main([]) == 0


# ---------------------------------------------------------------------------
# (e) main() no args + staged + content missing → exit 1
# ---------------------------------------------------------------------------


def test_main_no_args_staged_missing_both():
    with (
        patch.object(inv, "_is_worker_staged", return_value=True),
        patch.object(inv, "_get_staged_content", return_value=MISSING_BOTH),
    ):
        assert inv.main([]) == 2


def test_main_no_args_staged_missing_one():
    with (
        patch.object(inv, "_is_worker_staged", return_value=True),
        patch.object(inv, "_get_staged_content", return_value=MISSING_ONE),
    ):
        assert inv.main([]) == 2


# ---------------------------------------------------------------------------
# (f) main() no args + staged + content present → exit 0
# ---------------------------------------------------------------------------


def test_main_no_args_staged_passes():
    with (
        patch.object(inv, "_is_worker_staged", return_value=True),
        patch.object(inv, "_get_staged_content", return_value=FULL_CONTENT),
    ):
        assert inv.main([]) == 0


def test_main_no_args_staged_but_get_returns_none(capsys):
    """Staged with unreadable content is a VIOLATION, not a skip.

    Reversed from what this test used to assert. Staged-but-unreadable is what
    a deletion or rename of the Worker looks like, and the Worker owns the
    tinyassets.io/mcp route — letting that through silently is exactly the
    change nobody would notice until the public endpoint was gone. The hook now
    exits 2 and says so (pre_commit_invariant_worker.py:98).

    The old expectation of 0 treated the most dangerous case as the benign one,
    so the test is rewritten to the current contract rather than the guard being
    softened back.
    """
    with (
        patch.object(inv, "_is_worker_staged", return_value=True),
        patch.object(inv, "_get_staged_content", return_value=None),
    ):
        assert inv.main([]) == 2
    # The exit code alone is not actionable — the operator has to be told why.
    err = capsys.readouterr().err
    assert "INVARIANT VIOLATED" in err, err


# ---------------------------------------------------------------------------
# (g) Pre-commit hook source-of-truth contains the invariant
# ---------------------------------------------------------------------------


def test_hook_source_contains_invariant_section():
    """scripts/git-hooks/pre-commit must reference pre_commit_invariant_worker."""
    text = _HOOK_SOURCE.read_text(encoding="utf-8")
    assert "pre_commit_invariant_worker" in text


def test_hook_source_covers_worker_js_path():
    text = _HOOK_SOURCE.read_text(encoding="utf-8")
    assert "deploy/cloudflare-worker/worker.js" in text


# ---------------------------------------------------------------------------
# Integration: real worker.js passes the invariant
# ---------------------------------------------------------------------------


def test_real_worker_js_passes_invariant():
    """The live worker.js in the repo must satisfy the invariant."""
    if not _WORKER.is_file():
        pytest.skip("worker.js not present in repo")
    content = _WORKER.read_text(encoding="utf-8")
    missing = inv.check(content)
    assert missing == [], (
        f"worker.js is missing CF Access reads: {missing}. "
        "This means the deployed Worker will break when the Access gate is live."
    )

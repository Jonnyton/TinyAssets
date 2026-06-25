"""Guardrail tests for scripts/branch_janitor.py classification logic."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "branch_janitor", Path(__file__).resolve().parent.parent / "scripts" / "branch_janitor.py"
)
bj = importlib.util.module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
sys.modules["branch_janitor"] = bj
_SPEC.loader.exec_module(bj)

NOW = 1_700_000_000


def _age_ts(days: int) -> int:
    return NOW - days * 86400


@pytest.fixture
def patched(monkeypatch):
    """Inject a fixed branch set + merged-membership without touching git."""

    def _setup(branches, merged):
        monkeypatch.setattr(bj, "remote_branches", lambda remote, now: list(branches))
        monkeypatch.setattr(bj, "is_merged", lambda remote, name, base: name in merged)

    return _setup


def _verdict_for(verdicts, name):
    return next(v for v in verdicts if v.name == name)


def test_protected_branches_never_touched(patched):
    patched([("main", _age_ts(400)), ("release/1.2", _age_ts(400))], merged=set())
    out = bj.classify("origin", "origin/main", NOW, open_prs=set())
    assert _verdict_for(out, "main").category == "PROTECTED"
    assert _verdict_for(out, "release/1.2").category == "PROTECTED"


def test_merged_branch_is_sweepable(patched):
    patched([("feature/x", _age_ts(2))], merged={"feature/x"})
    out = bj.classify("origin", "origin/main", NOW, open_prs=set())
    assert _verdict_for(out, "feature/x").category == "MERGED"


def test_open_pr_protects_unmerged_stale_branch(patched):
    patched([("feature/live", _age_ts(120))], merged=set())
    out = bj.classify("origin", "origin/main", NOW, open_prs={"feature/live"})
    assert _verdict_for(out, "feature/live").category == "ACTIVE"


def test_recent_commit_never_deleted(patched):
    patched([("feature/fresh", _age_ts(3))], merged=set())
    out = bj.classify("origin", "origin/main", NOW, open_prs=set())
    assert _verdict_for(out, "feature/fresh").category == "ACTIVE"


def test_stale_unmerged_flagged_not_deleted(patched):
    patched([("feature/stale", _age_ts(35))], merged=set())
    out = bj.classify("origin", "origin/main", NOW, open_prs=set())
    assert _verdict_for(out, "feature/stale").category == "STALE_FLAG"


def test_past_grace_is_delete_candidate(patched):
    patched([("feature/old", _age_ts(60))], merged=set())
    out = bj.classify("origin", "origin/main", NOW, open_prs=set())
    assert _verdict_for(out, "feature/old").category == "STALE_DELETE"


def test_pr_lookup_failure_disables_unmerged_deletion(patched):
    patched([("feature/old", _age_ts(60))], merged=set())
    out = bj.classify("origin", "origin/main", NOW, open_prs=None)
    # No open-PR data => must not escalate to STALE_DELETE.
    assert _verdict_for(out, "feature/old").category == "STALE_FLAG"


def test_merged_takes_priority_over_protected_order(patched):
    # A merged, non-protected branch with old age still classifies MERGED.
    patched([("chore/done", _age_ts(200))], merged={"chore/done"})
    out = bj.classify("origin", "origin/main", NOW, open_prs=set())
    assert _verdict_for(out, "chore/done").category == "MERGED"

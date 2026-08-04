"""Guards for `scripts/pr_sync_behind.py`.

The script exists because branch protection's `strict: true` leaves PRs
BEHIND and GitHub's auto-merge does not update them. The risks worth pinning
are all about it doing MORE than asked: syncing a PR that a re-sync cannot
help, updating without being told to, or truncating a backlog silently.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "pr_sync_behind.py"


def _load():
    spec = importlib.util.spec_from_file_location("pr_sync_behind", _SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod():
    return _load()


def _pr(number, state, *, draft=False, auto=True):
    return {
        "number": number,
        "title": f"pr-{number}",
        "mergeStateStatus": state,
        "autoMergeRequest": {"enabledAt": "x"} if auto else None,
        "isDraft": draft,
        "author": {"login": "someone"},
        "headRefName": f"branch-{number}",
    }


def test_only_behind_is_syncable(mod):
    """BLOCKED/DIRTY/UNKNOWN must not be swept in.

    A re-sync fixes none of them: BLOCKED needs a failing check fixed, DIRTY
    needs a conflict resolved, UNKNOWN is a transient mid-computation state.
    Updating them burns a CI cycle each and changes nothing.
    """
    assert mod._SYNCABLE == {"BEHIND"}
    for state in ("BLOCKED", "DIRTY", "UNKNOWN", "CLEAN", "UNSTABLE"):
        assert state not in mod._SYNCABLE, state


def test_report_only_by_default(mod, monkeypatch, capsys):
    """Without --update the script must not call update-branch at all."""
    monkeypatch.setattr(mod, "_open_prs", lambda mine: [_pr(1, "BEHIND")])

    def _boom(number):  # pragma: no cover - must never run
        raise AssertionError("update-branch called without --update")

    monkeypatch.setattr(mod, "_update", _boom)
    monkeypatch.setattr(sys, "argv", ["pr_sync_behind.py"])

    assert mod.main() == 0
    assert "report only" in capsys.readouterr().out


def test_update_skips_drafts_and_non_behind(mod, monkeypatch, capsys):
    prs = [
        _pr(1, "BEHIND"),
        _pr(2, "BEHIND", draft=True),   # draft: not finished
        _pr(3, "BLOCKED"),              # a re-sync cannot help
        _pr(4, "CLEAN"),                # already fine
    ]
    monkeypatch.setattr(mod, "_open_prs", lambda mine: prs)
    called: list[int] = []
    monkeypatch.setattr(mod, "_update", lambda n: (called.append(n), (True, "updated"))[1])
    monkeypatch.setattr(sys, "argv", ["pr_sync_behind.py", "--update"])

    assert mod.main() == 0
    assert called == [1], called


def test_cap_is_both_enforced_and_announced(mod, monkeypatch, capsys):
    """The cap must actually LIMIT the run, and say what it dropped.

    Both halves are asserted because they fail independently. An earlier
    version of this test checked only the announcement, and a mutation that
    removed the slice (`todo = behind`) left it green: every PR was updated
    while the output still claimed a cap. Silent truncation hides a backlog;
    an unenforced cap floods CI. Neither is caught by the other's assertion.
    """
    monkeypatch.setattr(mod, "_open_prs", lambda mine: [_pr(i, "BEHIND") for i in range(5)])
    called: list[int] = []
    monkeypatch.setattr(mod, "_update", lambda n: (called.append(n), (True, "updated"))[1])
    monkeypatch.setattr(sys, "argv", ["pr_sync_behind.py", "--update", "--limit", "2"])

    assert mod.main() == 0
    assert len(called) == 2, f"cap not enforced — updated {len(called)} PRs"
    out = capsys.readouterr().out
    assert "capped at 2" in out
    assert "3 left" in out


def test_failure_is_reported_via_exit_code(mod, monkeypatch):
    """A conflict must not read as success — hard rule 8, fail loudly."""
    monkeypatch.setattr(mod, "_open_prs", lambda mine: [_pr(1, "BEHIND")])
    monkeypatch.setattr(mod, "_update", lambda n: (False, "conflict — resolve by hand"))
    monkeypatch.setattr(sys, "argv", ["pr_sync_behind.py", "--update"])

    assert mod.main() == 1


def test_never_checks_anything_out(mod):
    """Hard rule 13: the script must not mutate a working tree.

    It updates through the GitHub API, so it must never shell out to a git
    command that could disturb a dirty checkout.
    """
    source = _SCRIPT.read_text("utf-8")
    for forbidden in ("git checkout", "git switch", "git reset",
                      "git stash", "git clean", "git restore"):
        assert forbidden not in source, forbidden

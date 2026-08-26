"""Tests for the Hard Rule 14 gate: is this commit actually in production?

No network. `live_release_state` is the only part that talks to the live
surface, so every test stubs it and exercises the logic that decides SHIPPED /
NOT SHIPPED / UNKNOWN.

The distinction these tests exist to protect: **"I could not tell" must never
read as "yes, it shipped."** That is exit 2, not exit 0.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load():
    path = REPO_ROOT / "scripts" / "deployed_sha.py"
    spec = importlib.util.spec_from_file_location("deployed_sha_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _head() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()


def _parent() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD~1"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=True,
    ).stdout.strip()


def stub(mod, monkeypatch, release_state):
    monkeypatch.setattr(mod, "live_release_state", lambda url, timeout: release_state)


def test_deployed_head_contains_its_own_parent(monkeypatch):
    """The ordinary pass: production is ahead of the commit being claimed."""
    mod = load()
    stub(mod, monkeypatch, {"git_sha": _head()})

    assert mod.main(["--assert-contains", _parent()]) == 0


def test_deployed_parent_does_not_contain_head(monkeypatch):
    """The 2026-07-21 case: merged, but production is serving something older."""
    mod = load()
    stub(mod, monkeypatch, {"git_sha": _parent()})

    assert mod.main(["--assert-contains", _head()]) == 1


def test_commit_equal_to_deployed_counts_as_shipped(monkeypatch):
    mod = load()
    head = _head()
    stub(mod, monkeypatch, {"git_sha": head})

    assert mod.main(["--assert-contains", head]) == 0


def test_missing_release_state_is_unknown_not_shipped(monkeypatch):
    """Exit 2, never 0. A probe that cannot answer must not read as a pass."""
    mod = load()

    def boom(url, timeout):
        raise mod.DeployedShaError("get_status carries no release_state object")

    monkeypatch.setattr(mod, "live_release_state", boom)

    assert mod.main(["--assert-contains", _head()]) == 2


def test_empty_git_sha_is_unknown_not_shipped(monkeypatch):
    mod = load()
    stub(mod, monkeypatch, {"git_sha": "   "})

    assert mod.main(["--assert-contains", _head()]) == 2


def test_unfetched_deployed_sha_is_unknown_not_shipped(monkeypatch):
    """Production serving a commit this checkout lacks is UNKNOWN, not a fail.

    Reporting 1 here would say "not shipped" about a build that may well
    contain the commit; the honest answer is "fetch it, then re-run".
    """
    mod = load()
    stub(mod, monkeypatch, {"git_sha": "0" * 40})

    assert mod.main(["--assert-contains", _head()]) == 2


def test_plain_report_succeeds_without_assertion(monkeypatch):
    mod = load()
    stub(mod, monkeypatch, {"git_sha": _head()})

    assert mod.main([]) == 0


def test_report_counts_commits_not_yet_deployed(monkeypatch):
    mod = load()
    stub(mod, monkeypatch, {"git_sha": _parent()})

    info = mod.report("https://example.invalid/mcp", 1.0)

    assert info["deployed_sha"] == _parent()
    assert info["known_to_git"] is True
    assert info["deployed_subject"]


@pytest.mark.parametrize("bad", [{}, {"git_sha": None}, {"git_sha": ""}])
def test_unusable_release_state_shapes_all_raise(monkeypatch, bad):
    mod = load()
    stub(mod, monkeypatch, bad)

    with pytest.raises(mod.DeployedShaError):
        mod.report("https://example.invalid/mcp", 1.0)


def test_receipt_disagreeing_with_itself_is_unknown(monkeypatch):
    """git_sha vs image_tag mismatch is exit 2, never a pass.

    Agreement does not prove the running binary (see the module docstring and
    docs/concerns/2026-08-26-deployed-sha-proves-receipt-only.md). DISagreement
    does prove the receipt is untrustworthy, and an untrustworthy receipt must
    never read as shipped.
    """
    mod = load()
    stub(mod, monkeypatch, {
        "git_sha": _head(),
        "image_tag": "ghcr.io/jonnyton/tinyassets-daemon:deadbeefcafe",
    })

    assert mod.main(["--assert-contains", _head()]) == 2


def test_agreeing_receipt_still_passes(monkeypatch):
    mod = load()
    head = _head()
    stub(mod, monkeypatch, {
        "git_sha": head,
        "image_tag": f"ghcr.io/jonnyton/tinyassets-daemon:{head[:12]}",
    })

    assert mod.main(["--assert-contains", head]) == 0


def test_report_labels_what_it_actually_proves(monkeypatch):
    """The tool must not let a caller mistake a receipt for the running binary."""
    mod = load()
    stub(mod, monkeypatch, {"git_sha": _head()})

    assert mod.report("https://example.invalid/mcp", 1.0)["proves"] == "receipt"

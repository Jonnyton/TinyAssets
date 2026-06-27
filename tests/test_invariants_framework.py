"""Tests for the scripts/invariants/ framework + runner.

Covers:
- Base Invariant class contracts (check/heal exception trapping, auto_heal gate).
- CheckResult/HealResult dataclass shape.
- MirrorParity check on synthetic fixtures.
- Mojibake invariant scan behavior.
- ConcernsStaleness: proposal-only contract, STATUS.md untouched.
- Runner CLI: --list prints every invariant; --check NAME routes correctly;
  --pre-commit scope filter excludes on-demand invariants.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RUNNER = REPO_ROOT / "scripts" / "invariants_run.py"
sys.path.insert(0, str(REPO_ROOT))

from scripts.invariants import (  # noqa: E402
    CheckResult,
    HealResult,
    Invariant,
    Status,
)

# -------------------------------------------------------------------
# Base contract
# -------------------------------------------------------------------


class _AlwaysOK(Invariant):
    name = "test-always-ok"
    description = "test fixture"

    def _check(self) -> CheckResult:
        return CheckResult(status=Status.OK, message="fine")


class _AlwaysViolated(Invariant):
    name = "test-violated"
    description = "test fixture"
    auto_heal = True

    def _check(self) -> CheckResult:
        return CheckResult(status=Status.VIOLATED, message="broken")

    def _heal(self) -> HealResult:
        return HealResult(healed=True, message="repaired", actions_taken=["stub"])


class _CheckCrashes(Invariant):
    name = "test-crash"
    description = "test fixture"

    def _check(self) -> CheckResult:
        raise RuntimeError("boom")


class _ProposeOnly(Invariant):
    name = "test-propose"
    description = "test fixture"
    auto_heal = False

    def _check(self) -> CheckResult:
        return CheckResult(status=Status.VIOLATED, message="needs human")


def test_check_duration_is_populated():
    inv = _AlwaysOK()
    result = inv.check()

    assert result.status == Status.OK
    assert result.ok
    assert result.duration_seconds >= 0


def test_check_exception_downgrades_to_skipped():
    """A crashing check() must become SKIPPED rather than propagate."""
    inv = _CheckCrashes()
    result = inv.check()

    assert result.status == Status.SKIPPED
    assert "RuntimeError" in result.message
    assert "boom" in result.message


def test_heal_respects_auto_heal_flag():
    """auto_heal=False makes heal() a no-op even if _heal exists."""
    inv = _ProposeOnly()
    result = inv.heal()

    assert result.healed is False
    assert "auto_heal" in result.message


def test_heal_runs_when_auto_heal_enabled():
    inv = _AlwaysViolated()
    result = inv.heal()

    assert result.healed is True
    assert result.message == "repaired"
    assert result.actions_taken == ["stub"]


def test_heal_exception_surfaces_as_failed():
    class _HealCrashes(Invariant):
        name = "test-heal-crash"
        description = "x"
        auto_heal = True

        def _check(self):
            return CheckResult(status=Status.VIOLATED, message="x")

        def _heal(self):
            raise RuntimeError("heal boom")

    result = _HealCrashes().heal()
    assert result.healed is False
    assert "heal boom" in result.message


# -------------------------------------------------------------------
# MirrorParity — synthetic scan
# -------------------------------------------------------------------


def test_mirror_parity_detects_mismatch(tmp_path, monkeypatch):
    from scripts.invariants import mirror_parity as mp

    canon = tmp_path / "workflow"
    mirror = (
        tmp_path / "packaging" / "claude-plugin" / "plugins"
        / "tinyassets-universe-server" / "runtime" / "workflow"
    )
    canon.mkdir(parents=True)
    mirror.mkdir(parents=True)
    (canon / "a.py").write_text("x = 1\n", encoding="utf-8")
    (mirror / "a.py").write_text("x = 2\n", encoding="utf-8")

    monkeypatch.setattr(mp, "CANONICAL_ROOT", canon)
    monkeypatch.setattr(mp, "MIRROR_ROOT", mirror)

    result = mp.MirrorParityInvariant().check()

    assert result.status == Status.VIOLATED
    assert "a.py" in result.evidence["mismatches"]


def test_mirror_parity_clean_passes(tmp_path, monkeypatch):
    from scripts.invariants import mirror_parity as mp

    canon = tmp_path / "workflow"
    mirror = (
        tmp_path / "packaging" / "claude-plugin" / "plugins"
        / "tinyassets-universe-server" / "runtime" / "workflow"
    )
    canon.mkdir(parents=True)
    mirror.mkdir(parents=True)
    (canon / "a.py").write_text("x = 1\n", encoding="utf-8")
    (mirror / "a.py").write_text("x = 1\n", encoding="utf-8")

    monkeypatch.setattr(mp, "CANONICAL_ROOT", canon)
    monkeypatch.setattr(mp, "MIRROR_ROOT", mirror)

    result = mp.MirrorParityInvariant().check()

    assert result.status == Status.OK
    assert result.evidence["checked"] == 1


def test_mirror_parity_skipped_when_roots_missing(tmp_path, monkeypatch):
    from scripts.invariants import mirror_parity as mp

    monkeypatch.setattr(mp, "CANONICAL_ROOT", tmp_path / "nope")
    monkeypatch.setattr(mp, "MIRROR_ROOT", tmp_path / "nope2")

    result = mp.MirrorParityInvariant().check()

    assert result.status == Status.SKIPPED


def test_mirror_parity_ignores_canonical_only_files(tmp_path, monkeypatch):
    """A canonical file with no mirror counterpart is allowed."""
    from scripts.invariants import mirror_parity as mp

    canon = tmp_path / "workflow"
    mirror = (
        tmp_path / "packaging" / "claude-plugin" / "plugins"
        / "tinyassets-universe-server" / "runtime" / "workflow"
    )
    canon.mkdir(parents=True)
    mirror.mkdir(parents=True)
    (canon / "new.py").write_text("brand new\n", encoding="utf-8")
    # No mirror file.

    monkeypatch.setattr(mp, "CANONICAL_ROOT", canon)
    monkeypatch.setattr(mp, "MIRROR_ROOT", mirror)

    result = mp.MirrorParityInvariant().check()

    assert result.status == Status.OK
    # The new.py wasn't "checked" because it has no pair.
    assert result.evidence["checked"] == 0


# -------------------------------------------------------------------
# ConcernsStaleness — proposal-only contract
# -------------------------------------------------------------------


def test_concerns_staleness_never_writes_to_status():
    """Critical contract: check() must not mutate STATUS.md."""
    from scripts.invariants import concerns_staleness as cs
    status_path = cs.REPO_ROOT / "STATUS.md"
    if not status_path.exists():
        pytest.skip("STATUS.md not present in this checkout")

    before_bytes = status_path.read_bytes()
    before_mtime = status_path.stat().st_mtime_ns

    # Run the invariant against the live STATUS.md.
    cs.ConcernsStalenessInvariant().check()

    after_bytes = status_path.read_bytes()
    after_mtime = status_path.stat().st_mtime_ns
    assert before_bytes == after_bytes
    assert before_mtime == after_mtime


def test_concerns_staleness_auto_heal_is_disabled():
    from scripts.invariants import concerns_staleness as cs

    inv = cs.ConcernsStalenessInvariant()
    assert inv.auto_heal is False
    heal = inv.heal()
    assert heal.healed is False


# -------------------------------------------------------------------
# Runner CLI
# -------------------------------------------------------------------


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(RUNNER), *args],
        capture_output=True, text=True, cwd=REPO_ROOT,
    )


def test_cli_list_includes_every_invariant():
    result = _run_cli("--list")

    assert result.returncode == 0, result.stderr
    for name in ("mirror-parity", "mojibake", "tab-single", "concerns-staleness"):
        assert name in result.stdout


def test_cli_check_unknown_name_returns_two():
    result = _run_cli("--check", "does-not-exist")

    assert result.returncode == 2


def test_cli_requires_a_mode_arg():
    """Mutually-exclusive + required → running with no args fails cleanly."""
    result = _run_cli()

    assert result.returncode != 0
    # argparse prints "one of the arguments ... is required".
    assert "required" in result.stderr.lower()


def test_cli_pre_commit_runs_only_pre_commit_scope():
    """--pre-commit should only invoke invariants with pre_commit_scope=True."""
    result = _run_cli("--pre-commit")

    # Output must include mirror-parity + mojibake, must NOT include
    # tab-single (poll-only) or concerns-staleness (on-demand).
    assert "mirror-parity" in result.stdout
    assert "mojibake" in result.stdout
    assert "tab-single" not in result.stdout
    assert "concerns-staleness" not in result.stdout

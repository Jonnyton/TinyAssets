"""The always-loaded context-budget guard must actually be able to fail.

Context (2026-07-22): `scripts/check_context_budget.py` correctly detected that
STATUS.md was 7485 bytes against its own declared 4096-byte ceiling, printed
`OVER-HARD`, and exited 0. Nothing passed `--strict`, no CI workflow ran it, and
so a guard written specifically to stop always-loaded-context drift had never
once been able to fail anything.

These tests are the executable half of the fix. They pin BOTH exit semantics:

  ABSOLUTE  `--strict`                    -> 2 on any HARD breach.
  RATCHET   `--strict --baseline <json>`  -> 2 only when this change makes a HARD
                                             budget NEW or WORSE; pre-existing
                                             debt is waived.

Every "should fail" case below asserts a non-zero exit. A guard nobody has
watched go red is not a guard — that is the defect being fixed here, so the
red paths are tested as carefully as the green ones.

Note the deliberate distinction from `tests/test_context_budget_regression.py`,
which guards the *runtime* CoreMemory token budget (BUG-024). This file guards
the *instruction-file* budget. Same word, different subsystem.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from scripts import check_context_budget as ccb

# Ceilings come from the module under test so these stay correct if CONFIG moves.
STATUS_BUDGET = next(b for b in ccb.CONFIG if b.path == "STATUS.md")
assert STATUS_BUDGET.kind == "hard", "STATUS.md must stay the HARD-class file"


def _write_tree(root: Path, *, status_bytes: int, agents_bytes: int = 100,
                claude_bytes: int = 100) -> Path:
    """Build a fake always-loaded set with exact byte sizes."""
    root.mkdir(parents=True, exist_ok=True)
    # One line each, padded to the requested size, so `lines` stays predictable.
    (root / "STATUS.md").write_bytes(b"s" * (status_bytes - 1) + b"\n")
    (root / "AGENTS.md").write_bytes(b"a" * (agents_bytes - 1) + b"\n")
    (root / "CLAUDE.md").write_bytes(b"c" * (claude_bytes - 1) + b"\n")
    return root


def _snapshot(root: Path, dest: Path, capsys) -> Path:
    """Run --json against `root` and persist it as a baseline file."""
    assert ccb.main(["--json", "--root", str(root)]) == 0
    dest.write_text(capsys.readouterr().out, encoding="utf-8")
    return dest


UNDER = STATUS_BUDGET.max_bytes - 500
OVER = STATUS_BUDGET.max_bytes + 500
FAR_OVER = STATUS_BUDGET.max_bytes + 3000


class TestAbsoluteStrict:
    """`--strict` with no baseline keeps its original absolute contract."""

    def test_over_hard_budget_exits_2(self, tmp_path, capsys):
        root = _write_tree(tmp_path / "over", status_bytes=OVER)
        assert ccb.main(["--strict", "--root", str(root)]) == 2

    def test_within_budget_exits_0(self, tmp_path, capsys):
        root = _write_tree(tmp_path / "ok", status_bytes=UNDER)
        assert ccb.main(["--strict", "--root", str(root)]) == 0

    def test_without_strict_still_exits_0_but_reports(self, tmp_path, capsys):
        """The pre-fix behaviour, pinned deliberately.

        Plain runs stay advisory so humans can eyeball the table; the point of
        the fix is that a *gate* now exists, not that every invocation fails.
        """
        root = _write_tree(tmp_path / "over", status_bytes=OVER)
        assert ccb.main(["--root", str(root)]) == 0
        assert "OVER-HARD" in capsys.readouterr().out


class TestRatchet:
    """`--strict --baseline` fails only on new or worsened HARD breaches."""

    def test_preexisting_breach_unchanged_is_waived(self, tmp_path, capsys):
        """The case that made an absolute gate unlandable: STATUS.md is already
        over budget and 16 open PRs touch it. Not touching it must be green."""
        base = _write_tree(tmp_path / "base", status_bytes=OVER)
        baseline = _snapshot(base, tmp_path / "baseline.json", capsys)
        head = _write_tree(tmp_path / "head", status_bytes=OVER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 0
        assert "waived-preexisting" in capsys.readouterr().out

    def test_growing_an_already_over_file_fails(self, tmp_path, capsys):
        base = _write_tree(tmp_path / "base", status_bytes=OVER)
        baseline = _snapshot(base, tmp_path / "baseline.json", capsys)
        head = _write_tree(tmp_path / "head", status_bytes=OVER + 1)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 2
        assert "REGRESSED-worse" in capsys.readouterr().out

    def test_crossing_the_ceiling_fails(self, tmp_path, capsys):
        base = _write_tree(tmp_path / "base", status_bytes=UNDER)
        baseline = _snapshot(base, tmp_path / "baseline.json", capsys)
        head = _write_tree(tmp_path / "head", status_bytes=OVER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 2
        assert "REGRESSED-new" in capsys.readouterr().out

    def test_shrinking_while_still_over_passes(self, tmp_path, capsys):
        """A janitor PR must never be punished for inheriting the debt."""
        base = _write_tree(tmp_path / "base", status_bytes=FAR_OVER)
        baseline = _snapshot(base, tmp_path / "baseline.json", capsys)
        head = _write_tree(tmp_path / "head", status_bytes=OVER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 0

    def test_line_growth_alone_fails(self, tmp_path, capsys):
        """Bytes and lines are both ratcheted — shedding bytes must not buy
        the right to add rows to an over-budget file."""
        base = tmp_path / "base"
        _write_tree(base, status_bytes=OVER)
        baseline = _snapshot(base, tmp_path / "baseline.json", capsys)

        head = tmp_path / "head"
        _write_tree(head, status_bytes=OVER)
        # Same total size, more lines: rewrite as many short lines.
        (head / "STATUS.md").write_bytes(b"x\n" * (OVER // 2))

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 2

    def test_soft_growth_warns_but_does_not_fail(self, tmp_path, capsys):
        """SOFT ceilings are explicitly a host call, and AGENTS.md legitimately
        grows when a cross-provider convention lands. Surface it, don't block."""
        soft_over = next(b for b in ccb.CONFIG if b.path == "AGENTS.md").max_bytes + 500
        base = _write_tree(tmp_path / "base", status_bytes=UNDER,
                           agents_bytes=soft_over)
        baseline = _snapshot(base, tmp_path / "baseline.json", capsys)
        head = _write_tree(tmp_path / "head", status_bytes=UNDER,
                           agents_bytes=soft_over + 2000)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 0
        assert "Soft target grew" in capsys.readouterr().out

    def test_a_newly_added_budgeted_file_is_not_free(self, tmp_path, capsys):
        """A baseline missing an entry must read as 0 bytes / compliant, so
        introducing an over-budget always-loaded file counts as a regression
        rather than sliding in unmeasured."""
        baseline = tmp_path / "baseline.json"
        baseline.write_text(json.dumps({"results": []}), encoding="utf-8")
        head = _write_tree(tmp_path / "head", status_bytes=OVER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 2


class TestGateIntegrity:
    """You may not loosen the gate in the same change that benefits from it.

    Asked for by the 2026-07-22 cross-family (Codex) review, which called
    PR-controlled CONFIG the ratchet's strongest bypass: without these, a PR
    could raise `max_bytes`, downgrade STATUS.md to SOFT, or delete its entry,
    and the ratchet would report green on a strictly worse tree.
    """

    @staticmethod
    def _baseline_with(tmp_path: Path, **status_overrides) -> Path:
        """A baseline whose STATUS.md entry is exactly at its ceiling."""
        entry = {
            "path": "STATUS.md",
            "kind": "hard",
            "bytes": UNDER,
            "lines": 1,
            "max_bytes": STATUS_BUDGET.max_bytes,
            "max_lines": STATUS_BUDGET.max_lines,
            "over_bytes": False,
            "over_lines": False,
        }
        entry.update(status_overrides)
        dest = tmp_path / "baseline.json"
        dest.write_text(json.dumps({"results": [entry]}), encoding="utf-8")
        return dest

    def test_raising_the_byte_ceiling_fails(self, tmp_path, capsys, monkeypatch):
        """The brief's named gaming vector: bump 4096 until the tree fits."""
        baseline = self._baseline_with(tmp_path)
        monkeypatch.setattr(ccb, "CONFIG", tuple(
            ccb.Budget(b.path, b.kind, b.max_bytes + 10_000, b.max_lines, b.note)
            if b.path == "STATUS.md" else b
            for b in ccb.CONFIG
        ))
        head = _write_tree(tmp_path / "head", status_bytes=UNDER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 2
        assert "byte ceiling raised" in capsys.readouterr().out

    def test_raising_the_line_ceiling_fails(self, tmp_path, capsys, monkeypatch):
        baseline = self._baseline_with(tmp_path)
        monkeypatch.setattr(ccb, "CONFIG", tuple(
            ccb.Budget(b.path, b.kind, b.max_bytes, b.max_lines + 500, b.note)
            if b.path == "STATUS.md" else b
            for b in ccb.CONFIG
        ))
        head = _write_tree(tmp_path / "head", status_bytes=UNDER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 2
        assert "line ceiling raised" in capsys.readouterr().out

    def test_downgrading_hard_to_soft_fails(self, tmp_path, capsys, monkeypatch):
        baseline = self._baseline_with(tmp_path)
        monkeypatch.setattr(ccb, "CONFIG", tuple(
            ccb.Budget(b.path, "soft", b.max_bytes, b.max_lines, b.note)
            if b.path == "STATUS.md" else b
            for b in ccb.CONFIG
        ))
        head = _write_tree(tmp_path / "head", status_bytes=UNDER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 2
        assert "downgraded to soft" in capsys.readouterr().out

    def test_dropping_a_file_from_config_fails(self, tmp_path, capsys, monkeypatch):
        """Deleting the entry stops measurement entirely — the quietest bypass."""
        baseline = self._baseline_with(tmp_path)
        monkeypatch.setattr(ccb, "CONFIG", tuple(
            b for b in ccb.CONFIG if b.path != "STATUS.md"
        ))
        head = _write_tree(tmp_path / "head", status_bytes=UNDER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 2
        assert "dropped from CONFIG" in capsys.readouterr().out

    def test_lowering_a_ceiling_is_allowed(self, tmp_path, capsys, monkeypatch):
        """Tightening the gate is always welcome — only loosening fails."""
        baseline = self._baseline_with(tmp_path)
        monkeypatch.setattr(ccb, "CONFIG", tuple(
            ccb.Budget(b.path, b.kind, b.max_bytes - 100, b.max_lines, b.note)
            if b.path == "STATUS.md" else b
            for b in ccb.CONFIG
        ))
        head = _write_tree(tmp_path / "head", status_bytes=UNDER - 500)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 0

    def test_green_ratchet_never_claims_absolute_compliance(self, tmp_path, capsys):
        """Codex: 'presenting its green result as absolute compliance would be
        gaming'. A waived breach must say so in the same breath as the pass."""
        base = _write_tree(tmp_path / "base", status_bytes=OVER)
        baseline = _snapshot(base, tmp_path / "baseline.json", capsys)
        head = _write_tree(tmp_path / "head", status_bytes=OVER)

        assert ccb.main(["--strict", "--root", str(head),
                         "--baseline", str(baseline)]) == 0
        out = capsys.readouterr().out
        assert "still OVER budget" in out
        assert "NOT 'within budget'" in out


class TestBaselineHandling:
    def test_missing_baseline_fails_loudly(self, tmp_path, capsys):
        """Fail loudly, never silently (Hard Rule 8). A typo'd baseline path
        must not silently downgrade the gate to always-green — that is the
        exact wired-to-nothing failure mode this whole change exists to fix."""
        root = _write_tree(tmp_path / "head", status_bytes=UNDER)
        rc = ccb.main(["--strict", "--root", str(root),
                       "--baseline", str(tmp_path / "nope.json")])
        assert rc == 2
        assert "not found" in capsys.readouterr().err

    def test_json_output_carries_the_ratchet_verdict(self, tmp_path, capsys):
        base = _write_tree(tmp_path / "base", status_bytes=UNDER)
        baseline = _snapshot(base, tmp_path / "baseline.json", capsys)
        head = _write_tree(tmp_path / "head", status_bytes=OVER)

        ccb.main(["--json", "--root", str(head), "--baseline", str(baseline)])
        payload = json.loads(capsys.readouterr().out)

        assert payload["hard_regressions"] == ["STATUS.md"]
        verdicts = {d["path"]: d["verdict"] for d in payload["deltas"]}
        assert verdicts["STATUS.md"] == "REGRESSED-new"

    def test_list_paths_matches_config(self, capsys):
        """The CI baseline builder reads this list; drift would silently stop
        measuring a file."""
        assert ccb.main(["--list-paths"]) == 0
        printed = capsys.readouterr().out.split()
        assert printed == [b.path for b in ccb.CONFIG]

    def test_list_paths_is_lf_only(self, tmp_path):
        """Regression: `print()` emits CRLF on Windows, the trailing \\r became
        part of the path in the workflow's `while read` loop, every
        `git show <sha>:<path>\\r` missed, and the baseline read as all-zeros —
        making every file look newly-over-budget. Found by dry-running the CI
        logic on Windows, 2026-07-22. Subprocess, because capsys would hide it.
        """
        import subprocess

        out = subprocess.run(
            [sys.executable, str(ccb.REPO_ROOT / "scripts" / "check_context_budget.py"),
             "--list-paths"],
            capture_output=True, check=True,
        ).stdout
        assert b"\r" not in out, "CRLF here silently zeroes the CI baseline"
        assert out.decode().splitlines() == [b.path for b in ccb.CONFIG]


class TestInvariantRunnerGatesOnIt:
    """The runner's exit code is the on-demand enforcement surface."""

    def test_check_returns_nonzero_when_violated(self, monkeypatch, tmp_path):
        import scripts.invariants_run as runner
        from scripts.invariants import Status
        from scripts.invariants.context_budget import ContextBudgetInvariant

        over = _write_tree(tmp_path / "over", status_bytes=OVER)
        monkeypatch.setattr("scripts.invariants.context_budget.REPO_ROOT", over)

        assert ContextBudgetInvariant().check().status is Status.VIOLATED
        assert runner.main(["--check", "context-budget"]) == 1

    def test_check_returns_zero_when_clean(self, monkeypatch, tmp_path):
        import scripts.invariants_run as runner

        clean = _write_tree(tmp_path / "clean", status_bytes=UNDER)
        monkeypatch.setattr("scripts.invariants.context_budget.REPO_ROOT", clean)

        assert runner.main(["--check", "context-budget"]) == 0


@pytest.mark.parametrize("path", [b.path for b in ccb.CONFIG])
def test_every_budgeted_file_exists_in_the_repo(path):
    """CONFIG names a file that vanished => measure() reports MISSING and the
    guard quietly stops watching it."""
    assert (ccb.REPO_ROOT / path).is_file(), f"{path} is budgeted but missing"

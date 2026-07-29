from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "openspec_drain_supervisor.py"
SPEC = importlib.util.spec_from_file_location("openspec_drain_supervisor", SCRIPT)
assert SPEC is not None
drain = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = drain
SPEC.loader.exec_module(drain)

CLAIM_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "claim_check.py"
CLAIM_SPEC = importlib.util.spec_from_file_location(
    "claim_check_contract",
    CLAIM_SCRIPT,
)
assert CLAIM_SPEC is not None
claim_check = importlib.util.module_from_spec(CLAIM_SPEC)
assert CLAIM_SPEC.loader is not None
sys.modules[CLAIM_SPEC.name] = claim_check
CLAIM_SPEC.loader.exec_module(claim_check)


def _state(**overrides: object) -> dict[str, object]:
    state: dict[str, object] = {
        "run_id": "20260728-abc123",
        "identity": "drain-20260728-abc123",
        "provider": "codex",
        "model": None,
        "started_at": "2026-07-28T17:00:00-07:00",
        "deadline_at": "2026-07-29T01:00:00-07:00",
        "completed_slices": 0,
        "consecutive_failures": 0,
        "last_result": None,
        "resume_target": None,
        "recent_blocked": [],
        "merged_prs": [],
        "status": "running",
    }
    state.update(overrides)
    return state


def _snapshot_with_blocked(*targets: str) -> drain.CandidateSnapshot:
    return drain.CandidateSnapshot(
        pressure=drain.CandidatePressure(0, 0, 0),
        hints=(),
        blocked_targets=frozenset(targets),
    )


def test_parse_result_accepts_one_literal_final_marker() -> None:
    result = drain.parse_result(
        "Implemented and verified.\n"
        "DRAIN_RESULT: MERGED repair-first-contact https://github.com/o/r/pull/12\n"
    )
    assert result == drain.DrainResult(
        status="MERGED",
        target="repair-first-contact",
        pr="https://github.com/o/r/pull/12",
    )


def test_parse_result_canonicalizes_literal_human_task_label() -> None:
    result = drain.parse_result(
        "Blocked at publication.\n"
        "DRAIN_RESULT: BLOCKED main-red round 2 -\n"
    )

    assert result == drain.DrainResult(
        status="BLOCKED",
        target="main-red-round-2",
        pr="-",
    )


@pytest.mark.parametrize(
    "text",
    [
        "DRAIN_RESULT: <MERGED|BLOCKED> <target> <pr>",
        "DRAIN_RESULT: MERGED target https://github.com/o/r/pull/1\nextra",
        (
            "DRAIN_RESULT: BLOCKED first -\n"
            "DRAIN_RESULT: NO_CANDIDATE - -\n"
        ),
        "[peer_agent] ERROR: provider failed\nDRAIN_RESULT: FAILED - -",
        "DRAIN_RESULT: MERGED|PARTIAL target https://github.com/o/r/pull/1",
        "ordinary final prose",
    ],
)
def test_parse_result_rejects_ambiguous_or_echoed_markers(text: str) -> None:
    with pytest.raises(ValueError):
        drain.parse_result(text)


def test_worker_prompt_resumes_own_claim_and_carries_governance() -> None:
    prompt = drain.build_worker_prompt(
        _state(
            resume_target="provider-attempt-receipts",
            recent_blocked=["blocked-a", "blocked-b"],
        ),
        objective="Drain current OpenSpec delivery debt.",
    )
    normalized = " ".join(prompt.split())

    assert "drain-20260728-abc123" in prompt
    assert "provider-attempt-receipts" in prompt
    assert "MUST resume" in prompt
    assert "at most one PR" in prompt
    assert "at most 12 unchecked tasks" in prompt
    assert "blocked-a" in prompt
    assert "worktree_status.py" in prompt and "90 seconds" in prompt
    assert "not reliably OS-sandboxed" in prompt
    assert "shell `git` and `gh`" in normalized
    assert "`BLOCKED` is reserved" in normalized
    assert "must first land a sanitized STATUS dependency or blocker" in normalized
    assert "current `origin/main` classifies the exact target as blocked" in normalized
    assert "staging, committing, pushing, or creating the PR fails" in normalized
    assert "return `FAILED`" in normalized
    assert prompt.rstrip().endswith(
        "DRAIN_RESULT: <MERGED|PARTIAL|BLOCKED|NO_CANDIDATE|FAILED> "
        "<target-or-dash> <PR-url-or-dash>"
    )


def test_worker_prompt_requires_proven_exhaustion_before_no_candidate() -> None:
    prompt = drain.build_worker_prompt(
        _state(),
        objective="Drain current OpenSpec delivery debt.",
    )

    ordered_steps = [
        "claimable finish-first",
        "policy-qualified stale",
        "freshness-check",
        "cross-cutting",
    ]
    positions = [prompt.index(step) for step in ordered_steps]
    assert positions == sorted(positions)
    normalized = " ".join(prompt.split())
    assert "claimable` and `stale` counts are both zero" in normalized
    assert "NO_CANDIDATE" in prompt


def test_worker_prompt_claims_preselected_candidate_before_broad_audit() -> None:
    prompt = drain.build_worker_prompt(
        _state(),
        objective="Drain current OpenSpec delivery debt.",
        candidate_hints=(
            drain.CandidateHint(
                classification="CLAIMABLE",
                task_label="main-red round 2",
                files=("tests/test_universe_server_framing.py",),
            ),
        ),
    )

    assert "[CLAIMABLE] main-red round 2" in prompt
    assert "Before any broad audit or backlog scan" in prompt
    assert "--phase claim --limit 10" in " ".join(prompt.split())
    assert "commit that claim" in prompt
    assert prompt.index("commit that claim") < prompt.index(
        "openspec_flow.py audit"
    )


def test_candidate_snapshot_preserves_order_and_bounds_hints(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        claimable = [
            {
                "task_label": f"candidate-{index}",
                "files": [f"file-{index}.py"],
                "claimer": None,
            }
            for index in range(7)
        ]
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps(
                {
                    "counts": {
                        "claimable": 7,
                        "blocked": 0,
                        "in_flight": 1,
                        "host_owned": 0,
                        "stale": 1,
                    },
                    "claimable": claimable,
                    "stale": [
                        {
                            "row": {
                                "task_label": "stale-last",
                                "files": ["stale.py"],
                                "claimer": "old-session",
                            },
                            "reason": "no activity in 24h",
                            "suggested_reap_status": (
                                "reaped:drain-test:no-activity-24h"
                            ),
                        }
                    ],
                    "in_flight": [
                        {
                            "task_label": "resume-first",
                            "files": ["resume.py"],
                            "claimer": "drain-test",
                        }
                    ],
                }
            ),
            stderr="",
        )

    assert hasattr(drain, "inspect_candidate_snapshot")
    snapshot = drain.inspect_candidate_snapshot(
        repo=repo,
        provider="drain-test",
        runner=runner,
        max_hints=5,
    )

    assert snapshot.pressure == drain.CandidatePressure(
        claimable=7,
        stale=1,
        owned=1,
    )
    assert [hint.task_label for hint in snapshot.hints] == [
        "resume-first",
        "candidate-0",
        "candidate-1",
        "candidate-2",
        "candidate-3",
    ]
    assert snapshot.hints[0].classification == "OWNED"


def test_candidate_snapshot_unwraps_canonical_stale_rows(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    claimable_row = claim_check.Row(
        raw_task="**claimable-first**",
        files=["claimable.py"],
        depends_raw="-",
        status="pending",
        line_no=1,
    )
    stale_row = claim_check.Row(
        raw_task="**stale-second**",
        files=["stale.py"],
        depends_raw="-",
        status="claimed:closed-session",
        line_no=2,
    )
    payload = claim_check.build_payload(
        provider="drain-test",
        claimable=[claimable_row],
        blocked=[],
        in_flight=[],
        host_owned=[],
        stale=[(stale_row, "no activity in 24h")],
        show_reap=True,
    )

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps(payload),
            stderr="",
        )

    snapshot = drain.inspect_candidate_snapshot(
        repo=repo,
        provider="drain-test",
        runner=runner,
    )

    assert [
        (hint.classification, hint.task_label) for hint in snapshot.hints
    ] == [
        ("CLAIMABLE", "claimable-first"),
        ("STALE", "stale-second"),
    ]


def test_candidate_snapshot_extracts_all_blocked_targets_beyond_hint_limit(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    payload = {
        "counts": {
            "claimable": 2,
            "blocked": 3,
            "in_flight": 0,
            "host_owned": 0,
            "stale": 0,
        },
        "claimable": [
            {"task_label": "candidate one", "files": ["one.py"]},
            {"task_label": "candidate two", "files": ["two.py"]},
        ],
        "blocked": [
            {
                "row": {
                    "task_label": f"blocked target {index}",
                    "files": [f"blocked-{index}.py"],
                },
                "reasons": ["dependency"],
            }
            for index in range(3)
        ],
        "in_flight": [],
        "stale": [],
    }

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps(payload),
            stderr="",
        )

    snapshot = drain.inspect_candidate_snapshot(
        repo=repo,
        provider="drain-test",
        runner=runner,
        max_hints=1,
    )

    assert len(snapshot.hints) == 1
    assert snapshot.blocked_targets == frozenset(
        {
            "blocked-target-0",
            "blocked-target-1",
            "blocked-target-2",
        }
    )


def test_blocked_target_identity_does_not_alias_long_claimable_label(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    shared_prefix = "same long task identity " * 12
    claimable_label = f"{shared_prefix}alpha/beta"
    blocked_label = f"{shared_prefix}alpha-beta"
    payload = {
        "counts": {
            "claimable": 1,
            "blocked": 1,
            "in_flight": 0,
            "host_owned": 0,
            "stale": 0,
        },
        "claimable": [
            {"task_label": claimable_label, "files": ["claimable.py"]},
        ],
        "blocked": [
            {
                "row": {
                    "task_label": blocked_label,
                    "files": ["blocked.py"],
                },
                "reasons": ["dependency"],
            },
        ],
        "in_flight": [],
        "stale": [],
    }

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps(payload),
            stderr="",
        )

    snapshot = drain.inspect_candidate_snapshot(
        repo=repo,
        provider="drain-test",
        runner=runner,
    )
    claimable_target = drain._slugify(snapshot.hints[0].task_label)

    assert len(claimable_target) <= 48
    assert claimable_target not in snapshot.blocked_targets
    assert (
        drain.blocked_result_rejection(
            drain.DrainResult("BLOCKED", claimable_target, "-"),
            snapshot,
        )
        == f"target={claimable_target} is not blocked on current origin/main"
    )


def test_legacy_target_identity_migration_rekeys_admission_and_retries_blockers(
    tmp_path: Path,
) -> None:
    task_label = ("legacy long task identity " * 4) + "ending"
    legacy_target = re.sub(
        r"[^a-z0-9]+",
        "-",
        task_label.lower(),
    ).strip("-")[:48].rstrip("-")
    state = _state(
        admission={
            "target": legacy_target,
            "task_label": task_label,
            "worktree": str(tmp_path),
            "branch": f"drain/run/{legacy_target}",
        },
        resume_target=legacy_target,
        recent_blocked=[legacy_target, "another-legacy-target"],
    )

    changed = drain.migrate_target_identities(state)

    expected_target = drain._slugify(task_label)
    assert changed is True
    assert state["target_identity_version"] == 3
    assert state["admission"]["target"] == expected_target
    assert state["resume_target"] == expected_target
    assert state["recent_blocked"] == []
    assert drain.migrate_target_identities(state) is False


@pytest.mark.parametrize(
    "blocked",
    [
        {"row": {"task_label": "not-a-list"}},
        [{}],
        [{"row": "not-an-object", "reasons": ["dependency"]}],
    ],
)
def test_candidate_snapshot_rejects_malformed_blocked_collection(
    tmp_path: Path,
    blocked: object,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps(
                {
                    "counts": {
                        "claimable": 0,
                        "blocked": 1,
                        "in_flight": 0,
                        "host_owned": 0,
                        "stale": 0,
                    },
                    "claimable": [],
                    "blocked": blocked,
                    "in_flight": [],
                    "stale": [],
                }
            ),
            stderr="",
        )

    with pytest.raises(RuntimeError, match="claim pressure inspection failed"):
        drain.inspect_candidate_snapshot(
            repo=repo,
            provider="drain-test",
            runner=runner,
        )


def test_candidate_pressure_reads_claim_check_json(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            1,
            stdout=json.dumps(
                {
                    "counts": {
                        "claimable": 3,
                        "blocked": 2,
                        "in_flight": 1,
                        "host_owned": 4,
                        "stale": 2,
                    },
                    "in_flight": [
                        {"claimer": "drain-test"},
                        {"claimer": "other-provider"},
                    ],
                }
            ),
            stderr="",
        )

    assert hasattr(drain, "inspect_candidate_pressure")
    pressure = drain.inspect_candidate_pressure(
        repo=repo,
        provider="drain-test",
        runner=runner,
    )

    assert pressure.claimable == 3
    assert pressure.stale == 2
    assert pressure.owned == 1


def test_current_main_snapshot_fetches_before_ref_classification(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "controller"
    repo.mkdir()
    commands: list[list[str]] = []

    def runner(
        command: list[str],
        **kwargs: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if any("claim_check.py" in part for part in command):
            assert kwargs["encoding"] == "utf-8"
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps(
                    {
                        "counts": {
                            "claimable": 0,
                            "blocked": 0,
                            "in_flight": 0,
                            "host_owned": 0,
                            "stale": 0,
                        },
                        "claimable": [],
                        "stale": [],
                        "in_flight": [],
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    snapshot = drain.inspect_current_main_snapshot(
        repo=repo,
        provider="drain-test",
        runner=runner,
    )

    assert snapshot.pressure == drain.CandidatePressure(0, 0, 0)
    assert commands[0] == [
        "git",
        "-C",
        str(repo),
        "fetch",
        "--prune",
        "origin",
    ]
    assert "--status-ref" in commands[1]
    assert commands[1][commands[1].index("--status-ref") + 1] == "origin/main"


@pytest.mark.parametrize(
    ("claimable", "stale", "owned", "expected"),
    [
        (1, 0, 0, "claimable=1 stale=0 owned=0"),
        (0, 2, 0, "claimable=0 stale=2 owned=0"),
        (0, 0, 1, "claimable=0 stale=0 owned=1"),
        (0, 0, 0, None),
    ],
)
def test_no_candidate_rejection_requires_zero_pressure(
    claimable: int,
    stale: int,
    owned: int,
    expected: str | None,
) -> None:
    assert hasattr(drain, "CandidatePressure")
    assert hasattr(drain, "no_candidate_rejection")
    pressure = drain.CandidatePressure(
        claimable=claimable,
        stale=stale,
        owned=owned,
    )
    result = drain.DrainResult("NO_CANDIDATE", "-", "-")

    assert drain.no_candidate_rejection(result, pressure) == expected


def test_begin_attempt_marks_idle_controller_running() -> None:
    state = _state(attempts=1, status="idle")

    assert hasattr(drain, "begin_attempt")
    attempt = drain.begin_attempt(state)

    assert attempt == 2
    assert state["attempts"] == 2
    assert state["status"] == "running"


def test_codex_drain_dispatch_uses_balanced_reasoning_effort(
    tmp_path: Path,
) -> None:
    args = SimpleNamespace(
        provider="codex",
        repo=tmp_path,
        worker_timeout=5400,
        model=None,
    )

    assert hasattr(drain, "build_dispatch_command")
    command = drain.build_dispatch_command(
        args=args,
        prompt_path=tmp_path / "prompt.md",
        result_path=tmp_path / "result.md",
    )

    assert command[command.index("--effort") + 1] == "medium"

    args.provider = "claude"
    claude_command = drain.build_dispatch_command(
        args=args,
        prompt_path=tmp_path / "prompt.md",
        result_path=tmp_path / "result.md",
    )
    assert "--effort" not in claude_command


def test_repeated_target_attempts_get_distinct_deterministic_lanes(
    tmp_path: Path,
) -> None:
    first_worktree, first_branch = drain.admission_lane(
        repo=tmp_path / "controller",
        identity="drain-20260729-edda35",
        target="same-target",
        attempt=1,
    )
    second_worktree, second_branch = drain.admission_lane(
        repo=tmp_path / "controller",
        identity="drain-20260729-edda35",
        target="same-target",
        attempt=2,
    )

    assert first_worktree.name.endswith("-same-target-a001")
    assert second_worktree.name.endswith("-same-target-a002")
    assert first_worktree != second_worktree
    assert first_branch == "drain/20260729-edda35/same-target-a001"
    assert second_branch == "drain/20260729-edda35/same-target-a002"


def test_dispatch_completes_from_stable_valid_artifact_before_process_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result.md"
    result_path.write_text(
        "merged\n"
        "DRAIN_RESULT: PARTIAL target https://github.com/o/r/pull/12\n",
        encoding="utf-8",
    )
    args = SimpleNamespace(
        provider="codex",
        repo=tmp_path,
        worker_timeout=5400,
        model=None,
    )

    class HangingProcess:
        pid = 42
        returncode: int | None = None
        stdout = None
        stderr = None
        terminated = False

        def communicate(self, timeout: float) -> tuple[str, str]:
            if self.terminated:
                return "", ""
            raise subprocess.TimeoutExpired(["peer"], timeout)

        def poll(self) -> int | None:
            return self.returncode

    process = HangingProcess()
    monkeypatch.setattr(drain.subprocess, "Popen", lambda *_a, **_kw: process)

    def terminate(candidate: HangingProcess) -> None:
        candidate.terminated = True
        candidate.returncode = -9

    monkeypatch.setattr(drain, "_terminate_process_tree", terminate)

    completed = drain._dispatch(
        args=args,
        prompt_path=tmp_path / "prompt.md",
        result_path=result_path,
    )

    assert completed.returncode == 0
    assert process.terminated is True


def test_dispatch_does_not_complete_from_invalid_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result_path = tmp_path / "result.md"
    result_path.write_text("ordinary prose\n", encoding="utf-8")
    args = SimpleNamespace(
        provider="codex",
        repo=tmp_path,
        worker_timeout=5400,
        model=None,
    )

    class EventuallyExits:
        pid = 42
        returncode: int | None = None
        stdout = None
        stderr = None
        calls = 0

        def communicate(self, timeout: float) -> tuple[str, str]:
            self.calls += 1
            if self.calls < 3:
                raise subprocess.TimeoutExpired(["peer"], timeout)
            self.returncode = 0
            return "", ""

        def poll(self) -> int | None:
            return self.returncode

    process = EventuallyExits()
    monkeypatch.setattr(drain.subprocess, "Popen", lambda *_a, **_kw: process)
    monkeypatch.setattr(
        drain,
        "_terminate_process_tree",
        lambda _process: pytest.fail("invalid artifact terminated worker"),
    )

    completed = drain._dispatch(
        args=args,
        prompt_path=tmp_path / "prompt.md",
        result_path=result_path,
    )

    assert completed.returncode == 0
    assert process.calls == 3


def test_mechanical_admission_claims_candidate_in_prepared_worktree(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "controller"
    repo.mkdir()
    status_text = (
        "# Status\n\n"
        "## Work\n\n"
        "| Task | Files | Depends | Status |\n"
        "|---|---|---|---|\n"
        "| **main-red round 2** | `tests/red.py` | - | pending |\n"
    )
    (repo / "STATUS.md").write_text(status_text, encoding="utf-8")
    commands: list[list[str]] = []

    def runner(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if any("claim_check.py" in part for part in command):
            return subprocess.CompletedProcess(
                command,
                1,
                stdout=json.dumps(
                    {
                        "counts": {
                            "claimable": 1,
                            "blocked": 0,
                            "in_flight": 0,
                            "host_owned": 0,
                            "stale": 0,
                        },
                        "claimable": [
                            {
                                "task_label": "main-red round 2",
                                "files": ["tests/red.py"],
                                "claimer": None,
                                "line_no": 7,
                                "status": "pending",
                            }
                        ],
                        "stale": [],
                        "in_flight": [],
                    }
                ),
                stderr="",
            )
        if "status" in command:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        if "show-ref" in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        if "worktree" in command and "add" in command:
            worktree = Path(command[-2])
            worktree.mkdir()
            (worktree / "STATUS.md").write_text(status_text, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    admission = drain.admit_candidate(
        repo=repo,
        identity="drain-20260728-fast",
        attempt=1,
        hint=drain.CandidateHint(
            classification="CLAIMABLE",
            task_label="main-red round 2",
            files=("tests/red.py",),
            line_no=7,
            status="pending",
        ),
        runner=runner,
        today="2026-07-28",
    )

    claimed_status = (admission.worktree / "STATUS.md").read_text(
        encoding="utf-8"
    )
    assert "claimed:drain-20260728-fast ACTIVE 2026-07-28" in claimed_status
    assert admission.target == "main-red-round-2"
    assert (admission.worktree / "_PURPOSE.md").exists()
    assert any("worktree" in command and "add" in command for command in commands)
    assert sum("commit" in command for command in commands) == 1
    claim_commands = [
        command for command in commands if any("claim_check.py" in part for part in command)
    ]
    assert claim_commands
    assert all("--status-ref" not in command for command in claim_commands)


def test_admitted_prompt_forbids_reselection_and_duplicate_worktree(
    tmp_path: Path,
) -> None:
    admission = drain.Admission(
        target="main-red-round-2",
        task_label="main-red round 2",
        worktree=tmp_path / "wf-drain-fast-main-red",
        branch="drain/drain-fast/main-red-round-2",
    )

    prompt = drain.build_worker_prompt(
        _state(),
        objective="Drain current OpenSpec delivery debt.",
        admission=admission,
    )

    assert "already admitted and claimed" in prompt
    assert "Do not create another worktree" in prompt
    assert "Do not select a different lane" in prompt
    assert str(admission.worktree) in prompt


def test_mechanical_admission_never_deletes_preexisting_branch(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "controller"
    repo.mkdir()
    (repo / "STATUS.md").write_text(
        "## Work\n| Task | Files | Depends | Status |\n"
        "|---|---|---|---|\n"
        "| **target** | `x.py` | - | pending |\n",
        encoding="utf-8",
    )
    commands: list[list[str]] = []

    def runner(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if "show-ref" in command:
            return subprocess.CompletedProcess(command, 0, stdout="", stderr="")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    with pytest.raises(RuntimeError, match="branch already exists"):
        drain.admit_candidate(
            repo=repo,
            identity="drain-existing",
            attempt=1,
            hint=drain.CandidateHint(
                classification="CLAIMABLE",
                task_label="target",
                files=("x.py",),
                line_no=4,
                status="pending",
            ),
            runner=runner,
            today="2026-07-28",
        )

    assert not any("branch" in command and "-D" in command for command in commands)


def test_mechanical_stale_admission_commits_reap_before_claim(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "controller"
    repo.mkdir()
    status_text = (
        "## Work\n| Task | Files | Depends | Status |\n"
        "|---|---|---|---|\n"
        "| **stale target** | `x.py` | - | claimed:closed-session |\n"
    )
    (repo / "STATUS.md").write_text(status_text, encoding="utf-8")
    commands: list[list[str]] = []

    def runner(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        if any("claim_check.py" in part for part in command):
            return subprocess.CompletedProcess(
                command,
                1,
                stdout=json.dumps(
                    {
                        "counts": {
                            "claimable": 0,
                            "blocked": 0,
                            "in_flight": 1,
                            "host_owned": 0,
                            "stale": 1,
                        },
                        "claimable": [],
                        "in_flight": [
                            {
                                "task_label": "stale target",
                                "files": ["x.py"],
                                "line_no": 4,
                                "status": "claimed:closed-session",
                                "claimer": "closed-session",
                            }
                        ],
                        "stale": [
                            {
                                "row": {
                                    "task_label": "stale target",
                                    "files": ["x.py"],
                                    "line_no": 4,
                                    "status": "claimed:closed-session",
                                    "claimer": "closed-session",
                                },
                                "reason": "no activity in 24h",
                                "suggested_reap_status": (
                                    "reaped:drain-stale:no-activity-24h"
                                ),
                            }
                        ],
                    }
                ),
                stderr="",
            )
        if "show-ref" in command:
            return subprocess.CompletedProcess(command, 1, stdout="", stderr="")
        if "worktree" in command and "add" in command:
            worktree = Path(command[-2])
            worktree.mkdir()
            (worktree / "STATUS.md").write_text(status_text, encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    admission = drain.admit_candidate(
        repo=repo,
        identity="drain-stale",
        attempt=1,
        hint=drain.CandidateHint(
            classification="STALE",
            task_label="stale target",
            files=("x.py",),
            line_no=4,
            status="claimed:closed-session",
        ),
        runner=runner,
        today="2026-07-28",
    )

    commit_messages = [
        command[command.index("-m") + 1]
        for command in commands
        if "commit" in command
    ]
    assert commit_messages == [
        "coord: reap stale stale-target claim",
        "coord: claim stale-target for drain",
    ]
    assert "claimed:drain-stale ACTIVE 2026-07-28" in (
        admission.worktree / "STATUS.md"
    ).read_text(encoding="utf-8")


def test_admission_command_normalizes_timeout_to_runtime_error(
    tmp_path: Path,
) -> None:
    def runner(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 120)

    with pytest.raises(RuntimeError, match="timed out"):
        drain._admission_command(
            ["git", "fetch"],
            cwd=tmp_path,
            runner=runner,
        )


def test_admission_cleanup_never_masks_original_failure(tmp_path: Path) -> None:
    def runner(
        command: list[str],
        **_: object,
    ) -> subprocess.CompletedProcess[str]:
        raise subprocess.TimeoutExpired(command, 30)

    drain._best_effort_admission_cleanup(
        ["git", "worktree", "remove", "--force", "known-path"],
        cwd=tmp_path,
        runner=runner,
        timeout=30,
    )


def test_blocked_candidates_are_filtered_before_next_admission() -> None:
    hints = (
        drain.CandidateHint(
            "OWNED",
            "first target",
            (),
            1,
            "claimed:drain-test",
        ),
        drain.CandidateHint("CLAIMABLE", "first target", (), 1, "pending"),
        drain.CandidateHint("CLAIMABLE", "second target", (), 2, "pending"),
    )

    remaining = drain.filter_recently_blocked_hints(
        hints,
        recent_blocked=["first-target"],
    )

    assert [
        (hint.classification, hint.task_label) for hint in remaining
    ] == [
        ("OWNED", "first target"),
        ("CLAIMABLE", "second target"),
    ]


def test_recent_blockers_are_retained_only_while_current_main_blocks_them() -> None:
    assert drain.reconcile_recent_blocked(
        ["still-blocked", "cleared", "deleted"],
        blocked_targets=frozenset({"still-blocked", "unrelated"}),
    ) == ["still-blocked"]


@pytest.mark.parametrize(
    (
        "pressure",
        "candidate_hints",
        "recent_blocked",
        "has_admission",
        "expected",
    ),
    [
        (
            drain.CandidatePressure(1, 0, 0),
            (),
            ["first-target"],
            False,
            True,
        ),
        (
            drain.CandidatePressure(0, 1, 0),
            (),
            ["first-target"],
            False,
            True,
        ),
        (
            drain.CandidatePressure(1, 0, 0),
            (drain.CandidateHint("CLAIMABLE", "second target", ()),),
            ["first-target"],
            False,
            False,
        ),
        (
            drain.CandidatePressure(1, 0, 0),
            (),
            ["first-target"],
            True,
            False,
        ),
        (
            drain.CandidatePressure(0, 0, 1),
            (),
            ["first-target"],
            False,
            False,
        ),
        (
            drain.CandidatePressure(0, 0, 0),
            (),
            ["first-target"],
            False,
            False,
        ),
        (
            drain.CandidatePressure(1, 0, 0),
            (),
            [],
            False,
            False,
        ),
    ],
)
def test_recent_blocker_cooldown_only_suppresses_filtered_rediscovery(
    pressure: drain.CandidatePressure,
    candidate_hints: tuple[drain.CandidateHint, ...],
    recent_blocked: list[str],
    has_admission: bool,
    expected: bool,
) -> None:
    assert (
        drain.should_cooldown_without_worker(
            pressure=pressure,
            candidate_hints=candidate_hints,
            recent_blocked=recent_blocked,
            has_admission=has_admission,
        )
        is expected
    )


def test_blocked_result_skips_idle_only_for_a_different_candidate() -> None:
    snapshot = drain.CandidateSnapshot(
        pressure=drain.CandidatePressure(claimable=1, stale=0, owned=1),
        hints=(
            drain.CandidateHint(
                "OWNED",
                "first target",
                (),
                1,
                "claimed:drain-test",
            ),
            drain.CandidateHint(
                "CLAIMABLE",
                "second target",
                (),
                2,
                "pending",
            ),
        ),
    )

    assert drain.has_alternative_candidate(
        snapshot,
        recent_blocked=["first-target"],
        current_target="first-target",
    )
    assert not drain.has_alternative_candidate(
        drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(claimable=0, stale=0, owned=1),
            hints=snapshot.hints[:1],
        ),
        recent_blocked=["first-target"],
        current_target="first-target",
    )
    assert not drain.has_alternative_candidate(
        snapshot,
        recent_blocked=[],
        current_target="-",
    )


def test_admission_rejects_mismatched_worker_result(tmp_path: Path) -> None:
    admission = drain.Admission(
        target="assigned-target",
        task_label="assigned target",
        worktree=tmp_path,
        branch="drain/run/assigned-target",
    )

    rejection = drain.admission_result_rejection(
        drain.DrainResult("BLOCKED", "different-target", "-"),
        admission,
    )

    assert rejection == "assigned=assigned-target reported=different-target"


@pytest.mark.parametrize(
    ("blocked_targets", "expected"),
    [
        (frozenset({"assigned-target"}), None),
        (frozenset({"different-target"}), "target=assigned-target"),
        (frozenset(), "target=assigned-target"),
    ],
)
def test_blocked_result_requires_exact_current_main_blocked_target(
    blocked_targets: frozenset[str],
    expected: str | None,
) -> None:
    rejection = drain.blocked_result_rejection(
        drain.DrainResult("BLOCKED", "assigned-target", "-"),
        drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(1, 0, 0),
            hints=(),
            blocked_targets=blocked_targets,
        ),
    )

    if expected is None:
        assert rejection is None
    else:
        assert expected in rejection


def test_invalid_blocked_result_retains_admission_and_records_failure(
    tmp_path: Path,
) -> None:
    admission = {
        "target": "assigned-target",
        "task_label": "assigned target",
        "worktree": str(tmp_path),
        "branch": "drain/run/assigned-target",
    }
    state = _state(
        attempts=4,
        admission=admission,
        resume_target="assigned-target",
        recent_blocked=["other-target"],
    )

    drain.apply_invalid_blocked_result(
        state,
        drain.DrainResult("BLOCKED", "assigned-target", "-"),
        attempt=4,
        error="origin fetch failed",
    )

    assert state["admission"] == admission
    assert state["resume_target"] == "assigned-target"
    assert state["recent_blocked"] == ["other-target"]
    assert state["consecutive_failures"] == 1
    assert state["last_result"] == {
        "status": "INVALID_BLOCKED_RESULT",
        "attempt": 4,
        "target": "assigned-target",
        "error": "origin fetch failed",
    }
    assert state["status"] == "invalid-blocked-result"


def test_admitted_prompt_requires_exact_canonical_result_target(
    tmp_path: Path,
) -> None:
    admission = drain.Admission(
        target="assigned-target",
        task_label="assigned target",
        worktree=tmp_path,
        branch="drain/run/assigned-target",
    )

    prompt = drain.build_worker_prompt(
        _state(admission={}),
        objective="Drain current OpenSpec delivery debt.",
        admission=admission,
    )

    assert "Canonical result target: `assigned-target`" in prompt
    assert prompt.rstrip().endswith(
        "DRAIN_RESULT: <MERGED|PARTIAL|BLOCKED|FAILED> "
        "assigned-target <PR-url-or-dash>"
    )


def test_resume_replays_newly_valid_result_and_undoes_parser_strike(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "005.md").write_text(
        "Blocked at publication.\n"
        "DRAIN_RESULT: BLOCKED main-red round 2 -\n",
        encoding="utf-8",
    )
    state = _state(
        attempts=5,
        consecutive_failures=2,
        last_result={
            "status": "INVALID_RESULT",
            "attempt": 5,
            "error": "malformed",
        },
        admission={
            "target": "main-red-round-2",
            "task_label": "main-red round 2",
            "worktree": str(tmp_path),
            "branch": "drain/run/main-red-round-2",
        },
        resume_target="main-red-round-2",
    )

    recovered = drain.recover_invalid_result(
        state,
        results_dir=results_dir,
        repo=tmp_path,
        blocked_snapshot_inspector=lambda **_kwargs: _snapshot_with_blocked(
            "main-red-round-2"
        ),
    )

    assert recovered is True
    assert state["consecutive_failures"] == 0
    assert state["last_result"] == {
        "status": "BLOCKED",
        "target": "main-red-round-2",
        "pr": "-",
    }
    assert state["recent_blocked"] == ["main-red-round-2"]
    assert state["resume_target"] is None
    assert state["admission"] is None
    assert state["status"] == "blocked"


def test_resume_rejects_newly_parseable_private_blocker(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "005.md").write_text(
        "DRAIN_RESULT: BLOCKED main-red round 2 -\n",
        encoding="utf-8",
    )
    admission = {
        "target": "main-red-round-2",
        "task_label": "main-red round 2",
        "worktree": str(tmp_path),
        "branch": "drain/run/main-red-round-2",
    }
    state = _state(
        attempts=5,
        consecutive_failures=2,
        last_result={
            "status": "INVALID_RESULT",
            "attempt": 5,
            "error": "malformed",
        },
        admission=admission,
        resume_target="main-red-round-2",
    )

    recovered = drain.recover_invalid_result(
        state,
        results_dir=results_dir,
        repo=tmp_path,
        blocked_snapshot_inspector=lambda **_kwargs: _snapshot_with_blocked(),
    )

    assert recovered is True
    assert state["consecutive_failures"] == 2
    assert state["last_consumed_attempt"] == 5
    assert state["last_result"]["status"] == "INVALID_BLOCKED_RESULT"
    assert state["admission"] == admission
    assert state["recent_blocked"] == []


@pytest.mark.parametrize(
    "marker",
    [
        "DRAIN_RESULT: <BLOCKED> main-red round 2 -",
        "DRAIN_RESULT: BLOCKED different target -",
        (
            "DRAIN_RESULT: BLOCKED main-red round 2 -\n"
            "DRAIN_RESULT: BLOCKED main-red round 2 -"
        ),
    ],
)
def test_resume_retains_failure_when_last_result_cannot_be_safely_replayed(
    tmp_path: Path,
    marker: str,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "005.md").write_text(marker + "\n", encoding="utf-8")
    state = _state(
        attempts=5,
        consecutive_failures=2,
        last_result={
            "status": "INVALID_RESULT",
            "attempt": 5,
            "error": "malformed",
        },
        admission={
            "target": "main-red-round-2",
            "task_label": "main-red round 2",
            "worktree": str(tmp_path),
            "branch": "drain/run/main-red-round-2",
        },
        resume_target="main-red-round-2",
    )

    recovered = drain.recover_invalid_result(
        state,
        results_dir=results_dir,
        repo=tmp_path,
    )

    assert recovered is False
    assert state["consecutive_failures"] == 2
    assert state["last_result"]["status"] == "INVALID_RESULT"
    assert state["admission"]["target"] == "main-red-round-2"


def test_resume_consumes_valid_unrecorded_current_attempt(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "001.md").write_text(
        "Merged implementation; foldback remains.\n"
        "DRAIN_RESULT: PARTIAL assigned-target "
        "https://github.com/o/r/pull/12\n",
        encoding="utf-8",
    )
    state = _state(
        attempts=1,
        last_result=None,
        admission={
            "target": "assigned-target",
            "task_label": "assigned target",
            "worktree": str(tmp_path),
            "branch": "drain/run/assigned-target",
        },
        resume_target="assigned-target",
    )

    recovered = drain.recover_unconsumed_result(
        state,
        results_dir=results_dir,
        repo=tmp_path,
        merge_verifier=lambda *_args, **_kwargs: True,
    )

    assert recovered is True
    assert state["status"] == "partial"
    assert state["resume_target"] == "assigned-target"
    assert state["last_consumed_attempt"] == 1
    assert state["last_result"]["status"] == "PARTIAL"
    assert state["admission"]["target"] == "assigned-target"


def test_resume_rejects_unconsumed_private_blocker(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "001.md").write_text(
        "DRAIN_RESULT: BLOCKED assigned-target -\n",
        encoding="utf-8",
    )
    admission = {
        "target": "assigned-target",
        "task_label": "assigned target",
        "worktree": str(tmp_path),
        "branch": "drain/run/assigned-target",
    }
    state = _state(
        attempts=1,
        last_result=None,
        admission=admission,
        resume_target="assigned-target",
    )

    recovered = drain.recover_unconsumed_result(
        state,
        results_dir=results_dir,
        repo=tmp_path,
        blocked_snapshot_inspector=lambda **_kwargs: _snapshot_with_blocked(),
    )

    assert recovered is True
    assert state["consecutive_failures"] == 1
    assert state["last_consumed_attempt"] == 1
    assert state["last_result"]["status"] == "INVALID_BLOCKED_RESULT"
    assert state["admission"] == admission
    assert state["recent_blocked"] == []


def test_resume_refuses_unrecorded_result_for_different_admission(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "001.md").write_text(
        "DRAIN_RESULT: BLOCKED different-target -\n",
        encoding="utf-8",
    )
    state = _state(
        attempts=1,
        last_result=None,
        admission={
            "target": "assigned-target",
            "task_label": "assigned target",
            "worktree": str(tmp_path),
            "branch": "drain/run/assigned-target",
        },
    )

    assert not drain.recover_unconsumed_result(
        state,
        results_dir=results_dir,
        repo=tmp_path,
    )
    assert state["last_result"] is None
    assert "last_consumed_attempt" not in state


def test_resume_recovers_current_result_after_an_earlier_failed_attempt(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "003.md").write_text(
        "DRAIN_RESULT: BLOCKED assigned-target -\n",
        encoding="utf-8",
    )
    state = _state(
        attempts=3,
        last_consumed_attempt=1,
        last_result={
            "status": "INVALID_RESULT",
            "attempt": 2,
            "error": "malformed",
        },
        admission={
            "target": "assigned-target",
            "task_label": "assigned target",
            "worktree": str(tmp_path),
            "branch": "drain/run/assigned-target",
        },
    )

    assert drain.recover_unconsumed_result(
        state,
        results_dir=results_dir,
        repo=tmp_path,
        blocked_snapshot_inspector=lambda **_kwargs: _snapshot_with_blocked(
            "assigned-target"
        ),
    )
    assert state["last_consumed_attempt"] == 3
    assert state["status"] == "blocked"


def test_run_recovers_unconsumed_result_before_replacement_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    state = _state(
        attempts=1,
        last_result=None,
        admission={
            "target": "assigned-target",
            "task_label": "assigned target",
            "worktree": str(repo),
            "branch": "drain/run/assigned-target",
        },
        resume_target="assigned-target",
    )
    (run_dir / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (results_dir / "001.md").write_text(
        "DRAIN_RESULT: PARTIAL assigned-target "
        "https://github.com/o/r/pull/12\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(drain, "verify_merged", lambda *_a, **_kw: True)
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(0, 0, 0),
            hints=(),
            blocked_targets=frozenset({"assigned-target"}),
        ),
    )
    dispatched_prompts: list[str] = []

    def fake_dispatch(
        *,
        args: object,
        prompt_path: Path,
        result_path: Path,
        worker_cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        del args
        assert worker_cwd == repo
        dispatched_prompts.append(prompt_path.read_text(encoding="utf-8"))
        result_path.write_text(
            "DRAIN_RESULT: BLOCKED assigned-target -\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(drain, "_dispatch", fake_dispatch)

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--resume",
            "--once",
            "--hours",
            "1",
        ]
    )

    persisted = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    log = (run_dir / "supervisor.log").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "recovered unconsumed terminal result attempt=1 status=PARTIAL" in log
    assert len(dispatched_prompts) == 1
    assert "implementation PR is already merged" in dispatched_prompts[0]
    assert persisted["attempts"] == 2
    assert persisted["last_consumed_attempt"] == 2
    assert persisted["status"] == "blocked"


def test_resume_does_not_recover_a_missing_recorded_artifact(
    tmp_path: Path,
) -> None:
    state = _state(
        attempts=5,
        consecutive_failures=2,
        last_result={"status": "INVALID_RESULT", "attempt": 4},
        admission={
            "target": "main-red-round-2",
            "task_label": "main-red round 2",
            "worktree": str(tmp_path),
            "branch": "drain/run/main-red-round-2",
        },
    )

    assert (
        drain.recover_invalid_result(
            state,
            results_dir=tmp_path,
            repo=tmp_path,
        )
        is False
    )
    assert state["consecutive_failures"] == 2


def test_resume_replays_the_recorded_invalid_attempt_not_latest_attempt(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "005.md").write_text(
        "DRAIN_RESULT: BLOCKED main-red round 2 -\n",
        encoding="utf-8",
    )
    (results_dir / "006.md").write_text(
        "DRAIN_RESULT: BLOCKED different target -\n",
        encoding="utf-8",
    )
    state = _state(
        attempts=6,
        consecutive_failures=2,
        last_result={
            "status": "INVALID_RESULT",
            "attempt": 5,
            "error": "malformed",
        },
        admission={
            "target": "main-red-round-2",
            "task_label": "main-red round 2",
            "worktree": str(tmp_path),
            "branch": "drain/run/main-red-round-2",
        },
        resume_target="main-red-round-2",
    )

    recovered = drain.recover_invalid_result(
        state,
        results_dir=results_dir,
        repo=tmp_path,
        blocked_snapshot_inspector=lambda **_kwargs: _snapshot_with_blocked(
            "main-red-round-2"
        ),
    )

    assert recovered is True
    assert state["last_result"]["target"] == "main-red-round-2"


def test_legacy_failure_budget_can_replay_its_terminal_current_attempt(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "005.md").write_text(
        "DRAIN_RESULT: BLOCKED main-red round 2 -\n",
        encoding="utf-8",
    )
    state = _state(
        status="failure-budget",
        attempts=5,
        consecutive_failures=2,
        last_result={"status": "INVALID_RESULT", "error": "malformed"},
        admission={
            "target": "main-red-round-2",
            "task_label": "main-red round 2",
            "worktree": str(tmp_path),
            "branch": "drain/run/main-red-round-2",
        },
    )

    assert (
        drain.recover_invalid_result(
            state,
            results_dir=results_dir,
            repo=tmp_path,
            blocked_snapshot_inspector=lambda **_kwargs: _snapshot_with_blocked(
                "main-red-round-2"
            ),
        )
        is True
    )
    assert state["last_result"]["target"] == "main-red-round-2"


def test_resume_replayed_merge_uses_controller_verification(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "005.md").write_text(
        "DRAIN_RESULT: MERGED assigned target "
        "https://github.com/o/r/pull/12\n",
        encoding="utf-8",
    )
    state = _state(
        attempts=5,
        consecutive_failures=2,
        last_result={"status": "INVALID_RESULT", "attempt": 5},
        admission={
            "target": "assigned-target",
            "task_label": "assigned target",
            "worktree": str(tmp_path),
            "branch": "drain/run/assigned-target",
        },
    )
    verifier_calls: list[tuple[str, Path, str]] = []

    def verifier(
        pr: str,
        *,
        repo: Path,
        started_at: str,
    ) -> bool:
        verifier_calls.append((pr, repo, started_at))
        return True

    assert (
        drain.recover_invalid_result(
            state,
            results_dir=results_dir,
            repo=tmp_path,
            merge_verifier=verifier,
        )
        is True
    )
    assert verifier_calls == [
        (
            "https://github.com/o/r/pull/12",
            tmp_path,
            "2026-07-28T17:00:00-07:00",
        )
    ]
    assert state["completed_slices"] == 1
    assert state["admission"] is None


@pytest.mark.parametrize(
    "state_overrides",
    [
        {"admission": None},
        {"last_result": {"status": "INVALID_ADMISSION_RESULT", "attempt": 5}},
        {"last_result": {"status": "INVALID_RESULT"}},
    ],
)
def test_resume_requires_admission_and_an_exact_invalid_attempt(
    tmp_path: Path,
    state_overrides: dict[str, object],
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    (results_dir / "005.md").write_text(
        "DRAIN_RESULT: BLOCKED main-red round 2 -\n",
        encoding="utf-8",
    )
    state = _state(
        attempts=5,
        consecutive_failures=2,
        last_result={"status": "INVALID_RESULT", "attempt": 5},
        admission={
            "target": "main-red-round-2",
            "task_label": "main-red round 2",
            "worktree": str(tmp_path),
            "branch": "drain/run/main-red-round-2",
        },
    )
    state.update(state_overrides)

    assert (
        drain.recover_invalid_result(
            state,
            results_dir=results_dir,
            repo=tmp_path,
        )
        is False
    )
    assert state["consecutive_failures"] == 2


def test_run_replays_invalid_result_before_failure_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    state = _state(
        status="failure-budget",
        attempts=5,
        consecutive_failures=2,
        last_result={
            "status": "INVALID_RESULT",
            "error": "malformed",
        },
        admission={
            "target": "main-red-round-2",
            "task_label": "main-red round 2",
            "worktree": str(tmp_path),
            "branch": "drain/run/main-red-round-2",
        },
        resume_target="main-red-round-2",
    )
    (run_dir / "state.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )
    (results_dir / "005.md").write_text(
        "DRAIN_RESULT: BLOCKED main-red round 2 -\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(0, 0, 0),
            hints=(),
            blocked_targets=frozenset({"main-red-round-2"}),
        ),
    )

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--resume",
            "--dry-run",
            "--hours",
            "1",
            "--max-failures",
            "2",
        ]
    )

    persisted = json.loads(
        (run_dir / "state.json").read_text(encoding="utf-8")
    )
    assert exit_code == 0
    assert persisted["status"] == "dry-run"
    assert persisted["attempts"] == 6
    assert persisted["recent_blocked"] == ["main-red-round-2"]
    assert persisted["admission"] is None


def test_recovery_log_names_recorded_attempt_not_latest_counter(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    results_dir = run_dir / "results"
    results_dir.mkdir(parents=True)
    state = _state(
        attempts=6,
        consecutive_failures=1,
        last_result={"status": "INVALID_RESULT", "attempt": 5},
        admission={
            "target": "main-red-round-2",
            "task_label": "main-red round 2",
            "worktree": str(tmp_path),
            "branch": "drain/run/main-red-round-2",
        },
    )
    (run_dir / "state.json").write_text(
        json.dumps(state),
        encoding="utf-8",
    )
    (results_dir / "005.md").write_text(
        "DRAIN_RESULT: BLOCKED main-red round 2 -\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(0, 0, 0),
            hints=(),
            blocked_targets=frozenset({"main-red-round-2"}),
        ),
    )

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--resume",
            "--dry-run",
            "--hours",
            "1",
        ]
    )

    log = (run_dir / "supervisor.log").read_text(encoding="utf-8")
    assert exit_code == 0
    assert "replayed newly valid result attempt=5 status=BLOCKED" in log


def test_invalid_result_records_its_exact_attempt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"

    def fake_dispatch(
        *,
        args: object,
        prompt_path: Path,
        result_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        del args, prompt_path
        result_path.write_text("ordinary prose\n", encoding="utf-8")
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(drain, "_dispatch", fake_dispatch)
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(0, 0, 0),
            hints=(),
        ),
    )

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--once",
            "--hours",
            "1",
        ]
    )

    persisted = json.loads(
        (run_dir / "state.json").read_text(encoding="utf-8")
    )
    assert exit_code == 2
    assert persisted["last_result"]["status"] == "INVALID_RESULT"
    assert persisted["last_result"]["attempt"] == 1


def test_apply_merged_requires_controller_verification() -> None:
    state = _state(consecutive_failures=1)
    result = drain.DrainResult(
        "MERGED",
        "target",
        "https://github.com/o/r/pull/12",
    )

    drain.apply_result(state, result, merge_verified=False)

    assert state["completed_slices"] == 0
    assert state["consecutive_failures"] == 2
    assert state["status"] == "merge-verification-failed"


def test_verified_merge_records_bounded_receipt_and_rejects_exact_replay() -> None:
    state = _state()
    result = drain.DrainResult(
        "MERGED",
        "target",
        "https://github.com/o/r/pull/12",
    )

    drain.apply_result(state, result, merge_verified=True)

    assert state["completed_slices"] == 1
    assert state["merged_prs"] == ["https://github.com/o/r/pull/12"]
    assert (
        drain.duplicate_merge_rejection(result, state)
        == "already-consumed=https://github.com/o/r/pull/12"
    )


def test_merge_receipt_rejects_repo_case_and_number_format_replay() -> None:
    state = _state(
        completed_slices=1,
        merged_prs=["https://github.com/o/r/pull/12"],
    )
    replay = drain.DrainResult(
        "MERGED",
        "target",
        "https://github.com/O/R/pull/0012",
    )

    assert (
        drain.duplicate_merge_rejection(replay, state)
        == "already-consumed=https://github.com/o/r/pull/12"
    )


def test_merge_receipts_survive_for_the_whole_bounded_run() -> None:
    state = _state()
    first = drain.DrainResult(
        "MERGED",
        "target",
        "https://github.com/o/r/pull/1",
    )

    for number in range(1, 66):
        drain.apply_result(
            state,
            drain.DrainResult(
                "MERGED",
                f"target-{number}",
                f"https://github.com/o/r/pull/{number}",
            ),
            merge_verified=True,
        )

    assert len(state["merged_prs"]) == 65
    assert (
        drain.duplicate_merge_rejection(first, state)
        == "already-consumed=https://github.com/o/r/pull/1"
    )


def test_duplicate_merge_failure_retains_admission_and_does_not_count_slice(
    tmp_path: Path,
) -> None:
    admission = {
        "target": "target",
        "task_label": "target",
        "worktree": str(tmp_path),
        "branch": "drain/run/target",
    }
    state = _state(
        attempts=3,
        completed_slices=1,
        admission=admission,
        resume_target="target",
        merged_prs=["https://github.com/o/r/pull/12"],
    )

    drain.apply_invalid_duplicate_merge(
        state,
        drain.DrainResult(
            "MERGED",
            "target",
            "https://github.com/o/r/pull/12",
        ),
        attempt=3,
    )

    assert state["completed_slices"] == 1
    assert state["consecutive_failures"] == 1
    assert state["admission"] == admission
    assert state["resume_target"] == "target"
    assert state["last_result"]["status"] == "INVALID_DUPLICATE_MERGE"
    assert state["status"] == "invalid-duplicate-merge"


def test_legacy_merge_receipts_are_reconstructed_and_deduplicated(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    marker = (
        "DRAIN_RESULT: MERGED target "
        "https://github.com/o/r/pull/12\n"
    )
    (results_dir / "001.md").write_text(marker, encoding="utf-8")
    (results_dir / "002.md").write_text(
        "DRAIN_RESULT: MERGED target "
        "https://github.com/O/R/pull/0012\n",
        encoding="utf-8",
    )
    (results_dir / "003.md").write_text(
        "DRAIN_RESULT: BLOCKED target -\n",
        encoding="utf-8",
    )
    (tmp_path / "supervisor.log").write_text(
        "2026-07-29T00:00:00-07:00 result attempt=1 status=merged "
        "target=target pr=https://github.com/o/r/pull/12\n"
        "2026-07-29T00:01:00-07:00 result attempt=2 status=merged "
        "target=target pr=https://github.com/O/R/pull/0012\n",
        encoding="utf-8",
    )
    verifier_calls: list[str] = []

    receipts = drain.infer_legacy_merged_prs(
        state=_state(
            attempts=3,
            last_consumed_attempt=3,
            completed_slices=2,
        ),
        results_dir=results_dir,
        repo=tmp_path,
        merge_verifier=lambda pr, **_kwargs: verifier_calls.append(pr) or True,
    )

    assert receipts == ["https://github.com/o/r/pull/12"]
    assert verifier_calls == ["https://github.com/o/r/pull/12"]


def test_legacy_merge_receipts_exclude_prior_verification_failure(
    tmp_path: Path,
) -> None:
    results_dir = tmp_path / "results"
    results_dir.mkdir()
    pr = "https://github.com/o/r/pull/12"
    (results_dir / "001.md").write_text(
        f"DRAIN_RESULT: MERGED target {pr}\n",
        encoding="utf-8",
    )
    (tmp_path / "supervisor.log").write_text(
        "2026-07-29T00:00:00-07:00 result attempt=1 "
        f"status=merge-verification-failed target=target pr={pr}\n",
        encoding="utf-8",
    )
    verifier_calls: list[str] = []

    receipts = drain.infer_legacy_merged_prs(
        state=_state(
            attempts=1,
            last_consumed_attempt=1,
            completed_slices=0,
            status="merge-verification-failed",
        ),
        results_dir=results_dir,
        repo=tmp_path,
        merge_verifier=lambda candidate, **_kwargs: (
            verifier_calls.append(candidate) or True
        ),
    )

    assert receipts == []
    assert verifier_calls == []


def test_apply_partial_resets_failures_and_sets_resume_target() -> None:
    state = _state(consecutive_failures=1)
    result = drain.DrainResult(
        "PARTIAL",
        "target",
        "https://github.com/o/r/pull/12",
    )

    drain.apply_result(state, result, merge_verified=True)

    assert state["completed_slices"] == 0
    assert state["consecutive_failures"] == 0
    assert state["resume_target"] == "target"
    assert state["status"] == "partial"


def test_repeated_same_target_partial_consumes_failure_budget() -> None:
    state = _state(
        consecutive_failures=0,
        resume_target="target",
        consecutive_partial_target="target",
        consecutive_partials=1,
    )

    drain.apply_result(
        state,
        drain.DrainResult(
            "PARTIAL",
            "target",
            "https://github.com/o/r/pull/12",
        ),
        merge_verified=True,
    )

    assert state["consecutive_partials"] == 2
    assert state["consecutive_failures"] == 1
    assert state["status"] == "partial-stalled"


def test_blocked_target_is_bounded_and_no_candidate_does_not_fail() -> None:
    state = _state(recent_blocked=[f"old-{index}" for index in range(20)])

    drain.apply_result(state, drain.DrainResult("BLOCKED", "new", "-"))
    drain.apply_result(state, drain.DrainResult("NO_CANDIDATE", "-", "-"))

    assert state["consecutive_failures"] == 0
    assert state["recent_blocked"][-1] == "new"
    assert len(state["recent_blocked"]) == drain.MAX_RECENT_BLOCKED
    assert state["status"] == "idle"


def test_failed_delivery_preserves_admission_for_a_fresh_worker() -> None:
    admission = {
        "target": "target",
        "worktree": "C:/worktree",
        "branch": "drain/target",
    }
    state = _state(
        admission=admission,
        recent_blocked=["other-target"],
    )

    drain.apply_result(state, drain.DrainResult("FAILED", "target", "-"))

    assert state["admission"] == admission
    assert state["recent_blocked"] == ["other-target"]
    assert state["consecutive_failures"] == 1
    assert state["status"] == "failed"


def test_verify_merged_uses_github_pr_state() -> None:
    calls: list[list[str]] = []

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {"state": "MERGED", "mergedAt": "2026-07-28T20:00:00Z"}
            ),
            stderr="",
        )

    assert drain.verify_merged(
        "https://github.com/o/r/pull/12",
        runner=runner,
    )
    assert calls[0][:3] == ["gh", "pr", "view"]


def test_verify_merged_rejects_invalid_url_or_nonmerged_state() -> None:
    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps({"state": "OPEN", "mergedAt": None}),
            stderr="",
        )

    assert not drain.verify_merged("-", runner=runner)
    assert not drain.verify_merged(
        "https://github.com/o/r/pull/12",
        runner=runner,
    )


def test_verify_merged_rejects_wrong_repo_or_pre_run_merge(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    def runner(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if command[:2] == ["git", "-C"]:
            return subprocess.CompletedProcess(
                command,
                0,
                stdout="https://github.com/o/r.git\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            command,
            0,
            stdout=json.dumps(
                {"state": "MERGED", "mergedAt": "2026-07-28T19:00:00Z"}
            ),
            stderr="",
        )

    assert not drain.verify_merged(
        "https://github.com/other/repo/pull/12",
        repo=repo,
        started_at="2026-07-28T18:00:00-07:00",
        runner=runner,
    )
    assert not drain.verify_merged(
        "https://github.com/o/r/pull/12",
        repo=repo,
        started_at="2026-07-28T18:00:00-07:00",
        runner=runner,
    )


def test_lock_rejects_second_controller_and_allows_explicit_recovery(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "supervisor.lock"
    first = drain.RunLock(lock_path, recover=False)
    first.acquire()

    with pytest.raises(RuntimeError):
        drain.RunLock(lock_path, recover=False).acquire()
    with pytest.raises(RuntimeError):
        drain.RunLock(lock_path, recover=True).acquire()

    first.release()
    lock_path.write_text('{"pid": 99999999}\n', encoding="utf-8")
    recovered = drain.RunLock(lock_path, recover=True)
    recovered.acquire()
    recovered.release()
    assert not lock_path.exists()


@pytest.mark.skipif(os.name != "nt", reason="Windows lock recovery regression")
def test_pid_probe_detects_detached_unrelated_live_process() -> None:
    flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
    launcher_code = (
        "import subprocess,sys; "
        "p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],"
        f"creationflags={flags}); "
        "print(p.pid)"
    )
    launched = subprocess.run(
        [sys.executable, "-c", launcher_code],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    )
    pid = int(launched.stdout.strip())
    try:
        assert drain._pid_is_alive(pid)
    finally:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )


def test_interruptible_wait_observes_stop_without_full_interval(
    tmp_path: Path,
) -> None:
    stop = tmp_path / "supervisor.stop"
    sleeps: list[float] = []

    def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        stop.write_text("stop\n", encoding="utf-8")

    reason = drain.wait_interruptibly(
        stop_file=stop,
        seconds=1800,
        deadline_monotonic=10_000,
        monotonic=lambda: 0,
        sleep=fake_sleep,
    )

    assert reason == "stop-requested"
    assert sleeps == [drain.STOP_POLL_SECONDS]


@pytest.mark.parametrize(
    ("returncode", "text", "expected"),
    [
        (127, "[peer_agent] ERROR: CLI not launchable", "fatal"),
        (2, "[peer_agent] ERROR: unauthorized login", "transient"),
        (2, "[peer_agent] ERROR: rate limit reached", "transient"),
        (2, "[peer_agent] ERROR: authentication required", "transient"),
        (2, "[peer_agent] ERROR: authority resolver crashed", "failure"),
        (124, "[peer_agent] ERROR: exceeded timeout", "failure"),
        (2, "[peer_agent] ERROR: unexpected provider crash", "failure"),
    ],
)
def test_peer_failure_taxonomy(
    returncode: int,
    text: str,
    expected: str,
) -> None:
    assert drain.classify_peer_failure(returncode, text) == expected


def test_fourth_transient_becomes_a_failure_strike() -> None:
    state = _state(consecutive_transients=3)

    drain.apply_peer_failure(state, category="transient", returncode=2)

    assert state["consecutive_transients"] == 4
    assert state["consecutive_failures"] == 1
    assert state["status"] == "transient-failure"


def test_budget_reason_is_terminal() -> None:
    state = _state(completed_slices=3, consecutive_failures=0)

    assert (
        drain.budget_reason(
            state,
            now_monotonic=100,
            deadline_monotonic=90,
            max_slices=8,
            max_failures=2,
        )
        == "runtime-budget"
    )
    assert (
        drain.budget_reason(
            state,
            now_monotonic=50,
            deadline_monotonic=90,
            max_slices=3,
            max_failures=2,
        )
        == "slice-budget"
    )


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("runtime-budget", 0),
        ("slice-budget", 0),
        ("stop-requested", 0),
        ("dry-run", 0),
        ("merged", 0),
        ("partial", 0),
        ("blocked", 0),
        ("idle", 0),
        ("worker-failed", 2),
        ("invalid-result", 2),
        ("invalid-blocked-result", 2),
        ("invalid-duplicate-merge", 2),
        ("transient-provider-error", 2),
        ("transient-failure", 2),
        ("fatal-peer-error", 2),
        ("failure-budget", 2),
        ("merge-verification-failed", 2),
    ],
)
def test_terminal_exit_code_distinguishes_clean_and_failed_stops(
    status: str,
    expected: int,
) -> None:
    assert drain.exit_code_for_status(status) == expected


def test_dry_run_writes_state_and_prompt_without_dispatch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(0, 0, 0),
            hints=(),
        ),
    )

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--dry-run",
            "--hours",
            "1",
            "--max-slices",
            "1",
        ]
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    prompts = list((run_dir / "prompts").glob("*.md"))
    assert exit_code == 0
    assert state["status"] == "dry-run"
    assert len(prompts) == 1
    assert not list((run_dir / "results").glob("*.md"))


def test_default_run_directory_is_relative_to_repo(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(0, 0, 0),
            hints=(),
        ),
    )

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--dry-run",
            "--hours",
            "1",
            "--max-slices",
            "1",
        ]
    )

    assert exit_code == 0
    assert (repo / "output" / "openspec-drain" / "state.json").exists()


def test_stop_default_run_directory_is_relative_to_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    exit_code = drain.main(["stop", "--repo", str(repo)])

    assert exit_code == 0
    assert (repo / "output" / "openspec-drain" / "supervisor.stop").exists()


def test_once_mode_drives_dispatch_parse_and_merge_verification(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"

    def fake_dispatch(
        *,
        args: object,
        prompt_path: Path,
        result_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        del args, prompt_path
        result_path.write_text(
            "done\n"
            "DRAIN_RESULT: MERGED target https://github.com/o/r/pull/12\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(drain, "_dispatch", fake_dispatch)
    monkeypatch.setattr(drain, "verify_merged", lambda _url, **_kwargs: True)
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(0, 0, 0),
            hints=(),
        ),
    )

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--once",
            "--hours",
            "1",
            "--max-slices",
            "1",
        ]
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert state["completed_slices"] == 1
    assert state["status"] == "merged"


def test_run_rejects_already_consumed_merged_pr_without_counting_slice(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    pr = "https://github.com/o/r/pull/12"
    initial_state = _state(
        attempts=0,
        last_consumed_attempt=0,
        completed_slices=1,
        merged_prs=[pr],
    )
    monkeypatch.setattr(drain, "_new_state", lambda _args: initial_state)
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: _snapshot_with_blocked(),
    )

    def fake_dispatch(
        *,
        args: object,
        prompt_path: Path,
        result_path: Path,
    ) -> subprocess.CompletedProcess[str]:
        del args, prompt_path
        result_path.write_text(
            f"DRAIN_RESULT: MERGED old-target {pr}\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(drain, "_dispatch", fake_dispatch)

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--once",
            "--hours",
            "1",
            "--max-slices",
            "3",
        ]
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert state["completed_slices"] == 1
    assert state["consecutive_failures"] == 1
    assert state["last_result"]["status"] == "INVALID_DUPLICATE_MERGE"
    assert state["merged_prs"] == [pr]


def test_run_dispatches_inside_mechanically_admitted_lane(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wf-drain-fast-target"
    worktree.mkdir()
    run_dir = tmp_path / "run"
    hint = drain.CandidateHint(
        classification="CLAIMABLE",
        task_label="target",
        files=("x.py",),
        line_no=1,
        status="pending",
    )
    admission = drain.Admission(
        target="target",
        task_label="target",
        worktree=worktree,
        branch="drain/fast/target",
    )
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(claimable=1, stale=0, owned=0),
            hints=(hint,),
            blocked_targets=frozenset({"target"}),
        ),
    )
    monkeypatch.setattr(drain, "admit_candidate", lambda **_kwargs: admission)

    def fake_dispatch(
        *,
        args: object,
        prompt_path: Path,
        result_path: Path,
        worker_cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        del args
        assert worker_cwd == worktree
        assert "already admitted and claimed" in prompt_path.read_text(
            encoding="utf-8"
        )
        result_path.write_text(
            "preserved\nDRAIN_RESULT: BLOCKED target -\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(drain, "_dispatch", fake_dispatch)

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--hours",
            "1",
            "--max-slices",
            "1",
            "--once",
        ]
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert state["admission"] is None
    assert state["recent_blocked"] == ["target"]
    assert state["status"] == "blocked"


def test_run_cools_down_without_dispatch_when_recent_blockers_consume_hints(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"
    hint = drain.CandidateHint(
        classification="CLAIMABLE",
        task_label="blocked target",
        files=("x.py",),
        line_no=1,
        status="pending",
    )
    initial_state = _state(
        provider="codex",
        model=None,
        attempts=0,
        last_consumed_attempt=0,
        consecutive_transients=0,
        consecutive_partial_target=None,
        consecutive_partials=0,
        admission=None,
        recent_blocked=["blocked-target"],
    )
    monkeypatch.setattr(drain, "_new_state", lambda _args: initial_state)
    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: drain.CandidateSnapshot(
            pressure=drain.CandidatePressure(claimable=1, stale=0, owned=0),
            hints=(hint,),
            blocked_targets=frozenset({"blocked-target"}),
        ),
    )
    monkeypatch.setattr(
        drain,
        "_dispatch",
        lambda **_kwargs: pytest.fail(
            "filtered recent blocker must not launch a no-hint worker"
        ),
    )

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--hours",
            "1",
            "--max-slices",
            "1",
            "--once",
        ]
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert exit_code == 0
    assert state["status"] == "blocked-cooldown"
    assert state["last_result"] == {
        "status": "BLOCKED_COOLDOWN",
        "attempt": 1,
        "claimable": 1,
        "stale": 0,
    }
    assert not list((run_dir / "prompts").glob("*.md"))


def test_run_rejects_blocked_when_current_main_refresh_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    worktree = tmp_path / "wf-drain-fast-target"
    worktree.mkdir()
    run_dir = tmp_path / "run"
    hint = drain.CandidateHint(
        classification="CLAIMABLE",
        task_label="target",
        files=("x.py",),
        line_no=1,
        status="pending",
    )
    admission = drain.Admission(
        target="target",
        task_label="target",
        worktree=worktree,
        branch="drain/fast/target",
    )
    snapshots = iter(
        [
            drain.CandidateSnapshot(
                pressure=drain.CandidatePressure(claimable=1, stale=0, owned=0),
                hints=(hint,),
            ),
            RuntimeError("origin fetch failed"),
        ]
    )

    def inspect(**_kwargs: object) -> drain.CandidateSnapshot:
        value = next(snapshots)
        if isinstance(value, RuntimeError):
            raise value
        return value

    monkeypatch.setattr(drain, "inspect_current_main_snapshot", inspect)
    monkeypatch.setattr(drain, "admit_candidate", lambda **_kwargs: admission)

    def fake_dispatch(
        *,
        args: object,
        prompt_path: Path,
        result_path: Path,
        worker_cwd: Path,
    ) -> subprocess.CompletedProcess[str]:
        del args, prompt_path
        assert worker_cwd == worktree
        result_path.write_text(
            "private blocker\nDRAIN_RESULT: BLOCKED target -\n",
            encoding="utf-8",
        )
        return subprocess.CompletedProcess([], 0, stdout="", stderr="")

    monkeypatch.setattr(drain, "_dispatch", fake_dispatch)

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--hours",
            "1",
            "--max-slices",
            "1",
            "--once",
        ]
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert state["admission"]["target"] == "target"
    assert state["resume_target"] == "target"
    assert state["recent_blocked"] == []
    assert state["consecutive_failures"] == 1
    assert state["last_result"]["status"] == "INVALID_BLOCKED_RESULT"
    assert state["status"] == "invalid-blocked-result"


def test_run_does_not_dispatch_when_current_main_snapshot_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"

    monkeypatch.setattr(
        drain,
        "inspect_current_main_snapshot",
        lambda **_kwargs: (_ for _ in ()).throw(
            RuntimeError("origin fetch failed")
        ),
    )
    monkeypatch.setattr(
        drain,
        "_dispatch",
        lambda **_kwargs: pytest.fail(
            "worker must not dispatch without current-main snapshot"
        ),
    )

    exit_code = drain.main(
        [
            "run",
            "--repo",
            str(repo),
            "--run-dir",
            str(run_dir),
            "--hours",
            "1",
            "--max-slices",
            "1",
            "--once",
        ]
    )

    state = json.loads((run_dir / "state.json").read_text(encoding="utf-8"))
    assert exit_code == 2
    assert state["status"] == "candidate-snapshot-failed"
    assert state["consecutive_failures"] == 1
    assert state["last_result"]["status"] == "CANDIDATE_SNAPSHOT_FAILED"

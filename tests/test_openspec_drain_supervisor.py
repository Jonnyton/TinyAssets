from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "openspec_drain_supervisor.py"
SPEC = importlib.util.spec_from_file_location("openspec_drain_supervisor", SCRIPT)
assert SPEC is not None
drain = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = drain
SPEC.loader.exec_module(drain)


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
        "status": "running",
    }
    state.update(overrides)
    return state


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

    assert "drain-20260728-abc123" in prompt
    assert "provider-attempt-receipts" in prompt
    assert "MUST resume" in prompt
    assert "at most one PR" in prompt
    assert "at most 12 unchecked tasks" in prompt
    assert "blocked-a" in prompt
    assert "worktree_status.py" in prompt and "90 seconds" in prompt
    assert "not reliably OS-sandboxed" in prompt
    assert prompt.rstrip().endswith(
        "DRAIN_RESULT: <MERGED|PARTIAL|BLOCKED|NO_CANDIDATE|FAILED> "
        "<target-or-dash> <PR-url-or-dash>"
    )


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


def test_dry_run_writes_state_and_prompt_without_dispatch(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_dir = tmp_path / "run"

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


def test_default_run_directory_is_relative_to_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

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

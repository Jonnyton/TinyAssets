#!/usr/bin/env python3
"""Run bounded OpenSpec delivery slices through sequential fresh peer workers."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
PEER_AGENT = REPO_ROOT / "scripts" / "peer_agent.py"
STATUSES = {"MERGED", "PARTIAL", "BLOCKED", "NO_CANDIDATE", "FAILED"}
RESULT_PREFIX = "DRAIN_RESULT:"
RESULT_RE = re.compile(
    r"^DRAIN_RESULT: "
    r"(MERGED|PARTIAL|BLOCKED|NO_CANDIDATE|FAILED) "
    r"([A-Za-z0-9][A-Za-z0-9._-]*|-) "
    r"(https://github\.com/[^/\s]+/[^/\s]+/pull/[0-9]+|-)$"
)
PR_RE = re.compile(
    r"^https://github\.com/"
    r"(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+)/pull/(?P<number>[0-9]+)$"
)
TRANSIENT_PATTERNS = (
    "rate limit",
    "rate-limit",
    "unauthorized",
    "authentication",
    "auth/login",
    "login",
    "http 401",
)
STOP_POLL_SECONDS = 5.0
MAX_RECENT_BLOCKED = 12
MAX_FREE_TRANSIENTS = 3


@dataclass(frozen=True)
class DrainResult:
    status: str
    target: str
    pr: str


@dataclass(frozen=True)
class CandidatePressure:
    claimable: int
    stale: int


def parse_result(text: str) -> DrainResult:
    """Parse exactly one literal terminal marker on the final non-empty line."""
    if "[peer_agent] ERROR" in text:
        raise ValueError("peer-agent error block is not a drain result")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    markers = [line for line in lines if line.startswith(RESULT_PREFIX)]
    if len(markers) != 1 or not lines or markers[0] != lines[-1]:
        raise ValueError("expected exactly one final drain result marker")
    marker = markers[0]
    if any(character in marker for character in "<>|"):
        raise ValueError("placeholder or pipe syntax is not a literal result")
    match = RESULT_RE.fullmatch(marker)
    if not match:
        raise ValueError("malformed drain result marker")
    status, target, pr = match.groups()
    if status not in STATUSES:
        raise ValueError(f"unknown drain result status: {status}")
    if status in {"MERGED", "PARTIAL"} and (
        target == "-" or not PR_RE.fullmatch(pr)
    ):
        raise ValueError(f"{status} requires a target and GitHub PR URL")
    if status == "NO_CANDIDATE" and (target != "-" or pr != "-"):
        raise ValueError("NO_CANDIDATE requires dash placeholders")
    return DrainResult(status=status, target=target, pr=pr)


def inspect_candidate_pressure(
    *,
    repo: Path,
    provider: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> CandidatePressure:
    """Read canonical claim pressure without mutating coordination state."""
    command = [
        sys.executable,
        str(repo / "scripts" / "claim_check.py"),
        "--provider",
        provider,
        "--json",
    ]
    try:
        completed = runner(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        payload = json.loads(completed.stdout)
        counts = payload["counts"]
        claimable = int(counts["claimable"])
        stale = int(counts["stale"])
        if claimable < 0 or stale < 0:
            raise ValueError("candidate counts cannot be negative")
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        raise RuntimeError(f"claim pressure inspection failed: {exc}") from exc
    return CandidatePressure(claimable=claimable, stale=stale)


def no_candidate_rejection(
    result: DrainResult,
    pressure: CandidatePressure,
) -> str | None:
    """Explain why NO_CANDIDATE is not credible under current claim state."""
    if result.status != "NO_CANDIDATE":
        return None
    if pressure.claimable == 0 and pressure.stale == 0:
        return None
    return f"claimable={pressure.claimable} stale={pressure.stale}"


def begin_attempt(state: dict[str, Any]) -> int:
    """Persist honest active status before dispatching the next worker."""
    state["attempts"] += 1
    state["status"] = "running"
    return int(state["attempts"])


def build_worker_prompt(state: dict[str, Any], *, objective: str) -> str:
    """Return the fixed governance brief for one disposable drain worker."""
    identity = state["identity"]
    resume = state.get("resume_target")
    blocked = state.get("recent_blocked", [])
    resume_text = (
        f"STATUS may contain `{identity}` on `{resume}`. You MUST resume and "
        "finish/fold back that target before selecting any different work."
        if resume
        else (
            f"Before selection, search STATUS for an existing `{identity}` claim. "
            "If one exists, you MUST resume it first."
        )
    )
    blocked_text = ", ".join(blocked) if blocked else "(none)"
    return f"""You are one disposable TinyAssets OpenSpec drain worker.

Run identity: `{identity}`
Objective: {objective}
Recent blocked targets to avoid unless their blocker visibly cleared: {blocked_text}

{resume_text}

Authority and safety:
- You are write-capable and are not reliably OS-sandboxed on this Windows host.
  Safety comes from the clean worktree, exact claims, one-PR scope, review, CI,
  finite timeout, and preserved artifacts.
- Never edit the dirty/stale primary checkout. Fetch current origin/main and
  create one clean purpose-named sibling worktree plus `_PURPOSE.md` before edits.
- Follow AGENTS.md and the provider lifecycle gates. Cap the global
  `worktree_status.py` diagnostic at 90 seconds; if it times out, record that and
  continue only from the clean current-main worktree. Exact `claim_check.py`,
  `openspec_flow.py`, and provider-context checks still apply.
- Use the exact STATUS identity `{identity}`. Never mint a suffix. Resume your
  own existing claim before admitting another.

Delivery contract:
1. Run `python scripts/openspec_flow.py audit` and inspect STATUS/PLAN/dependencies.
2. Prove candidate exhaustion in this exact order before `NO_CANDIDATE`:
   a. resume this drain identity's existing claim;
   b. select a claimable finish-first STATUS row;
   c. reap and claim the first policy-qualified stale claim under AGENTS.md;
   d. freshness-check blocker/dependency labels against current main, PRs, and
      worktrees, removing only labels disproved by current evidence;
   e. promote one safe non-overlapping cross-cutting recovery task under
      AGENTS.md "Staying unblocked".
   `NO_CANDIDATE` is permitted only when claim_check JSON `claimable` and `stale`
   counts are both zero and no safe promotion exists. Never steal a live claim
   or invent work merely to stay busy.
3. Own one concrete acceptance contract and at most one PR.
4. For a grandfathered oversized change, deliver one recovery slice containing
   at most 12 unchecked tasks and prefer materially fewer within this worker.
   Work inside the existing change; do not mechanically fan out child changes.
5. Implement test-first, obtain required independent review, push the PR, and
   wait for required CI/auto-merge.
6. Verify the PR is actually merged. Sync/archive OpenSpec when complete and
   retire the STATUS row. If merge succeeded but foldback remains, report
   PARTIAL so the next fresh worker resumes it.
7. Preserve blockers honestly. Do not broaden into full-platform conversion.

Your last non-empty line must replace every placeholder in exactly this form.
Do not print any other DRAIN_RESULT line:
DRAIN_RESULT: <MERGED|PARTIAL|BLOCKED|NO_CANDIDATE|FAILED> <target-or-dash> <PR-url-or-dash>"""


def verify_merged(
    pr_url: str,
    *,
    repo: Path | None = None,
    started_at: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    """Verify squash-safe merged state through GitHub, not branch ancestry."""
    pr_match = PR_RE.fullmatch(pr_url)
    if not pr_match:
        return False
    try:
        if repo is not None:
            origin = runner(
                ["git", "-C", str(repo), "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                check=False,
                timeout=15,
            )
            expected_slug = _github_repo_slug(origin.stdout) if origin.returncode == 0 else None
            actual_slug = f"{pr_match.group('owner')}/{pr_match.group('repo')}".lower()
            if expected_slug is None or actual_slug != expected_slug:
                return False
        result = runner(
            ["gh", "pr", "view", pr_url, "--json", "state,mergedAt"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            return False
        payload = json.loads(result.stdout)
        if payload.get("state") != "MERGED" or not payload.get("mergedAt"):
            return False
        if started_at is not None and _parse_timestamp(payload["mergedAt"]) < _parse_timestamp(
            started_at
        ):
            return False
    except (
        OSError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ):
        return False
    return True


def _github_repo_slug(remote_url: str) -> str | None:
    match = re.search(
        r"github\.com(?::|/)(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
        remote_url.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return f"{match.group('owner')}/{match.group('repo')}".lower()


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def apply_result(
    state: dict[str, Any],
    result: DrainResult,
    *,
    merge_verified: bool = False,
) -> None:
    """Apply one parsed result to persistent controller state."""
    state["consecutive_transients"] = 0
    if result.status != "PARTIAL":
        state["consecutive_partial_target"] = None
        state["consecutive_partials"] = 0
    state["last_result"] = {
        "status": result.status,
        "target": result.target,
        "pr": result.pr,
    }
    if result.status in {"MERGED", "PARTIAL"} and not merge_verified:
        state["consecutive_failures"] += 1
        state["resume_target"] = result.target
        state["status"] = "merge-verification-failed"
        return
    if result.status == "MERGED":
        state["completed_slices"] += 1
        state["consecutive_failures"] = 0
        state["consecutive_partial_target"] = None
        state["consecutive_partials"] = 0
        state["resume_target"] = None
        state["status"] = "merged"
    elif result.status == "PARTIAL":
        repeated = state.get("consecutive_partial_target") == result.target
        partials = state.get("consecutive_partials", 0) + 1 if repeated else 1
        state["consecutive_partial_target"] = result.target
        state["consecutive_partials"] = partials
        state["resume_target"] = result.target
        if partials > 1:
            state["consecutive_failures"] += 1
            state["status"] = "partial-stalled"
        else:
            state["consecutive_failures"] = 0
            state["status"] = "partial"
    elif result.status == "BLOCKED":
        blocked = [
            target
            for target in state.get("recent_blocked", [])
            if target != result.target
        ]
        if result.target != "-":
            blocked.append(result.target)
        state["recent_blocked"] = blocked[-MAX_RECENT_BLOCKED:]
        state["resume_target"] = None
        state["consecutive_failures"] = 0
        state["status"] = "blocked"
    elif result.status == "NO_CANDIDATE":
        state["consecutive_failures"] = 0
        state["status"] = "idle"
    else:
        state["consecutive_failures"] += 1
        state["status"] = "failed"


def classify_peer_failure(returncode: int, text: str) -> str:
    """Classify peer launcher failures into fatal, transient, or budgeted."""
    if returncode == 127:
        return "fatal"
    lowered = text.lower()
    if any(pattern in lowered for pattern in TRANSIENT_PATTERNS):
        return "transient"
    return "failure"


def apply_peer_failure(
    state: dict[str, Any],
    *,
    category: str,
    returncode: int,
) -> None:
    """Apply a launcher failure with a bounded transient retry allowance."""
    state["last_result"] = {
        "status": "PEER_ERROR",
        "category": category,
        "returncode": returncode,
    }
    if category == "fatal":
        state["status"] = "fatal-peer-error"
        return
    if category == "transient":
        transients = state.get("consecutive_transients", 0) + 1
        state["consecutive_transients"] = transients
        if transients > MAX_FREE_TRANSIENTS:
            state["consecutive_failures"] += 1
            state["status"] = "transient-failure"
        else:
            state["status"] = "transient-provider-error"
        return
    state["consecutive_transients"] = 0
    state["consecutive_failures"] += 1
    state["status"] = "worker-failed"


def budget_reason(
    state: dict[str, Any],
    *,
    now_monotonic: float,
    deadline_monotonic: float,
    max_slices: int,
    max_failures: int,
) -> str | None:
    if now_monotonic >= deadline_monotonic:
        return "runtime-budget"
    if state["completed_slices"] >= max_slices:
        return "slice-budget"
    if state["consecutive_failures"] >= max_failures:
        return "failure-budget"
    return None


def exit_code_for_status(status: str) -> int:
    failed = {
        "worker-failed",
        "invalid-result",
        "transient-provider-error",
        "transient-failure",
        "fatal-peer-error",
        "failure-budget",
        "merge-verification-failed",
    }
    return 2 if status in failed else 0


def wait_interruptibly(
    *,
    stop_file: Path,
    seconds: float,
    deadline_monotonic: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> str:
    """Wait in short polls so a stop request is observed promptly."""
    end = min(deadline_monotonic, monotonic() + max(0.0, seconds))
    while monotonic() < end:
        if stop_file.exists():
            return "stop-requested"
        sleep(min(STOP_POLL_SECONDS, max(0.0, end - monotonic())))
    return "deadline" if monotonic() >= deadline_monotonic else "interval"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


class RunLock:
    """Exclusive run-directory lock with explicit stale-lock recovery."""

    def __init__(self, path: Path, *, recover: bool) -> None:
        self.path = path
        self.recover = recover
        self.acquired = False

    def acquire(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.recover and self.path.exists():
            try:
                lock_data = json.loads(self.path.read_text(encoding="utf-8"))
                lock_pid = int(lock_data["pid"])
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                lock_pid = -1
            if lock_pid > 0 and _pid_is_alive(lock_pid):
                raise RuntimeError(
                    f"controller lock belongs to live pid {lock_pid}: {self.path}"
                )
            self.path.unlink(missing_ok=True)
        try:
            descriptor = os.open(
                self.path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as exc:
            raise RuntimeError(
                f"controller lock exists: {self.path}; inspect status and use "
                "--recover-stale-lock only after proving no controller is live"
            ) from exc
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"pid": os.getpid(), "acquired_at": _now_iso()}, handle)
            handle.write("\n")
        self.acquired = True

    def release(self) -> None:
        if self.acquired:
            self.path.unlink(missing_ok=True)
            self.acquired = False


def _now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _pid_is_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    if os.name == "nt":
        return _windows_pid_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _windows_pid_is_alive(pid: int) -> bool:
    """Probe a Windows PID without console-control signal semantics."""
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    handle = kernel32.OpenProcess(
        process_query_limited_information,
        False,
        pid,
    )
    if not handle:
        error = ctypes.get_last_error()
        return error != 87
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _new_state(args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now().astimezone()
    run_id = f"{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:6]}"
    return {
        "run_id": run_id,
        "identity": f"drain-{run_id}",
        "provider": args.provider,
        "model": args.model,
        "started_at": now.isoformat(timespec="seconds"),
        "deadline_at": (now + timedelta(hours=args.hours)).isoformat(
            timespec="seconds"
        ),
        "completed_slices": 0,
        "consecutive_failures": 0,
        "consecutive_transients": 0,
        "consecutive_partial_target": None,
        "consecutive_partials": 0,
        "attempts": 0,
        "last_result": None,
        "resume_target": None,
        "recent_blocked": [],
        "status": "starting",
    }


def _log(run_dir: Path, message: str) -> None:
    line = f"{_now_iso()} {message}"
    print(line, flush=True)
    with (run_dir / "supervisor.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def _dispatch(
    *,
    args: argparse.Namespace,
    prompt_path: Path,
    result_path: Path,
) -> subprocess.CompletedProcess[str]:
    command = [
        sys.executable,
        str(PEER_AGENT),
        args.provider,
        "--write",
        "--cwd",
        str(args.repo),
        "--timeout",
        str(args.worker_timeout),
        "--prompt-file",
        str(prompt_path),
        "--out",
        str(result_path),
    ]
    if args.model:
        command.extend(["--model", args.model])
    process = subprocess.Popen(
        command,
        cwd=args.repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        stdout, stderr = process.communicate(timeout=args.worker_timeout + 90)
        return subprocess.CompletedProcess(
            command,
            process.returncode,
            stdout=stdout,
            stderr=stderr,
        )
    except subprocess.TimeoutExpired as exc:
        _terminate_process_tree(process)
        try:
            stdout, stderr = process.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            if process.stdout:
                process.stdout.close()
            if process.stderr:
                process.stderr.close()
            process.wait(timeout=10)
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
        return subprocess.CompletedProcess(
            command,
            124,
            stdout=stdout or "",
            stderr=stderr or "outer supervisor timeout",
        )


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    """Stop a timed-out launcher and its descendants where the OS supports it."""
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            pass
        if process.poll() is None:
            process.kill()
    else:
        process.kill()


def _run(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    state_path = run_dir / "state.json"
    stop_file = run_dir / "supervisor.stop"
    prompts_dir = run_dir / "prompts"
    results_dir = run_dir / "results"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    results_dir.mkdir(parents=True, exist_ok=True)
    lock = RunLock(
        run_dir / "supervisor.lock",
        recover=args.recover_stale_lock,
    )
    try:
        lock.acquire()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    try:
        if stop_file.exists():
            if not args.clear_stop:
                print(
                    f"stop marker exists: {stop_file}; use --clear-stop to start",
                    file=sys.stderr,
                )
                return 2
            stop_file.unlink()

        if state_path.exists():
            if not args.resume:
                print(
                    f"state already exists: {state_path}; use --resume or a new run dir",
                    file=sys.stderr,
                )
                return 2
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state.setdefault("consecutive_transients", 0)
            state.setdefault("consecutive_partial_target", None)
            state.setdefault("consecutive_partials", 0)
            if state["provider"] != args.provider or state.get("model") != args.model:
                print("resume provider/model must match persisted state", file=sys.stderr)
                return 2
            now = datetime.now().astimezone()
            state["deadline_at"] = (now + timedelta(hours=args.hours)).isoformat(
                timespec="seconds"
            )
            state["status"] = "resuming"
        else:
            state = _new_state(args)

        deadline_monotonic = time.monotonic() + args.hours * 3600
        state["status"] = "running"
        atomic_write_json(state_path, state)

        while True:
            reason = budget_reason(
                state,
                now_monotonic=time.monotonic(),
                deadline_monotonic=deadline_monotonic,
                max_slices=args.max_slices,
                max_failures=args.max_failures,
            )
            if reason:
                state["status"] = reason
                break
            if stop_file.exists():
                state["status"] = "stop-requested"
                break

            attempt = begin_attempt(state)
            prompt_path = prompts_dir / f"{attempt:03d}.md"
            result_path = results_dir / f"{attempt:03d}.md"
            prompt_path.write_text(
                build_worker_prompt(state, objective=args.objective) + "\n",
                encoding="utf-8",
            )
            atomic_write_json(state_path, state)

            if args.dry_run:
                state["status"] = "dry-run"
                break

            _log(run_dir, f"dispatch attempt={attempt} provider={args.provider}")
            completed = _dispatch(
                args=args,
                prompt_path=prompt_path,
                result_path=result_path,
            )
            text = (
                result_path.read_text(encoding="utf-8", errors="replace")
                if result_path.exists()
                else f"{completed.stdout}\n{completed.stderr}"
            )
            if completed.returncode != 0:
                category = classify_peer_failure(completed.returncode, text)
                apply_peer_failure(
                    state,
                    category=category,
                    returncode=completed.returncode,
                )
                if category == "fatal":
                    atomic_write_json(state_path, state)
                    break
                atomic_write_json(state_path, state)
                if args.once:
                    break
                if category == "failure":
                    continue
                wait_interruptibly(
                    stop_file=stop_file,
                    seconds=args.idle_minutes * 60,
                    deadline_monotonic=deadline_monotonic,
                )
                continue

            try:
                result = parse_result(text)
            except ValueError as exc:
                state["consecutive_transients"] = 0
                state["consecutive_failures"] += 1
                state["last_result"] = {
                    "status": "INVALID_RESULT",
                    "error": str(exc),
                }
                state["status"] = "invalid-result"
                atomic_write_json(state_path, state)
                if args.once:
                    break
                continue

            if result.status == "NO_CANDIDATE":
                try:
                    pressure = inspect_candidate_pressure(
                        repo=args.repo,
                        provider=state["identity"],
                    )
                    rejection = no_candidate_rejection(result, pressure)
                except RuntimeError as exc:
                    rejection = str(exc)
                if rejection:
                    state["consecutive_transients"] = 0
                    state["consecutive_failures"] += 1
                    state["last_result"] = {
                        "status": "INVALID_NO_CANDIDATE",
                        "error": rejection,
                    }
                    state["status"] = "invalid-result"
                    atomic_write_json(state_path, state)
                    _log(
                        run_dir,
                        f"reject attempt={attempt} NO_CANDIDATE {rejection}",
                    )
                    if args.once:
                        break
                    continue

            verified = (
                verify_merged(
                    result.pr,
                    repo=args.repo,
                    started_at=state["started_at"],
                )
                if result.status in {"MERGED", "PARTIAL"}
                else False
            )
            apply_result(state, result, merge_verified=verified)
            atomic_write_json(state_path, state)
            _log(
                run_dir,
                f"result attempt={attempt} status={state['status']} "
                f"target={result.target} pr={result.pr}",
            )
            if args.once:
                break
            if result.status == "MERGED" and verified:
                continue
            if (
                result.status == "PARTIAL"
                and verified
                and state["status"] == "partial"
            ):
                continue
            if result.status in {"BLOCKED", "NO_CANDIDATE"} or (
                result.status == "PARTIAL" and verified
            ):
                wait_interruptibly(
                    stop_file=stop_file,
                    seconds=args.idle_minutes * 60,
                    deadline_monotonic=deadline_monotonic,
                )

        state["ended_at"] = _now_iso()
        atomic_write_json(state_path, state)
        _log(run_dir, f"supervisor exit status={state['status']}")
        return exit_code_for_status(state["status"])
    finally:
        lock.release()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run = subparsers.add_parser("run", help="run the bounded sequential drain")
    run.add_argument("--repo", type=Path, default=Path.cwd())
    run.add_argument("--run-dir", type=Path)
    run.add_argument("--provider", choices=["codex", "claude"], default="codex")
    run.add_argument("--model")
    run.add_argument("--objective", default="Drain current OpenSpec delivery debt.")
    run.add_argument("--hours", type=float, default=8.0)
    run.add_argument("--max-slices", type=int, default=8)
    run.add_argument("--worker-timeout", type=int, default=5400)
    run.add_argument("--max-failures", type=int, default=2)
    run.add_argument("--idle-minutes", type=float, default=30.0)
    run.add_argument("--once", action="store_true")
    run.add_argument("--dry-run", action="store_true")
    run.add_argument("--resume", action="store_true")
    run.add_argument("--clear-stop", action="store_true")
    run.add_argument("--recover-stale-lock", action="store_true")
    status = subparsers.add_parser("status", help="print persisted run state")
    status.add_argument("--repo", type=Path, default=Path.cwd())
    status.add_argument("--run-dir", type=Path)
    stop = subparsers.add_parser("stop", help="request a graceful stop")
    stop.add_argument("--repo", type=Path, default=Path.cwd())
    stop.add_argument("--run-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "status":
        run_dir = args.run_dir or args.repo / "output" / "openspec-drain"
        state_path = run_dir.resolve() / "state.json"
        if not state_path.exists():
            print(f"no drain state: {state_path}", file=sys.stderr)
            return 1
        print(state_path.read_text(encoding="utf-8"), end="")
        return 0
    if args.command == "stop":
        run_dir = args.run_dir or args.repo / "output" / "openspec-drain"
        stop_file = run_dir.resolve() / "supervisor.stop"
        stop_file.parent.mkdir(parents=True, exist_ok=True)
        stop_file.write_text(f"stop requested {_now_iso()}\n", encoding="utf-8")
        print(f"stop requested: {stop_file}")
        return 0
    for name in (
        "hours",
        "max_slices",
        "worker_timeout",
        "max_failures",
        "idle_minutes",
    ):
        if getattr(args, name) <= 0:
            print(f"--{name.replace('_', '-')} must be positive", file=sys.stderr)
            return 2
    if not args.repo.resolve().is_dir():
        print(f"repo is not a directory: {args.repo}", file=sys.stderr)
        return 2
    args.repo = args.repo.resolve()
    if args.run_dir is None:
        args.run_dir = args.repo / "output" / "openspec-drain"
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())

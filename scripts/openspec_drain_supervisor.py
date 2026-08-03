#!/usr/bin/env python3
"""Run bounded OpenSpec delivery slices through sequential fresh peer workers."""

from __future__ import annotations

import argparse
import hashlib
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
OPENSPEC_FLOW = REPO_ROOT / "scripts" / "openspec_flow.py"
STATUSES = {"MERGED", "PARTIAL", "BLOCKED", "NO_CANDIDATE", "FAILED"}
RESULT_PREFIX = "DRAIN_RESULT:"
RESULT_TARGET_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._-]{0,239}$")
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
RESULT_POLL_SECONDS = 1.0
MAX_RECENT_BLOCKED = 12
MAX_FREE_TRANSIENTS = 3
MAX_CANDIDATE_HINTS = 5
DRAIN_CODEX_EFFORT = "medium"
TARGET_IDENTITY_VERSION = 3


@dataclass(frozen=True)
class DrainResult:
    status: str
    target: str
    pr: str


@dataclass(frozen=True)
class CandidatePressure:
    claimable: int
    stale: int
    owned: int
    refinable: int = 0


@dataclass(frozen=True)
class CandidateHint:
    classification: str
    task_label: str
    files: tuple[str, ...]
    line_no: int = 0
    status: str = ""


@dataclass(frozen=True)
class CandidateSnapshot:
    pressure: CandidatePressure
    hints: tuple[CandidateHint, ...]
    blocked_targets: frozenset[str] = frozenset()
    blocked_hints: tuple[CandidateHint, ...] = ()


@dataclass(frozen=True)
class Admission:
    target: str
    task_label: str
    worktree: Path
    branch: str


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
    payload = marker[len(RESULT_PREFIX) :].strip()
    status, separator, remainder = payload.partition(" ")
    target_text, target_separator, pr = remainder.rpartition(" ")
    if not separator or not target_separator or not target_text or not pr:
        raise ValueError("malformed drain result marker")
    if status not in STATUSES:
        raise ValueError(f"unknown drain result status: {status}")
    if pr != "-" and not PR_RE.fullmatch(pr):
        raise ValueError("malformed drain result PR")
    if target_text == "-":
        target = "-"
    elif RESULT_TARGET_RE.fullmatch(target_text):
        target = _slugify(target_text)
    else:
        raise ValueError("malformed drain result target")
    if status in {"MERGED", "PARTIAL"} and (
        target == "-" or not PR_RE.fullmatch(pr)
    ):
        raise ValueError(f"{status} requires a target and GitHub PR URL")
    if status == "NO_CANDIDATE" and (target != "-" or pr != "-"):
        raise ValueError("NO_CANDIDATE requires dash placeholders")
    return DrainResult(status=status, target=target, pr=pr)


def _candidate_hint(row: dict[str, Any], classification: str) -> CandidateHint:
    task_label = row.get("task_label")
    files = row.get("files", [])
    if not isinstance(task_label, str) or not task_label.strip():
        raise TypeError("candidate task_label must be a non-empty string")
    if not isinstance(files, list) or not all(
        isinstance(path, str) for path in files
    ):
        raise TypeError("candidate files must be a string list")
    return CandidateHint(
        classification=classification,
        task_label=" ".join(task_label.split()),
        files=tuple(" ".join(path.split())[:160] for path in files[:4]),
        line_no=int(row.get("line_no", 0)),
        status=str(row.get("status", "")),
    )


def _slugify(value: str, *, limit: int = 48) -> str:
    normalized_label = " ".join(value.split()).casefold()
    slug = re.sub(r"[^a-z0-9]+", "-", normalized_label).strip("-")
    slug = slug or "candidate"
    if len(slug) <= limit:
        return slug
    # Hash the complete label before its punctuation is folded into the
    # readable prefix. Distinct labels must not inherit one another's blocker.
    digest = hashlib.sha256(normalized_label.encode("utf-8")).hexdigest()[:8]
    if limit <= len(digest):
        return digest[:limit]
    prefix = slug[: limit - len(digest) - 1].rstrip("-")
    return f"{prefix}-{digest}" if prefix else digest[:limit]


def migrate_target_identities(state: dict[str, Any]) -> bool:
    """Rekey pre-hash admission state and release incompatible cooldowns."""
    try:
        version = int(state.get("target_identity_version", 1))
    except (TypeError, ValueError):
        version = 1
    if version >= TARGET_IDENTITY_VERSION:
        return False

    admission = state.get("admission")
    if isinstance(admission, dict):
        task_label = admission.get("task_label")
        old_target = admission.get("target")
        if isinstance(task_label, str) and isinstance(old_target, str):
            new_target = _slugify(" ".join(task_label.split()))
            admission["target"] = new_target
            if state.get("resume_target") == old_target:
                state["resume_target"] = new_target

    # Legacy entries contain only the old lossy slug, so they cannot be
    # rekeyed safely. Releasing them causes a harmless current-main retry.
    state["recent_blocked"] = []
    state["target_identity_version"] = TARGET_IDENTITY_VERSION
    return True


def _admission_command(
    command: list[str],
    *,
    cwd: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    timeout: int = 120,
) -> subprocess.CompletedProcess[str]:
    try:
        completed = runner(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"admission command timed out after {timeout}s: {' '.join(command)}"
        ) from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(
            f"admission command could not run: {' '.join(command)}: {exc}"
        ) from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(
            f"admission command failed ({completed.returncode}): "
            f"{' '.join(command)}: {detail}"
        )
    return completed


def _best_effort_admission_cleanup(
    command: list[str],
    *,
    cwd: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    timeout: int,
) -> None:
    try:
        runner(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        pass


def _set_status_claim(
    status_path: Path,
    *,
    hint: CandidateHint,
    status: str,
    expected_status: str | None = None,
) -> None:
    lines = status_path.read_text(encoding="utf-8").splitlines()
    if hint.line_no <= 0 or hint.line_no > len(lines):
        raise RuntimeError(f"candidate line is outside STATUS.md: {hint.line_no}")
    index = hint.line_no - 1
    cells = lines[index].split("|")
    if len(cells) < 6:
        raise RuntimeError(f"candidate line is not a four-cell table row: {hint.line_no}")
    current = cells[4].strip()
    expected = expected_status or hint.status
    if current != expected:
        raise RuntimeError(
            f"candidate status changed before admission: {current!r} != {expected!r}"
        )
    cells[4] = f" {status} "
    lines[index] = "|".join(cells)
    status_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def admission_lane(
    *,
    repo: Path,
    identity: str,
    target: str,
    attempt: int,
) -> tuple[Path, str]:
    """Derive the deterministic branch/worktree lane for one exact attempt."""
    if attempt < 1:
        raise ValueError("admission attempt must be positive")
    run_slug = _slugify(identity.removeprefix("drain-"), limit=32)
    attempt_slug = f"a{attempt:03d}"
    worktree = (
        repo.parent
        / f"wf-drain-{run_slug}-{target[:32]}-{attempt_slug}"
    )
    branch = f"drain/{run_slug}/{target}-{attempt_slug}"
    return worktree, branch


def admit_candidate(
    *,
    repo: Path,
    identity: str,
    hint: CandidateHint,
    attempt: int,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    today: str | None = None,
) -> Admission:
    """Mechanically prepare and claim one canonical candidate before dispatch."""
    if hint.classification not in {"CLAIMABLE", "STALE"}:
        raise RuntimeError(f"candidate cannot be mechanically admitted: {hint.classification}")
    if hint.line_no <= 0 or not hint.status:
        raise RuntimeError("candidate lacks canonical line/status metadata")
    date = today or datetime.now().astimezone().date().isoformat()
    target = _slugify(hint.task_label)
    worktree, branch = admission_lane(
        repo=repo,
        identity=identity,
        target=target,
        attempt=attempt,
    )

    clean = _admission_command(
        ["git", "-C", str(repo), "status", "--porcelain"],
        cwd=repo,
        runner=runner,
        timeout=30,
    )
    if clean.stdout.strip():
        raise RuntimeError("controller checkout is dirty; refusing admission")
    _admission_command(
        ["git", "-C", str(repo), "fetch", "--prune", "origin"],
        cwd=repo,
        runner=runner,
    )
    if worktree.exists():
        raise RuntimeError(f"admission worktree already exists: {worktree}")
    try:
        branch_check = runner(
            [
                "git",
                "-C",
                str(repo),
                "show-ref",
                "--verify",
                "--quiet",
                f"refs/heads/{branch}",
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeError(f"cannot inspect admission branch: {exc}") from exc
    if branch_check.returncode == 0:
        raise RuntimeError(f"admission branch already exists: {branch}")
    if branch_check.returncode != 1:
        raise RuntimeError(
            f"cannot inspect admission branch ({branch_check.returncode}): "
            f"{branch_check.stderr.strip()}"
        )
    try:
        _admission_command(
            [
                "git",
                "-C",
                str(repo),
                "worktree",
                "add",
                "-b",
                branch,
                str(worktree),
                "origin/main",
            ],
            cwd=repo,
            runner=runner,
        )
        _admission_command(
            [
                sys.executable,
                str(worktree / "scripts" / "provider_context_feed.py"),
                "--provider",
                identity,
                "--phase",
                "claim",
                "--limit",
                "10",
            ],
            cwd=worktree,
            runner=runner,
        )
        fresh_snapshot = inspect_candidate_snapshot(
            repo=worktree,
            provider=identity,
            runner=runner,
        )
        fresh_hint = next(
            (
                candidate
                for candidate in fresh_snapshot.hints
                if candidate.classification == hint.classification
                and candidate.task_label == hint.task_label
                and candidate.status == hint.status
            ),
            None,
        )
        if fresh_hint is None:
            raise RuntimeError(
                f"candidate is no longer admissible on current main: {hint.task_label}"
            )
        hint = fresh_hint
        (worktree / "_PURPOSE.md").write_text(
            "\n".join(
                [
                    "# Purpose",
                    "",
                    f"- Drain identity: `{identity}`",
                    f"- Assigned target: `{hint.task_label}`",
                    f"- Branch: `{branch}`",
                    f"- Worktree: `{worktree}`",
                    "- Review gate: independent review + required CI",
                    "- Publish route: one PR, then OpenSpec sync/archive foldback",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        status_path = worktree / "STATUS.md"
        if hint.classification == "STALE":
            reaped_status = f"reaped:{identity}:no-activity-24h"
            _set_status_claim(
                status_path,
                hint=hint,
                status=reaped_status,
            )
            _admission_command(
                ["git", "-C", str(worktree), "add", "STATUS.md"],
                cwd=worktree,
                runner=runner,
                timeout=30,
            )
            _admission_command(
                [
                    "git",
                    "-C",
                    str(worktree),
                    "commit",
                    "-m",
                    f"coord: reap stale {target} claim",
                ],
                cwd=worktree,
                runner=runner,
            )
        _set_status_claim(
            status_path,
            hint=hint,
            status=f"claimed:{identity} ACTIVE {date}",
            expected_status=(
                reaped_status if hint.classification == "STALE" else None
            ),
        )
        _admission_command(
            ["git", "-C", str(worktree), "add", "STATUS.md"],
            cwd=worktree,
            runner=runner,
            timeout=30,
        )
        _admission_command(
            [
                "git",
                "-C",
                str(worktree),
                "commit",
                "-m",
                f"coord: claim {target} for drain",
            ],
            cwd=worktree,
            runner=runner,
        )
    except Exception as exc:
        if worktree.exists():
            _best_effort_admission_cleanup(
                [
                    "git",
                    "-C",
                    str(repo),
                    "worktree",
                    "remove",
                    "--force",
                    str(worktree),
                ],
                cwd=repo,
                runner=runner,
                timeout=60,
            )
        _best_effort_admission_cleanup(
            ["git", "-C", str(repo), "branch", "-D", branch],
            cwd=repo,
            runner=runner,
            timeout=30,
        )
        if isinstance(exc, RuntimeError):
            raise
        raise RuntimeError(f"admission failed: {exc}") from exc
    return Admission(
        target=target,
        task_label=hint.task_label,
        worktree=worktree,
        branch=branch,
    )


def filter_recently_blocked_hints(
    hints: tuple[CandidateHint, ...],
    *,
    recent_blocked: list[str],
) -> tuple[CandidateHint, ...]:
    blocked = set(recent_blocked)
    return tuple(
        hint
        for hint in hints
        if hint.classification == "OWNED"
        or _slugify(hint.task_label) not in blocked
    )


def filter_recently_consumed_hints(
    hints: tuple[CandidateHint, ...],
    *,
    recent_consumed_targets: list[str],
) -> tuple[CandidateHint, ...]:
    """Exclude run-local targets whose canonical merge was already consumed."""

    consumed = set(recent_consumed_targets)
    return tuple(
        hint
        for hint in hints
        if _slugify(hint.task_label) not in consumed
    )


def reconcile_recent_blocked(
    recent_blocked: list[str],
    *,
    blocked_targets: frozenset[str],
) -> list[str]:
    """Drop run-local suppression as soon as current main clears the blocker."""
    return [target for target in recent_blocked if target in blocked_targets]


def should_cooldown_without_worker(
    *,
    pressure: CandidatePressure,
    candidate_hints: tuple[CandidateHint, ...],
    recent_blocked: list[str],
    recent_consumed_targets: list[str] | tuple[str, ...] = (),
    has_admission: bool,
) -> bool:
    """Avoid a no-hint worker when only run-local blocker filtering hid work."""
    consumed_only = (
        bool(recent_consumed_targets)
        and not candidate_hints
        and (
            pressure.owned > 0
            or pressure.claimable > 0
            or pressure.stale > 0
            or pressure.refinable > 0
        )
    )
    blocked_only = (
        not has_admission
        and bool(recent_blocked)
        and not candidate_hints
        and pressure.owned == 0
        and (
            pressure.claimable > 0
            or pressure.stale > 0
            or pressure.refinable > 0
        )
    )
    return not has_admission and (consumed_only or blocked_only)


def has_alternative_candidate(
    snapshot: CandidateSnapshot,
    *,
    recent_blocked: list[str],
    recent_consumed_targets: list[str] | tuple[str, ...] = (),
    current_target: str,
) -> bool:
    """Return whether a different eligible candidate remains after a block."""
    if current_target == "-":
        return False
    hints = filter_recently_blocked_hints(
        snapshot.hints,
        recent_blocked=recent_blocked,
    )
    hints = filter_recently_consumed_hints(
        hints,
        recent_consumed_targets=list(recent_consumed_targets),
    )
    return any(
        hint.classification in {"OWNED", "CLAIMABLE", "STALE", "REFINERY"}
        and _slugify(hint.task_label) != current_target
        for hint in hints
    )


def admission_result_rejection(
    result: DrainResult,
    admission: Admission,
) -> str | None:
    if result.status == "NO_CANDIDATE":
        return f"admitted={admission.target}"
    if result.target != admission.target:
        return f"assigned={admission.target} reported={result.target}"
    return None


def refinery_result_rejection(
    result: DrainResult,
    hint: CandidateHint,
) -> str | None:
    """Reject a coordination-only result outside its exact assignment."""
    target = _slugify(hint.task_label)
    if result.status == "MERGED":
        return "refinery cannot report MERGED"
    if result.status == "NO_CANDIDATE":
        return "refinery cannot report NO_CANDIDATE"
    if result.target != target:
        return f"assigned={target} reported={result.target}"
    return None


def refinery_continuation_rejection(
    assigned: CandidateHint,
    snapshot: CandidateSnapshot,
) -> str | None:
    """Reject coordination that did not expose claimable work in its boundary."""
    claimable = (
        hint for hint in snapshot.hints if hint.classification == "CLAIMABLE"
    )
    if any(
        left in right or right in left
        for hint in claimable
        for left in assigned.files
        for right in hint.files
    ):
        return None
    boundary = assigned.files[0] if assigned.files else assigned.task_label
    return (
        "merged refinery coordination did not expose claimable work in "
        f"{boundary}"
    )


def duplicate_merge_rejection(
    result: DrainResult,
    state: dict[str, Any],
) -> str | None:
    """Reject a previously consumed merge receipt before it counts again."""
    if result.status not in {"MERGED", "PARTIAL"}:
        return None
    receipt = canonical_pr_receipt(result.pr)
    consumed = {
        canonical_pr_receipt(pr)
        for pr in state.get("merged_prs", [])
        if isinstance(pr, str)
    }
    if receipt in consumed:
        return f"already-consumed={receipt}"
    return None


def inspect_candidate_snapshot(
    *,
    repo: Path,
    provider: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    max_hints: int = MAX_CANDIDATE_HINTS,
    status_ref: str | None = None,
) -> CandidateSnapshot:
    """Read ordered canonical candidates without mutating coordination state."""
    if max_hints < 0:
        raise ValueError("max_hints cannot be negative")
    command = [
        sys.executable,
        str(repo / "scripts" / "claim_check.py"),
        "--provider",
        provider,
        "--json",
    ]
    if status_ref is not None:
        command.extend(["--status-ref", status_ref])
    try:
        completed = runner(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        payload = json.loads(completed.stdout)
        counts = payload["counts"]
        claimable = int(counts["claimable"])
        stale = int(counts["stale"])
        in_flight = payload.get("in_flight", [])
        claimable_rows = payload.get("claimable", [])
        blocked_rows = payload.get("blocked", [])
        stale_rows = payload.get("stale", [])
        if not all(
            isinstance(rows, list)
            for rows in (in_flight, claimable_rows, blocked_rows, stale_rows)
        ):
            raise TypeError("candidate collections must be lists")
        if not all(
            isinstance(row, dict)
            for rows in (in_flight, claimable_rows, blocked_rows, stale_rows)
            for row in rows
        ):
            raise TypeError("candidate rows must be objects")
        unwrapped_blocked_rows = []
        for entry in blocked_rows:
            row = entry.get("row")
            if not isinstance(row, dict):
                raise TypeError("blocked candidate row must be an object")
            unwrapped_blocked_rows.append(row)
        unwrapped_stale_rows = []
        for entry in stale_rows:
            row = entry.get("row")
            if not isinstance(row, dict):
                raise TypeError("stale candidate row must be an object")
            unwrapped_stale_rows.append(row)
        owned = sum(
            1
            for row in in_flight
            if row.get("claimer") == provider
        )
        if claimable < 0 or stale < 0:
            raise ValueError("candidate counts cannot be negative")
        ordered_rows = [
            *((row, "OWNED") for row in in_flight if row.get("claimer") == provider),
            *((row, "CLAIMABLE") for row in claimable_rows),
            *((row, "STALE") for row in unwrapped_stale_rows),
        ]
        hints = tuple(
            _candidate_hint(row, classification)
            for row, classification in ordered_rows[:max_hints]
        )
        blocked_targets = frozenset(
            _slugify(_candidate_hint(row, "BLOCKED").task_label)
            for row in unwrapped_blocked_rows
        )
        blocked_hints = tuple(
            _candidate_hint(row, "REFINERY") for row in unwrapped_blocked_rows
        )
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        raise RuntimeError(f"claim pressure inspection failed: {exc}") from exc
    return CandidateSnapshot(
        pressure=CandidatePressure(
            claimable=claimable,
            stale=stale,
            owned=owned,
        ),
        hints=hints,
        blocked_targets=blocked_targets,
        blocked_hints=blocked_hints,
    )


def inspect_refinery_hints(
    *,
    repo: Path,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    status_ref: str,
) -> tuple[CandidateHint, ...]:
    """Return safe coordination-only targets from one exact OpenSpec snapshot."""
    command = [
        sys.executable,
        str(OPENSPEC_FLOW),
        "--repo",
        str(repo),
        "audit",
        "--json",
        "--ref",
        status_ref,
    ]
    try:
        completed = runner(
            command,
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
            timeout=60,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(detail or f"exit {completed.returncode}")
        payload = json.loads(completed.stdout)
        changes = payload["changes"]
        if not isinstance(changes, list) or not all(
            isinstance(change, dict) for change in changes
        ):
            raise TypeError("OpenSpec flow changes must be an object list")
        eligible: list[tuple[int, int, str, str]] = []
        order = {"complete-but-unarchived": 0, "untracked": 1}
        for change in changes:
            classification = change.get("classification")
            if classification not in order:
                continue
            owners = change.get("owners", [])
            if not isinstance(owners, list) or not all(
                isinstance(owner, str) for owner in owners
            ):
                raise TypeError("refinery owners must be a string list")
            active_status = change.get("active_status", False)
            if not isinstance(active_status, bool):
                raise TypeError("refinery active_status must be boolean")
            if owners or active_status:
                continue
            name = change.get("name")
            remaining = change.get("remaining_tasks")
            if not isinstance(name, str) or not name.strip():
                raise TypeError("refinery change name must be non-empty")
            if not isinstance(remaining, int) or remaining < 0:
                raise TypeError("refinery remaining_tasks must be non-negative")
            eligible.append((order[classification], remaining, name, classification))
        eligible.sort(key=lambda item: item[:3])
        return tuple(
            CandidateHint(
                classification="REFINERY",
                task_label=f"Refine OpenSpec {name}",
                files=(f"openspec/changes/{name}/",),
                status=classification,
            )
            for _order, _remaining, name, classification in eligible
        )
    except (
        KeyError,
        OSError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
        subprocess.SubprocessError,
    ) as exc:
        raise RuntimeError(f"OpenSpec refinery inspection failed: {exc}") from exc


def inspect_current_main_snapshot(
    *,
    repo: Path,
    provider: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    max_hints: int = MAX_CANDIDATE_HINTS,
) -> CandidateSnapshot:
    """Fetch origin and classify the exact current origin/main STATUS state."""
    _admission_command(
        ["git", "-C", str(repo), "fetch", "--prune", "origin"],
        cwd=repo,
        runner=runner,
    )
    claim_snapshot = inspect_candidate_snapshot(
        repo=repo,
        provider=provider,
        runner=runner,
        max_hints=max_hints,
        status_ref="origin/main",
    )
    pressure = claim_snapshot.pressure
    if pressure.claimable or pressure.stale or pressure.owned:
        return claim_snapshot

    flow_hints = inspect_refinery_hints(
        repo=repo,
        runner=runner,
        status_ref="origin/main",
    )
    combined: list[CandidateHint] = []
    seen_targets: set[str] = set()
    for hint in (*flow_hints, *claim_snapshot.blocked_hints):
        target = _slugify(hint.task_label)
        if target in seen_targets:
            continue
        seen_targets.add(target)
        combined.append(hint)
    return CandidateSnapshot(
        pressure=CandidatePressure(
            claimable=0,
            stale=0,
            owned=0,
            refinable=len(combined),
        ),
        hints=tuple(combined[:max_hints]),
        blocked_targets=claim_snapshot.blocked_targets,
        blocked_hints=claim_snapshot.blocked_hints,
    )


def inspect_candidate_pressure(
    *,
    repo: Path,
    provider: str,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> CandidatePressure:
    """Fetch and read canonical claim pressure from exact current main."""
    return inspect_current_main_snapshot(
        repo=repo,
        provider=provider,
        runner=runner,
        max_hints=0,
    ).pressure


def no_candidate_rejection(
    result: DrainResult,
    pressure: CandidatePressure,
) -> str | None:
    """Explain why NO_CANDIDATE is not credible under current claim state."""
    if result.status != "NO_CANDIDATE":
        return None
    if (
        pressure.claimable == 0
        and pressure.stale == 0
        and pressure.owned == 0
        and pressure.refinable == 0
    ):
        return None
    return (
        f"claimable={pressure.claimable} stale={pressure.stale} "
        f"owned={pressure.owned} refinable={pressure.refinable}"
    )


def blocked_result_rejection(
    result: DrainResult,
    snapshot: CandidateSnapshot,
) -> str | None:
    """Explain why a BLOCKED marker lacks durable current-main proof."""
    if result.status != "BLOCKED":
        return None
    if result.target in snapshot.blocked_targets:
        return None
    return f"target={result.target} is not blocked on current origin/main"


def current_main_blocked_result_rejection(
    result: DrainResult,
    *,
    repo: Path,
    provider: str,
    inspector: Callable[..., CandidateSnapshot] | None = None,
) -> str | None:
    """Refresh current main and fail closed when BLOCKED lacks shared proof."""
    if result.status != "BLOCKED":
        return None
    snapshot_inspector = inspector or inspect_current_main_snapshot
    try:
        snapshot = snapshot_inspector(
            repo=repo,
            provider=provider,
            max_hints=0,
        )
    except RuntimeError as exc:
        return str(exc)
    return blocked_result_rejection(result, snapshot)


def begin_attempt(state: dict[str, Any]) -> int:
    """Persist honest active status before dispatching the next worker."""
    state["attempts"] += 1
    state["status"] = "running"
    return int(state["attempts"])


def build_worker_prompt(
    state: dict[str, Any],
    *,
    objective: str,
    candidate_hints: tuple[CandidateHint, ...] = (),
    admission: Admission | None = None,
) -> str:
    """Return the fixed governance brief for one disposable drain worker."""
    identity = state["identity"]
    resume = state.get("resume_target")
    blocked = state.get("recent_blocked", [])
    consumed = state.get("recent_consumed_targets", [])
    refinery_hint = next(
        (
            hint
            for hint in candidate_hints
            if hint.classification == "REFINERY"
        ),
        None,
    )
    refinery_mode = admission is None and refinery_hint is not None
    if admission is not None:
        partial_resume = (
            isinstance(state.get("last_result"), dict)
            and state["last_result"].get("status") == "PARTIAL"
            and state["last_result"].get("continuation_kind") != "refinery"
        )
        foldback_text = (
            "\nThe implementation PR is already merged. Before foldback, fetch "
            "origin/main and restack this branch onto current main with a clean "
            "tree. Do not publish until the diff excludes the merged implementation. "
            "That implementation PR belongs to the previous worker and does not "
            "consume this worker's PR budget. Create at most one fresh foldback PR "
            "for the remaining coordination diff, and cite that fresh foldback PR "
            "in the terminal marker; never repeat the implementation PR."
            if partial_resume
            else ""
        )
        resume_text = f"""The controller already admitted and claimed your lane:
- Target: `{admission.task_label}`
- Canonical result target: `{admission.target}`
- Worktree: `{admission.worktree}`
- Branch: `{admission.branch}`

You are already inside that prepared worktree. Do not create another worktree.
Do not select a different lane. Verify the exact claim, then build this target.
Your terminal marker MUST use `{admission.target}`, never the human task label.
{foldback_text}"""
    else:
        refinery_continuation = (
            isinstance(state.get("last_result"), dict)
            and state["last_result"].get("continuation_kind") == "refinery"
        )
        if refinery_continuation:
            resume_text = (
                "The prior refinery PR is a coordination receipt only. Recheck the "
                "current controller snapshot and follow its normal admission; do not "
                "treat the refinery pseudo-target as an implementation claim."
            )
        elif resume:
            resume_text = (
                f"STATUS may contain `{identity}` on `{resume}`. You MUST resume and "
                "finish/fold back that target before selecting any different work."
            )
        else:
            resume_text = (
                f"Before selection, search STATUS for an existing `{identity}` claim. "
                "If one exists, you MUST resume it first."
            )
    blocked_text = ", ".join(blocked) if blocked else "(none)"
    consumed_text = ", ".join(consumed) if consumed else "(none)"
    candidate_text = (
        "\n".join(
            f"- [{hint.classification}] {hint.task_label}"
            + (f" | files: {', '.join(hint.files)}" if hint.files else "")
            for hint in candidate_hints
        )
        if candidate_hints
        else "- (no controller hint; run the canonical claim check directly)"
    )
    worktree_rule = (
        "- Work only in the controller-prepared worktree above. Do not create or "
        "switch to another lane."
        if admission is not None
        else (
            "- Never edit the dirty/stale primary checkout. Fetch current origin/main "
            "and create one clean purpose-named sibling worktree plus `_PURPOSE.md` "
            "before edits."
        )
    )
    startup_contract = (
        f"""1. Verify STATUS in this prepared worktree contains the exact
   `claimed:{identity}` admission for `{admission.task_label}`. Run
   `provider_context_feed.py --provider {identity} --phase build --limit 10`.
   Do not perform candidate selection and do not create another lane."""
        if admission is not None
        else (
            f"""1. Fetch current origin/main, then run exact `claim_check.py --json`
   with `{identity}` and
   `provider_context_feed.py --provider {identity} --phase claim --limit 10`.
   Revalidate `[REFINERY] {refinery_hint.task_label}` with
   `openspec_flow.py audit --ref origin/main`. This target authorizes
   coordination reconciliation only: create one clean purpose-named worktree,
   but MUST NOT edit product files or implement the change in this attempt.
   Land exactly one reviewed coordination PR that adds or corrects the exact
   `{refinery_hint.task_label}` pending or blocked STATUS row. Its Files cell
   names the later implementation/foldback artifacts and omits STATUS itself.
   Model the exact next slice, not completion of the whole legacy change.
   `Depends` contains only unresolved prerequisites that must land before that
   slice can begin. Downstream test, review, deployment, rendered, or
   organic-use proof stays in OpenSpec tasks or the row's acceptance text and
   MUST NOT make earlier implementation non-claimable. Inspect unchecked tasks
   for one <=12-task slice, preferably fewer. If that direct slice is blocked,
   promote the shortest concrete autonomous prerequisite-removal slice that is
   non-overlapping and needs no host-only authority. A blocked umbrella row is
   forbidden while either kind of executable slice exists. Return BLOCKED only
   after proving no bounded unchecked-task slice and no autonomous
   prerequisite-removal slice can start under the current claim, host, policy,
   and review gates.
   Return PARTIAL after a safe pending row merges; return BLOCKED only after a
   durable blocker row merges and current main classifies this exact target
   blocked. If the target disappeared or became live-owned/host-owned, return
   FAILED without inventing replacement work."""
            if refinery_mode
            else f"""1. Before any broad audit or backlog scan, run exact
   `claim_check.py --json` with `{identity}`, then run
   `provider_context_feed.py --provider {identity} --phase claim --limit 10`.
   Resume an owned row first. Otherwise revalidate the controller snapshot in
   listed order and claim the first row that remains CLAIMABLE, or reap the
   first row that remains policy-qualified STALE. Immediately edit STATUS with
   the exact identity and commit that claim in the clean lane. Do not spend a
   broad research pass before you commit that claim."""
        )
    )
    if refinery_mode:
        result_statuses = "<PARTIAL|BLOCKED|FAILED>"
    elif admission is not None:
        result_statuses = "<MERGED|PARTIAL|BLOCKED|FAILED>"
    else:
        result_statuses = "<MERGED|PARTIAL|BLOCKED|NO_CANDIDATE|FAILED>"
    result_target = (
        admission.target
        if admission is not None
        else (
            _slugify(refinery_hint.task_label)
            if refinery_mode
            else "<target-or-dash>"
        )
    )
    post_admission_contract = (
        "2. This attempt is coordination-only. Do not run apply, sync/archive, "
        "or product tests; the next normally admitted worker owns delivery."
        if refinery_mode
        else """2. Only after the durable claim, run `python scripts/openspec_flow.py audit`
   and the scoped STATUS/PLAN/dependency and provider-context checks needed for
   that lane."""
    )
    delivery_execution_contract = (
        """5. Do not implement, sync, archive, or change task checkboxes in the
   refinery target. This attempt ends after one exact STATUS promotion/blocker.
6. Create that coordination PR as a draft with `gh pr create --draft`. Obtain
   required independent review of the exact head, then add exactly one receipt
   to the PR body before marking it ready:
   `Drain-Review-Verdict: APPROVE`,
   `Drain-Review-Head: <40-character lowercase head SHA>`, and
   `Drain-Review-Artifact: <docs path or GitHub URL>`.
   Any later commit invalidates the receipt and requires a fresh exact-head
   review. Do not invoke `gh pr merge` directly; the trusted repository workflow
   owns auto-merge enrollment.
7. Verify the coordination PR is actually merged. Return PARTIAL for a pending
   row or BLOCKED for a current-main blocked row using the exact assigned target."""
        if refinery_mode
        else """5. For a grandfathered oversized change, deliver one recovery slice containing
   at most 12 unchecked tasks and prefer materially fewer within this worker.
   Work inside the existing change; do not mechanically fan out child changes.
6. Implement test-first and create the PR as a draft with `gh pr create --draft`.
   Obtain required independent review of the exact head, then add exactly one
   receipt to the PR body before marking it ready:
   `Drain-Review-Verdict: APPROVE`,
   `Drain-Review-Head: <40-character lowercase head SHA>`, and
   `Drain-Review-Artifact: <docs path or GitHub URL>`.
   Any later commit invalidates the receipt and requires a fresh exact-head
   review. Do not invoke `gh pr merge` directly; the trusted repository workflow
   owns auto-merge enrollment. Use shell `git` and `gh` commands from the
   assigned worktree to stage, commit, push, create the PR, and wait for required
   CI/auto-merge. Do not treat an unavailable provider-specific GitHub action as
   proof that repository publication is unavailable.
7. Verify the PR is actually merged. Sync/archive OpenSpec when complete and
   retire the STATUS row. If merge succeeded but foldback remains, report
   PARTIAL so the next fresh worker resumes it."""
    )
    return f"""You are one disposable TinyAssets OpenSpec drain worker.

Run identity: `{identity}`
Objective: {objective}
Recent blocked targets to avoid unless their blocker visibly cleared: {blocked_text}
Already-consumed targets to exclude for this entire run: {consumed_text}

{resume_text}

Controller candidate snapshot (ordered, taken immediately before dispatch):
{candidate_text}

Authority and safety:
- You are write-capable and are not reliably OS-sandboxed on this Windows host.
  Safety comes from the clean worktree, exact claims, one-PR scope, review, CI,
  finite timeout, and preserved artifacts.
{worktree_rule}
- Follow AGENTS.md and the provider lifecycle gates. Run
  `worktree_status.py --provider {identity}` and cap that exact-identity
  diagnostic at 15 seconds; if it times out, record that and continue only
  from the clean exact worktree above. Zero matching rows grant no authority
  and do not prove a lane is clean. Exact `claim_check.py`,
  `openspec_flow.py`, prepared-worktree/STATUS verification, and
  provider-context checks still apply.
- Use the exact STATUS identity `{identity}`. Never mint a suffix. Resume your
  own existing claim before admitting another.

Delivery contract:
{startup_contract}
{post_admission_contract}
3. Prove candidate exhaustion in this exact order before `NO_CANDIDATE`:
   a. resume this drain identity's existing claim;
   b. select a claimable finish-first STATUS row;
   c. reap and claim the first policy-qualified stale claim under AGENTS.md;
   d. freshness-check blocker/dependency labels against current main, PRs, and
      worktrees, removing only labels disproved by current evidence;
   e. promote one safe non-overlapping cross-cutting recovery task under
      AGENTS.md "Staying unblocked".
   `NO_CANDIDATE` is permitted only when claimable, stale, exact-identity-owned,
   and exact-current-main refinable counts are all zero. Never steal a live
   claim or invent work merely to stay busy.
4. Own one concrete acceptance contract and at most one PR per disposable
   worker attempt.
{delivery_execution_contract}
8. Preserve blockers honestly. `BLOCKED` is reserved for a durable task, host,
   dependency, review, or policy gate. Before returning `BLOCKED`, you must
   first land a sanitized STATUS dependency or blocker through normal review
   and confirm current `origin/main` classifies the exact target as blocked.
   Result-file prose alone is invalid. If verified local work exists but
   staging, committing, pushing, or creating the PR fails, preserve the
   worktree and return `FAILED`; the next fresh worker will resume the same
   admission within the finite failure budget. Do not broaden into full-platform
   conversion.

Your last non-empty line must replace every placeholder in exactly this form.
Do not print any other DRAIN_RESULT line:
DRAIN_RESULT: {result_statuses} {result_target} <PR-url-or-dash>"""


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


def verify_preexisting_open_pr_owner(
    pr_url: str,
    *,
    started_at: str,
    repo: Path | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> bool:
    """Return true only for an exact-repository open PR older than this run."""
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
            ["gh", "pr", "view", pr_url, "--json", "state,createdAt"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
        if result.returncode != 0:
            return False
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            return False
        created_at = payload.get("createdAt")
        if payload.get("state") != "OPEN" or not isinstance(created_at, str):
            return False
        return _parse_timestamp(created_at) < _parse_timestamp(started_at)
    except (
        OSError,
        TypeError,
        ValueError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
    ):
        return False


def _github_repo_slug(remote_url: str) -> str | None:
    match = re.search(
        r"github\.com(?::|/)(?P<owner>[^/\s]+)/(?P<repo>[^/\s]+?)(?:\.git)?$",
        remote_url.strip(),
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    return f"{match.group('owner')}/{match.group('repo')}".lower()


def canonical_pr_receipt(pr_url: str) -> str:
    """Return the stable GitHub identity for a parsed pull-request URL."""
    match = PR_RE.fullmatch(pr_url)
    if not match:
        return pr_url
    owner = match.group("owner").lower()
    repo = match.group("repo").lower()
    number = match.group("number").lstrip("0") or "0"
    return f"https://github.com/{owner}/{repo}/pull/{number}"


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
    if result.status == "PARTIAL" and state.get("attempt_kind") == "refinery":
        state["last_result"]["continuation_kind"] = "refinery"
    if result.status in {"MERGED", "PARTIAL"} and not merge_verified:
        state["consecutive_failures"] += 1
        state["resume_target"] = result.target
        state["status"] = "merge-verification-failed"
        return
    if result.status in {"MERGED", "PARTIAL"}:
        receipt = canonical_pr_receipt(result.pr)
        merged_prs = [
            canonical_pr_receipt(pr)
            for pr in state.get("merged_prs", [])
            if isinstance(pr, str) and canonical_pr_receipt(pr) != receipt
        ]
        merged_prs.append(receipt)
        # A run is already bounded by max_slices. Keep every accepted
        # merge-backed receipt so neither completed nor continuation work can
        # become replayable later in the same run.
        state["merged_prs"] = merged_prs
    if result.status == "MERGED":
        state["completed_slices"] += 1
        state["consecutive_failures"] = 0
        state["consecutive_partial_target"] = None
        state["consecutive_partials"] = 0
        state["resume_target"] = None
        state["status"] = "merged"
    elif result.status == "PARTIAL":
        state["resume_target"] = result.target
        if state.get("attempt_kind") == "refinery":
            state["consecutive_failures"] = 0
            state["consecutive_partial_target"] = None
            state["consecutive_partials"] = 0
            state["status"] = "partial"
        else:
            repeated = state.get("consecutive_partial_target") == result.target
            partials = (
                state.get("consecutive_partials", 0) + 1 if repeated else 1
            )
            state["consecutive_partial_target"] = result.target
            state["consecutive_partials"] = partials
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


def apply_invalid_blocked_result(
    state: dict[str, Any],
    result: DrainResult,
    *,
    attempt: int,
    error: str,
) -> None:
    """Record a rejected private blocker without releasing its admission."""
    state["consecutive_transients"] = 0
    state["consecutive_failures"] += 1
    state["last_result"] = {
        "status": "INVALID_BLOCKED_RESULT",
        "attempt": attempt,
        "target": result.target,
        "error": error,
    }
    state["status"] = "invalid-blocked-result"


def apply_duplicate_merge_suppression(
    state: dict[str, Any],
    result: DrainResult,
    *,
    attempt: int,
) -> None:
    """Suppress a stale target whose merge receipt was already consumed."""
    state["consecutive_transients"] = 0
    if result.status == "MERGED":
        state["consecutive_failures"] = 0
    consumed = [
        target
        for target in state.get("recent_consumed_targets", [])
        if target != result.target
    ]
    if result.target != "-":
        consumed.append(result.target)
    state["recent_consumed_targets"] = consumed
    state["admission"] = None
    state["refinery_assignment"] = None
    state["resume_target"] = None
    state["last_result"] = {
        "status": "INVALID_DUPLICATE_MERGE",
        "attempt": attempt,
        "target": result.target,
        "pr": result.pr,
    }
    state["last_consumed_attempt"] = attempt
    state["status"] = "duplicate-merge-suppressed"


def apply_preexisting_open_pr_suppression(
    state: dict[str, Any],
    result: DrainResult,
    *,
    attempt: int,
) -> None:
    """Skip refinery work already owned before this drain run began."""
    state["consecutive_transients"] = 0
    state["consecutive_failures"] = 0
    consumed = [
        target
        for target in state.get("recent_consumed_targets", [])
        if target != result.target
    ]
    consumed.append(result.target)
    state["recent_consumed_targets"] = consumed
    state["admission"] = None
    state["refinery_assignment"] = None
    state["resume_target"] = None
    state["last_result"] = {
        "status": "PREEXISTING_OPEN_PR_OWNER",
        "attempt": attempt,
        "target": result.target,
        "pr": result.pr,
    }
    state["last_consumed_attempt"] = attempt
    state["status"] = "live-owned-refinery-suppressed"


def infer_legacy_merged_prs(
    *,
    state: dict[str, Any],
    results_dir: Path,
    repo: Path,
    merge_verifier: Callable[..., bool] = verify_merged,
) -> list[str]:
    """Reconstruct accepted verified merge-backed receipts for old state."""
    try:
        last_consumed = max(0, int(state.get("last_consumed_attempt", 0)))
        completed_slices = max(0, int(state.get("completed_slices", 0)))
        started_at = str(state["started_at"])
    except (KeyError, TypeError, ValueError):
        return []
    log_path = results_dir.parent / "supervisor.log"
    try:
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # Result text alone cannot prove that merge verification succeeded.
        return []
    ordinary_attempts = {
        int(match.group("attempt"))
        for match in re.finditer(
            r"\bresult attempt=(?P<attempt>[1-9][0-9]*) "
            r"status=(?:merged|partial|partial-stalled)\b",
            log_text,
        )
        if int(match.group("attempt")) <= last_consumed
    }
    ordinary_merged_attempts = {
        int(match.group("attempt"))
        for match in re.finditer(
            r"\bresult attempt=(?P<attempt>[1-9][0-9]*) status=merged\b",
            log_text,
        )
        if int(match.group("attempt")) <= last_consumed
    }
    recovery_candidates = sorted(
        {
            int(match.group("attempt"))
            for match in re.finditer(
                r"\b(?:replayed newly valid result|"
                r"recovered unconsumed terminal result) "
                r"attempt=(?P<attempt>[1-9][0-9]*) status=MERGED\b",
                log_text,
            )
            if int(match.group("attempt")) <= last_consumed
        }
        - ordinary_merged_attempts
    )
    # Legacy recovery logs recorded the worker marker but not the controller's
    # verification status. The completed-slice ledger bounds how many of those
    # ambiguous recovery events can have succeeded.
    recovery_slots = max(0, completed_slices - len(ordinary_merged_attempts))
    # If fewer recovery slots exist than recovery candidates, the legacy
    # artifacts prove how many succeeded but not which PRs succeeded. Trusting
    # any candidate could suppress a legitimate retry, so fail open to retry.
    accepted_recoveries = (
        recovery_candidates
        if recovery_slots >= len(recovery_candidates)
        else []
    )
    accepted_attempts = ordinary_attempts | set(accepted_recoveries)
    receipts: list[str] = []
    for attempt in sorted(accepted_attempts):
        try:
            result = parse_result(
                (results_dir / f"{attempt:03d}.md").read_text(
                    encoding="utf-8",
                    errors="replace",
                )
            )
        except (OSError, ValueError):
            continue
        receipt = canonical_pr_receipt(result.pr)
        if result.status not in {"MERGED", "PARTIAL"} or receipt in receipts:
            continue
        if not merge_verifier(
            result.pr,
            repo=repo,
            started_at=started_at,
        ):
            continue
        receipts.append(receipt)
    return receipts


def _recorded_invalid_result_attempt(state: dict[str, Any]) -> int | None:
    last_result = state.get("last_result")
    if (
        not isinstance(last_result, dict)
        or last_result.get("status") != "INVALID_RESULT"
    ):
        return None
    attempt_value = last_result.get("attempt")
    if attempt_value is None:
        if state.get("status") != "failure-budget":
            return None
        attempt_value = state.get("attempts")
    try:
        attempt = int(attempt_value)
    except (TypeError, ValueError):
        return None
    return attempt if attempt >= 1 else None


def recover_invalid_result(
    state: dict[str, Any],
    *,
    results_dir: Path,
    repo: Path,
    merge_verifier: Callable[..., bool] = verify_merged,
    blocked_snapshot_inspector: Callable[..., CandidateSnapshot] | None = None,
) -> bool:
    """Replay the exact newly valid artifact through ordinary result handling."""
    admission_data = state.get("admission")
    attempt = _recorded_invalid_result_attempt(state)
    if attempt is None or not isinstance(admission_data, dict):
        return False
    try:
        started_at = str(state["started_at"])
        admission = Admission(
            target=str(admission_data["target"]),
            task_label=str(admission_data["task_label"]),
            worktree=Path(admission_data["worktree"]),
            branch=str(admission_data["branch"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    result_path = results_dir / f"{attempt:03d}.md"
    try:
        result = parse_result(
            result_path.read_text(encoding="utf-8", errors="replace")
        )
    except (OSError, ValueError):
        return False
    if admission_result_rejection(result, admission):
        return False

    if duplicate_merge_rejection(result, state):
        apply_duplicate_merge_suppression(
            state,
            result,
            attempt=attempt,
        )
        state["last_consumed_attempt"] = attempt
        return True

    blocked_rejection = current_main_blocked_result_rejection(
        result,
        repo=repo,
        provider=str(state["identity"]),
        inspector=blocked_snapshot_inspector,
    )
    if blocked_rejection:
        state["consecutive_failures"] = max(
            0,
            int(state.get("consecutive_failures", 0)) - 1,
        )
        apply_invalid_blocked_result(
            state,
            result,
            attempt=attempt,
            error=blocked_rejection,
        )
        state["last_consumed_attempt"] = attempt
        return True

    verified = (
        merge_verifier(
            result.pr,
            repo=repo,
            started_at=started_at,
        )
        if result.status in {"MERGED", "PARTIAL"}
        else False
    )
    state["consecutive_failures"] = max(
        0,
        int(state.get("consecutive_failures", 0)) - 1,
    )
    apply_result(state, result, merge_verified=verified)
    state["last_consumed_attempt"] = attempt
    if result.status == "BLOCKED" or (
        result.status == "MERGED" and verified
    ):
        state["admission"] = None
    return True


def _unconsumed_result_attempt(state: dict[str, Any]) -> int | None:
    """Return the exact live attempt whose terminal artifact is not recorded."""
    if state.get("status") != "running":
        return None
    try:
        attempt = int(state.get("attempts", 0))
    except (TypeError, ValueError):
        return None
    if attempt < 1:
        return None

    consumed_value = state.get("last_consumed_attempt")
    if consumed_value is None:
        last_result = state.get("last_result")
        if last_result is None:
            consumed = 0
        elif isinstance(last_result, dict) and last_result.get("attempt"):
            try:
                consumed = int(last_result["attempt"])
            except (TypeError, ValueError):
                return None
        else:
            return None
    else:
        try:
            consumed = int(consumed_value)
        except (TypeError, ValueError):
            return None
    return attempt if attempt > consumed else None


def recover_unconsumed_result(
    state: dict[str, Any],
    *,
    results_dir: Path,
    repo: Path,
    merge_verifier: Callable[..., bool] = verify_merged,
    preexisting_owner_verifier: Callable[..., bool] = (
        verify_preexisting_open_pr_owner
    ),
    blocked_snapshot_inspector: Callable[..., CandidateSnapshot] | None = None,
) -> bool:
    """Apply a valid current-attempt artifact left behind by a dead controller."""
    admission_data = state.get("admission")
    refinery_data = state.get("refinery_assignment")
    attempt = _unconsumed_result_attempt(state)
    if attempt is None or not (
        isinstance(admission_data, dict) or isinstance(refinery_data, dict)
    ):
        return False
    try:
        started_at = str(state["started_at"])
        result = parse_result(
            (results_dir / f"{attempt:03d}.md").read_text(
                encoding="utf-8",
                errors="replace",
            )
        )
    except (KeyError, TypeError, ValueError, OSError):
        return False

    if not isinstance(admission_data, dict):
        try:
            if refinery_data["classification"] != "REFINERY":
                return False
            files_data = refinery_data["files"]
            if not isinstance(files_data, list) or not all(
                isinstance(path, str) for path in files_data
            ):
                return False
            refinery = CandidateHint(
                classification="REFINERY",
                task_label=str(refinery_data["task_label"]),
                files=tuple(files_data),
                line_no=int(refinery_data.get("line_no", 0)),
                status=str(refinery_data.get("status", "")),
            )
        except (KeyError, TypeError, ValueError):
            return False
        if refinery_result_rejection(result, refinery):
            return False
        if result.status != "FAILED" or not preexisting_owner_verifier(
            result.pr,
            repo=repo,
            started_at=started_at,
        ):
            return False
        apply_preexisting_open_pr_suppression(
            state,
            result,
            attempt=attempt,
        )
        return True

    try:
        admission = Admission(
            target=str(admission_data["target"]),
            task_label=str(admission_data["task_label"]),
            worktree=Path(admission_data["worktree"]),
            branch=str(admission_data["branch"]),
        )
    except (KeyError, TypeError, ValueError):
        return False
    if admission_result_rejection(result, admission):
        return False

    if duplicate_merge_rejection(result, state):
        apply_duplicate_merge_suppression(
            state,
            result,
            attempt=attempt,
        )
        state["last_consumed_attempt"] = attempt
        return True

    blocked_rejection = current_main_blocked_result_rejection(
        result,
        repo=repo,
        provider=str(state["identity"]),
        inspector=blocked_snapshot_inspector,
    )
    if blocked_rejection:
        apply_invalid_blocked_result(
            state,
            result,
            attempt=attempt,
            error=blocked_rejection,
        )
        state["last_consumed_attempt"] = attempt
        return True

    verified = (
        merge_verifier(
            result.pr,
            repo=repo,
            started_at=started_at,
        )
        if result.status in {"MERGED", "PARTIAL"}
        else False
    )
    apply_result(state, result, merge_verified=verified)
    state["last_consumed_attempt"] = attempt
    if result.status == "BLOCKED" or (
        result.status == "MERGED" and verified
    ):
        state["admission"] = None
    return True


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
        "invalid-blocked-result",
        "invalid-duplicate-merge",
        "invalid-refinery-continuation",
        "transient-provider-error",
        "transient-failure",
        "fatal-peer-error",
        "failure-budget",
        "merge-verification-failed",
        "candidate-snapshot-failed",
    }
    return 2 if status in failed else 0


def wait_interruptibly(
    *,
    stop_file: Path,
    seconds: float,
    deadline_monotonic: float,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    off_file: Path | None = None,
) -> str:
    """Wait in short polls so a stop request is observed promptly.

    ``off_file`` is the durable drain.off marker: entry gating alone is
    not enough, because a supervisor already inside its attempt loop
    must also observe the marker without a restart.
    """
    end = min(deadline_monotonic, monotonic() + max(0.0, seconds))
    while monotonic() < end:
        if stop_file.exists():
            return "stop-requested"
        if off_file is not None and off_file.exists():
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
        "attempt_kind": None,
        "last_consumed_attempt": 0,
        "last_result": None,
        "resume_target": None,
        "admission": None,
        "recent_blocked": [],
        "recent_consumed_targets": [],
        "merged_prs": [],
        "merge_receipts_version": 2,
        "target_identity_version": TARGET_IDENTITY_VERSION,
        "status": "starting",
    }


def _log(run_dir: Path, message: str) -> None:
    line = f"{_now_iso()} {message}"
    print(line, flush=True)
    with (run_dir / "supervisor.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def build_dispatch_command(
    *,
    args: argparse.Namespace,
    prompt_path: Path,
    result_path: Path,
    worker_cwd: Path | None = None,
) -> list[str]:
    cwd = worker_cwd or args.repo
    command = [
        sys.executable,
        str(PEER_AGENT),
        args.provider,
        "--write",
        "--cwd",
        str(cwd),
        "--timeout",
        str(args.worker_timeout),
        "--prompt-file",
        str(prompt_path),
        "--out",
        str(result_path),
    ]
    if args.model:
        command.extend(["--model", args.model])
    if args.provider == "codex":
        command.extend(["--effort", DRAIN_CODEX_EFFORT])
    return command


def _dispatch(
    *,
    args: argparse.Namespace,
    prompt_path: Path,
    result_path: Path,
    worker_cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    command = build_dispatch_command(
        args=args,
        prompt_path=prompt_path,
        result_path=result_path,
        worker_cwd=worker_cwd,
    )
    stdout_path = result_path.with_suffix(result_path.suffix + ".stdout.log")
    stderr_path = result_path.with_suffix(result_path.suffix + ".stderr.log")
    stdout_path.parent.mkdir(parents=True, exist_ok=True)
    with (
        stdout_path.open("w", encoding="utf-8") as stdout_handle,
        stderr_path.open("w", encoding="utf-8") as stderr_handle,
    ):
        process = subprocess.Popen(
            command,
            cwd=worker_cwd or args.repo,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
    deadline = time.monotonic() + args.worker_timeout + 90
    prior_valid_artifact: str | None = None
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _terminate_and_reap_process(process)
            stdout, stderr = _read_dispatch_logs(stdout_path, stderr_path)
            return subprocess.CompletedProcess(
                command,
                124,
                stdout=stdout or "",
                stderr=stderr or "outer supervisor timeout",
            )
        try:
            process.wait(timeout=min(RESULT_POLL_SECONDS, remaining))
            stdout, stderr = _read_dispatch_logs(stdout_path, stderr_path)
            return subprocess.CompletedProcess(
                command,
                process.returncode,
                stdout=stdout,
                stderr=stderr,
            )
        except subprocess.TimeoutExpired:
            try:
                artifact = result_path.read_text(
                    encoding="utf-8",
                    errors="replace",
                )
                parse_result(artifact)
            except (OSError, ValueError):
                prior_valid_artifact = None
                continue
            if artifact != prior_valid_artifact:
                prior_valid_artifact = artifact
                continue

            _terminate_and_reap_process(process)
            stdout, stderr = _read_dispatch_logs(stdout_path, stderr_path)
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=stdout,
                stderr=stderr,
            )


def _read_dispatch_logs(stdout_path: Path, stderr_path: Path) -> tuple[str, str]:
    def read(path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    return read(stdout_path), read(stderr_path)


def _terminate_and_reap_process(process: subprocess.Popen[str]) -> None:
    """Terminate and boundedly reap a launcher that owns no supervisor pipes."""
    _terminate_process_tree(process)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            # A completed result artifact is authoritative. Do not keep the
            # 24/7 supervisor blocked on a broken Windows process handle.
            pass


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
        # The production drain is Windows-only. A future POSIX deployment
        # needs process-group creation and group termination before enablement.
        process.kill()


def _run(args: argparse.Namespace) -> int:
    run_dir = args.run_dir.resolve()
    state_path = run_dir / "state.json"
    stop_file = run_dir / "supervisor.stop"
    off_marker = (
        args.repo / "output" / "openspec-drain-watchdog" / "drain.off"
    )
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

        recovered_result = False
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
            state.setdefault("admission", None)
            state.setdefault("attempt_kind", None)
            state.setdefault("recent_consumed_targets", [])
            migrate_target_identities(state)
            if state["provider"] != args.provider or state.get("model") != args.model:
                print("resume provider/model must match persisted state", file=sys.stderr)
                return 2
            state.pop("ended_at", None)
            now = datetime.now().astimezone()
            state["deadline_at"] = (now + timedelta(hours=args.hours)).isoformat(
                timespec="seconds"
            )
            # Make the run discoverably unfinished before recovery can perform
            # external merge verification or any other interruptible work.
            atomic_write_json(state_path, state)
            if int(state.get("merge_receipts_version", 0)) < 2:
                existing_receipts = [
                    canonical_pr_receipt(pr)
                    for pr in state.get("merged_prs", [])
                    if isinstance(pr, str)
                ]
                inferred_receipts = infer_legacy_merged_prs(
                    state=state,
                    results_dir=results_dir,
                    repo=args.repo,
                    merge_verifier=verify_merged,
                )
                state["merged_prs"] = list(
                    dict.fromkeys(existing_receipts + inferred_receipts)
                )
                state["merge_receipts_version"] = 2
            recovery_attempt = _recorded_invalid_result_attempt(state)
            recovered_invalid_result = recover_invalid_result(
                state,
                results_dir=results_dir,
                repo=args.repo,
                merge_verifier=verify_merged,
            )
            recovered_result = recovered_invalid_result
            if not recovered_result:
                recovery_attempt = _unconsumed_result_attempt(state)
                recovered_result = recover_unconsumed_result(
                    state,
                    results_dir=results_dir,
                    repo=args.repo,
                    merge_verifier=verify_merged,
                )
            if recovered_result:
                recovery_message = (
                    "replayed newly valid result"
                    if recovered_invalid_result
                    else "recovered unconsumed terminal result"
                )
                _log(
                    run_dir,
                    f"{recovery_message} attempt={recovery_attempt} "
                    f"status={state['last_result']['status']}",
                )
        else:
            state = _new_state(args)

        deadline_monotonic = time.monotonic() + args.hours * 3600
        if not recovered_result:
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
            if stop_file.exists() or off_marker.exists():
                state["status"] = "stop-requested"
                break

            attempt = begin_attempt(state)
            prompt_path = prompts_dir / f"{attempt:03d}.md"
            result_path = results_dir / f"{attempt:03d}.md"
            try:
                snapshot = inspect_current_main_snapshot(
                    repo=args.repo,
                    provider=state["identity"],
                    max_hints=(
                        MAX_CANDIDATE_HINTS
                        + len(state.get("recent_blocked", []))
                        + len(state.get("recent_consumed_targets", []))
                    ),
                )
                previous_blocked = state.get("recent_blocked", [])
                current_blocked = reconcile_recent_blocked(
                    previous_blocked,
                    blocked_targets=snapshot.blocked_targets,
                )
                if current_blocked != previous_blocked:
                    state["recent_blocked"] = current_blocked
                    _log(
                        run_dir,
                        f"released cleared blockers attempt={attempt} "
                        f"count={len(previous_blocked) - len(current_blocked)}",
                    )
                candidate_hints = snapshot.hints
                candidate_hints = filter_recently_blocked_hints(
                    candidate_hints,
                    recent_blocked=state.get("recent_blocked", []),
                )
                candidate_hints = filter_recently_consumed_hints(
                    candidate_hints,
                    recent_consumed_targets=state.get(
                        "recent_consumed_targets",
                        [],
                    ),
                )[:MAX_CANDIDATE_HINTS]
                pressure = snapshot.pressure
                _log(
                    run_dir,
                    "candidates "
                    f"attempt={attempt} claimable={pressure.claimable} "
                    f"stale={pressure.stale} owned={pressure.owned} "
                    f"refinable={pressure.refinable} "
                    f"hints={len(candidate_hints)}",
                )
            except RuntimeError as exc:
                state["consecutive_failures"] += 1
                state["status"] = "candidate-snapshot-failed"
                state["last_result"] = {
                    "status": "CANDIDATE_SNAPSHOT_FAILED",
                    "error": str(exc),
                }
                atomic_write_json(state_path, state)
                _log(
                    run_dir,
                    f"candidate snapshot unavailable attempt={attempt}: {exc}",
                )
                if args.once:
                    break
                continue
            admission_data = state.get("admission")
            admission = (
                Admission(
                    target=str(admission_data["target"]),
                    task_label=str(admission_data["task_label"]),
                    worktree=Path(admission_data["worktree"]),
                    branch=str(admission_data["branch"]),
                )
                if isinstance(admission_data, dict)
                else None
            )
            if admission is not None and not admission.worktree.is_dir():
                state["consecutive_failures"] += 1
                state["status"] = "admission-missing"
                state["last_result"] = {
                    "status": "ADMISSION_MISSING",
                    "target": admission.target,
                    "worktree": str(admission.worktree),
                }
                atomic_write_json(state_path, state)
                _log(
                    run_dir,
                    f"admission missing attempt={attempt} path={admission.worktree}",
                )
                if args.once:
                    break
                continue
            if should_cooldown_without_worker(
                pressure=pressure,
                candidate_hints=candidate_hints,
                recent_blocked=state.get("recent_blocked", []),
                recent_consumed_targets=state.get(
                    "recent_consumed_targets",
                    [],
                ),
                has_admission=admission is not None,
            ):
                state["last_result"] = {
                    "status": "BLOCKED_COOLDOWN",
                    "attempt": attempt,
                    "claimable": pressure.claimable,
                    "stale": pressure.stale,
                    "refinable": pressure.refinable,
                }
                state["status"] = "blocked-cooldown"
                atomic_write_json(state_path, state)
                _log(
                    run_dir,
                    f"cooldown attempt={attempt} filtered recent blockers "
                    f"claimable={pressure.claimable} stale={pressure.stale} "
                    f"refinable={pressure.refinable}",
                )
                if args.once:
                    break
                wait_interruptibly(
                    stop_file=stop_file,
                    off_file=off_marker,
                    seconds=args.idle_minutes * 60,
                    deadline_monotonic=deadline_monotonic,
                )
                continue
            if (
                admission is None
                and not args.dry_run
                and candidate_hints
                and candidate_hints[0].classification in {"CLAIMABLE", "STALE"}
            ):
                try:
                    admission = admit_candidate(
                        repo=args.repo,
                        identity=state["identity"],
                        hint=candidate_hints[0],
                        attempt=attempt,
                    )
                except RuntimeError as exc:
                    state["consecutive_failures"] += 1
                    state["status"] = "admission-failed"
                    state["last_result"] = {
                        "status": "ADMISSION_FAILED",
                        "error": str(exc),
                    }
                    atomic_write_json(state_path, state)
                    _log(
                        run_dir,
                        f"admission failed attempt={attempt}: {exc}",
                    )
                    if args.once:
                        break
                    continue
                state["admission"] = {
                    "target": admission.target,
                    "task_label": admission.task_label,
                    "worktree": str(admission.worktree),
                    "branch": admission.branch,
                }
                state["resume_target"] = admission.target
                atomic_write_json(state_path, state)
                _log(
                    run_dir,
                    f"admitted attempt={attempt} target={admission.target} "
                    f"worktree={admission.worktree}",
                )
            assigned_refinery = (
                next(
                    (
                        hint
                        for hint in candidate_hints
                        if hint.classification == "REFINERY"
                    ),
                    None,
                )
                if admission is None
                else None
            )
            state["attempt_kind"] = (
                "refinery" if assigned_refinery is not None else "delivery"
            )
            state["refinery_assignment"] = (
                {
                    "classification": assigned_refinery.classification,
                    "task_label": assigned_refinery.task_label,
                    "files": list(assigned_refinery.files),
                    "line_no": assigned_refinery.line_no,
                    "status": assigned_refinery.status,
                }
                if assigned_refinery is not None
                else None
            )
            prompt_path.write_text(
                build_worker_prompt(
                    state,
                    objective=args.objective,
                    candidate_hints=candidate_hints,
                    admission=admission,
                )
                + "\n",
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
                **(
                    {"worker_cwd": admission.worktree}
                    if admission is not None
                    else {}
                ),
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
                    off_file=off_marker,
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
                    "attempt": attempt,
                    "error": str(exc),
                }
                state["status"] = "invalid-result"
                atomic_write_json(state_path, state)
                if args.once:
                    break
                continue

            if admission is not None:
                admission_rejection = admission_result_rejection(
                    result,
                    admission,
                )
                if admission_rejection:
                    state["consecutive_transients"] = 0
                    state["consecutive_failures"] += 1
                    state["last_result"] = {
                        "status": "INVALID_ADMISSION_RESULT",
                        "error": admission_rejection,
                    }
                    state["status"] = "invalid-result"
                    atomic_write_json(state_path, state)
                    _log(
                        run_dir,
                        f"reject attempt={attempt} result {admission_rejection}",
                    )
                    if args.once:
                        break
                    continue

            if assigned_refinery is not None:
                refinery_rejection = refinery_result_rejection(
                    result,
                    assigned_refinery,
                )
                if refinery_rejection:
                    state["consecutive_transients"] = 0
                    state["consecutive_failures"] += 1
                    state["last_result"] = {
                        "status": "INVALID_REFINERY_RESULT",
                        "error": refinery_rejection,
                    }
                    state["status"] = "invalid-result"
                    atomic_write_json(state_path, state)
                    _log(
                        run_dir,
                        f"reject attempt={attempt} refinery {refinery_rejection}",
                    )
                    if args.once:
                        break
                    continue

                if result.status == "FAILED" and verify_preexisting_open_pr_owner(
                    result.pr,
                    repo=args.repo,
                    started_at=state["started_at"],
                ):
                    apply_preexisting_open_pr_suppression(
                        state,
                        result,
                        attempt=attempt,
                    )
                    atomic_write_json(state_path, state)
                    _log(
                        run_dir,
                        "suppress attempt="
                        f"{attempt} pre-existing open PR owner "
                        f"target={result.target} pr={result.pr}",
                    )
                    if args.once:
                        break
                    continue

            duplicate_rejection = duplicate_merge_rejection(result, state)
            if duplicate_rejection:
                apply_duplicate_merge_suppression(
                    state,
                    result,
                    attempt=attempt,
                )
                atomic_write_json(state_path, state)
                _log(
                    run_dir,
                    f"reject attempt={attempt} {result.status} "
                    f"{duplicate_rejection}",
                )
                if args.once:
                    break
                continue

            if result.status == "BLOCKED":
                blocked_rejection = current_main_blocked_result_rejection(
                    result,
                    repo=args.repo,
                    provider=state["identity"],
                )
                if blocked_rejection:
                    apply_invalid_blocked_result(
                        state,
                        result,
                        attempt=attempt,
                        error=blocked_rejection,
                    )
                    atomic_write_json(state_path, state)
                    _log(
                        run_dir,
                        f"reject attempt={attempt} BLOCKED {blocked_rejection}",
                    )
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
            if (
                assigned_refinery is not None
                and result.status == "PARTIAL"
                and verified
            ):
                try:
                    continuation_snapshot = inspect_current_main_snapshot(
                        repo=args.repo,
                        provider=state["identity"],
                        max_hints=100,
                    )
                    continuation_rejection = refinery_continuation_rejection(
                        assigned_refinery,
                        continuation_snapshot,
                    )
                except RuntimeError as exc:
                    continuation_rejection = str(exc)
                if continuation_rejection:
                    state["consecutive_transients"] = 0
                    state["consecutive_failures"] += 1
                    state["last_result"] = {
                        "status": "INVALID_REFINERY_CONTINUATION",
                        "error": continuation_rejection,
                    }
                    state["status"] = "invalid-refinery-continuation"
                    state["last_consumed_attempt"] = attempt
                    atomic_write_json(state_path, state)
                    _log(
                        run_dir,
                        "reject attempt="
                        f"{attempt} refinery continuation {continuation_rejection}",
                    )
                    if args.once:
                        break
                    continue
            apply_result(state, result, merge_verified=verified)
            if assigned_refinery is not None:
                state["refinery_assignment"] = None
            state["last_consumed_attempt"] = attempt
            if result.status == "BLOCKED" or (
                result.status == "MERGED" and verified
            ):
                state["admission"] = None
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
            if result.status == "BLOCKED":
                try:
                    next_snapshot = inspect_current_main_snapshot(
                        repo=args.repo,
                        provider=state["identity"],
                        max_hints=(
                            MAX_CANDIDATE_HINTS
                            + len(state.get("recent_blocked", []))
                            + len(
                                state.get("recent_consumed_targets", [])
                            )
                        ),
                    )
                    alternative = has_alternative_candidate(
                        next_snapshot,
                        recent_blocked=state.get("recent_blocked", []),
                        recent_consumed_targets=state.get(
                            "recent_consumed_targets",
                            [],
                        ),
                        current_target=result.target,
                    )
                except RuntimeError as exc:
                    alternative = False
                    _log(
                        run_dir,
                        f"post-block snapshot unavailable attempt={attempt}: {exc}",
                    )
                if alternative:
                    _log(
                        run_dir,
                        f"post-block alternative available attempt={attempt}",
                    )
                    continue
            if result.status in {"BLOCKED", "NO_CANDIDATE"} or (
                result.status == "PARTIAL" and verified
            ):
                wait_interruptibly(
                    stop_file=stop_file,
                    off_file=off_marker,
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
    off_marker = args.repo / "output" / "openspec-drain-watchdog" / "drain.off"
    if off_marker.exists():
        # Durable off switch shared with the watchdog; --clear-stop must
        # not override it. Removing the file is the only re-enable.
        print(
            f"drain.off present: {off_marker}; refusing to run",
            file=sys.stderr,
        )
        return 2
    if args.run_dir is None:
        args.run_dir = args.repo / "output" / "openspec-drain"
    return _run(args)


if __name__ == "__main__":
    raise SystemExit(main())

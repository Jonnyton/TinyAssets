#!/usr/bin/env python3
"""Prune stale team dirs at session start.

Background: `~/.claude/teams/<team>/` and `~/.claude/tasks/<team>/` accumulate
across sessions because the harness only removes a team when every member's
`shutdown_approved` handshake completes. Aborted sessions, rate-limit
crashes, and force-quits all leave full team dirs behind. The other
SessionStart hook (`roster_model_audit.py`) cross-scans every team dir,
so stale entries trigger spurious EMERGENCY warnings.

This hook prunes any team dir whose `inboxes/` and `config.json` mtimes
are both older than ACTIVE_THRESHOLD_MIN minutes — i.e. nothing has
written to that team in the recent past, so no live process is using it.
Pruned dirs are MOVED (not deleted) under
`<TEMP>/claude-teams-stale-<unix-ts>/<team-name>/` so they can be recovered
for ~7 days before TEMP cleanup reclaims them.

Reference: `docs/audits/2026-04-25-despawn-chain-protocol.md` §6 CHANGE-1.

Env vars:
- `TINYASSETS_DISABLE_TEAM_PRUNE` truthy → skip prune entirely.
- `TINYASSETS_TEAM_PRUNE_DRY_RUN` truthy → list what would be pruned without
  moving anything.

Errors are caught and written to stderr; the hook always exits 0 so
session start does not crash on a fs hiccup.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path

ACTIVE_THRESHOLD_MIN = 60
_TRUTHY = {"1", "true", "yes", "on"}


def _is_truthy(name: str) -> bool:
    val = os.environ.get(name, "").strip().lower()
    return val in _TRUTHY


def _teams_root() -> Path:
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    return Path(home) / ".claude" / "teams"


def _tasks_root() -> Path:
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME") or ""
    return Path(home) / ".claude" / "tasks"


def _temp_root() -> Path:
    base = os.environ.get("TEMP") or os.environ.get("TMP") or "/tmp"
    return Path(base)


def _path_mtime(path: Path) -> float | None:
    try:
        return path.stat().st_mtime
    except (OSError, ValueError):
        return None


def _team_is_active(team_dir: Path, threshold_seconds: float, now: float) -> bool:
    """Active if inboxes/ OR config.json mtime is within threshold."""
    inboxes = team_dir / "inboxes"
    config = team_dir / "config.json"
    for candidate in (inboxes, config):
        mtime = _path_mtime(candidate)
        if mtime is not None and (now - mtime) <= threshold_seconds:
            return True
    return False


def _move_dir(src: Path, dst: Path, dry_run: bool) -> bool:
    if dry_run:
        return True
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return True
    except (OSError, shutil.Error) as exc:
        print(f"[stale-pruner] failed to move {src} -> {dst}: {exc}", file=sys.stderr)
        return False


def main() -> int:
    if _is_truthy("TINYASSETS_DISABLE_TEAM_PRUNE"):
        return 0

    dry_run = _is_truthy("TINYASSETS_TEAM_PRUNE_DRY_RUN")
    teams_root = _teams_root()
    if not teams_root.is_dir():
        return 0

    now = time.time()
    threshold_seconds = ACTIVE_THRESHOLD_MIN * 60.0
    stamp = int(now)
    stale_parent = _temp_root() / f"claude-teams-stale-{stamp}"
    tasks_root = _tasks_root()

    pruned: list[str] = []
    failed: list[str] = []

    for team_dir in sorted(teams_root.iterdir()):
        if not team_dir.is_dir():
            continue
        try:
            if _team_is_active(team_dir, threshold_seconds, now):
                continue
        except OSError as exc:
            print(
                f"[stale-pruner] skipping {team_dir.name} (stat error: {exc})",
                file=sys.stderr,
            )
            continue

        team_name = team_dir.name
        teams_dst = stale_parent / "teams" / team_name
        if _move_dir(team_dir, teams_dst, dry_run):
            pruned.append(team_name)
        else:
            failed.append(team_name)
            continue

        matching_tasks = tasks_root / team_name
        if matching_tasks.is_dir():
            tasks_dst = stale_parent / "tasks" / team_name
            _move_dir(matching_tasks, tasks_dst, dry_run)

    if not pruned and not failed:
        return 0

    if dry_run:
        header = (
            f"[stale-team-pruner] DRY RUN — would prune {len(pruned)} stale team dir(s) "
            f"to {stale_parent}"
        )
    else:
        header = (
            f"[stale-team-pruner] pruned {len(pruned)} stale team dir(s) -> {stale_parent}"
        )

    lines = [header]
    if pruned:
        sample = pruned[:8]
        more = len(pruned) - len(sample)
        suffix = f" (+{more} more)" if more > 0 else ""
        lines.append(f"  pruned: {', '.join(sample)}{suffix}")
    if failed:
        lines.append(f"  failed: {', '.join(failed)}")
    msg = "\n".join(lines)

    try:
        print(json.dumps({"systemMessage": msg}))
    except (OSError, ValueError) as exc:
        print(f"[stale-pruner] failed to emit systemMessage: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - hook must never crash session start
        print(f"[stale-pruner] unexpected error: {exc}", file=sys.stderr)
        sys.exit(0)

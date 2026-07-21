#!/usr/bin/env python3
"""Fleet supervisor — keep N Codex + N Claude peer lanes alive, autonomously.

Host directive (2026-07-20): the fleet must stay at its floor *at all times*, not
just at turn boundaries. The Stop hook alone cannot do that — it only fires when
the lead ends a turn, so during long working turns lanes drain and nothing
refills them. This daemon closes that gap: it polls the live lane count and
dispatches queued briefs whenever a provider is below floor.

Queue layout (briefs are plain prompt files, dispatched oldest-first):

    <queue-root>/codex/*.md      -> dispatched with `peer_agent.py codex`
    <queue-root>/claude/*.md     -> dispatched with `peer_agent.py claude`
    <queue-root>/dispatched/     -> briefs are moved here once launched
    <queue-root>/supervisor.log  -> one line per action

A brief may carry a first-line directive comment to control its dispatch:

    <!-- peer: --write --cwd C:/path/to/worktree --timeout 5400 -->

Output files are named after the brief stem, into --gate-dir.

Usage:
  python scripts/fleet_supervisor.py --daemon          # run until stopped
  python scripts/fleet_supervisor.py --once            # single reconcile pass
  python scripts/fleet_supervisor.py --status          # print and exit

Stop it by deleting the queue root's `supervisor.stop` file's absence — i.e.
create `supervisor.stop` to request a clean shutdown.
"""

from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

# This supervisor may live in a worktree that predates scripts/peer_agent.py.
# Fall back to the primary checkout so a worktree-hosted supervisor still works.
_PRIMARY = Path("C:/Users/Jonathan/Projects/TinyAssets")


def _peer_agent() -> Path:
    local = REPO_ROOT / "scripts" / "peer_agent.py"
    return local if local.is_file() else _PRIMARY / "scripts" / "peer_agent.py"

from fleet_status import live_lanes  # noqa: E402

PROVIDERS = ("codex", "claude")
CLAUDE_ALIASES = {"claude", "fable"}
DIRECTIVE_RE = re.compile(r"<!--\s*peer:\s*(.+?)\s*-->")
# Flags a brief may set for itself. --out is derived, never taken from the brief.
ALLOWED_FLAGS = {"--write", "--cwd", "--timeout", "--model"}


def _count(lanes: list[dict], provider: str) -> int:
    names = CLAUDE_ALIASES if provider == "claude" else {provider}
    return sum(1 for lane in lanes if lane["provider"] in names)


def _log(queue_root: Path, message: str) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%S")
    line = f"{stamp} {message}"
    print(line, flush=True)
    try:
        with (queue_root / "supervisor.log").open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def _parse_directive(brief: Path) -> list[str]:
    """Extra peer_agent flags from the brief's `<!-- peer: ... -->` comment."""
    try:
        head = brief.read_text(encoding="utf-8", errors="replace")[:2000]
    except OSError:
        return []
    match = DIRECTIVE_RE.search(head)
    if not match:
        return []
    tokens = shlex.split(match.group(1))
    args, index = [], 0
    while index < len(tokens):
        token = tokens[index]
        if token not in ALLOWED_FLAGS:
            index += 1  # ignore anything not explicitly permitted
            continue
        args.append(token)
        if token != "--write" and index + 1 < len(tokens):
            args.append(tokens[index + 1])
            index += 1
        index += 1
    return args


def _next_brief(queue_root: Path, provider: str) -> Path | None:
    lane_dir = queue_root / provider
    if not lane_dir.is_dir():
        return None
    briefs = sorted(lane_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
    return briefs[0] if briefs else None


def _dispatch(brief: Path, provider: str, gate_dir: Path, queue_root: Path) -> bool:
    out_path = gate_dir / f"{brief.stem}.md"
    directive = _parse_directive(brief)  # parse before moving the file

    # Move the brief into dispatched/ BEFORE launching, and point the child at
    # that stable path. Popen returns as soon as the process is spawned — long
    # before the child interpreter starts and opens --prompt-file. If we renamed
    # AFTER dispatch (the old order) the rename raced the child's read and the
    # brief vanished from under it: observed 2026-07-20, 9 lanes died with
    # "cannot read prompt: No such file or directory". Rename-first closes it.
    dispatched = queue_root / "dispatched"
    dispatched.mkdir(parents=True, exist_ok=True)
    launch_path = dispatched / brief.name
    try:
        # os.replace (not Path.rename): atomic overwrite on BOTH platforms.
        # Path.rename raises WinError 183 on Windows when a same-named brief is
        # already in dispatched/ (a re-stocked/re-run brief), which wedged the
        # dispatch loop on 2026-07-20. Overwrite instead — a re-run is fine.
        os.replace(str(brief), str(launch_path))
    except OSError as exc:
        _log(queue_root, f"ERROR moving {brief.name} to dispatched: {exc}")
        return False

    # peer_agent.py defaults Claude lanes to `--model fable`. When Fable is
    # rate-limited the CLI exits 1 after ~25s with EMPTY stderr, so every Claude
    # lane dies silently and the fleet reports "dispatched" while producing
    # nothing — observed 2026-07-21, 4 lanes lost this way before anyone noticed
    # because a dead lane and a working one look identical from the queue log.
    # Pin a reachable model unless the brief pinned one itself.
    if provider == "claude" and "--model" not in directive:
        fallback = os.environ.get("WORKFLOW_CLAUDE_MODEL", "").strip()
        if fallback:
            directive = [*directive, "--model", fallback]

    cmd = [
        sys.executable,
        str(_peer_agent()),
        provider,
        "--out",
        str(out_path),
        "--prompt-file",
        str(launch_path),
        *directive,
    ]
    try:
        subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            cmd,
            cwd=str(_peer_agent().parent.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        try:  # dispatch failed — roll the brief back so it isn't lost
            launch_path.rename(brief)
        except OSError:
            pass
        _log(queue_root, f"ERROR dispatching {brief.name}: {exc}")
        return False

    _log(queue_root, f"dispatched {provider:<6} {brief.name} -> {out_path.name}")
    return True


def reconcile(queue_root: Path, gate_dir: Path, floors: dict[str, int]) -> dict:
    """One pass: top every provider back up to its floor. Returns a summary."""
    lanes = live_lanes()
    summary = {}
    for provider in PROVIDERS:
        have = _count(lanes, provider)
        want = floors[provider]
        launched = 0
        while have + launched < want:
            brief = _next_brief(queue_root, provider)
            if brief is None:
                _log(
                    queue_root,
                    f"QUEUE EMPTY for {provider}: {have + launched}/{want} live — "
                    f"add briefs to {queue_root / provider}",
                )
                break
            if not _dispatch(brief, provider, gate_dir, queue_root):
                # A brief that can't be dispatched must NOT wedge the whole
                # provider loop (2026-07-20: a dispatched/ name collision raised
                # every cycle and stalled all lanes). Quarantine it, keep going.
                failed = queue_root / "failed"
                failed.mkdir(parents=True, exist_ok=True)
                try:
                    os.replace(str(brief), str(failed / brief.name))
                except OSError:
                    pass
                continue
            launched += 1
            time.sleep(1)  # let the process register before recounting
        summary[provider] = {"live": have, "launched": launched, "floor": want}
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue-root", default="output/s2-gate/_queue")
    parser.add_argument("--gate-dir", default="output/s2-gate")
    parser.add_argument("--floor-codex", type=int, default=4)
    parser.add_argument("--floor-claude", type=int, default=4)
    parser.add_argument("--interval", type=int, default=45, help="poll seconds")
    parser.add_argument("--daemon", action="store_true")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args()

    def _resolve(value: str) -> Path:
        path = Path(value)
        return path if path.is_absolute() else REPO_ROOT / path

    queue_root = _resolve(args.queue_root)
    gate_dir = _resolve(args.gate_dir)
    floors = {"codex": args.floor_codex, "claude": args.floor_claude}
    for provider in PROVIDERS:
        (queue_root / provider).mkdir(parents=True, exist_ok=True)

    if args.status:
        lanes = live_lanes()
        for provider in PROVIDERS:
            queued = len(list((queue_root / provider).glob("*.md")))
            print(
                f"{provider:<7} live={_count(lanes, provider)}/{floors[provider]} "
                f"queued={queued}"
            )
        return 0

    if args.once or not args.daemon:
        summary = reconcile(queue_root, gate_dir, floors)
        for provider, info in summary.items():
            print(
                f"{provider:<7} live={info['live']}/{info['floor']} "
                f"launched={info['launched']}"
            )
        return 0

    stop_file = queue_root / "supervisor.stop"
    _log(queue_root, f"supervisor start floors={floors} interval={args.interval}s")
    while not stop_file.exists():
        try:
            reconcile(queue_root, gate_dir, floors)
        except Exception as exc:  # noqa: BLE001 - never let one pass kill the loop
            _log(queue_root, f"ERROR in reconcile pass: {exc}")
        time.sleep(args.interval)
    _log(queue_root, "supervisor stop (supervisor.stop present)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

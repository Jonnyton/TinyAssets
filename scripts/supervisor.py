#!/usr/bin/env python3
"""Trajectory supervisor — watch evaluated progress, not activity.

AVO's supervisor "monitors the broader trajectory for stagnation or repeated
unproductive cycles and can redirect the main agent toward alternative
strategies". The word doing the work is **evaluated**: AVO's loop is
inspect/plan/edit/**evaluate** over a scored git lineage, and its supervisor
responds to a stalled *evaluated* search — not to a busy one.

**One predicate: `repeat_failure`.** The same normalized command failing
identically N times since the last commit. That is outcome-centred — a test or
gate result is an evaluation, and repeating an evaluation that keeps returning
the same failure is the stall AVO's supervisor exists to break. It matches the
number `AGENTS.md` already uses (stuck 3+ iterations) rather than inventing one.

**Two predicates were deleted 2026-08-26 after a cross-family review.**
`edit_thrash` (same file edited 5x) and `no_landing` (40 tool calls without a
commit) measured *activity*, not progress: five edits and forty commands say
nothing about whether the work is converging, and their thresholds were
arbitrary where 3 at least had a precedent. Supervising activity is how a
supervisor becomes noise, and a noisy supervisor gets ignored — which is worse
than none, because it costs tokens and trains the reader to skip its output.

An earlier design also proposed a zero-product-churn predicate. Codex refuted
it — it fires on legitimate spec, docs, and security work, *including the
harness reset that introduced this file*. That refutation is kept as an
executable test (`test_reset_shaped_session_does_not_trip`).

Warnings only, never blocking. A supervisor that can stop a session is a new
ratchet, and ratchets are what this reset removed.

CLI:

    python scripts/supervisor.py record --kind edit --target tinyassets/x.py
    python scripts/supervisor.py check          # human-readable
    python scripts/supervisor.py check --json
    python scripts/supervisor.py reset          # clear the event log

The store is `.agents/supervisor/events.jsonl`, gitignored, capped by count and
age, session-scoped, and reset by a commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
STORE_DIR = REPO_ROOT / ".agents" / "supervisor"
EVENTS = STORE_DIR / "events.jsonl"

# Retention. Both bounds are cheap and independent: a burst of tool calls is
# capped by count, an abandoned session is capped by age.
MAX_EVENTS = 2000
MAX_AGE_SECONDS = 24 * 3600

# Thresholds. AGENTS.md's prose rule says "stuck 3+ iterations", so
# repeat_failure matches it exactly rather than inventing a new number.
REPEAT_FAILURE_N = 3

# Commands whose repetition is meaningful. A failing `ls` is not a stuck loop.
_INTERESTING = re.compile(
    r"\b(pytest|ruff|npm|node|python|py|git|gh|actionlint|invariants_run|"
    r"check_context_budget|mcp_public_canary|deployed_sha|build_plugin)\b"
)
# Volatile fragments that would otherwise make every invocation look unique.
_VOLATILE = re.compile(
    r"(--basetemp[= ]\S+|/tmp/\S+|[A-Za-z]:\\\\[^\s\"']+|\b[0-9a-f]{7,40}\b|"
    r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2})?\b|\b\d{10,}\b)"
)


def normalize_command(cmd: str) -> str:
    """Collapse a shell command to a stable signature.

    Two runs of the same failing test must hash the same even though their temp
    dirs, timestamps, and shas differ — otherwise a stuck loop looks like N
    distinct commands and the predicate never fires.
    """
    text = _VOLATILE.sub("", (cmd or "").strip())
    text = re.sub(r"\s+", " ", text)
    return text[:400]


def command_signature(cmd: str) -> str:
    return hashlib.sha256(normalize_command(cmd).encode("utf-8")).hexdigest()[:12]


def is_interesting(cmd: str) -> bool:
    return bool(_INTERESTING.search(cmd or ""))


# --------------------------------------------------------------------- store


def _now() -> float:
    return time.time()


def session_id(explicit: str | None = None) -> str:
    """Stable per-session id.

    Events carried no session identity until 2026-08-26, so two concurrent
    sessions (or a new one reading a previous one's log) contaminated each
    other's predicates -- one session's three failures could trip a redirect in
    another. Predicates now only see their own session's events.

    **The hook payload is the authority.** Claude Code supplies `session_id` in
    every hook's JSON; the hooks pass it here. The parent-process id is NOT a
    session identity -- each hook runs in its own shell, so separate PIDs churn
    within a single session (observed: 27300 and 19564 in one session), and PID
    reuse can collide across sessions. That bug made records fragment while
    looking like isolation. Env vars are a fallback for direct CLI use; the
    "unknown" sentinel is deliberately stable rather than random, so manual runs
    group together instead of each becoming its own island.
    """
    if explicit:
        return str(explicit)[:64]
    for var in ("CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        value = os.environ.get(var, "").strip()
        if value:
            return value[:64]
    return "cli-unknown"


def record(kind: str, target: str = "", detail: dict[str, Any] | None = None,
           *, store: Path | None = None, now: float | None = None,
           sid: str | None = None) -> None:
    """Append one event. Never raises — a broken recorder must not break a turn."""
    path = store or EVENTS
    event = {
        "ts": now if now is not None else _now(),
        "sid": session_id(sid),
        "kind": kind,
        "target": target,
        "detail": detail or {},
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(event) + "\n")
        _prune(path, now=now)
    except OSError:
        return


def _prune(path: Path, *, now: float | None = None) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    # Age-prune UNCONDITIONALLY. An earlier version returned early below 200
    # records "cheaply", which meant a small log kept events older than the age
    # bound -- and three stale failures were enough to trip repeat_failure on a
    # fresh session. The count test passed the whole time because it used 300
    # events, above the early-return threshold. Codex found it 2026-08-26.
    cutoff = (now if now is not None else _now()) - MAX_AGE_SECONDS
    kept: list[str] = []
    for line in lines[-MAX_EVENTS:]:
        try:
            if float(json.loads(line).get("ts", 0)) >= cutoff:
                kept.append(line)
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    try:
        path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    except OSError:
        return


def load(store: Path | None = None) -> list[dict[str, Any]]:
    path = store or EVENTS
    try:
        raw = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in raw:
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict):
            out.append(event)
    return out


# ---------------------------------------------------------------- predicates


@dataclass
class Finding:
    predicate: str
    summary: str
    evidence: dict[str, Any] = field(default_factory=dict)
    redirect: str = ""


def _since_last_commit(events: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Events after the most recent commit, which is the unit of landed work."""
    events = list(events)
    for i in range(len(events) - 1, -1, -1):
        if events[i].get("kind") == "commit":
            return events[i + 1:]
    return events


def repeat_failure(events: list[dict[str, Any]]) -> Finding | None:
    """Same normalized command, same non-zero exit, N times since last commit."""
    counts: dict[tuple[str, int], list[dict[str, Any]]] = {}
    for e in _since_last_commit(events):
        if e.get("kind") != "command":
            continue
        detail = e.get("detail") or {}
        code = detail.get("exit_code")
        if not isinstance(code, int) or code == 0:
            continue
        sig = detail.get("signature")
        if not sig:
            continue
        counts.setdefault((sig, code), []).append(e)
    for (sig, code), hits in counts.items():
        if len(hits) >= REPEAT_FAILURE_N:
            cmd = (hits[-1].get("detail") or {}).get("normalized", "")
            return Finding(
                predicate="repeat_failure",
                summary=(
                    f"the same command has failed with exit {code} "
                    f"{len(hits)} times since the last commit"
                ),
                evidence={"signature": sig, "exit_code": code,
                          "count": len(hits), "command": cmd},
                redirect=(
                    "You are repeating an approach that is not working. Before "
                    "running it again, state: what exactly failed, what specific "
                    "change would fix it, and whether this is the same approach "
                    "as last time. If it is, change the approach or hand it to "
                    "the other model family (peer-agents skill) for fresh eyes."
                ),
            )
    return None


PREDICATES = (repeat_failure,)


def check(store: Path | None = None, sid: str | None = None) -> list[Finding]:
    """Evaluate predicates against THIS session's events only.

    Events with no ``sid`` predate the 2026-08-26 partitioning and are ignored
    rather than attributed to whoever happens to be running now.
    """
    current = session_id(sid)
    events = [e for e in load(store) if e.get("sid") == current]
    findings = [f for f in (p(events) for p in PREDICATES) if f is not None]
    return findings


# ---------------------------------------------------------------------- CLI


def _git_head() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
            capture_output=True, text=True, check=False,
        ).stdout.strip()[:12]
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    rec = sub.add_parser("record", help="append an event")
    rec.add_argument("--kind", required=True, choices=["edit", "command", "commit"])
    rec.add_argument("--target", default="")
    rec.add_argument("--exit-code", type=int, default=None)
    rec.add_argument("--command", default="")

    chk = sub.add_parser("check", help="evaluate the predicates")
    chk.add_argument("--json", action="store_true")

    sub.add_parser("reset", help="clear the event log")

    args = ap.parse_args(argv)

    if args.cmd == "record":
        detail: dict[str, Any] = {}
        if args.command:
            detail["normalized"] = normalize_command(args.command)
            detail["signature"] = command_signature(args.command)
        if args.exit_code is not None:
            detail["exit_code"] = args.exit_code
        record(args.kind, args.target, detail)
        return 0

    if args.cmd == "reset":
        try:
            EVENTS.unlink()
        except OSError:
            pass
        print("supervisor log cleared")
        return 0

    findings = check()
    if args.json:
        print(json.dumps(
            {"head": _git_head(),
             "findings": [
                 {"predicate": f.predicate, "summary": f.summary,
                  "evidence": f.evidence, "redirect": f.redirect}
                 for f in findings]},
            indent=2,
        ))
        return 0

    if not findings:
        print("supervisor: no stagnation signal")
        return 0
    for f in findings:
        print(f"[{f.predicate}] {f.summary}")
        print(f"  -> {f.redirect}")
    return 0


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    raise SystemExit(main())

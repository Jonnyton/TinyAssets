#!/usr/bin/env python3
"""SessionEnd hook: nudge to capture a reflection / memory update + commit, while
context is still fresh.

Automates the project's manual continuous-learning norm — its own rule says
"automatic norms become hooks; memory alone lapses." Fires on `SessionEnd`
(once per session; `Stop` would fire every turn). NON-blocking: emits a nudge on
stderr (exit 2 = non-blocking notice on SessionEnd) ONLY when the working tree
still has uncommitted changes to durable paths; otherwise silent. Opt-in via
`scripts/setup_claude_settings.py --apply`. Basis:
docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md (R6).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

# A change to one of these is "durable work" worth reflecting on / committing.
DURABLE_HINTS = (
    "AGENTS.md", "PLAN.md", "STATUS.md", "CLAUDE.md",
    ".claude/skills/", ".claude/agents/", ".claude/hooks/", ".agents/skills/",
    "scripts/", "workflow/", "docs/", "tests/",
)


def _root(payload: dict) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    return Path(payload.get("cwd") or os.getcwd()).resolve()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}
    root = _root(payload)
    try:
        r = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True, text=True, timeout=5, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0
    if r.returncode != 0:
        return 0
    # porcelain lines are "XY <path>"; strip the 2-char status + space.
    changed = [ln[3:] for ln in r.stdout.splitlines() if ln.strip()]
    durable = [c for c in changed if any(h in c for h in DURABLE_HINTS)]
    if not durable:
        return 0
    sample = ", ".join(durable[:4]) + (" ..." if len(durable) > 4 else "")
    print(
        "Session-end reflection: uncommitted durable changes remain "
        f"({sample}). While context is fresh -- commit them, and capture any "
        "reusable learning in memory / AGENTS.md / a skill.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

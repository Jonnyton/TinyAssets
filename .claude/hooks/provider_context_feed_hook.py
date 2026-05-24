#!/usr/bin/env python3
"""Claude Code hook that injects the provider context feed at action checkpoints."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

PHASE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "foldback",
        re.compile(r"\b(push|pull request|merge|land|commit|ship|fold[- ]?back)\b", re.I),
    ),
    ("review", re.compile(r"\b(review|verify|audit|approve|quality gate)\b", re.I)),
    (
        "memory-write",
        re.compile(r"\b(remember|memory|idea|inbox|reflection|handoff|purpose)\b", re.I),
    ),
    ("build", re.compile(r"\b(build|implement|fix|code|edit|refactor|test)\b", re.I)),
    ("plan", re.compile(r"\b(plan|design|spec|scope|research|implication)\b", re.I)),
    ("claim", re.compile(r"\b(claim|status|task|worktree|pipeline)\b", re.I)),
)


def phase_for_prompt(prompt: str) -> str | None:
    for phase, pattern in PHASE_PATTERNS:
        if pattern.search(prompt):
            return phase
    return None


def _project_dir(payload: dict[str, Any]) -> Path:
    explicit = os.environ.get("CLAUDE_PROJECT_DIR") or payload.get("cwd")
    return Path(explicit or os.getcwd())


def _load_candidates(project_dir: Path, phase: str) -> list[dict[str, Any]]:
    script = project_dir / "scripts" / "provider_context_feed.py"
    if not script.is_file():
        return []
    try:
        result = subprocess.run(
            [
                "python",
                str(script),
                "--provider",
                "claude",
                "--phase",
                phase,
                "--limit",
                "10",
                "--json",
            ],
            cwd=project_dir,
            capture_output=True,
            text=True,
            timeout=8,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode not in (0, 2):
        return []
    try:
        data = json.loads(result.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def render_context(candidates: list[dict[str, Any]], phase: str) -> str:
    if not candidates:
        return ""
    lines = [
        f"Provider-context feed checkpoint: {phase}",
        "Before advancing, read relevant candidates and fold them into the",
        "current STATUS/worktree/PR lane, or note why they do not apply.",
    ]
    for item in candidates:
        path = item.get("path", "?")
        line = item.get("line", "?")
        signal = item.get("signal", "?")
        text = str(item.get("text", ""))[:220]
        lines.append(f"- {path}:{line} [{signal}] {text}")
    return "\n".join(lines)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    event_name = str(payload.get("hook_event_name") or "")
    if event_name == "SessionStart":
        phase = "claim"
    elif event_name == "UserPromptSubmit":
        phase = phase_for_prompt(str(payload.get("prompt") or ""))
        if phase is None:
            return 0
    else:
        return 0

    context = render_context(_load_candidates(_project_dir(payload), phase), phase)
    if not context:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": event_name,
                    "additionalContext": context,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

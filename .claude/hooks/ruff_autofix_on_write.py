#!/usr/bin/env python3
"""PostToolUse hook: auto-run `ruff --fix` on Python files the agent just edited.

Wires the project's "ruff on every touched file" discipline as a deterministic
hook instead of trusting the agent to remember it (SDLC whitepaper: "wire
deterministic checks as hooks, don't rely on the model's memory"). Best-effort
and NON-blocking: it auto-fixes what ruff can and always exits 0 — it never
blocks an edit. If ruff is unavailable it stays silent. Opt-in via
`scripts/setup_claude_settings.py --apply`. Basis:
docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md (R7).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def _root(payload: dict) -> Path:
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    for c in (cwd, *cwd.parents):
        if (c / "AGENTS.md").exists():
            return c
    return cwd


def _edited_paths(payload: dict, root: Path) -> list[Path]:
    ti = payload.get("tool_input") or {}
    raw: list[str] = []
    for key in ("file_path", "path"):
        v = ti.get(key)
        if isinstance(v, str):
            raw.append(v)
    edits = ti.get("edits")
    if isinstance(edits, list):
        for e in edits:
            if isinstance(e, dict):
                v = e.get("file_path") or e.get("path")
                if isinstance(v, str):
                    raw.append(v)
    out: list[Path] = []
    for r in raw:
        p = Path(r)
        if not p.is_absolute():
            p = root / p
        out.append(p)
    return out


def _under(p: Path, root: Path) -> bool:
    try:
        p.resolve().relative_to(root)
        return True
    except ValueError:
        return False


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if payload.get("tool_name") not in WRITE_TOOLS:
        return 0
    root = _root(payload)
    pys = [
        p for p in _edited_paths(payload, root)
        if p.suffix == ".py" and p.is_file() and _under(p, root)
    ]
    if not pys:
        return 0
    try:
        fix = subprocess.run(
            [sys.executable, "-m", "ruff", "check", "--fix", *map(str, pys)],
            cwd=root, capture_output=True, text=True, timeout=30, check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return 0  # ruff missing / failed -> best-effort, stay quiet
    # ruff prints "Found N errors (M fixed, ...)" when it changed something;
    # surface a one-line trace to stdout (logged, not blocking) so the auto-fix
    # is visible. Check both streams — ruff's summary goes to stdout.
    blob = ((fix.stdout or "") + (fix.stderr or "")).strip()
    fixed_line = next(
        (ln.strip() for ln in blob.splitlines() if "fixed" in ln.lower()), ""
    )
    if fixed_line:
        print(f"ruff_autofix_on_write: {fixed_line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

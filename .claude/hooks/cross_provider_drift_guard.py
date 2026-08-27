#!/usr/bin/env python3
"""Run the cross-provider drift checker after provider-specific edits."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

RELEVANT_PREFIXES = (
    ".agents/skills/",
    ".claude/agents/",
    ".claude/skills/",
    ".codex/",
    ".cursor/rules/",
)

RELEVANT_FILES = {
    "AGENTS.md",
    "CLAUDE.md",
    "CLAUDE_LEAD_OPS.md",
    ".cursorrules",
}

WRITE_TOOLS = {"Write", "Edit", "MultiEdit"}


def project_root(payload: dict) -> Path:
    env_root = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_root:
        return Path(env_root).resolve()

    cwd = Path(payload.get("cwd") or os.getcwd()).resolve()
    for candidate in (cwd, *cwd.parents):
        if (candidate / "AGENTS.md").exists():
            return candidate
    return cwd


def relpath(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root).as_posix()
    except ValueError:
        return path.as_posix().replace("\\", "/")


def extract_paths(payload: dict, root: Path) -> list[str]:
    tool_input = payload.get("tool_input") or {}
    raw_paths: list[str] = []

    for key in ("file_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            raw_paths.append(value)

    for key in ("file_paths", "paths"):
        value = tool_input.get(key)
        if isinstance(value, list):
            raw_paths.extend(str(item) for item in value if item)

    edits = tool_input.get("edits")
    if isinstance(edits, list):
        for edit in edits:
            if isinstance(edit, dict):
                value = edit.get("file_path") or edit.get("path")
                if isinstance(value, str):
                    raw_paths.append(value)

    paths: list[str] = []
    for raw in raw_paths:
        path = Path(raw)
        if not path.is_absolute():
            path = root / path
        paths.append(relpath(root, path))
    return sorted(set(paths))


def is_relevant(path: str) -> bool:
    normalized = path.replace("\\", "/")
    return normalized in RELEVANT_FILES or any(
        normalized.startswith(prefix) for prefix in RELEVANT_PREFIXES
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        payload = {}

    if payload.get("tool_name") not in WRITE_TOOLS:
        return 0

    root = project_root(payload)
    changed_paths = [path for path in extract_paths(payload, root) if is_relevant(path)]
    if not changed_paths:
        return 0

    checker = root / "scripts" / "check_cross_provider_drift.py"
    if not checker.exists():
        print(
            "CROSS_PROVIDER_DRIFT_GUARD: scripts/check_cross_provider_drift.py "
            "is missing; create it or remove the hook reference.",
            file=sys.stderr,
        )
        return 2

    result = subprocess.run(
        [sys.executable, str(checker), "--paths", *changed_paths],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return 0

    print("CROSS_PROVIDER_DRIFT_GUARD: blocking provider-rule drift.", file=sys.stderr)
    if result.stdout:
        print(result.stdout.rstrip(), file=sys.stderr)
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

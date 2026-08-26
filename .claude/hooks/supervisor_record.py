#!/usr/bin/env python3
"""PostToolUse hook: feed the trajectory supervisor its event stream.

Codex's objection to the supervisor was that a Stop hook has no event stream
from which to know "the same test failed three times" — implementing those
predicates means building persistent logging, normalization, storage, and
retention. That was correct. This file is that stream.

Records three kinds:
  * ``edit``    — Write/Edit, keyed by repo-relative path
  * ``command`` — Bash, keyed by a normalized command signature + exit code
  * ``commit``  — a successful `git commit`, which resets every predicate

Never blocks, never prints, never raises. A recorder that can break a turn is
worse than no recorder, so every failure path returns 0 silently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _project_dir(payload: dict) -> Path:
    raw = payload.get("cwd") or payload.get("project_dir")
    return Path(raw) if raw else Path.cwd()


def _load_supervisor(project: Path):
    script = project / "scripts" / "supervisor.py"
    if not script.exists():
        return None
    import importlib.util

    spec = importlib.util.spec_from_file_location("supervisor_for_hook", script)
    if spec is None or spec.loader is None:
        return None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        return None
    return mod


def _rel(project: Path, raw: str) -> str:
    if not raw:
        return ""
    try:
        return str(Path(raw).resolve().relative_to(project.resolve())).replace("\\", "/")
    except (ValueError, OSError):
        return str(raw).replace("\\", "/")


def _exit_code(response) -> int | None:
    if not isinstance(response, dict):
        return None
    for key in ("exit_code", "exitCode", "returncode", "status"):
        value = response.get(key)
        if isinstance(value, int):
            return value
    # Claude Code does not always surface a code; infer failure from the
    # error channel so a repeatedly-failing command is still countable.
    if response.get("is_error") or response.get("isError"):
        return 1
    stderr = response.get("stderr") or ""
    if isinstance(stderr, str) and stderr.strip():
        return 1
    return 0


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0

    project = _project_dir(payload)
    # Claude supplies the stable session id in every hook payload. Using it
    # is what makes session scoping real -- the previous PPID fallback gave a
    # different id per hook shell, fragmenting one session into many.
    sid = str(payload.get("session_id") or "") or None
    sup = _load_supervisor(project)
    if sup is None:
        return 0

    tool = str(payload.get("tool_name") or "")
    tool_input = payload.get("tool_input") or {}
    response = payload.get("tool_response")
    if not isinstance(tool_input, dict):
        tool_input = {}

    try:
        if tool in {"Write", "Edit", "NotebookEdit"}:
            target = _rel(project, str(tool_input.get("file_path") or ""))
            if target:
                sup.record("edit", target, sid=sid)
            return 0

        if tool in {"Bash", "PowerShell"}:
            command = str(tool_input.get("command") or "")
            if not command:
                return 0
            code = _exit_code(response)
            # A successful commit is the landing signal that resets predicates.
            if code == 0 and "git commit" in command and "--dry-run" not in command:
                sup.record("commit", "", {"command": sup.normalize_command(command)}, sid=sid)
                return 0
            if not sup.is_interesting(command):
                return 0
            sup.record("command", "", {
                "normalized": sup.normalize_command(command),
                "signature": sup.command_signature(command),
                "exit_code": code if isinstance(code, int) else 0,
            }, sid=sid)
            return 0
    except Exception:
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""SessionStart hook: surface what the last session already tried.

AVO's persistent memory exists so an agent can "resume from the current state
rather than repeatedly reconstructing the search". This repo's other memory
surfaces record CONCLUSIONS -- durable lessons, known-bad findings, what landed.
None of them answers *what was already attempted in this lane, and did it work?*

Without that a fresh session re-derives context and can re-attempt an approach a
previous one already disproved. The supervisor has been recording attempts and
outcomes all along; nothing read them back. This is the read.

Silent when there is nothing to say, which is the common case. Never blocks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _project_dir(payload: dict) -> Path:
    raw = payload.get("cwd") or payload.get("project_dir")
    return Path(raw) if raw else Path.cwd()


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(payload, dict):
        return 0
    if str(payload.get("hook_event_name") or "") != "SessionStart":
        return 0

    project = _project_dir(payload)
    script = project / "scripts" / "supervisor.py"
    if not script.exists():
        return 0

    import importlib.util

    spec = importlib.util.spec_from_file_location("supervisor_for_resume", script)
    if spec is None or spec.loader is None:
        return 0
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
        rendered = mod.render_resume(mod.resume())
    except Exception:
        return 0

    if not rendered:
        return 0

    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": rendered,
                }
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

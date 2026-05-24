#!/usr/bin/env python3
"""PreToolUse REJECT for Edit/Write on existing files under FUSE mount.

Background: PostToolUse guard (.claude/hooks/fuse_write_truncation_guard.py)
catches truncation AFTER it happens. After the 4th truncation incident
(2026-05-02, workflow/api/status.py), the auto-iterate ladder escalates
to PreToolUse REJECTION so the agent never even attempts the unreliable
path on existing files.

Logic:
  - Only fires for tool_name in {"Write", "Edit"}.
  - Only fires when the target file ALREADY EXISTS (new files via Write
    are usually fine on this mount).
  - Only fires when the path resolves under the FUSE-mounted project
    (heuristic: anything containing 'busy-clever' or 'sessions/' which
    are Cowork-mount markers, OR anything under the absolute project
    root if running from Claude Code on host).

On match: exit 2 with stderr explaining the heredoc / fuse_safe_write.py
recipe. The agent must rewrite via the safe path.

Wired into .claude/settings.json under hooks.PreToolUse[matcher="Write"]
and [matcher="Edit"].

Spec reference: WebSite/HOOKS_FUSE_QUIRKS.md (auto-iterate ladder rung 4).
"""

from __future__ import annotations

import json
import os
import sys


def _is_fuse_path(path: str) -> bool:
    """Heuristic: does this path resolve under the FUSE-mounted project?"""
    if not path:
        return False
    # Cowork mount markers — these only appear in Cowork sandbox paths.
    if "busy-clever" in path or "/sessions/" in path:
        return True
    # Claude Code on the Windows host writes through the project tree
    # directly — that's not the FUSE mount and Edit/Write work fine.
    # Only reject when we have explicit Cowork-style markers above.
    return False


def _emit_reject(file_path: str, tool_name: str) -> int:
    print(
        "FUSE_PRE_WRITE_REJECT: "
        f"refusing {tool_name} on existing FUSE-mount path {file_path}.\n"
        "Edit/Write silently truncate file overwrites on Cowork's FUSE mount.\n"
        "Use one of these safe paths instead:\n"
        "\n"
        "  Option A — bash heredoc (good for inline content):\n"
        f'    cat > "{file_path}" << \'FILE_EOF\'\n'
        "    ...full file content...\n"
        "    FILE_EOF\n"
        "\n"
        "  Option B — fuse_safe_write.py wrapper:\n"
        f"    python3 scripts/fuse_safe_write.py --path {file_path} --content-from /tmp/source.txt\n"
        "\n"
        "After every write: verify with `wc -l <path>` + `tail -5 <path>`.\n"
        "See WebSite/HOOKS_FUSE_QUIRKS.md for the auto-iterate ladder.",
        file=sys.stderr,
    )
    return 2


def _check(payload: dict) -> int:
    tool_name = payload.get("tool_name") or payload.get("tool") or ""
    if tool_name not in ("Write", "Edit"):
        return 0
    tool_input = payload.get("tool_input") or payload.get("input") or {}
    file_path = tool_input.get("file_path") or ""
    if not file_path:
        return 0
    if not os.path.isfile(file_path):
        # New file — Write is fine.
        return 0
    if not _is_fuse_path(file_path):
        return 0
    return _emit_reject(file_path, tool_name)


def main() -> int:
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return 0  # Don't break the agent if the hook payload is malformed.
    return _check(payload)


if __name__ == "__main__":
    sys.exit(main())

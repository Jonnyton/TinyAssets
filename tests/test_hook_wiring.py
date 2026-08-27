r"""Every wired hook command must actually be runnable.

`.claude/settings.json` wired all seven hooks as
`python "$env:CLAUDE_PROJECT_DIR/.claude/hooks/<x>.py"`. That is PowerShell
syntax. Claude Code runs a hook in whichever shell the triggering tool used, so
the SessionStart hooks worked (PowerShell) while every `PostToolUse` hook after
a Bash tool call died with

    can't open file '...\TinyAssets\:CLAUDE_PROJECT_DIR\.claude\hooks\supervisor_record.py'

-- `$env` expanded to nothing in bash, leaving a `:CLAUDE_PROJECT_DIR` literal.
The AVO supervisor recorded nothing in those sessions and said so only in a hook
error nobody was reading. Found 2026-08-26.

Hooks run with cwd set to the project directory, so a plain relative path is the
one form that resolves under both shells.
"""

from __future__ import annotations

import json
import re
import shlex
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SETTINGS = REPO_ROOT / ".claude" / "settings.json"

# Anything that only one shell expands. `$env:X` is PowerShell-only; `$X` and
# `${X}` are POSIX-only; `%X%` is cmd-only.
SHELL_SPECIFIC = re.compile(r"\$env:|\$\{?[A-Za-z_]\w*\}?|%[A-Za-z_]\w*%")


def _hook_commands() -> list[tuple[str, str]]:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    found: list[tuple[str, str]] = []
    for event, entries in (settings.get("hooks") or {}).items():
        for entry in entries:
            for hook in entry.get("hooks") or []:
                command = hook.get("command")
                if command:
                    found.append((event, command))
    return found


def test_settings_wires_at_least_one_hook() -> None:
    # Guards the guard: an empty list would make every test below vacuous.
    assert _hook_commands(), "no hook commands found — this test cannot fail"


@pytest.mark.parametrize("event,command", _hook_commands())
def test_hook_script_exists(event: str, command: str) -> None:
    parts = shlex.split(command, posix=False)
    scripts = [p.strip('"') for p in parts if p.strip('"').endswith(".py")]
    assert scripts, f"{event}: no .py script in {command!r}"
    for script in scripts:
        assert (REPO_ROOT / script).is_file(), (
            f"{event}: wired hook script does not exist: {script!r}"
        )


@pytest.mark.parametrize("event,command", _hook_commands())
def test_hook_command_is_shell_agnostic(event: str, command: str) -> None:
    hit = SHELL_SPECIFIC.search(command)
    assert hit is None, (
        f"{event}: {command!r} uses shell-specific expansion {hit.group(0)!r}. "
        "Hooks run under PowerShell or bash depending on the triggering tool; "
        "use a path relative to the project directory instead."
    )

"""Tests for the shared Claude Code config merge tool (scripts/setup_claude_settings.py).

Locks the merge contract: local keys are never clobbered, lists union, and drift
is detected. Basis: docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md (R5).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "setup_claude_settings.py"


def _load():
    spec = importlib.util.spec_from_file_location("setup_claude_settings", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mod = _load()


def test_merge_preserves_local_scalars_and_hooks():
    local = {
        "permissions": {
            "defaultMode": "auto",
            "allow": ["Bash(*)"],
            "deny": ["Read(**/secret/**)"],
        },
        "hooks": {"SessionStart": [{"hooks": [{"command": "local-hook"}]}]},
        "env": {"FOO": "bar"},
    }
    shared = {
        "permissions": {"deny": ["Read(**/__pycache__/**)"]},
        "env": {"CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS": "1"},
    }
    merged = mod.merge(local, shared)
    # local scalars / lists / nested hooks untouched
    assert merged["permissions"]["defaultMode"] == "auto"
    assert merged["permissions"]["allow"] == ["Bash(*)"]
    assert merged["hooks"]["SessionStart"][0]["hooks"][0]["command"] == "local-hook"
    assert merged["env"]["FOO"] == "bar"
    # shared additions merged in
    assert "Read(**/secret/**)" in merged["permissions"]["deny"]
    assert "Read(**/__pycache__/**)" in merged["permissions"]["deny"]
    assert merged["env"]["CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"] == "1"


def test_merge_local_scalar_wins_on_conflict():
    merged = mod.merge({"x": "local"}, {"x": "shared"})
    assert merged["x"] == "local"


def test_union_list_dedupes_and_preserves_order():
    assert mod._union_list(["a", "b"], ["b", "c"]) == ["a", "b", "c"]


def test_missing_entries_detects_drift():
    local = {"permissions": {"deny": ["Read(**/secret/**)"]}}
    shared = {"permissions": {"deny": ["Read(**/secret/**)", "Read(**/node_modules/**)"]}}
    missing = list(mod._missing_entries(local, shared))
    assert len(missing) == 1
    assert "node_modules" in missing[0]


def test_missing_entries_empty_when_local_covers_shared():
    local = {"env": {"A": "1"}, "permissions": {"deny": ["x"]}}
    shared = {"env": {"A": "1"}, "permissions": {"deny": ["x"]}}
    assert list(mod._missing_entries(local, shared)) == []


def test_strip_private_drops_underscore_keys():
    assert mod._strip_private({"_comment": "x", "env": {"A": "1"}}) == {"env": {"A": "1"}}

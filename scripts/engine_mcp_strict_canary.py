#!/usr/bin/env python3
"""Negative canary: --strict-mcp-config excludes ambient/account MCP connectors.

Run this on the DEPLOYMENT's pinned ``claude`` CLI (inside the prod container for
the daemon deployment) BEFORE enabling ``TINYASSETS_ENGINE_MCP_TOOLS``. The
engine-tools slice drops the ``mcp__*`` wildcard deny when the flag is on and
relies on ``--strict-mcp-config`` for isolation from the logged-in account
connectors — so a CLI version that regressed strict mode silently re-exposes
them (Codex 2026-08-13 ADAPT #14 / enable-gate task 2.1 of
``openspec/changes/engine-mcp-read-tools``).

The probe starts ``claude -p`` with a strict MCP config naming a single
deliberately-DEAD server (a command that exits immediately), then asks the model
to enumerate its ``mcp__`` tools. PASS = no ``mcp__`` tool other than the dead
server's is visible. FAIL = any other ``mcp__`` name appears (ambient connectors
leaked) — do NOT enable the flag on this CLI.

Exit codes: 0 pass, 1 fail, 2 probe error.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

_PROMPT = (
    "Print exactly one line and nothing else, in this exact format: the text "
    "'TOOLCHECK:' followed by a comma-separated list of the exact names of "
    "every tool you have whose name starts with 'mcp__', or 'TOOLCHECK: NONE' "
    "if you have no such tools."
)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        config_path = Path(td) / "strict_canary_mcp.json"
        # A server whose command exits immediately: connects nothing, so ANY
        # mcp__ tool the model still sees must be an ambient leak.
        config_path.write_text(json.dumps({
            "mcpServers": {
                "canarydead": {"command": "false", "args": []},
            }
        }), encoding="utf-8")
        try:
            proc = subprocess.run(
                [
                    "claude", "-p", _PROMPT,
                    "--strict-mcp-config", "--mcp-config", str(config_path),
                    "--setting-sources", "project",
                ],
                capture_output=True, text=True, timeout=180,
            )
        except FileNotFoundError:
            print("CANARY ERROR: claude CLI not found on PATH", file=sys.stderr)
            return 2
        except subprocess.TimeoutExpired:
            print("CANARY ERROR: claude -p timed out", file=sys.stderr)
            return 2
    if proc.returncode != 0:
        print(
            f"CANARY ERROR: claude -p exit {proc.returncode}: "
            f"{proc.stderr[-400:]}",
            file=sys.stderr,
        )
        return 2
    # Positive control (Codex 2026-08-13 residuals #4): a blank or evasive model
    # response must NOT count as PASS. The probe is inconclusive unless the
    # model produced the demanded TOOLCHECK marker — deterministic evidence that
    # the instruction was followed — and only then is the name list trusted.
    marker = re.search(r"TOOLCHECK:\s*(.*)", proc.stdout)
    if marker is None:
        print(
            "CANARY ERROR: probe inconclusive — the model did not produce the "
            "TOOLCHECK marker. Raw head: " + proc.stdout[:200],
            file=sys.stderr,
        )
        return 2
    listed = marker.group(1)
    leaked = sorted(
        name for name in set(re.findall(r"mcp__[A-Za-z0-9_]+(?:__[A-Za-z0-9_-]+)?", listed))
        if not name.startswith("mcp__canarydead")
    )
    if leaked:
        print("CANARY FAIL: ambient MCP tools visible under --strict-mcp-config:")
        for name in leaked:
            print(f"  {name}")
        print("Do NOT enable TINYASSETS_ENGINE_MCP_TOOLS on this CLI version.")
        return 1
    if "NONE" not in listed and not re.search(r"mcp__", listed):
        # Marker present but neither NONE nor any tool name: still inconclusive.
        print(
            "CANARY ERROR: probe inconclusive — TOOLCHECK line carried neither "
            "NONE nor tool names: " + listed[:200],
            file=sys.stderr,
        )
        return 2
    version = subprocess.run(
        ["claude", "--version"], capture_output=True, text=True, timeout=30,
    ).stdout.strip()
    print(f"CANARY PASS: no ambient MCP tools under --strict-mcp-config ({version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

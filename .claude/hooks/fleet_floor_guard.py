#!/usr/bin/env python3
"""Stop hook — keep the peer-agent fleet above its floor.

Host directive (2026-07-20): the distributed-execution build must keep at least
FLOOR_CODEX Codex lanes and FLOOR_CLAUDE Claude/Fable lanes running continuously,
so both subscriptions stay saturated instead of idling between rounds. The
failure mode this guards is the lead finishing a turn with lanes drained and the
fleet quietly parked until the next human prompt.

On Stop: count live `scripts/peer_agent.py` lanes. If either provider is below
its floor, block (exit 2) and tell the lead to refill before ending the turn.

Escape hatches, so this can never wedge a session:
  * `.claude/fleet.off`            -> guard disabled entirely
  * `MAX_CONSECUTIVE_BLOCKS`       -> after N blocks in a row it yields
  * any failure to inspect processes -> allow (fail-open; this is a nudge, not
    a security gate, and a broken CIM query must not trap the session)

State lives in `.claude/.fleet_floor_state.json` (block counter only).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

FLOOR_CODEX = int(os.environ.get("TINYASSETS_FLEET_FLOOR_CODEX", "4"))
FLOOR_CLAUDE = int(os.environ.get("TINYASSETS_FLEET_FLOOR_CLAUDE", "4"))
MAX_CONSECUTIVE_BLOCKS = 3

PROJECT_DIR = Path(
    os.environ.get("CLAUDE_PROJECT_DIR") or Path(__file__).resolve().parent.parent.parent
)
STATE_PATH = PROJECT_DIR / ".claude" / ".fleet_floor_state.json"
OFF_SWITCH = PROJECT_DIR / ".claude" / "fleet.off"

# Claude-family lanes dispatch as provider `claude` (defaults to --model fable).
CLAUDE_PROVIDERS = {"claude", "fable"}
CODEX_PROVIDERS = {"codex"}


def _read_blocks() -> int:
    try:
        return int(json.loads(STATE_PATH.read_text(encoding="utf-8"))["blocks"])
    except (OSError, ValueError, KeyError, TypeError):
        return 0


def _write_blocks(count: int) -> None:
    try:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(json.dumps({"blocks": count}), encoding="utf-8")
    except OSError:
        pass


def _allow(reset: bool = True) -> None:
    if reset:
        _write_blocks(0)
    sys.exit(0)


def main() -> None:
    if OFF_SWITCH.exists():
        _allow()

    sys.path.insert(0, str(PROJECT_DIR / "scripts"))
    try:
        from fleet_status import live_lanes  # noqa: PLC0415
    except ImportError:
        _allow()  # fail-open: no supervisor available

    try:
        lanes = live_lanes()
    except Exception:  # noqa: BLE001 - fail-open on any inspection error
        _allow()

    codex = sum(1 for lane in lanes if lane["provider"] in CODEX_PROVIDERS)
    claude = sum(1 for lane in lanes if lane["provider"] in CLAUDE_PROVIDERS)
    if codex >= FLOOR_CODEX and claude >= FLOOR_CLAUDE:
        _allow()

    blocks = _read_blocks() + 1
    if blocks > MAX_CONSECUTIVE_BLOCKS:
        print(
            f"[fleet_floor_guard] below floor (codex {codex}/{FLOOR_CODEX}, "
            f"claude {claude}/{FLOOR_CLAUDE}) but yielding after "
            f"{MAX_CONSECUTIVE_BLOCKS} consecutive blocks — refill manually.",
            file=sys.stderr,
        )
        _allow()

    _write_blocks(blocks)
    short = []
    if codex < FLOOR_CODEX:
        short.append(f"codex {codex}/{FLOOR_CODEX} (need {FLOOR_CODEX - codex} more)")
    if claude < FLOOR_CLAUDE:
        short.append(
            f"claude {claude}/{FLOOR_CLAUDE} (need {FLOOR_CLAUDE - claude} more)"
        )

    print(
        "FLEET BELOW FLOOR — do not end the turn with lanes drained.\n"
        f"  Short: {'; '.join(short)}\n"
        "  Refill with backgrounded dispatches before stopping:\n"
        "    python scripts/peer_agent.py <codex|claude> [--write --cwd <worktree>] \\\n"
        "        --timeout 3000 --out output/s2-gate/<lane>.md \\\n"
        "        --prompt-file <brief>\n"
        "  Pick the next lanes from the S2/S4/S6-S9 queue in\n"
        "  output/s2-gate/s2-fix2-report.md and RESUME-SPEC-2.md.\n"
        "  Read landed results first: python scripts/fleet_status.py\n"
        f"  (Disable: touch .claude/fleet.off — block {blocks}/"
        f"{MAX_CONSECUTIVE_BLOCKS}.)",
        file=sys.stderr,
    )
    sys.exit(2)


if __name__ == "__main__":
    main()

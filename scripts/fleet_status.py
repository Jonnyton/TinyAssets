#!/usr/bin/env python3
"""Fleet status — how many peer-agent lanes are alive, and what landed.

The distributed-execution build runs a standing fleet of `scripts/peer_agent.py`
lanes (Codex builders/attackers + Claude/Fable reviewers) dispatched as
background jobs. This reports, in one glance:

  * live lanes per provider, with age and the --out file each will land in
  * finished lanes whose --out file exists, with the trailing VERDICT line
  * lanes that died writing a `[peer_agent] ERROR` block

Exit code is 0 always (this is a report, never a gate). The Stop-hook gate is
`.claude/hooks/fleet_floor_guard.py`, which imports `live_lanes()` from here.

Usage:
  python scripts/fleet_status.py                 # full report
  python scripts/fleet_status.py --gate-dir output/s2-gate
  python scripts/fleet_status.py --json          # machine-readable
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# peer_agent.py writes this marker into --out when a lane fails.
ERROR_MARKER = "[peer_agent] ERROR"
VERDICT_RE = re.compile(r"^\s*VERDICT:\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

_PS_QUERY = (
    "Get-CimInstance Win32_Process "
    "-Filter \"Name='python.exe' OR Name='python3.exe'\" "
    "| Select-Object ProcessId,CreationDate,CommandLine "
    "| ConvertTo-Json -Depth 2 -Compress"
)


def _powershell_processes() -> list[dict]:
    """All python processes with their command lines, via CIM. [] if unavailable."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS_QUERY],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    raw = (proc.stdout or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    # ConvertTo-Json emits a bare object (not a list) for a single match.
    return data if isinstance(data, list) else [data]


def _parse_flag(cmdline: str, flag: str) -> str | None:
    """Pull `--flag value` out of a command line, tolerating quotes."""
    match = re.search(rf"{re.escape(flag)}\s+(\"[^\"]+\"|'[^']+'|\S+)", cmdline)
    if not match:
        return None
    return match.group(1).strip("\"'")


def _age_seconds(creation_date: object) -> int | None:
    """CIM CreationDate -> age in seconds. Handles /Date(ms)/ and CIM strings."""
    if isinstance(creation_date, dict):  # ConvertTo-Json may nest it
        creation_date = creation_date.get("value") or creation_date.get("DateTime")
    if not isinstance(creation_date, str):
        return None
    epoch_ms = re.search(r"/Date\((\d+)", creation_date)
    if epoch_ms:
        return max(0, int(time.time() - int(epoch_ms.group(1)) / 1000))
    cim = re.match(r"(\d{14})", creation_date)  # yyyymmddHHMMSS
    if cim:
        struct = time.strptime(cim.group(1), "%Y%m%d%H%M%S")
        return max(0, int(time.time() - time.mktime(struct)))
    return None


def live_lanes() -> list[dict]:
    """Currently-running peer_agent.py lanes, one dict per lane."""
    lanes = []
    for proc in _powershell_processes():
        cmdline = proc.get("CommandLine") or ""
        if "peer_agent.py" not in cmdline:
            continue
        # The provider is the first bare word after the script path.
        provider_match = re.search(r"peer_agent\.py\"?\s+(\w+)", cmdline)
        lanes.append(
            {
                "pid": proc.get("ProcessId"),
                "provider": provider_match.group(1) if provider_match else "unknown",
                "out": _parse_flag(cmdline, "--out"),
                "write": "--write" in cmdline,
                "age_s": _age_seconds(proc.get("CreationDate")),
            }
        )
    return lanes


def landed_lanes(gate_dir: Path, since_s: int = 86400) -> list[dict]:
    """Result files written in the window, newest first, with their verdicts."""
    if not gate_dir.is_dir():
        return []
    cutoff = time.time() - since_s
    results = []
    for path in sorted(
        gate_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        stat = path.stat()
        if stat.st_mtime < cutoff:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        verdict_match = VERDICT_RE.search(text)
        results.append(
            {
                "file": path.name,
                "bytes": stat.st_size,
                "failed": ERROR_MARKER in text,
                "verdict": verdict_match.group(1) if verdict_match else None,
                "age_s": int(time.time() - stat.st_mtime),
            }
        )
    return results


def _fmt_age(seconds: int | None) -> str:
    if seconds is None:
        return "?"
    if seconds < 90:
        return f"{seconds}s"
    if seconds < 5400:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gate-dir", default="output/s2-gate")
    parser.add_argument("--since", type=int, default=14400, help="landed window (s)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    gate_dir = Path(args.gate_dir)
    if not gate_dir.is_absolute():
        gate_dir = REPO_ROOT / gate_dir

    lanes = live_lanes()
    landed = landed_lanes(gate_dir, args.since)
    by_provider: dict[str, int] = {}
    for lane in lanes:
        by_provider[lane["provider"]] = by_provider.get(lane["provider"], 0) + 1

    if args.json:
        print(json.dumps({"live": lanes, "landed": landed, "by_provider": by_provider}))
        return 0

    counts = ", ".join(f"{n}x {p}" for p, n in sorted(by_provider.items())) or "none"
    print(f"FLEET: {len(lanes)} live lane(s) — {counts}")
    for lane in sorted(lanes, key=lambda item: item["provider"]):
        tag = "BUILD" if lane["write"] else "read "
        out = Path(lane["out"]).name if lane["out"] else "(no --out)"
        print(
            f"  [{tag}] {lane['provider']:<7} pid={lane['pid']:<7} "
            f"{_fmt_age(lane['age_s']):>6}  -> {out}"
        )

    print(f"\nLANDED (last {args.since // 3600}h) in {gate_dir.name}/:")
    if not landed:
        print("  (nothing)")
    for item in landed[:25]:
        if item["failed"]:
            state = "FAILED"
        elif item["verdict"]:
            state = item["verdict"][:34]
        else:
            state = "(no verdict line)"
        print(
            f"  {_fmt_age(item['age_s']):>6} {item['bytes']:>7}B  "
            f"{item['file']:<44} {state}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Shared-browser lock between lead + user-sim.

Host rule (2026-04-19): lead can drive the CDP Chrome (for ops work
like GoDaddy / Cloudflare dashboards) through the same browser
user-sim uses for live missions. ONE TAB rule still holds. Only one
owner drives at a time.

Lock shape: a JSON file at ``output/.browser_lock.json`` with:
  {"owner": "lead" | "user-sim", "started_at": iso, "intent": str,
   "pid": int}

Callers:
  - lead: acquire("lead", "godaddy-dns"), release().
  - user-sim's auth hook: read — if owned by lead, return heal-other
    (don't launch user-sim until lead releases).
  - tab_watchdog: read — if owned by lead, skip heal + log.

Tab-hygiene rule unchanged: exactly one tab. What changes is *which
tab content is legitimate* — when lead owns the lock, non-claude.ai
URLs are fine (GoDaddy, Cloudflare, etc). When nobody owns, default
back to claude.ai preference.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCK = ROOT / "output" / ".browser_lock.json"


def read() -> dict | None:
    if not LOCK.exists():
        return None
    try:
        return json.loads(LOCK.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def is_held_by(owner: str) -> bool:
    state = read()
    return state is not None and state.get("owner") == owner


def is_held() -> bool:
    return read() is not None


def acquire(owner: str, intent: str, force: bool = False) -> bool:
    """Take the lock. Returns True on success, False if another owner holds.

    When ``force=True`` the caller overrides any existing lock — reserved
    for stale-lock recovery (e.g., owner PID no longer alive).
    """
    existing = read()
    if existing is not None and not force:
        if existing.get("owner") == owner:
            return True
        if _pid_alive(existing.get("pid")):
            return False
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "owner": owner,
        "started_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "intent": intent,
        "pid": os.getpid(),
    }
    LOCK.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return True


def release(owner: str) -> bool:
    """Release the lock if held by ``owner``. Returns True if released."""
    state = read()
    if state is None:
        return True
    if state.get("owner") != owner:
        return False
    try:
        LOCK.unlink()
    except OSError:
        return False
    return True


def _pid_alive(pid: int | None) -> bool:
    try:
        parsed_pid = int(pid) if pid is not None else 0
    except (TypeError, ValueError):
        return False
    if parsed_pid <= 0:
        return False

    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        process_query_limited_information = 0x1000
        still_active = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(
            process_query_limited_information, False, parsed_pid,
        )
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == still_active
        finally:
            kernel32.CloseHandle(handle)

    try:
        os.kill(parsed_pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main() -> int:
    import argparse

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    acq = sub.add_parser("acquire")
    acq.add_argument("owner")
    acq.add_argument("intent")
    acq.add_argument("--force", action="store_true")
    rel = sub.add_parser("release")
    rel.add_argument("owner")
    ns = p.parse_args()

    if ns.cmd == "status":
        state = read()
        print(json.dumps(state, indent=2) if state else "unheld")
        return 0 if state is None else 1
    if ns.cmd == "acquire":
        ok = acquire(ns.owner, ns.intent, force=ns.force)
        print("acquired" if ok else "held by someone else")
        return 0 if ok else 1
    if ns.cmd == "release":
        ok = release(ns.owner)
        print("released" if ok else "not held by you")
        return 0 if ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(main())

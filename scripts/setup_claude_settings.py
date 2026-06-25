#!/usr/bin/env python3
"""Merge the committed shared Claude Code config into the local settings.json.

`.claude/settings.json` is gitignored (machine-local + OS-specific hook
commands), so the blog's "version-control your exclusions so all developers get
consistent noise reduction" doesn't happen by default. This script closes that
gap: `.claude/settings.shared.json` is committed and carries the OS-agnostic,
clearly-shareable config (env + a Read deny-list of generated/vendored paths);
this tool merges it into the operator's local `.claude/settings.json` WITHOUT
clobbering local-only keys (allow-list, defaultMode, OS-specific hooks).

Merge rules: lists are unioned (order-preserving, de-duplicated); dicts recurse;
scalars keep the LOCAL value when present (the shared file never overrides a
deliberate local choice). Keys starting with `_` (e.g. `_comment`) are ignored.

Basis: docs/audits/2026-06-24-sdlc-vibe-coding-claude-best-practices-adoption.md (R5).

Usage:
  python scripts/setup_claude_settings.py                 # dry-run: show the diff
  python scripts/setup_claude_settings.py --apply    # write (backs up .bak first)
  python scripts/setup_claude_settings.py --check    # exit 2 if local drifts from shared
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _strip_private(obj):
    if isinstance(obj, dict):
        return {k: _strip_private(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_private(v) for v in obj]
    return obj


def _union_list(local: list, shared: list) -> list:
    out = list(local)
    seen = {json.dumps(x, sort_keys=True) for x in local}
    for item in shared:
        key = json.dumps(item, sort_keys=True)
        if key not in seen:
            out.append(item)
            seen.add(key)
    return out


def merge(local, shared):
    """Deep-merge shared into local. Local scalars win; lists union; dicts recurse."""
    if isinstance(local, dict) and isinstance(shared, dict):
        out = dict(local)
        for k, sv in shared.items():
            out[k] = merge(local[k], sv) if k in local else sv
        return out
    if isinstance(local, list) and isinstance(shared, list):
        return _union_list(local, shared)
    # scalar or type mismatch: keep the local value (deliberate override)
    return local


def _missing_entries(local, shared, path=""):
    """Yield dotted paths of shared leaves/list-items absent from local (drift)."""
    if isinstance(shared, dict):
        for k, sv in shared.items():
            lv = local.get(k) if isinstance(local, dict) else None
            yield from _missing_entries(lv, sv, f"{path}.{k}" if path else k)
    elif isinstance(shared, list):
        local_keys = (
            {json.dumps(x, sort_keys=True) for x in local}
            if isinstance(local, list) else set()
        )
        for item in shared:
            if json.dumps(item, sort_keys=True) not in local_keys:
                yield f"{path}[] {json.dumps(item)}"
    else:
        if local != shared:
            yield f"{path} = {json.dumps(shared)}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--root", default=str(REPO_ROOT), help="Repo root.")
    ap.add_argument("--shared", default=None, help="Override shared template path.")
    ap.add_argument("--local", default=None, help="Override local settings path.")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write merged settings (backs up .bak).")
    mode.add_argument("--check", action="store_true", help="Exit 2 if local drifts from shared.")
    args = ap.parse_args(argv)

    root = Path(args.root)
    shared_path = Path(args.shared) if args.shared else root / ".claude" / "settings.shared.json"
    local_path = Path(args.local) if args.local else root / ".claude" / "settings.json"

    if not shared_path.is_file():
        print(f"shared template not found: {shared_path}", file=sys.stderr)
        return 1
    shared = _strip_private(json.loads(shared_path.read_text(encoding="utf-8")))
    local = (
        json.loads(local_path.read_text(encoding="utf-8"))
        if local_path.is_file() else {}
    )

    missing = list(_missing_entries(local, shared))

    if args.check:
        if missing:
            print(f"DRIFT: {len(missing)} shared entr(y/ies) missing from {local_path.name}:")
            for m in missing:
                print(f"  + {m}")
            print("\nRun: python scripts/setup_claude_settings.py --apply")
            return 2
        print(f"OK: {local_path.name} already carries all shared entries.")
        return 0

    if not missing:
        print(f"OK: {local_path.name} already carries all shared config; nothing to merge.")
        return 0

    merged = merge(local, shared)
    print(f"{len(missing)} shared entr(y/ies) to add to {local_path}:")
    for m in missing:
        print(f"  + {m}")

    if not args.apply:
        print("\n(dry-run) Re-run with --apply to write. Existing local keys are preserved.")
        return 0

    if local_path.is_file():
        backup = local_path.with_suffix(".json.bak")
        backup.write_text(local_path.read_text(encoding="utf-8"), encoding="utf-8")
        print(f"backed up -> {backup}")
    local_path.parent.mkdir(parents=True, exist_ok=True)
    local_path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {local_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

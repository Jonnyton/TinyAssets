#!/usr/bin/env python3
"""Read-only: which directories under the data root an ownership row names.

A universe exists because an ownership row says so, not because a folder is on
disk (`openspec/specs/universe-lifecycle-and-soul/spec.md`, "A universe exists
because an ownership row names it"). That change makes an unowned directory
invisible to every reader -- which is the point for a prune's archive or an
operational bucket, and a REGRESSION for a real universe that never got a row.

That second case is why this script exists. Run it against a data root BEFORE
the deploy that lands the predicate:

    python scripts/universe_ownership_inventory.py
    python scripts/universe_ownership_inventory.py --data-dir /data

It reads. It does not write, move or delete any universe file, and on a root that
already has an ownership store (every live one) it leaves the store byte-identical
too -- the only exception is that `owned_universe_id` will initialize an ABSENT
schema, which is a no-op anywhere this question is worth asking.

It is NOT the prune: deciding what to remove needs a positive reason to believe a
directory was a universe, which this deliberately does not guess at. Its only
recommendation is ever "write the missing ownership row".

Exit codes:
  0  every directory that looks like a universe is owned (safe to deploy)
  1  at least one AT-RISK directory: it carries `soul.md` (or a universe serial
     id) and no ownership row names it, so it would go dark
  2  the data root or the ownership store could not be read -- unknown, not safe
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

# The four names the retired denylist carried, plus the operational buckets a
# live root is known to hold. Used ONLY to label a row, never to decide
# anything -- an unowned directory is unowned whether or not it is on this list.
KNOWN_OPERATIONAL = frozenset({
    "cloud-automation-inputs",
    "daemon_wikis",
    "lance",
    "lancedb",
    "output",
    "runs",
    "scratch",
    "wiki",
    "workspaces",
})


def _looks_like_a_universe(path: Path) -> str:
    """Why this directory looks like somebody's universe, or ``""``.

    A POSITIVE signal, not the absence of one. `soul.md` is the canonical
    completed-seed marker and a serial id is one the platform generated, so
    either means a universe most likely lived here -- and an unowned directory
    carrying one is the case that must block a deploy.
    """
    from tinyassets.ids import is_universe_serial

    if (path / "soul.md").is_file():
        return "carries soul.md"
    if is_universe_serial(path.name):
        return "platform-generated serial id"
    if (path / "PROGRAM.md").is_file():
        return "carries PROGRAM.md (legacy premise)"
    return ""


def inventory(base: Path) -> dict[str, Any]:
    """Every directory under ``base``, with its owners and its risk label."""
    import sqlite3

    from tinyassets.daemon_server import list_universe_acl, owned_universe_id
    from tinyassets.storage import _connect

    owners_by_home: dict[str, list[str]] = {}
    try:
        with _connect(base) as conn:
            rows = conn.execute(
                "SELECT founder_sub, universe_id FROM founder_home"
            ).fetchall()
    except sqlite3.OperationalError:
        # No store yet (a root nothing has ever run against). Nothing is bound,
        # which is the honest answer -- and NOT initializing the schema to find
        # that out is what keeps this read-only on a root it was pointed at by
        # mistake.
        rows = []
    for row in rows:
        uid = str(row["universe_id"] or "").strip()
        if uid:
            owners_by_home.setdefault(uid, []).append(str(row["founder_sub"]))

    rows: list[dict[str, Any]] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        owned_id = owned_universe_id(base, child.name)
        acl = [
            f"{r['actor_id']}:{r['permission']}"
            for r in list_universe_acl(base, universe_id=owned_id or child.name)
        ]
        homes = owners_by_home.get(owned_id or child.name, [])
        signal = _looks_like_a_universe(child)
        rows.append({
            "directory": child.name,
            "owned_as": owned_id,
            "acl_grants": sorted(acl),
            "home_bindings": sorted(homes),
            "universe_signal": signal,
            # The whole point of the report: an owned directory is served as
            # before; an unowned one with a universe signal goes DARK.
            "verdict": (
                "owned"
                if owned_id
                else "at-risk: would go dark"
                if signal
                else "unowned (no universe signal)"
            ),
            "known_operational_name": child.name in KNOWN_OPERATIONAL,
        })
    return {
        "data_dir": str(base),
        "directories": rows,
        "owned": sum(1 for r in rows if r["owned_as"]),
        "at_risk": [r["directory"] for r in rows if r["verdict"].startswith("at-risk")],
        "unowned_no_signal": [
            r["directory"] for r in rows if r["verdict"].startswith("unowned")
        ],
    }


def _render(report: dict[str, Any]) -> str:
    lines = [f"data root: {report['data_dir']}", ""]
    width = max((len(r["directory"]) for r in report["directories"]), default=9)
    for row in report["directories"]:
        owners = ", ".join(row["acl_grants"] + row["home_bindings"]) or "-"
        lines.append(
            f"  {row['directory']:<{width}}  {row['verdict']:<28}  {owners}"
            + (f"  ({row['universe_signal']})" if row["universe_signal"] else "")
        )
    lines += ["", f"owned: {report['owned']}"]
    if report["at_risk"]:
        lines.append(
            "AT RISK -- these look like universes and nobody owns them, so the "
            "ownership predicate would hide them:"
        )
        lines += [f"  - {name}" for name in report["at_risk"]]
        lines.append(
            "Write the missing ownership row (a universe_acl grant or a "
            "founder_home binding) BEFORE deploying. Nothing here is deleted "
            "either way -- an unowned directory is hidden, not removed."
        )
    else:
        lines.append("no at-risk directories: every universe-looking directory is owned")
    if report["unowned_no_signal"]:
        lines.append(
            "unowned with no universe signal (expected -- archives and "
            "operational buckets): " + ", ".join(report["unowned_no_signal"])
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--data-dir",
        default="",
        help="Data root to inspect. Default: the resolver "
             "(tinyassets.storage.data_dir), so this reads the same root the "
             "daemon does rather than a re-implemented precedence.",
    )
    parser.add_argument("--json", action="store_true", help="Emit the raw report.")
    args = parser.parse_args(argv)

    if args.data_dir:
        base = Path(args.data_dir).expanduser().resolve()
    else:
        from tinyassets.storage import data_dir

        base = data_dir()

    if not base.is_dir():
        print(f"data root does not exist: {base}", file=sys.stderr)
        return 2
    try:
        report = inventory(base)
    except Exception as exc:  # noqa: BLE001 - unknown is not safe
        print(f"could not read the ownership store: {exc}", file=sys.stderr)
        return 2

    print(json.dumps(report, indent=2) if args.json else _render(report))
    return 1 if report["at_risk"] else 0


if __name__ == "__main__":
    sys.exit(main())

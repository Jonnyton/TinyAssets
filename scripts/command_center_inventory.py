"""Read-only inventory for the command-center cutover (design E1).

Walks a data root and reports everything the cutover must change, so the
migration's job is a number to bring to zero, and the dry run has something to
compare against:

* every home (``u-<ulid>`` / ``cc-<ulid>``) entry, classified by
  ``tinyassets.command_center_layout`` into user content / platform state, with
  the entries the table does not know listed separately -- the migration refuses
  to run while any exist;
* ``config.yaml`` files still holding authority fields (#4263 D8a);
* every SQLite file: tables, columns and schema SQL (CHECK / index / trigger /
  view) that name ``universe``, and per column the count of values holding a
  ``u-<ulid>`` id, a ``universe:`` actor prefix, or the bare word ``universe``
  -- TEXT and BLOB alike (a BLOB is scanned as bytes, so canonical-JSON custody
  records and checkpoint payloads are counted);
* JSON files: keys naming ``universe`` and ``u-<ulid>`` values;
* LanceDB table schemas when ``lancedb`` is importable (reported as unscanned
  otherwise -- never silently skipped).

Never writes: SQLite opens with ``mode=ro`` (``immutable=1`` when the WAL cannot
be read without writing). Run it against a copy of production, not production.

    python scripts/command_center_inventory.py /path/to/data-copy [--json] [--strict]

``--strict`` exits 2 when any home entry is unclassified.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from tinyassets.command_center_layout import (  # noqa: E402
    CONFIG_AUTHORITY_FIELDS,
    PLATFORM,
    USER,
    classify,
)

ULID = r"[0-9a-hjkmnp-tv-z]{26}"
HOME_RE = re.compile(rf"^(?:u|cc)-{ULID}$")
U_ID = re.compile(rf"(?<![0-9a-z-])u-{ULID}(?![0-9a-z])".encode())
ACTOR = re.compile(rb"universe:")
WORD = re.compile(rb"universe", re.IGNORECASE)
_JSON_LIMIT = 5_000_000


def _open_ro(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri()
    try:
        conn = sqlite3.connect(f"{uri}?mode=ro", uri=True)
        conn.execute("SELECT count(*) FROM sqlite_master").fetchone()
        return conn
    except sqlite3.Error:
        return sqlite3.connect(f"{uri}?mode=ro&immutable=1", uri=True)


def _as_bytes(value: Any) -> bytes | None:
    if isinstance(value, bytes | bytearray | memoryview):
        return bytes(value)
    if isinstance(value, str):
        return value.encode("utf-8", "surrogatepass")
    return None


def scan_sqlite(path: Path, *, values: bool = True) -> dict[str, Any]:
    """Names (and, unless ``values=False``, values) in one database file. Read-only."""
    report: dict[str, Any] = {
        "tables": [], "columns": [], "schema_sql": [], "values": [], "error": None,
    }
    try:
        conn = _open_ro(path)
    except sqlite3.Error as exc:
        report["error"] = str(exc)
        return report
    try:
        objects = conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master"
        ).fetchall()
        tables = [name for kind, name, _t, _s in objects if kind == "table"
                  and not name.startswith("sqlite_")]
        for kind, name, _tbl, sql in objects:
            if "universe" in name.lower() and kind == "table":
                report["tables"].append(name)
            if sql and "universe" in sql.lower() and kind in ("index", "trigger", "view"):
                report["schema_sql"].append({"type": kind, "name": name})
            if kind == "table" and sql and re.search(
                    r"CHECK\s*\([^)]*'universe'", sql, re.IGNORECASE):
                report["schema_sql"].append({"type": "check", "name": name})
        for table in tables:
            columns = [row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')]
            for column in columns:
                if "universe" in column.lower():
                    report["columns"].append({"table": table, "column": column})
                if not values:
                    continue
                counts = {"u_ids": 0, "actor_prefix": 0, "word": 0}
                for (value,) in conn.execute(f'SELECT "{column}" FROM "{table}"'):
                    raw = _as_bytes(value)
                    if not raw:
                        continue
                    if U_ID.search(raw):
                        counts["u_ids"] += 1
                    if ACTOR.search(raw):
                        counts["actor_prefix"] += 1
                    if WORD.search(raw):
                        counts["word"] += 1
                if any(counts.values()):
                    report["values"].append({"table": table, "column": column, **counts})
    except sqlite3.Error as exc:
        report["error"] = str(exc)
    finally:
        conn.close()
    return report


def _json_counts(node: Any, counts: dict[str, int]) -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            if isinstance(key, str) and "universe" in key.lower():
                counts["keys"] += 1
            if isinstance(key, str) and U_ID.search(key.encode()):
                counts["u_id_keys"] += 1
            _json_counts(value, counts)
    elif isinstance(node, list):
        for item in node:
            _json_counts(item, counts)
    elif isinstance(node, str) and U_ID.search(node.encode()):
        counts["u_id_values"] += 1


def scan_json(path: Path) -> dict[str, int] | None:
    try:
        if path.stat().st_size > _JSON_LIMIT:
            return None
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    counts = {"keys": 0, "u_id_keys": 0, "u_id_values": 0}
    _json_counts(document, counts)
    return counts if any(counts.values()) else None


def config_authority(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [name for name in CONFIG_AUTHORITY_FIELDS
            if re.search(rf"^\s*{name}\s*:", text, re.MULTILINE)]


def scan_lancedb(path: Path) -> dict[str, Any]:
    try:
        import lancedb  # type: ignore[import-not-found]
    except ImportError:
        return {"scanned": False, "reason": "lancedb not importable"}
    try:
        db = lancedb.connect(str(path))
        tables = {}
        for name in db.table_names():
            schema = db.open_table(name).schema
            tables[name] = [field.name for field in schema if "universe" in field.name.lower()]
        return {"scanned": True, "tables": tables}
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        return {"scanned": False, "reason": f"{type(exc).__name__}: {exc}"}


def inventory(root: Path, *, values: bool = True) -> dict[str, Any]:
    root = Path(root)
    report: dict[str, Any] = {
        "data_root": str(root), "homes": {}, "sqlite": {}, "json": {}, "lancedb": {},
    }
    for entry in sorted(root.iterdir()):
        if entry.is_dir() and HOME_RE.match(entry.name):
            home = {USER: [], PLATFORM: [], "unclassified": [], "config_authority": []}
            for child in sorted(entry.iterdir()):
                kind = classify(child.name)
                home[kind if kind else "unclassified"].append(child.name)
                if child.name == "config.yaml":
                    home["config_authority"] = config_authority(child)
            report["homes"][entry.name] = home
    for path in sorted(root.rglob("*")):
        try:
            if not path.is_file():
                if path.is_dir() and path.name == "lancedb":
                    report["lancedb"][path.relative_to(root).as_posix()] = scan_lancedb(path)
                continue
        except OSError:
            continue
        rel = path.relative_to(root).as_posix()
        if "lancedb" in path.parts:
            continue
        if path.suffix == ".db":
            found = scan_sqlite(path, values=values)
            keys = ("tables", "columns", "schema_sql", "values")
            if found["error"] or any(found[k] for k in keys):
                report["sqlite"][rel] = found
        elif path.suffix == ".json":
            counts = scan_json(path)
            if counts:
                report["json"][rel] = counts
    homes = report["homes"].values()
    report["totals"] = {
        "homes": len(report["homes"]),
        "unclassified_entries": sum(len(h["unclassified"]) for h in homes),
        "configs_with_authority": sum(1 for h in homes if h["config_authority"]),
        "sqlite_files_with_findings": len(report["sqlite"]),
        "universe_tables": sum(len(s["tables"]) for s in report["sqlite"].values()),
        "universe_columns": sum(len(s["columns"]) for s in report["sqlite"].values()),
        "schema_objects": sum(len(s["schema_sql"]) for s in report["sqlite"].values()),
        "value_rows_with_u_ids": sum(v["u_ids"] for s in report["sqlite"].values()
                                     for v in s["values"]),
        "json_files_with_findings": len(report["json"]),
        "lancedb_unscanned": sum(1 for v in report["lancedb"].values() if not v.get("scanned")),
    }
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("data_root")
    parser.add_argument("--json", action="store_true", help="print the full report")
    parser.add_argument("--no-values", action="store_true",
                        help="names and schema only (cheap enough for a live box)")
    parser.add_argument("--strict", action="store_true",
                        help="exit 2 if any home entry is unclassified")
    args = parser.parse_args(argv)
    root = Path(args.data_root)
    if not root.is_dir():
        print(f"not a directory: {root}", file=sys.stderr)
        return 1
    report = inventory(root, values=not args.no_values)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        for key, value in report["totals"].items():
            print(f"{key}: {value}")
        for home, entries in report["homes"].items():
            if entries["unclassified"]:
                print(f"unclassified in {home}: {', '.join(entries['unclassified'])}")
    if args.strict and report["totals"]["unclassified_entries"]:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Clean-slate universe reset — start fresh for the first real universe creation.

Clears everything that represents "a universe exists" (per-universe brain
directories, the ``.active_universe`` marker, and the universe-scoped index /
ACL / rules / notes / snapshots / branch-instance tables) AND the hosted-daemon
state (global daemon identities + universe-scoped runtime instances), while
PRESERVING the branch commons — ``branch_definitions``, ``goals``, gate claims,
canonical bindings, the whole ``.runs.db`` (run history + ``branch_versions`` +
outcome/contribution/gate events), and the wiki commons.

After a confirmed reset there is no account binding, no universe, and no hosted
daemon; the next authenticated founder's first contact creates a fresh home
universe. Destructive — callers gate on an explicit confirm.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import time
import uuid
from pathlib import Path
from typing import AbstractSet

# Universe-scoped tables in .tinyassets.db, cleared entirely. Every row belongs
# to a universe (index / visibility / ownership / per-universe runtime + branch
# INSTANCES). The reusable commons (branch_definitions, goals, gate_claims,
# canonical_bindings) have no universe_id and are NOT listed here.
_UNIVERSE_SCOPED_TABLES: tuple[str, ...] = (
    "universes",
    "universe_rules",
    "universe_acl",             # founder ownership grants
    "universe_notes",
    "universe_work_targets",
    "universe_hard_priorities",
    "universe_snapshots",
    "branches",                 # per-universe branch instances (NOT branch_definitions)
    "branch_heads",
    "founder_home",             # first-contact home binding (D10); present once that lands
)

# Daemon tables — cleared to reach "no hosted daemons". Daemon identity is
# platform-global (author_definitions has no universe_id); runtime instances are
# universe-scoped. Both go so a fresh start has zero daemons.
_DAEMON_TABLES: tuple[str, ...] = (
    "author_runtime_instances",
    "author_definitions",
    "author_forks",
)

_RESET_TABLES: tuple[str, ...] = _UNIVERSE_SCOPED_TABLES + _DAEMON_TABLES

# Commons that MUST survive a reset (documented for the summary; never touched).
_PRESERVED: tuple[str, ...] = (
    "branch_definitions", "branch_versions", "goals", "gate_claims",
    "canonical_bindings",
    ".runs.db (runs / branch_versions / outcomes / gate + contribution events)",
    "wiki/ commons",
)


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,),
    ).fetchone() is not None


def universe_dirs(base: Path) -> list[Path]:
    """Universe directories under ``base`` (excludes reserved operational dirs
    like wiki/output/runs/lance and any dotfile)."""
    from tinyassets.api.universe import _is_listable_universe_dir

    if not base.is_dir():
        return []
    return sorted(p for p in base.iterdir() if _is_listable_universe_dir(p))


class ResetPlanChangedError(RuntimeError):
    """The confirmed scope differs from the exact plan the operator reviewed."""


class ResetRestoreConflictError(RuntimeError):
    """A restore would overwrite state created after the reset."""


_RESET_BACKUP_DIR = ".resets"


def _require_test_principal(
    principal: str,
    allowed_principals: AbstractSet[str],
) -> str:
    subject = (principal or "").strip()
    allowed = {str(value).strip() for value in allowed_principals if str(value).strip()}
    if not subject or subject == "anonymous" or subject not in allowed:
        raise PermissionError(
            f"{subject or '<empty>'!r} is not an allowlisted test identity"
        )
    return subject


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _table_names(conn: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def _table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({_quoted(table)})")]


def _primary_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    keyed = [
        (int(row[5]), str(row[1]))
        for row in conn.execute(f"PRAGMA table_info({_quoted(table)})")
        if int(row[5]) > 0
    ]
    return [name for _, name in sorted(keyed)]


def _select_rows(
    conn: sqlite3.Connection,
    table: str,
    where: str,
    params: list[str],
) -> list[dict[str, object]]:
    old_factory = conn.row_factory
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            f"SELECT * FROM {_quoted(table)} WHERE {where}",
            params,
        ).fetchall()
    finally:
        conn.row_factory = old_factory
    return [dict(row) for row in rows]


def _row_keys(
    conn: sqlite3.Connection,
    table: str,
    rows: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not rows:
        return []
    keys = _primary_key_columns(conn, table)
    if not keys:
        raise RuntimeError(
            f"scoped reset refuses table {table!r}: matched rows have no primary key"
        )
    return sorted(
        ({key: row[key] for key in keys} for row in rows),
        key=lambda item: json.dumps(item, sort_keys=True, separators=(",", ":")),
    )


def _owned_universe_ids(conn: sqlite3.Connection, principal: str) -> list[str]:
    """Homes plus self-granted admin universes; delegated admin is not ownership."""
    tables = set(_table_names(conn))
    owned: set[str] = set()
    if "founder_home" in tables:
        owned.update(
            str(row[0])
            for row in conn.execute(
                "SELECT universe_id FROM founder_home WHERE founder_sub = ?",
                (principal,),
            )
            if row[0]
        )
    if "universe_acl" in tables:
        owned.update(
            str(row[0])
            for row in conn.execute(
                "SELECT universe_id FROM universe_acl "
                "WHERE actor_id = ? AND permission = 'admin' AND granted_by = ?",
                (principal, principal),
            )
            if row[0]
        )
    return sorted(owned)


def _safe_universe_dir(data_dir: Path, universe_id: str) -> Path | None:
    from tinyassets.api.universe import _TOP_LEVEL_OPERATIONAL_DATA_DIRS

    uid = (universe_id or "").strip()
    if (
        not uid
        or Path(uid).name != uid
        or uid.startswith(".")
        or uid in _TOP_LEVEL_OPERATIONAL_DATA_DIRS
    ):
        return None
    path = data_dir / uid
    try:
        if path.resolve().parent != data_dir.resolve():
            return None
    except OSError:
        return None
    return path


def _scope_rows(
    conn: sqlite3.Connection,
    data_dir: Path,
    principal: str,
) -> tuple[list[str], dict[str, list[dict[str, object]]]]:
    owned = _owned_universe_ids(conn, principal)
    placeholders = ",".join("?" for _ in owned)
    full_rows: dict[str, list[dict[str, object]]] = {}

    for table in _table_names(conn):
        columns = set(_table_columns(conn, table))
        if table in {"universe_acl", "founder_home"} or "universe_id" not in columns:
            continue
        if owned:
            rows = _select_rows(
                conn,
                table,
                f"universe_id IN ({placeholders})",
                list(owned),
            )
            if rows:
                full_rows[table] = rows

    branch_ids = [
        str(row["branch_id"])
        for row in full_rows.get("branches", [])
        if row.get("branch_id")
    ]
    if branch_ids and "branch_heads" in _table_names(conn):
        marks = ",".join("?" for _ in branch_ids)
        rows = _select_rows(conn, "branch_heads", f"branch_id IN ({marks})", branch_ids)
        if rows:
            full_rows["branch_heads"] = rows

    vote_ids = [
        str(row["vote_id"])
        for row in full_rows.get("vote_windows", [])
        if row.get("vote_id")
    ]
    if vote_ids and "vote_ballots" in _table_names(conn):
        marks = ",".join("?" for _ in vote_ids)
        rows = _select_rows(conn, "vote_ballots", f"vote_id IN ({marks})", vote_ids)
        if rows:
            full_rows["vote_ballots"] = rows

    if "universe_acl" in _table_names(conn):
        if owned:
            rows = _select_rows(
                conn,
                "universe_acl",
                f"actor_id = ? OR universe_id IN ({placeholders})",
                [principal, *owned],
            )
        else:
            rows = _select_rows(conn, "universe_acl", "actor_id = ?", [principal])
        if rows:
            full_rows["universe_acl"] = rows
    if "founder_home" in _table_names(conn):
        rows = _select_rows(conn, "founder_home", "founder_sub = ?", [principal])
        if rows:
            full_rows["founder_home"] = rows

    dirs = []
    for uid in owned:
        path = _safe_universe_dir(data_dir, uid)
        if path is not None and path.is_dir():
            dirs.append(uid)
    return sorted(dirs), dict(sorted(full_rows.items()))


def _plan_from_scope(
    conn: sqlite3.Connection,
    data_dir: Path,
    principal: str,
) -> tuple[dict[str, object], dict[str, list[dict[str, object]]]]:
    dirs, full_rows = _scope_rows(conn, data_dir, principal)
    keys = {
        table: _row_keys(conn, table, rows)
        for table, rows in full_rows.items()
    }
    digest_input = {
        "data_dir": str(data_dir.resolve()),
        "principal": principal,
        "universe_dirs": dirs,
        "rows": keys,
    }
    digest = hashlib.sha256(
        json.dumps(
            digest_input,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    plan: dict[str, object] = {
        **digest_input,
        "plan_id": f"sha256:{digest}",
        "preserved": list(_PRESERVED),
        "reversible": True,
        "confirmed": False,
    }
    return plan, full_rows


def plan_test_identity_reset(
    data_dir: Path,
    *,
    principal: str,
    allowed_principals: AbstractSet[str],
) -> dict[str, object]:
    """Enumerate an allowlisted test identity's exact reset scope, read-only."""
    from tinyassets.storage import DB_FILENAME

    subject = _require_test_principal(principal, allowed_principals)
    db_path = data_dir / DB_FILENAME
    if not db_path.is_file():
        digest_input = {
            "data_dir": str(data_dir.resolve()),
            "principal": subject,
            "universe_dirs": [],
            "rows": {},
        }
        digest = hashlib.sha256(
            json.dumps(digest_input, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return {
            **digest_input,
            "plan_id": f"sha256:{digest}",
            "preserved": list(_PRESERVED),
            "reversible": True,
            "confirmed": False,
        }
    with sqlite3.connect(str(db_path)) as conn:
        plan, _ = _plan_from_scope(conn, data_dir, subject)
    return plan


def _write_backup(
    data_dir: Path,
    *,
    principal: str,
    plan: dict[str, object],
    full_rows: dict[str, list[dict[str, object]]],
) -> tuple[str, Path]:
    reset_id = f"r-{uuid.uuid4().hex[:16]}"
    bundle = data_dir / _RESET_BACKUP_DIR / reset_id
    universes_backup = bundle / "u"
    universes_backup.mkdir(parents=True)
    for uid in plan["universe_dirs"]:
        source = _safe_universe_dir(data_dir, str(uid))
        if source is None or not source.is_dir():
            raise ResetPlanChangedError(f"planned universe directory changed: {uid}")
        shutil.copytree(source, universes_backup / str(uid))
    manifest = {
        "schema_version": 1,
        "reset_id": reset_id,
        "principal": principal,
        "plan_id": plan["plan_id"],
        "universe_dirs": plan["universe_dirs"],
        "row_keys": plan["rows"],
        "rows": full_rows,
        "created_at": time.time(),
    }
    encoded = json.dumps(manifest, sort_keys=True, indent=2)
    temp = bundle / "manifest.json.tmp"
    temp.write_text(encoded + "\n", encoding="utf-8")
    temp.replace(bundle / "manifest.json")
    return reset_id, bundle


def _delete_exact_rows(
    conn: sqlite3.Connection,
    rows: dict[str, list[dict[str, object]]],
) -> dict[str, int]:
    first = ["branch_heads", "vote_ballots"]
    last = ["universe_acl", "founder_home", "universe_rules", "universes"]
    middle = sorted(set(rows) - set(first) - set(last))
    removed: dict[str, int] = {}
    for table in [*first, *middle, *last]:
        table_rows = rows.get(table, [])
        if not table_rows:
            continue
        keys = _primary_key_columns(conn, table)
        count = 0
        for row in table_rows:
            where = " AND ".join(f"{_quoted(key)} = ?" for key in keys)
            cursor = conn.execute(
                f"DELETE FROM {_quoted(table)} WHERE {where}",
                [row[key] for key in keys],
            )
            count += max(0, cursor.rowcount)
        if count:
            removed[table] = count
    return removed


def reset_test_identity(
    data_dir: Path,
    *,
    principal: str,
    allowed_principals: AbstractSet[str],
    confirm: bool,
    plan_id: str = "",
) -> dict[str, object]:
    """Plan or apply one reversible, allowlisted test-identity reset."""
    from tinyassets.storage import DB_FILENAME

    subject = _require_test_principal(principal, allowed_principals)
    plan = plan_test_identity_reset(
        data_dir,
        principal=subject,
        allowed_principals=allowed_principals,
    )
    if not confirm:
        return plan
    if not plan_id or plan_id != plan["plan_id"]:
        raise ResetPlanChangedError(
            "reset scope changed or no reviewed plan_id was supplied"
        )
    if not plan["universe_dirs"] and not plan["rows"]:
        return {**plan, "confirmed": True, "done": True, "reset_id": ""}

    db_path = data_dir / DB_FILENAME
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        locked_plan, full_rows = _plan_from_scope(conn, data_dir, subject)
        if locked_plan["plan_id"] != plan_id:
            raise ResetPlanChangedError("reset scope changed after planning")
        reset_id, bundle = _write_backup(
            data_dir,
            principal=subject,
            plan=locked_plan,
            full_rows=full_rows,
        )
        try:
            removed = _delete_exact_rows(conn, full_rows)
            for uid in locked_plan["universe_dirs"]:
                path = _safe_universe_dir(data_dir, str(uid))
                if path is None:
                    raise ResetPlanChangedError(f"unsafe universe directory: {uid}")
                shutil.rmtree(path)
            conn.commit()
        except Exception:
            conn.rollback()
            for uid in locked_plan["universe_dirs"]:
                source = bundle / "u" / str(uid)
                target = _safe_universe_dir(data_dir, str(uid))
                if target is not None and source.is_dir():
                    if target.exists():
                        shutil.rmtree(target)
                    shutil.copytree(source, target)
            raise
    return {
        **plan,
        "confirmed": True,
        "done": True,
        "reset_id": reset_id,
        "rows_removed": removed,
    }


def _load_manifest(data_dir: Path, reset_id: str) -> tuple[Path, dict[str, object]]:
    rid = (reset_id or "").strip()
    if not rid or any(ch not in "abcdefghijklmnopqrstuvwxyz0123456789-" for ch in rid):
        raise ValueError("invalid reset_id")
    bundle = data_dir / _RESET_BACKUP_DIR / rid
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"unknown reset backup: {rid}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("reset_id") != rid:
        raise ValueError("invalid reset backup manifest")
    return bundle, manifest


def _row_exists(
    conn: sqlite3.Connection,
    table: str,
    key: dict[str, object],
) -> bool:
    where = " AND ".join(f"{_quoted(column)} = ?" for column in key)
    return conn.execute(
        f"SELECT 1 FROM {_quoted(table)} WHERE {where} LIMIT 1",
        list(key.values()),
    ).fetchone() is not None


def restore_test_identity(
    data_dir: Path,
    *,
    principal: str,
    allowed_principals: AbstractSet[str],
    reset_id: str,
    confirm: bool,
) -> dict[str, object]:
    """Plan or restore one scoped backup without overwriting newer state."""
    from tinyassets.storage import DB_FILENAME

    subject = _require_test_principal(principal, allowed_principals)
    bundle, manifest = _load_manifest(data_dir, reset_id)
    if manifest.get("principal") != subject:
        raise PermissionError("reset backup belongs to a different test identity")
    result: dict[str, object] = {
        "principal": subject,
        "reset_id": reset_id,
        "universe_dirs": list(manifest.get("universe_dirs", [])),
        "rows": dict(manifest.get("row_keys", {})),
        "confirmed": confirm,
    }
    if manifest.get("restored_at") is not None:
        return {**result, "restored": True, "already_restored": True}
    if not confirm:
        return result

    for uid in result["universe_dirs"]:
        target = _safe_universe_dir(data_dir, str(uid))
        if target is None or target.exists():
            raise ResetRestoreConflictError(
                f"restore target already exists or is unsafe: {uid}"
            )

    db_path = data_dir / DB_FILENAME
    full_rows = manifest.get("rows", {})
    if not isinstance(full_rows, dict):
        raise ValueError("invalid reset backup rows")
    created_dirs: list[Path] = []
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for table, keys in result["rows"].items():
            for key in keys:
                if _row_exists(conn, str(table), key):
                    raise ResetRestoreConflictError(
                        f"restore row already exists: {table} {key}"
                    )
        priority = {
            "universes": 0,
            "universe_rules": 1,
            "branches": 2,
            "vote_windows": 2,
            "universe_acl": 3,
            "founder_home": 3,
            "branch_heads": 4,
            "vote_ballots": 4,
        }
        try:
            for table in sorted(full_rows, key=lambda name: (priority.get(name, 2), name)):
                for row in full_rows[table]:
                    columns = list(row)
                    marks = ",".join("?" for _ in columns)
                    conn.execute(
                        f"INSERT INTO {_quoted(table)} "
                        f"({','.join(_quoted(column) for column in columns)}) "
                        f"VALUES ({marks})",
                        [row[column] for column in columns],
                    )
            for uid in result["universe_dirs"]:
                source = bundle / "u" / str(uid)
                target = _safe_universe_dir(data_dir, str(uid))
                if target is None or not source.is_dir():
                    raise ValueError(f"reset backup directory missing: {uid}")
                shutil.copytree(source, target)
                created_dirs.append(target)
            conn.commit()
        except Exception:
            conn.rollback()
            for target in created_dirs:
                if target.is_dir():
                    shutil.rmtree(target)
            raise

    manifest["restored_at"] = time.time()
    manifest_path = bundle / "manifest.json"
    temp = bundle / "manifest.json.tmp"
    temp.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temp.replace(manifest_path)
    return {**result, "restored": True}


def reset(data_dir: Path, *, confirm: bool) -> dict[str, object]:
    """Plan (and, when ``confirm``, execute) a clean-slate reset.

    Returns a plan dict describing what would be / was cleared. Idempotent:
    running twice is safe. Preserves the branch commons and ``.runs.db``.
    """
    from tinyassets.storage import DB_FILENAME

    udirs = universe_dirs(data_dir)
    marker = data_dir / ".active_universe"
    db_path = data_dir / DB_FILENAME

    table_counts: dict[str, int] = {}
    if db_path.is_file():
        conn = sqlite3.connect(str(db_path))
        try:
            for table in _RESET_TABLES:
                if _table_exists(conn, table):
                    n = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    if n:
                        table_counts[table] = n
        finally:
            conn.close()

    plan: dict[str, object] = {
        "data_dir": str(data_dir),
        "universe_dirs": [p.name for p in udirs],
        "active_universe_marker": marker.is_file(),
        "db_rows_to_clear": dict(table_counts),
        "preserved": list(_PRESERVED),
        "confirmed": confirm,
    }
    if not confirm:
        return plan

    for p in udirs:
        shutil.rmtree(p)
    if marker.is_file():
        marker.unlink()
    if db_path.is_file() and table_counts:
        conn = sqlite3.connect(str(db_path))
        try:
            for table in table_counts:
                conn.execute(f"DELETE FROM {table}")
            conn.commit()
        finally:
            conn.close()
    plan["done"] = True
    return plan


def load_test_identity_roster(raw: str | None = None) -> dict[str, str]:
    """Load operator aliases mapped to real resolved WorkOS subjects.

    This configuration contains identity identifiers only. It deliberately has
    no bearer-token, shared-secret, or auth-bypass representation.
    """
    source = raw if raw is not None else os.environ.get(
        "TINYASSETS_TEST_IDENTITIES", ""
    )
    try:
        parsed = json.loads(source)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            "TINYASSETS_TEST_IDENTITIES must be a JSON object of alias to subject"
        ) from exc
    if not isinstance(parsed, dict) or not parsed:
        raise ValueError(
            "TINYASSETS_TEST_IDENTITIES must be a non-empty JSON object"
        )

    roster: dict[str, str] = {}
    for raw_alias, raw_subject in parsed.items():
        if not isinstance(raw_alias, str) or not isinstance(raw_subject, str):
            raise ValueError("test identity aliases and subjects must be strings")
        alias = raw_alias.strip()
        subject = raw_subject.strip()
        if not alias or not subject:
            raise ValueError("test identity aliases and subjects must be non-empty")
        if subject == "anonymous":
            raise ValueError("anonymous cannot be a test identity")
        roster[alias] = subject
    if len(set(roster.values())) != len(roster):
        raise ValueError("test identity subjects must be unique")
    return roster


def main(argv: list[str] | None = None) -> int:
    """Operator CLI for plan/apply/restore of an allowlisted test identity."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Scoped, reversible TinyAssets test-identity reset",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    def add_scope(command: argparse.ArgumentParser) -> None:
        command.add_argument("--data-dir", required=True, type=Path)
        command.add_argument(
            "--identity",
            required=True,
            help="alias from TINYASSETS_TEST_IDENTITIES (never a bearer token)",
        )

    plan_parser = commands.add_parser("plan", help="enumerate exact reset scope")
    add_scope(plan_parser)
    apply_parser = commands.add_parser("apply", help="apply a reviewed reset plan")
    add_scope(apply_parser)
    apply_parser.add_argument("--plan-id", required=True)
    restore_parser = commands.add_parser("restore", help="plan or apply a restore")
    add_scope(restore_parser)
    restore_parser.add_argument("--reset-id", required=True)
    restore_parser.add_argument(
        "--confirm",
        action="store_true",
        help="restore after reviewing the default dry-run output",
    )

    args = parser.parse_args(argv)
    try:
        roster = load_test_identity_roster()
        principal = roster[args.identity]
        allowed = frozenset(roster.values())
        if args.command == "plan":
            result = plan_test_identity_reset(
                args.data_dir,
                principal=principal,
                allowed_principals=allowed,
            )
        elif args.command == "apply":
            result = reset_test_identity(
                args.data_dir,
                principal=principal,
                allowed_principals=allowed,
                confirm=True,
                plan_id=args.plan_id,
            )
        else:
            result = restore_test_identity(
                args.data_dir,
                principal=principal,
                allowed_principals=allowed,
                reset_id=args.reset_id,
                confirm=args.confirm,
            )
    except KeyError:
        parser.error(f"unknown test identity alias: {args.identity}")
    except (PermissionError, ResetPlanChangedError, ResetRestoreConflictError,
            FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised through main()
    raise SystemExit(main())

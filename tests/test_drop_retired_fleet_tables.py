"""The host action that drops the retired fleet tables backs up first and is idempotent."""

from __future__ import annotations

import importlib.util
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "drop_retired_fleet_tables.py"
_spec = importlib.util.spec_from_file_location("drop_retired_fleet_tables", _SCRIPT)
drop = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(drop)

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)


def _live_db(tmp_path: Path) -> Path:
    """Production's shape: the retired tables (captured schema) beside a live one."""
    db = tmp_path / ".tinyassets.db"
    ddl = (Path(__file__).parent / "fixtures" / "retired_fleet_tables.sql").read_text(
        encoding="utf-8"
    )
    with closing(sqlite3.connect(db)) as conn, conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(ddl)
        conn.execute("CREATE TABLE keep_me (id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO keep_me (id) VALUES (7)")
        conn.execute(
            "INSERT INTO cloud_automation_controls (universe_id, automation_id, "
            "principal_id, definition_json, definition_digest, cadence_seconds, "
            "revision, desired_state, updated_at, record_json) VALUES "
            "('u', 'a', 'p', '{}', 'd', 300, 1, 'stopped', 't', '{}')"
        )
        # A binding with an attempt: the RESTRICT foreign key production's 10
        # bindings sit behind, so the drop order is exercised, not assumed.
        conn.execute(
            "INSERT INTO background_branch_bindings VALUES "
            "('b1', 'active', 1, 'p', 'u', 'br', 'k', 's', 'r', 'd', '{}')"
        )
        conn.execute(
            "INSERT INTO background_branch_attempts VALUES "
            "('at1', 'key1', 'b1', 1, 'claimed', 't', 0, 'd', '{}')"
        )
    return db


def _tables(db: Path) -> set[str]:
    with closing(sqlite3.connect(db)) as conn:
        return {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def test_a_dry_run_reports_and_changes_nothing(tmp_path: Path) -> None:
    db = _live_db(tmp_path)
    before = _tables(db)

    report = drop.run(db, apply=False, now=NOW)

    assert report["applied"] is False
    assert report["present"]["cloud_automation_controls"] == 1
    assert _tables(db) == before
    assert not list(tmp_path.glob("*.bak"))


def test_apply_backs_up_then_drops_only_the_retired_tables(tmp_path: Path) -> None:
    db = _live_db(tmp_path)

    report = drop.run(db, apply=True, now=NOW)

    assert report["applied"] is True
    remaining = _tables(db)
    assert not set(drop.RETIRED_TABLES) & remaining
    assert "keep_me" in remaining
    backup = Path(report["backup"])
    # The backup holds the dropped data, byte-for-byte restorable.
    with closing(sqlite3.connect(backup)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM cloud_automation_controls").fetchone()[0] == 1
        assert conn.execute("SELECT id FROM keep_me").fetchone()[0] == 7


def test_a_second_run_is_a_no_op(tmp_path: Path) -> None:
    db = _live_db(tmp_path)
    drop.run(db, apply=True, now=NOW)

    again = drop.run(db, apply=True, now=datetime(2026, 9, 29, 13, 0, tzinfo=timezone.utc))

    assert again["present"] == {} and again["applied"] is False
    assert len(list(tmp_path.glob("*.bak"))) == 1  # no second backup


def test_a_failed_backup_verification_drops_nothing(tmp_path: Path, monkeypatch) -> None:
    db = _live_db(tmp_path)
    before = _tables(db)

    def corrupt(_backup, _expected):
        raise RuntimeError("backup row counts differ from live")

    monkeypatch.setattr(drop, "_verify", corrupt)
    with pytest.raises(RuntimeError, match="differ"):
        drop.run(db, apply=True, now=NOW)
    assert _tables(db) == before


def test_the_main_entry_refuses_a_missing_database(tmp_path: Path, capsys) -> None:
    assert drop.main(["--db", str(tmp_path / "absent.db"), "--apply"]) == 1
    assert "REFUSED" in capsys.readouterr().err

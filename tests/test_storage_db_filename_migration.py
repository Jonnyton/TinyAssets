"""Tests for the `.tinyassets.db` filename migration."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from tinyassets.storage import DB_FILENAME, _connect, db_path

LEGACY_DB_FILENAME = ".author_server.db"


def _seed_sqlite(path: Path, marker: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE marker (value TEXT NOT NULL)")
        conn.execute("INSERT INTO marker (value) VALUES (?)", (marker,))
        conn.commit()
    finally:
        conn.close()


def _read_marker(path: Path) -> str:
    conn = sqlite3.connect(path)
    try:
        row = conn.execute("SELECT value FROM marker").fetchone()
    finally:
        conn.close()
    return str(row[0])


def _backup_primary_files(path: Path) -> list[Path]:
    return sorted(
        p for p in path.iterdir()
        if (
            p.name.startswith(f"{LEGACY_DB_FILENAME}.legacy-")
            and not p.name.endswith(("-wal", "-shm"))
        )
    )


def test_connect_creates_workflow_db_for_fresh_universe(tmp_path: Path) -> None:
    conn = _connect(tmp_path)
    conn.close()

    assert (tmp_path / DB_FILENAME).is_file()
    assert not (tmp_path / LEGACY_DB_FILENAME).exists()


def test_db_path_migrates_legacy_db_filename(tmp_path: Path) -> None:
    legacy = tmp_path / LEGACY_DB_FILENAME
    _seed_sqlite(legacy, "legacy")

    resolved = db_path(tmp_path)

    assert resolved == tmp_path / DB_FILENAME
    assert resolved.is_file()
    assert not legacy.exists()
    assert _read_marker(resolved) == "legacy"


def test_db_path_migrates_wal_and_shm_siblings(tmp_path: Path) -> None:
    legacy = tmp_path / LEGACY_DB_FILENAME
    _seed_sqlite(legacy, "legacy")
    (tmp_path / f"{LEGACY_DB_FILENAME}-wal").write_bytes(b"wal-bytes")
    (tmp_path / f"{LEGACY_DB_FILENAME}-shm").write_bytes(b"shm-bytes")

    resolved = db_path(tmp_path)

    assert (tmp_path / f"{DB_FILENAME}-wal").read_bytes() == b"wal-bytes"
    assert (tmp_path / f"{DB_FILENAME}-shm").read_bytes() == b"shm-bytes"
    assert not (tmp_path / f"{LEGACY_DB_FILENAME}-wal").exists()
    assert not (tmp_path / f"{LEGACY_DB_FILENAME}-shm").exists()
    assert resolved == tmp_path / DB_FILENAME


def test_db_path_prefers_workflow_db_and_backs_up_legacy(
    tmp_path: Path,
    caplog,
) -> None:
    canonical = tmp_path / DB_FILENAME
    legacy = tmp_path / LEGACY_DB_FILENAME
    _seed_sqlite(canonical, "canonical")
    _seed_sqlite(legacy, "legacy")
    (tmp_path / f"{LEGACY_DB_FILENAME}-wal").write_bytes(b"legacy-wal")

    with caplog.at_level(logging.WARNING, logger="tinyassets.storage"):
        resolved = db_path(tmp_path)

    backups = _backup_primary_files(tmp_path)
    assert resolved == canonical
    assert _read_marker(canonical) == "canonical"
    assert len(backups) == 1
    assert (tmp_path / f"{backups[0].name}-wal").read_bytes() == b"legacy-wal"
    assert _read_marker(backups[0]) == "legacy"
    assert not legacy.exists()
    assert "backed up legacy SQLite files" in caplog.text


def test_db_path_migration_is_idempotent(tmp_path: Path) -> None:
    legacy = tmp_path / LEGACY_DB_FILENAME
    _seed_sqlite(legacy, "legacy")

    first = db_path(tmp_path)
    second = db_path(tmp_path)

    assert first == second == tmp_path / DB_FILENAME
    assert _read_marker(first) == "legacy"
    assert _backup_primary_files(tmp_path) == []


def test_db_path_is_exported_from_storage() -> None:
    import tinyassets.storage

    assert "db_path" in tinyassets.storage.__all__
    assert "author_server_db_path" not in tinyassets.storage.__all__
    assert callable(tinyassets.storage.db_path)

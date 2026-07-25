"""Tests for the `.tinyassets.db` filename migration."""

from __future__ import annotations

import contextlib
import logging
import os
import sqlite3
from pathlib import Path

import pytest

from tinyassets.storage import DB_FILENAME, _connect, db_path

LEGACY_DB_FILENAME = ".author_server.db"
# Canonical name between 20047d1d (2026-05-01) and 89edf995 (2026-06-26).
WORKFLOW_DB_FILENAME = ".workflow.db"


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


def _all_backup_primary_files(path: Path) -> list[Path]:
    """Timestamped backups of any legacy generation, excluding WAL/SHM siblings."""
    return sorted(
        p for p in path.iterdir()
        if ".legacy-" in p.name and not p.name.endswith(("-wal", "-shm"))
    )


def test_connect_creates_workflow_db_for_fresh_universe(tmp_path: Path) -> None:
    with _connect(tmp_path) as conn:
        assert conn is not None

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


def test_db_path_migrates_workflow_db_generation(tmp_path: Path) -> None:
    """`.workflow.db` was the canonical name between 20047d1d and 89edf995.

    The hard rename moved the canonical name on to `.tinyassets.db` without
    adding `.workflow.db` to the legacy chain, so any universe last booted in
    that window is invisible to the migrator.
    """
    stranded = tmp_path / WORKFLOW_DB_FILENAME
    _seed_sqlite(stranded, "workflow-generation")

    resolved = db_path(tmp_path)

    assert resolved == tmp_path / DB_FILENAME
    assert not stranded.exists()
    assert _read_marker(resolved) == "workflow-generation"


def test_db_path_migrates_workflow_db_wal_and_shm_siblings(tmp_path: Path) -> None:
    stranded = tmp_path / WORKFLOW_DB_FILENAME
    _seed_sqlite(stranded, "workflow-generation")
    (tmp_path / f"{WORKFLOW_DB_FILENAME}-wal").write_bytes(b"wal-bytes")
    (tmp_path / f"{WORKFLOW_DB_FILENAME}-shm").write_bytes(b"shm-bytes")

    resolved = db_path(tmp_path)

    assert resolved == tmp_path / DB_FILENAME
    assert (tmp_path / f"{DB_FILENAME}-wal").read_bytes() == b"wal-bytes"
    assert (tmp_path / f"{DB_FILENAME}-shm").read_bytes() == b"shm-bytes"
    assert not (tmp_path / f"{WORKFLOW_DB_FILENAME}-wal").exists()
    assert not (tmp_path / f"{WORKFLOW_DB_FILENAME}-shm").exists()


def test_db_path_prefers_newest_legacy_generation(tmp_path: Path, caplog) -> None:
    """Newest legacy generation wins; older generations are backed up, never lost."""
    _seed_sqlite(tmp_path / LEGACY_DB_FILENAME, "author-server")
    _seed_sqlite(tmp_path / WORKFLOW_DB_FILENAME, "workflow-generation")

    with caplog.at_level(logging.WARNING, logger="tinyassets.storage"):
        resolved = db_path(tmp_path)

    assert resolved == tmp_path / DB_FILENAME
    assert _read_marker(resolved) == "workflow-generation"
    assert not (tmp_path / LEGACY_DB_FILENAME).exists()
    assert not (tmp_path / WORKFLOW_DB_FILENAME).exists()

    backups = _backup_primary_files(tmp_path)
    assert len(backups) == 1
    assert _read_marker(backups[0]) == "author-server"


def test_db_path_backs_up_every_legacy_generation_when_canonical_exists(
    tmp_path: Path,
    caplog,
) -> None:
    _seed_sqlite(tmp_path / DB_FILENAME, "canonical")
    _seed_sqlite(tmp_path / LEGACY_DB_FILENAME, "author-server")
    _seed_sqlite(tmp_path / WORKFLOW_DB_FILENAME, "workflow-generation")

    with caplog.at_level(logging.WARNING, logger="tinyassets.storage"):
        resolved = db_path(tmp_path)

    assert resolved == tmp_path / DB_FILENAME
    assert _read_marker(resolved) == "canonical"
    assert not (tmp_path / LEGACY_DB_FILENAME).exists()
    assert not (tmp_path / WORKFLOW_DB_FILENAME).exists()

    markers = sorted(
        _read_marker(p) for p in _all_backup_primary_files(tmp_path)
    )
    assert markers == ["author-server", "workflow-generation"]


def test_workflow_db_migration_is_idempotent(tmp_path: Path) -> None:
    _seed_sqlite(tmp_path / WORKFLOW_DB_FILENAME, "workflow-generation")

    first = db_path(tmp_path)
    second = db_path(tmp_path)

    assert first == second == tmp_path / DB_FILENAME
    assert _read_marker(first) == "workflow-generation"
    assert _all_backup_primary_files(tmp_path) == []


def _seed_workflow_generation(work: Path) -> None:
    work.mkdir(parents=True, exist_ok=True)
    _seed_sqlite(work / WORKFLOW_DB_FILENAME, "workflow-generation")
    (work / f"{WORKFLOW_DB_FILENAME}-wal").write_bytes(b"wal-bytes")
    (work / f"{WORKFLOW_DB_FILENAME}-shm").write_bytes(b"shm-bytes")


def _run_with_replace_failing_at(work: Path, fail_at: int, monkeypatch) -> None:
    """Run db_path(), raising OSError on the `fail_at`-th os.replace call."""
    from tinyassets import storage as storage_mod

    real_replace = os.replace
    calls = {"n": 0}

    def flaky(src, dst):  # noqa: ANN001, ANN202
        calls["n"] += 1
        if calls["n"] >= fail_at:
            raise OSError("simulated crash mid-migration")
        return real_replace(src, dst)

    monkeypatch.setattr(storage_mod.os, "replace", flaky)
    try:
        with contextlib.suppress(OSError):
            db_path(work)
    finally:
        monkeypatch.undo()


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_migration_never_strands_sidecars_from_canonical_primary(
    tmp_path: Path,
    monkeypatch,
    fail_at: int,
) -> None:
    """A crash mid-migration must never split the primary DB from its WAL.

    The primary's rename is the completion marker, so at every interruption
    point either the canonical name has not been claimed yet, or the sidecars
    carrying its committed pages already arrived with it. The inverse — a
    canonical primary beside a stranded legacy WAL — is silent data loss: the
    next boot sees a canonical file, skips migration, and opens a DB whose
    committed-but-uncheckpointed pages are in a WAL it will never read.
    """
    work = tmp_path / f"attempt-{fail_at}"
    _seed_workflow_generation(work)

    _run_with_replace_failing_at(work, fail_at, monkeypatch)

    if (work / DB_FILENAME).exists():
        assert not (work / f"{WORKFLOW_DB_FILENAME}-wal").exists()
        assert not (work / f"{WORKFLOW_DB_FILENAME}-shm").exists()


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_migration_resumes_cleanly_after_interruption(
    tmp_path: Path,
    monkeypatch,
    fail_at: int,
) -> None:
    """Re-running after a crash completes the migration with data intact."""
    work = tmp_path / f"resume-{fail_at}"
    _seed_workflow_generation(work)

    _run_with_replace_failing_at(work, fail_at, monkeypatch)
    resolved = db_path(work)

    assert resolved == work / DB_FILENAME
    # Sidecars are asserted before _read_marker: opening the DB lets SQLite
    # clean up the synthetic sidecars, which would mask a failed move.
    assert (work / f"{DB_FILENAME}-wal").read_bytes() == b"wal-bytes"
    assert (work / f"{DB_FILENAME}-shm").read_bytes() == b"shm-bytes"
    assert not (work / WORKFLOW_DB_FILENAME).exists()
    assert not (work / f"{WORKFLOW_DB_FILENAME}-wal").exists()
    assert not (work / f"{WORKFLOW_DB_FILENAME}-shm").exists()
    assert _read_marker(resolved) == "workflow-generation"


def test_db_path_fails_closed_on_sidecar_orphaned_by_old_migrator(tmp_path: Path) -> None:
    """Pre-fix migrator renamed the primary first, so a crash could orphan a WAL.

    That WAL can hold committed transactions absent from the canonical DB, and
    SQLite validates a WAL against the exact database that wrote it, so it can
    neither be re-attached nor assumed redundant. Opening the canonical file
    anyway would silently serve incomplete state, so db_path must refuse.
    """
    _seed_sqlite(tmp_path / DB_FILENAME, "canonical")
    orphan = tmp_path / f"{WORKFLOW_DB_FILENAME}-wal"
    orphan.write_bytes(b"orphaned-wal")

    with pytest.raises(RuntimeError, match="orphaned"):
        db_path(tmp_path)


def test_orphaned_sidecar_refusal_is_sticky(tmp_path: Path) -> None:
    """The refusal must not clear itself on the next boot.

    Archiving the orphan before raising would make the second attempt succeed
    silently, reintroducing exactly the data loss the refusal exists to stop.
    """
    _seed_sqlite(tmp_path / DB_FILENAME, "canonical")
    orphan = tmp_path / f"{WORKFLOW_DB_FILENAME}-wal"
    orphan.write_bytes(b"orphaned-wal")

    for _ in range(3):
        with pytest.raises(RuntimeError, match="orphaned"):
            db_path(tmp_path)

    assert orphan.read_bytes() == b"orphaned-wal", "orphan must be left in place"


def test_orphan_refusal_clears_once_host_removes_the_sidecar(tmp_path: Path) -> None:
    """The documented recovery path actually works."""
    _seed_sqlite(tmp_path / DB_FILENAME, "canonical")
    orphan = tmp_path / f"{WORKFLOW_DB_FILENAME}-wal"
    orphan.write_bytes(b"orphaned-wal")

    with pytest.raises(RuntimeError):
        db_path(tmp_path)

    orphan.unlink()

    assert db_path(tmp_path) == tmp_path / DB_FILENAME


@pytest.mark.parametrize("fail_at", [1, 2, 3])
def test_interrupted_backup_never_divorces_sidecars_from_their_primary(
    tmp_path: Path,
    monkeypatch,
    fail_at: int,
) -> None:
    """An interrupted backup must not silently produce an unreadable backup.

    The backup destination is timestamped, so a resumed backup cannot rejoin a
    half-moved destination. Moving sidecars first makes the collision counter
    treat the interrupted attempt's own sidecars as a conflict and bump the
    primary to `<name>-1`, permanently divorcing it from the `-wal` holding its
    committed pages -- and the run still logs a successful backup. Every
    `.legacy-` sidecar must therefore keep a matching `.legacy-` primary.
    """
    work = tmp_path / f"backup-{fail_at}"
    work.mkdir()
    _seed_sqlite(work / DB_FILENAME, "canonical")
    _seed_sqlite(work / WORKFLOW_DB_FILENAME, "workflow-generation")
    (work / f"{WORKFLOW_DB_FILENAME}-wal").write_bytes(b"wal-bytes")
    (work / f"{WORKFLOW_DB_FILENAME}-shm").write_bytes(b"shm-bytes")

    _run_with_replace_failing_at(work, fail_at, monkeypatch)
    db_path(work)

    names = {p.name for p in work.iterdir()}
    backup_sidecars = {
        n for n in names if ".legacy-" in n and n.endswith(("-wal", "-shm"))
    }
    for sidecar in backup_sidecars:
        primary = sidecar[: -len("-wal")]
        assert primary in names, (
            f"backup sidecar {sidecar} has no matching primary {primary}; "
            f"its committed pages are unreadable. present={sorted(names)}"
        )


def test_db_path_is_exported_from_storage() -> None:
    import tinyassets.storage

    assert "db_path" in tinyassets.storage.__all__
    assert "author_server_db_path" not in tinyassets.storage.__all__
    assert callable(tinyassets.storage.db_path)

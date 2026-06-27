"""Run-transcript rotation tests (BUG-023 Phase 2).

Covers:
- Files older than retention get gzipped + moved to archived/.
- Files under retention stay put.
- Recursive + non-recursive modes preserve relative paths.
- Already-archived files are skipped (idempotent re-run).
- Per-file OSError is collected into errors[] and does not abort loop.
- Missing runs_dir → empty result, no raise.
- Env var `TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS` drives default.
"""
from __future__ import annotations

import gzip
import os
from pathlib import Path

import pytest

from tinyassets.storage.rotation import (
    RotationResult,
    _retention_days_from_env,
    rotate_run_transcripts,
)


@pytest.fixture
def runs_dir(tmp_path: Path) -> Path:
    d = tmp_path / "runs"
    d.mkdir()
    return d


def _set_mtime(path: Path, seconds_ago: float, *, clock: float) -> None:
    target = clock - seconds_ago
    os.utime(path, (target, target))


class TestRetentionEnvParsing:
    def test_default_when_unset(self, monkeypatch):
        monkeypatch.delenv(
            "TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS", raising=False,
        )
        assert _retention_days_from_env() == 30

    def test_valid_int(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS", "7")
        assert _retention_days_from_env() == 7

    def test_non_integer_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv(
            "TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS", "abc",
        )
        assert _retention_days_from_env() == 30

    def test_zero_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS", "0")
        assert _retention_days_from_env() == 30

    def test_negative_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS", "-5")
        assert _retention_days_from_env() == 30


class TestRotationHappyPath:
    def test_old_file_is_archived(self, runs_dir: Path):
        clock = 1_000_000_000.0
        old = runs_dir / "old.log"
        old.write_text("stale run output")
        _set_mtime(old, seconds_ago=31 * 86400, clock=clock)

        result = rotate_run_transcripts(
            runs_dir,
            retention_days=30,
            now_fn=lambda: clock,
        )

        assert result.archived == 1
        assert result.errors == []
        assert not old.exists()
        archived = runs_dir / "archived" / "old.log.gz"
        assert archived.exists()
        with gzip.open(archived, "rt") as f:
            assert f.read() == "stale run output"

    def test_recent_file_stays(self, runs_dir: Path):
        clock = 1_000_000_000.0
        recent = runs_dir / "recent.log"
        recent.write_text("fresh run")
        _set_mtime(recent, seconds_ago=2 * 86400, clock=clock)

        result = rotate_run_transcripts(
            runs_dir,
            retention_days=30,
            now_fn=lambda: clock,
        )

        assert result.archived == 0
        assert result.skipped_under_retention == 1
        assert recent.exists()
        assert not (runs_dir / "archived" / "recent.log.gz").exists()

    def test_nested_directory_preserves_relative_path(self, runs_dir: Path):
        clock = 1_000_000_000.0
        nested_dir = runs_dir / "2026-03"
        nested_dir.mkdir()
        nested = nested_dir / "run.log"
        nested.write_text("nested run")
        _set_mtime(nested, seconds_ago=40 * 86400, clock=clock)

        result = rotate_run_transcripts(
            runs_dir,
            retention_days=30,
            now_fn=lambda: clock,
        )

        assert result.archived == 1
        assert (runs_dir / "archived" / "2026-03" / "run.log.gz").exists()


class TestIdempotency:
    def test_rerun_after_archival_is_noop(self, runs_dir: Path):
        clock = 1_000_000_000.0
        old = runs_dir / "old.log"
        old.write_text("data")
        _set_mtime(old, seconds_ago=40 * 86400, clock=clock)

        rotate_run_transcripts(
            runs_dir, retention_days=30, now_fn=lambda: clock,
        )
        second = rotate_run_transcripts(
            runs_dir, retention_days=30, now_fn=lambda: clock,
        )

        assert second.archived == 0
        assert second.scanned == 0  # source gone, archived/ skipped
        assert (runs_dir / "archived" / "old.log.gz").exists()

    def test_stale_archive_with_lingering_source_converges(
        self, runs_dir: Path,
    ):
        """If a prior rotation gzipped but failed to delete the source,
        a re-run should clean up the source and skip without re-archiving."""
        clock = 1_000_000_000.0
        old = runs_dir / "leaked.log"
        old.write_text("data")
        _set_mtime(old, seconds_ago=40 * 86400, clock=clock)

        archive_dir = runs_dir / "archived"
        archive_dir.mkdir()
        archived_existing = archive_dir / "leaked.log.gz"
        with gzip.open(archived_existing, "wb") as f:
            f.write(b"data")

        result = rotate_run_transcripts(
            runs_dir, retention_days=30, now_fn=lambda: clock,
        )

        assert not old.exists()  # source unlinked on convergence
        assert archived_existing.exists()  # archive preserved
        assert result.skipped_already_archived >= 1


class TestSkipsGzInLiveDir:
    def test_gz_file_in_runs_is_not_re_archived(self, runs_dir: Path):
        clock = 1_000_000_000.0
        stray_gz = runs_dir / "manual-upload.txt.gz"
        stray_gz.write_bytes(b"\x1f\x8b\x08")  # gzip header bytes
        _set_mtime(stray_gz, seconds_ago=40 * 86400, clock=clock)

        result = rotate_run_transcripts(
            runs_dir, retention_days=30, now_fn=lambda: clock,
        )

        assert result.archived == 0
        assert result.skipped_already_archived == 1
        assert stray_gz.exists()


class TestErrorsDoNotAbort:
    def test_missing_runs_dir_returns_empty(self, tmp_path: Path):
        missing = tmp_path / "not_there"
        result = rotate_run_transcripts(
            missing, retention_days=30, now_fn=lambda: 1_000_000_000.0,
        )
        assert isinstance(result, RotationResult)
        assert result.scanned == 0
        assert result.archived == 0
        assert result.errors == []


class TestBoundaryConditions:
    def test_exactly_at_retention_does_not_archive(self, runs_dir: Path):
        clock = 1_000_000_000.0
        boundary = runs_dir / "boundary.log"
        boundary.write_text("data")
        # Exactly retention_days old → mtime == cutoff → not archived
        # (cutoff is exclusive: only files with mtime < cutoff move).
        _set_mtime(boundary, seconds_ago=30 * 86400, clock=clock)

        result = rotate_run_transcripts(
            runs_dir, retention_days=30, now_fn=lambda: clock,
        )

        assert result.archived == 0
        assert boundary.exists()

    def test_just_past_retention_archives(self, runs_dir: Path):
        clock = 1_000_000_000.0
        past = runs_dir / "past.log"
        past.write_text("data")
        _set_mtime(past, seconds_ago=30 * 86400 + 1, clock=clock)

        result = rotate_run_transcripts(
            runs_dir, retention_days=30, now_fn=lambda: clock,
        )

        assert result.archived == 1


class TestMixedFixture:
    def test_mixed_recent_and_old_files(self, runs_dir: Path):
        clock = 1_000_000_000.0
        for i in range(5):
            f = runs_dir / f"old-{i}.log"
            f.write_text(f"old {i}")
            _set_mtime(f, seconds_ago=60 * 86400, clock=clock)
        for i in range(3):
            f = runs_dir / f"new-{i}.log"
            f.write_text(f"new {i}")
            _set_mtime(f, seconds_ago=1 * 86400, clock=clock)

        result = rotate_run_transcripts(
            runs_dir, retention_days=30, now_fn=lambda: clock,
        )

        assert result.archived == 5
        assert result.skipped_under_retention == 3
        assert result.errors == []
        for i in range(5):
            assert (runs_dir / "archived" / f"old-{i}.log.gz").exists()
            assert not (runs_dir / f"old-{i}.log").exists()
        for i in range(3):
            assert (runs_dir / f"new-{i}.log").exists()

"""Run-transcript rotation (BUG-023 Phase 2).

Moves run transcripts older than a retention window into an ``archived/``
subdirectory, compressed with gzip. Prevents the 2026-04-23 P0 class where
run artifacts accumulate silently until the volume fills.

Design:
- Reads retention days from ``TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS``
  (default 30). Files whose mtime is older than ``now - retention`` move.
- Only regular files under ``<data_dir>/runs/`` (non-recursive relative
  to the runs root by default; descended when ``recursive=True``).
- Destination preserves the relative path + appends ``.gz`` suffix,
  placed under ``<data_dir>/runs/archived/``. Already-archived files are
  skipped; re-running is idempotent.
- Never crashes the caller — per-file errors are collected into the
  result, not raised. The rotation loop logs and continues.

Scheduled via ``scripts/rotate_run_transcripts.py`` (CLI entry) which
can be wired to a systemd timer or invoked inline from the existing
disk-watch cadence.
"""
from __future__ import annotations

import gzip
import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from tinyassets.storage import data_dir

logger = logging.getLogger(__name__)

_DEFAULT_RETENTION_DAYS = 30
_ARCHIVED_DIRNAME = "archived"
_RUNS_DIRNAME = "runs"


@dataclass
class RotationResult:
    """Summary of a rotation pass, for logging + test assertions."""

    scanned: int = 0
    archived: int = 0
    skipped_already_archived: int = 0
    skipped_under_retention: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "scanned": self.scanned,
            "archived": self.archived,
            "skipped_already_archived": self.skipped_already_archived,
            "skipped_under_retention": self.skipped_under_retention,
            "errors": list(self.errors),
        }


def _retention_days_from_env() -> int:
    raw = os.environ.get("TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS", "").strip()
    if not raw:
        return _DEFAULT_RETENTION_DAYS
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS=%r is not an integer; "
            "using default %d",
            raw, _DEFAULT_RETENTION_DAYS,
        )
        return _DEFAULT_RETENTION_DAYS
    if value < 1:
        logger.warning(
            "TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS=%d is < 1; using default %d",
            value, _DEFAULT_RETENTION_DAYS,
        )
        return _DEFAULT_RETENTION_DAYS
    return value


def rotate_run_transcripts(
    runs_dir: Path | None = None,
    *,
    retention_days: int | None = None,
    now_fn: Callable[[], float] = time.time,
    recursive: bool = True,
) -> RotationResult:
    """Compress + archive run transcripts older than the retention window.

    Parameters
    ----------
    runs_dir
        Directory holding run transcripts. Defaults to
        ``data_dir() / "runs"``.
    retention_days
        Files with mtime older than ``now - retention_days`` move.
        Defaults to ``TINYASSETS_RUN_TRANSCRIPT_RETENTION_DAYS`` env var,
        or 30.
    now_fn
        Injection seam for mock clock. Returns POSIX seconds.
    recursive
        When True, descends into subdirectories under ``runs_dir`` and
        mirrors the relative path into ``archived/``. When False, only
        top-level files rotate.
    """
    base = runs_dir if runs_dir is not None else data_dir() / _RUNS_DIRNAME
    if retention_days is None:
        retention_days = _retention_days_from_env()

    result = RotationResult()

    if not base.is_dir():
        # No runs dir yet → nothing to rotate, not an error.
        return result

    cutoff_ts = now_fn() - (retention_days * 86400)
    archived_root = base / _ARCHIVED_DIRNAME

    iterator = base.rglob("*") if recursive else base.iterdir()
    for src in iterator:
        try:
            # Skip the archive dir itself + any contents beneath it.
            if archived_root in src.parents or src == archived_root:
                continue
            if not src.is_file():
                continue

            # Already-archived files (end with .gz under archived root) are
            # impossible here due to the parent-of-archived_root guard,
            # but also skip any .gz that looks like prior rotation output.
            if src.suffix == ".gz" and src.name.endswith(".gz"):
                # Inside the live runs dir (not archived/), a .gz file is
                # either a user-written artifact OR a prior rotation that
                # failed mid-move. Skip it either way — idempotent.
                result.skipped_already_archived += 1
                continue

            result.scanned += 1

            try:
                mtime = src.stat().st_mtime
            except OSError as exc:
                result.errors.append((str(src), f"stat failed: {exc}"))
                continue

            if mtime >= cutoff_ts:
                result.skipped_under_retention += 1
                continue

            rel = src.relative_to(base)
            dest = archived_root / rel.with_suffix(rel.suffix + ".gz")
            dest.parent.mkdir(parents=True, exist_ok=True)

            if dest.exists():
                # Rare: a previous run archived this file but didn't
                # delete the source. Treat as already-archived and drop
                # the source to converge.
                try:
                    src.unlink()
                    result.skipped_already_archived += 1
                except OSError as exc:
                    result.errors.append(
                        (str(src), f"unlink after stale-archive: {exc}")
                    )
                continue

            try:
                with src.open("rb") as fsrc, gzip.open(dest, "wb") as fdst:
                    shutil.copyfileobj(fsrc, fdst)
                src.unlink()
            except OSError as exc:
                result.errors.append((str(src), f"compress+move failed: {exc}"))
                # Clean up partial dest if write crashed mid-stream.
                try:
                    if dest.exists():
                        dest.unlink()
                except OSError:
                    pass
                continue

            result.archived += 1
            logger.info(
                "rotate_run_transcripts: archived %s -> %s",
                src, dest,
            )
        except Exception as exc:  # noqa: BLE001 — rotation never crashes
            result.errors.append((str(src), f"unexpected: {exc}"))
            logger.exception("rotate_run_transcripts: unexpected on %s", src)

    return result


# ---------------------------------------------------------------------------
# Activity-log rotation (BUG-023 Phase 3)
# ---------------------------------------------------------------------------

_ACTIVITY_LOG_SOFT_CAP_ENV = "TINYASSETS_CAP_ACTIVITY_LOG_BYTES"
_ACTIVITY_LOG_FILENAME = "activity.log"


def _activity_log_soft_cap_bytes() -> int:
    raw = os.environ.get(_ACTIVITY_LOG_SOFT_CAP_ENV, "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; activity_log rotation disabled",
            _ACTIVITY_LOG_SOFT_CAP_ENV, raw,
        )
        return 0
    return max(0, value)


def rotate_activity_log(
    log_path: Path | None = None,
    *,
    soft_cap_bytes: int | None = None,
) -> bool:
    """Rotate activity.log when it exceeds the soft cap.

    When the log file's size >= ``soft_cap_bytes``, renames it to
    ``activity.log.1``. The live file is then absent so subsequent
    writes start fresh.

    Parameters
    ----------
    log_path
        Path to the log file. Defaults to ``data_dir() / "activity.log"``.
    soft_cap_bytes
        Size threshold in bytes. When 0 or None, reads
        ``TINYASSETS_CAP_ACTIVITY_LOG_BYTES`` from env; if still 0, rotation
        is disabled and the function returns False.

    Returns
    -------
    bool
        True if rotation happened, False otherwise.
    """
    if log_path is None:
        log_path = data_dir() / _ACTIVITY_LOG_FILENAME
    if soft_cap_bytes is None:
        soft_cap_bytes = _activity_log_soft_cap_bytes()
    if soft_cap_bytes <= 0:
        return False

    try:
        size = log_path.stat().st_size if log_path.exists() else 0
    except OSError:
        return False

    if size < soft_cap_bytes:
        return False

    rotated = log_path.with_name(log_path.name + ".1")
    try:
        log_path.replace(rotated)
    except OSError as exc:
        logger.warning("rotate_activity_log: rename failed: %s", exc)
        return False

    logger.info(
        "rotate_activity_log: rotated %s -> %s (was %d bytes, cap %d)",
        log_path, rotated, size, soft_cap_bytes,
    )
    return True


# ---------------------------------------------------------------------------
# Universe-outputs pruning (BUG-023 Phase 3)
# ---------------------------------------------------------------------------

_UNIVERSE_OUTPUTS_HARD_CAP_ENV = "TINYASSETS_CAP_UNIVERSE_OUTPUTS_BYTES"
_OUTPUT_DIRNAME = "output"


def _universe_outputs_hard_cap_bytes() -> int:
    raw = os.environ.get(_UNIVERSE_OUTPUTS_HARD_CAP_ENV, "").strip()
    if not raw:
        return 0
    try:
        value = int(raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; universe_outputs pruning disabled",
            _UNIVERSE_OUTPUTS_HARD_CAP_ENV, raw,
        )
        return 0
    return max(0, value)


def prune_universe_outputs(
    outputs_dir: Path | None = None,
    *,
    hard_cap_bytes: int | None = None,
) -> list[str]:
    """Prune oldest files from universe outputs until under the soft cap.

    When total bytes in ``outputs_dir`` exceeds ``hard_cap_bytes``, deletes
    the oldest files (by mtime) until the directory is back under 80% of
    the hard cap. Audit-logs every deletion with path + reason.

    Parameters
    ----------
    outputs_dir
        Directory to prune. Defaults to ``data_dir() / "output"``.
    hard_cap_bytes
        Hard cap in bytes. When 0 or None, reads
        ``TINYASSETS_CAP_UNIVERSE_OUTPUTS_BYTES`` from env; if still 0,
        pruning is disabled and an empty list is returned.

    Returns
    -------
    list[str]
        Paths of files deleted, in deletion order (oldest first).
    """
    if outputs_dir is None:
        outputs_dir = data_dir() / _OUTPUT_DIRNAME
    if hard_cap_bytes is None:
        hard_cap_bytes = _universe_outputs_hard_cap_bytes()
    if hard_cap_bytes <= 0:
        return []

    if not outputs_dir.is_dir():
        return []

    soft_cap = int(hard_cap_bytes * 0.80)

    candidates: list[tuple[float, int, Path]] = []
    total_bytes = 0
    for child in outputs_dir.rglob("*"):
        try:
            if not child.is_file():
                continue
            st = child.stat()
            candidates.append((st.st_mtime, st.st_size, child))
            total_bytes += st.st_size
        except OSError:
            continue

    if total_bytes <= hard_cap_bytes:
        return []

    candidates.sort(key=lambda t: t[0])

    deleted: list[str] = []
    for mtime, size, path in candidates:
        if total_bytes <= soft_cap:
            break
        try:
            path.unlink()
            total_bytes -= size
            deleted.append(str(path))
            logger.info(
                "prune_universe_outputs: deleted %s (mtime=%s, size=%d) "
                "reason=hard_cap_exceeded",
                path, mtime, size,
            )
        except OSError as exc:
            logger.warning("prune_universe_outputs: unlink %s failed: %s", path, exc)

    return deleted


# ---------------------------------------------------------------------------
# Startup storage probe (BUG-023 Phase 3)
# ---------------------------------------------------------------------------


def startup_storage_probe(
    *,
    log_path: Path | None = None,
    outputs_dir: Path | None = None,
) -> dict[str, object]:
    """Run storage enforcement at daemon startup.

    Checks activity_log and universe_outputs immediately; runs rotation
    or pruning if over cap.

    Returns
    -------
    dict with keys:
        activity_log_rotated: bool
        universe_outputs_pruned: list[str]
    """
    activity_rotated = rotate_activity_log(log_path)
    outputs_pruned = prune_universe_outputs(outputs_dir)
    return {
        "activity_log_rotated": activity_rotated,
        "universe_outputs_pruned": outputs_pruned,
    }


# ---------------------------------------------------------------------------
# Required data-file probe (BUG-027)
# ---------------------------------------------------------------------------

_REQUIRED_DATA_FILES: list[str] = [
    "data/world_rules.lp",
]


def startup_file_probe(package_root: Path | None = None) -> list[str]:
    """Check that required static data files are present under package_root.

    Returns a list of relative paths (relative to package_root) that are
    missing.  An empty list means all required files are present.

    Parameters
    ----------
    package_root:
        Root directory to search (defaults to the repo/package root derived
        from this module's location: parents[3] of rotation.py puts us at
        the checkout root where data/ lives).
    """
    import logging as _logging

    _log = _logging.getLogger(__name__)

    if package_root is None:
        package_root = Path(__file__).resolve().parents[2]

    missing: list[str] = []
    for rel in _REQUIRED_DATA_FILES:
        full = package_root / rel
        if not full.exists():
            missing.append(rel)
            _log.warning(
                "Required data file missing: %s (expected at %s). "
                "Cloud image may be missing COPY data/world_rules.lp.",
                rel,
                full,
            )
    return missing

"""Workspace staging: created per operation, removed on EVERY exit, swept by liveness.

Staging is a worker's private scratch for one checkout, push or remote probe. It
holds the credentialed clone, the bundle and the git homes, so a staging directory
left behind is both a disk leak and possibly retained credential material.
Measured 2026-09-30 on production: 334 leaked directories, 2.8 GiB, in one universe
-- every checkout that failed before its success-path ``rmtree`` left its staging
behind, and push staging was never removed at all (concern
2026-09-30-workspace-staging-leaks-on-failed-checkouts).

Three rules:

1. **Owned.** A staging directory is created under
   ``<base>/.workspace-staging/<owner token>/...``, where the token is this
   process's `process_liveness` token for that staging root, and its liveness
   lock is held before the directory exists. Whether a directory is in use is
   therefore a FACT the kernel keeps, not a guess from its age.
2. **Removed on every exit.** `staging()` removes its directory in a ``finally``:
   success, failure, exception and cancellation alike.
3. **Swept by proof, completely.** `sweep()` removes a token's directory only when
   `process_liveness.owner_state` says the owner is ``dead``. ``alive`` and
   ``unknown`` are never touched. Removal first RENAMES the tree to a
   ``.trash-*`` name in the same root -- so no partial tree is ever left under a
   name something might use -- then deletes it; a delete interrupted half way is
   finished by the next sweep, because trash is nobody's.

Entries from before this layout (no token) were written by code that no longer
exists; they are removed only when nothing in them was modified after this process
started, so a layout proof and a time bound together -- never age alone.
"""

from __future__ import annotations

import logging
import os
import re
import secrets
import shutil
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from tinyassets import process_liveness

logger = logging.getLogger(__name__)

STAGING_DIR = ".workspace-staging"
_TRASH_PREFIX = ".trash-"
_TOKEN_NAME = re.compile(r"^proc_[0-9a-f]{24}$")

#: Anything under a legacy (pre-token) entry modified after this instant may be
#: a live write, so it is kept. Set at import: nothing in THIS process can have
#: written a legacy entry, because this code never creates one.
_PROCESS_STARTED_AT = time.time()

#: How often the background sweeper runs after its startup pass.
SWEEP_INTERVAL_S = 600.0


def staging_root(base_path: str | Path) -> Path:
    return Path(base_path) / STAGING_DIR


def create(base_path: str | Path, *parts: str) -> Path:
    """A fresh staging directory owned by this process.

    The liveness lock is taken FIRST, so there is no instant at which the
    directory exists and its owner cannot be proven alive.
    """
    for part in parts:
        if not part or Path(part).name != part or part in {".", ".."}:
            raise ValueError(f"not a single path segment: {part!r}")
    root = staging_root(base_path)
    root.mkdir(parents=True, exist_ok=True)
    token = process_liveness.owner_token(root)
    path = root.joinpath(token, *parts)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _tree_bytes_and_newest(path: Path) -> tuple[int, float]:
    """Logical bytes and newest mtime of a tree, without following links."""
    try:
        top = os.lstat(path)
    except FileNotFoundError:
        return 0, 0.0
    total, newest = 0, top.st_mtime
    if not stat.S_ISDIR(top.st_mode):
        return (top.st_size if stat.S_ISREG(top.st_mode) else 0), newest
    stack = [path]
    while stack:
        directory = stack.pop()
        try:
            entries = list(os.scandir(directory))
        except OSError:
            continue
        for entry in entries:
            try:
                st = entry.stat(follow_symlinks=False)
            except OSError:
                continue
            newest = max(newest, st.st_mtime)
            if stat.S_ISDIR(st.st_mode):
                stack.append(Path(entry.path))
            elif stat.S_ISREG(st.st_mode):
                total += st.st_size
    return total, newest


def _rmtree(path: Path) -> None:
    def _onerror(func, target, exc_info):  # noqa: ANN001 - shutil callback
        if isinstance(exc_info[1], FileNotFoundError):
            return  # another remover got there first
        try:
            os.chmod(target, stat.S_IWRITE | stat.S_IREAD | stat.S_IEXEC)
            func(target)
        except FileNotFoundError:
            return

    shutil.rmtree(path, onerror=_onerror)


def _remove_completely(root: Path, path: Path) -> bool:
    """Rename ``path`` to trash inside ``root``, then delete the trash.

    Returns True when nothing is left at either name. On False the tree is at a
    ``.trash-*`` name (or, if the rename itself failed, where it was) and the next
    sweep finishes it; either way it is logged.
    """
    if not os.path.lexists(path):
        return True
    trash = root / f"{_TRASH_PREFIX}{secrets.token_hex(8)}"
    try:
        os.rename(path, trash)
    except FileNotFoundError:
        return True
    except OSError:
        logger.exception("workspace staging could not be moved aside: %s", path)
        return False
    try:
        _rmtree(trash)
    except OSError:
        logger.exception("workspace staging removal incomplete; the sweep retries: %s", trash)
    if os.path.lexists(trash):
        logger.error("workspace staging still present after removal; the sweep retries: %s", trash)
        return False
    return True


def _root_of(path: Path) -> Path:
    for parent in path.parents:
        if parent.name == STAGING_DIR:
            return parent
    raise ValueError(f"{path} is not inside a {STAGING_DIR} directory")


def remove(path: str | Path) -> bool:
    """Remove one staging directory completely. Never raises: it runs in a
    ``finally`` whose own exception must win. False means the sweep owns it now."""
    try:
        target = Path(path)
        return _remove_completely(_root_of(target), target)
    except Exception:  # noqa: BLE001 - see docstring
        logger.exception("workspace staging removal failed for %s", path)
        return False


@contextmanager
def staging(base_path: str | Path, *parts: str) -> Iterator[Path]:
    """``with staging(base, run, node) as path:`` -- removed on every exit."""
    path = create(base_path, *parts)
    try:
        yield path
    finally:
        remove(path)


@dataclass
class SweepReport:
    removed: int = 0
    removed_bytes: int = 0
    kept_live: int = 0
    kept_unknown: int = 0
    failed: int = 0
    roots: list[str] = field(default_factory=list)

    def add(self, other: SweepReport) -> None:
        self.removed += other.removed
        self.removed_bytes += other.removed_bytes
        self.kept_live += other.kept_live
        self.kept_unknown += other.kept_unknown
        self.failed += other.failed
        self.roots.extend(other.roots)


def sweep(base_path: str | Path) -> SweepReport:
    """Remove every staging entry under ``base_path`` that no live owner holds.

    Idempotent: a second pass over the same state removes nothing more.
    """
    report = SweepReport()
    root = staging_root(base_path)
    try:
        info = os.lstat(root)
    except FileNotFoundError:
        return report
    if not stat.S_ISDIR(info.st_mode):
        return report  # a link or a file named like the root is not ours to walk
    report.roots.append(str(root))
    for entry in sorted(os.listdir(root)):
        path = root / entry
        if entry == process_liveness.LIVENESS_DIR:
            continue
        if entry.startswith(_TRASH_PREFIX):
            removable = True
        elif _TOKEN_NAME.match(entry):
            state = process_liveness.owner_state(root, entry)
            if state == process_liveness.ALIVE:
                report.kept_live += 1
                continue
            if state != process_liveness.DEAD:
                report.kept_unknown += 1  # never proven dead: never deleted
                continue
            removable = True
        else:
            # Legacy layout: kept unless nothing in it changed since we started.
            _, newest = _tree_bytes_and_newest(path)
            removable = newest < _PROCESS_STARTED_AT
            if not removable:
                report.kept_unknown += 1
                continue
        size, _ = _tree_bytes_and_newest(path)
        if _remove_completely(root, path):
            report.removed += 1
            report.removed_bytes += size
            if _TOKEN_NAME.match(entry):
                process_liveness.remove_if_dead(
                    root, entry, still_named=lambda t: os.path.lexists(root / t),
                )
        else:
            report.failed += 1
    return report


def sweep_data_root(data_root: str | Path) -> SweepReport:
    """Sweep the data root's staging and every universe directory's staging, and
    log the inventory of what was removed."""
    base = Path(data_root)
    report = SweepReport()
    candidates = [base]
    try:
        for child in sorted(base.iterdir()):
            if child.is_dir() and not child.is_symlink():
                candidates.append(child)
    except OSError:
        logger.exception("workspace staging sweep could not list %s", base)
    for candidate in candidates:
        try:
            report.add(sweep(candidate))
        except Exception:  # noqa: BLE001 - one root must not stop the others
            logger.exception("workspace staging sweep failed under %s", candidate)
            report.failed += 1
    if report.removed or report.failed:
        logger.warning(
            "workspace staging sweep: removed %d dir(s), %d bytes; kept %d live, "
            "%d unproven; %d failed (retried next pass)",
            report.removed, report.removed_bytes, report.kept_live,
            report.kept_unknown, report.failed,
        )
    return report


_SWEEPER: threading.Thread | None = None
_STOP = threading.Event()
_SWEEPER_LOCK = threading.Lock()


def start_sweeper(data_root: str | Path, *, interval_s: float = SWEEP_INTERVAL_S) -> bool:
    """Sweep now and then every ``interval_s``, on a daemon thread. Once per
    process; returns False when one is already running."""
    global _SWEEPER
    with _SWEEPER_LOCK:
        if _SWEEPER is not None and _SWEEPER.is_alive():
            return False
        _STOP.clear()

        def _loop() -> None:
            while True:
                try:
                    sweep_data_root(data_root)
                except Exception:  # noqa: BLE001 - the next pass retries
                    logger.exception("workspace staging sweep pass failed")
                if _STOP.wait(interval_s):
                    return

        _SWEEPER = threading.Thread(target=_loop, name="workspace-staging-sweep", daemon=True)
        _SWEEPER.start()
        return True


def stop_sweeper(timeout_s: float = 5.0) -> bool:
    global _SWEEPER
    with _SWEEPER_LOCK:
        thread = _SWEEPER
        _STOP.set()
    if thread is None:
        return True
    thread.join(timeout_s)
    with _SWEEPER_LOCK:
        if _SWEEPER is thread and not thread.is_alive():
            _SWEEPER = None
    return not thread.is_alive()


__all__ = [
    "STAGING_DIR",
    "SweepReport",
    "create",
    "remove",
    "staging",
    "staging_root",
    "start_sweeper",
    "stop_sweeper",
    "sweep",
    "sweep_data_root",
]

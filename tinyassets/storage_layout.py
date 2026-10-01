"""The data-layout marker: an image never runs against data it does not understand.

The universe -> command center cutover (`openspec/changes/rename-universe-to-
command-center`, design D7.2 / D10) renames tables, columns, files and ids in one
locked migration run. An image built for the old layout must never start against
renamed data: it would find no ``universes`` table and could create a blank home
for a person who already has one. So this marker ships first (C4a), alone, and is
the production baseline before any migration exists:

* ``data_dir()/.layout.json`` holds ``{"layout": <n>, "state": "stable"}``. It is
  written, atomically, the first time an image that knows layout 1 finds none.
* Every process that serves or writes calls `require_layout` before it opens a
  database. It refuses -- loudly, serving nothing -- unless it knows the layout
  AND the state is ``stable``. A migration writes ``"state": "migrating"``
  durably before its first change, so a crash mid-run leaves a marker every
  image refuses.
* The caller also holds a SHARED lock on ``data_dir()/.layout.lock`` for its
  lifetime (Linux; ``flock``), so a migration, which takes it exclusively, can
  never run while anything reads. Host jobs (``deploy/backup.sh``) take the same
  lock through the bind mount.

``python -m tinyassets.storage_layout check [DATA_DIR]`` exits 0 when this code
may run on that data, 3 when it may not; ``deploy/deploy_fail_safe.sh`` uses the
marker the same way before it rolls back to an older image.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

#: The layout this code reads and writes. The cutover's image bumps it to 2.
LAYOUT = 1
#: Layouts this code understands. A newer one means "migrated past me".
KNOWN_LAYOUTS = frozenset({1})
STABLE = "stable"
MARKER = ".layout.json"
LOCK = ".layout.lock"

_held_locks: list[Any] = []


class LayoutRefused(RuntimeError):
    """This code must not run against this data."""


def marker_path(base: Path) -> Path:
    return Path(base) / MARKER


def read_marker(base: Path) -> dict[str, Any] | None:
    path = marker_path(base)
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    try:
        document = json.loads(raw)
    except ValueError as exc:
        raise LayoutRefused(f"{path} is not valid JSON ({exc}); nothing was opened") from None
    if not isinstance(document, dict):
        raise LayoutRefused(f"{path} is not a JSON object; nothing was opened")
    return document


def _write_atomically(path: Path, document: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(document, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    if hasattr(os, "O_DIRECTORY"):
        fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def check(base: Path) -> dict[str, Any]:
    """The marker if this code may run on ``base``, writing it when absent.

    Raises LayoutRefused otherwise. Never opens a database.
    """
    base = Path(base)
    document = read_marker(base)
    if document is None:
        base.mkdir(parents=True, exist_ok=True)
        document = {"layout": LAYOUT, "state": STABLE}
        _write_atomically(marker_path(base), document)
        return document
    layout, state = document.get("layout"), document.get("state")
    if state != STABLE:
        raise LayoutRefused(
            f"{marker_path(base)} says state={state!r}: a migration did not finish. "
            "Nothing was opened; restore the backup or finish the migration first."
        )
    if layout not in KNOWN_LAYOUTS:
        raise LayoutRefused(
            f"{marker_path(base)} says layout={layout!r}; this code understands "
            f"{sorted(KNOWN_LAYOUTS)}. Nothing was opened; run the image built for "
            "that layout."
        )
    return document


def _hold_shared_lock(base: Path) -> None:
    try:
        import fcntl
    except ImportError:  # Windows local installs: single process, no host jobs.
        return
    handle = open(Path(base) / LOCK, "a+")  # noqa: SIM115 - held for the process lifetime
    fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
    _held_locks.append(handle)


def require_layout(base: Path | None = None) -> dict[str, Any]:
    """Refuse to start unless this code understands the data; then hold the lock."""
    if base is None:
        from tinyassets.storage import data_dir

        base = data_dir()
    document = check(Path(base))
    _hold_shared_lock(Path(base))
    return document


def main(argv: list[str]) -> int:
    if not argv or argv[0] != "check":
        print("usage: python -m tinyassets.storage_layout check [DATA_DIR]", file=sys.stderr)
        return 2
    if len(argv) > 1:
        base = Path(argv[1])
    else:
        from tinyassets.storage import data_dir

        base = data_dir()
    try:
        document = check(base)
    except LayoutRefused as exc:
        print(f"layout refused: {exc}", file=sys.stderr)
        return 3
    print(json.dumps(document))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

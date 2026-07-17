"""Anti-rollback epoch mirror.

The vault's claims, tombstones, and ciphertext all share ONE SQLite recovery
domain, so restoring an OLDER snapshot silently rolls back consumed refresh
claims and deletion tombstones. Pure in-snapshot state cannot detect that.

The honest, standard guarantee (per the r9 review): a rollback FORCES
REAUTHORIZATION — NOT "the bytes are unrecoverable". We detect it with a
monotonic epoch that is bumped on every mutation and MIRRORED to a small file
kept OUTSIDE the restored snapshot. After a restore the DB epoch is behind the
mirror; any read/refresh then raises ``REAUTHORIZATION_REQUIRED`` (for rotating
one-use tokens the provider has already invalidated the restored token, so this
is exactly right).

The mirror only ever moves FORWARD (high-water), so a lost/behind mirror never
false-positives — only a mirror strictly AHEAD of the DB signals a rollback.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
from pathlib import Path


def mirror_filename(store_id: str) -> str:
    """Filename-safe per-store mirror name (store_id may contain ``:`` / ``/``)."""
    digest = hashlib.sha256(store_id.encode("utf-8")).hexdigest()[:32]
    return f"{digest}.epoch"


class EpochMirror:
    """High-water epoch stored in a file outside the DB snapshot."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def read(self) -> int:
        try:
            return int(self._path.read_text(encoding="utf-8").strip() or "0")
        except (OSError, ValueError):
            return 0  # missing/unreadable mirror is treated as 0 (never ahead)

    def advance(self, epoch: int) -> None:
        """Move the mirror forward to at least ``epoch`` (best-effort, atomic)."""
        if epoch <= self.read():
            return
        tmp = self._path.with_name(self._path.name + ".tmp")
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(str(int(epoch)), encoding="utf-8")
            os.replace(tmp, self._path)
        except OSError:
            with contextlib.suppress(OSError):
                os.remove(tmp)

    def is_rolled_back(self, db_epoch: int) -> bool:
        """True iff the DB epoch is BEHIND the mirror (a restore happened)."""
        return int(db_epoch) < self.read()

"""Every SQLite writer is fenced, infrastructure, or owed before the handover.

Change execution-owner-lease D3: a store left out of the inventory is a store a
stale owner can still write once a second owner process exists (slice C2).
"""

from __future__ import annotations

import re
from pathlib import Path

from tinyassets import owner_stores

_REPO = Path(__file__).resolve().parents[1]
_WRITE = re.compile(r"INSERT INTO|UPDATE [a-z_]+ SET|DELETE FROM")


def _writers() -> set[str]:
    found = set()
    for path in (_REPO / "tinyassets").rglob("*.py"):
        if _WRITE.search(path.read_text(encoding="utf-8", errors="replace")):
            found.add(path.relative_to(_REPO).as_posix())
    return found


def test_every_sqlite_writer_is_accounted_for():
    known = (set(owner_stores.FENCED) | owner_stores.INFRASTRUCTURE
             | owner_stores.FENCE_BEFORE_C2)
    unaccounted = sorted(_writers() - known)
    assert not unaccounted, (
        f"new SQLite writers {unaccounted}: fence them (FENCED) or list them in "
        "FENCE_BEFORE_C2 in tinyassets/owner_stores.py")


def test_the_inventory_names_no_ghosts():
    writers = _writers()
    listed = set(owner_stores.FENCED) | owner_stores.FENCE_BEFORE_C2
    assert listed <= writers, f"listed but not writers: {sorted(listed - writers)}"
    assert not set(owner_stores.FENCED) & owner_stores.FENCE_BEFORE_C2


def test_the_handover_cannot_ship_while_any_store_is_unfenced():
    if owner_stores.HANDOVER_ENABLED:
        assert not owner_stores.FENCE_BEFORE_C2, (
            "C2 enables a second owner process; every owner store must be fenced first")


def test_fenced_writers_actually_check_the_fence():
    for module in owner_stores.FENCED:
        source = (_REPO / module).read_text(encoding="utf-8")
        assert "check_fence(" in source, module

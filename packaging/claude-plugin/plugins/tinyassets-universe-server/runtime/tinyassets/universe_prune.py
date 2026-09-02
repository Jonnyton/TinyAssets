"""Cutting an unowned directory out of the data root.

Founder, 2026-09-02: *"leaving old folders is not a prune, a prune cuts bad
branches off. this made the branches unconnected but still sitting in the
tree."*

Every cleanup so far has been a one-off script that renamed a universe
directory aside — `_removed_universes_20260828`, `_removed_legacy_20260829`,
`_backup_subject_migration_...`. Those scripts are gone; the directories are
not. And because a universe was defined as "any directory under the data
root", each pile was itself served as a public universe, so the prune added
to the count it was reducing.

This module is the cut. It removes a directory that NOBODY OWNS, and it
re-reads ownership immediately before removing, inside the same call — never
off an inventory taken earlier. On 2026-08-26 a live user's bound universe was
archived off a stale listing; that is the failure this ordering exists to
prevent.

It reports before it removes, always. `plan()` is pure.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Platform infrastructure that shares the data root with universes. Not
#: universes, and not leftovers either: deleting them breaks a running daemon.
INFRASTRUCTURE_DIRS = frozenset({"lance", "output", "runs", "wiki"})

#: Files whose presence says a directory held real work. Reported, never
#: decisive: the founder decides, this only makes the decision informed.
_SIGNIFICANT = (
    "universe.json",
    "soul.json",
    "premise.md",
    "status.json",
    "activity.log",
    "checkpoints.db",
)


@dataclass(frozen=True)
class DirectoryReport:
    """What one directory under the data root is, before anything is removed."""

    name: str
    path: str
    owners: list[str]
    is_infrastructure: bool
    file_count: int
    byte_count: int
    notable_files: list[str] = field(default_factory=list)

    @property
    def removable(self) -> bool:
        """Unowned and not infrastructure. A directory with ANY owner is
        somebody's universe and is never removable by this path."""
        return not self.owners and not self.is_infrastructure

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "owners": list(self.owners),
            "is_infrastructure": self.is_infrastructure,
            "file_count": self.file_count,
            "byte_count": self.byte_count,
            "notable_files": list(self.notable_files),
            "removable": self.removable,
        }


def _measure(path: Path) -> tuple[int, int, list[str]]:
    """(file count, bytes, notable file names). Never raises: an unreadable
    entry is reported as zero rather than aborting the inventory."""
    files = 0
    total = 0
    notable: list[str] = []
    for child in path.rglob("*"):
        try:
            if not child.is_file():
                continue
            files += 1
            total += child.stat().st_size
            if child.name in _SIGNIFICANT and child.name not in notable:
                notable.append(child.name)
        except OSError:
            continue
    return files, total, sorted(notable)


def plan(base_path: str | Path) -> list[DirectoryReport]:
    """Every directory under the data root, with its owners. Pure: reads only.

    Read this before removing anything. `removable` says a directory has no
    owner, which is what makes it not a universe -- it does not say the
    directory is worthless, which is why the report carries its size and its
    notable files.
    """
    from tinyassets.daemon_server import universe_owners

    base = Path(base_path)
    if not base.is_dir():
        return []
    reports: list[DirectoryReport] = []
    for child in sorted(base.iterdir()):
        if not child.is_dir() or child.name.startswith("."):
            continue
        files, total, notable = _measure(child)
        reports.append(DirectoryReport(
            name=child.name,
            path=str(child),
            owners=universe_owners(base, universe_id=child.name),
            is_infrastructure=child.name in INFRASTRUCTURE_DIRS,
            file_count=files,
            byte_count=total,
            notable_files=notable,
        ))
    return reports


def prune(
    base_path: str | Path,
    *,
    names: list[str],
    apply: bool = False,
) -> dict[str, Any]:
    """Remove the named directories, if and only if nobody owns them.

    ``apply=False`` (the default) changes nothing and returns what it would do.

    The ownership query runs HERE, per directory, immediately before the
    removal -- not from a plan the caller passed in. A caller that read the
    inventory an hour ago, or on another machine, cannot make this delete a
    universe somebody has since claimed.
    """
    from tinyassets.daemon_server import universe_owners

    base = Path(base_path)
    removed: list[str] = []
    refused: list[dict[str, Any]] = []

    for name in names:
        target = base / name
        if name.startswith(".") or "/" in name or "\\" in name or name in ("", ".", ".."):
            refused.append({"name": name, "reason": "not a simple directory name"})
            continue
        if name in INFRASTRUCTURE_DIRS:
            refused.append({"name": name, "reason": "platform infrastructure"})
            continue
        if not target.is_dir():
            refused.append({"name": name, "reason": "not a directory under the data root"})
            continue
        try:
            if target.resolve().parent != base.resolve():
                refused.append({"name": name, "reason": "resolves outside the data root"})
                continue
        except OSError as exc:
            refused.append({"name": name, "reason": f"could not resolve: {exc}"})
            continue
        # THE CHECK, inside the destructive step.
        owners = universe_owners(base, universe_id=name)
        if owners:
            refused.append({
                "name": name,
                "reason": "owned",
                "owners": owners,
            })
            continue
        if not apply:
            removed.append(name)
            continue
        try:
            shutil.rmtree(target)
        except OSError as exc:
            refused.append({"name": name, "reason": f"removal failed: {exc}"})
            continue
        removed.append(name)

    return {
        "applied": bool(apply),
        "removed": removed,
        "refused": refused,
        "removed_count": len(removed),
        "refused_count": len(refused),
    }

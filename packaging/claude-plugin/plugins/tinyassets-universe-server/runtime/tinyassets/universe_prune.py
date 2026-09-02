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
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

#: Platform infrastructure that shares the data root with universes. Not
#: universes, and not leftovers either: deleting them breaks a running daemon.
#:
#: This is the ONE definition -- `tinyassets/reset.py` imports it rather than
#: keeping a second copy.
#:
#: It is a LABEL, not the safety property. Five of these were missing when the
#: list was the only thing standing between a prune and daemon memory
#: (`daemon_wikis`), retained user inputs (`cloud-automation-inputs`), the
#: brain's vector store (`lancedb`, which is not `lance`), the workspace pool
#: (`scratch`) and every founder's stored offers (`founder_offers`). A list
#: that has to be complete to be safe is not a safety mechanism, so what
#: actually protects them is `_universe_signal` below: a prune needs a positive
#: reason to believe a directory was a universe, and an operational store has
#: none.
INFRASTRUCTURE_DIRS = frozenset({
    "cloud-automation-inputs",
    # `deploy/compose.yml` sets TINYASSETS_REPO_ROOT=/data/community-pool. It is
    # named only through an environment variable, which is why reading the
    # Python source for `data_dir() / "..."` never found it -- so the drift test
    # reads the compose file too now (Codex code review round 2, P0).
    "community-pool",
    "daemon_wikis",
    "founder_offers",
    "lance",
    "lancedb",
    "output",
    "runs",
    "scratch",
    "wiki",
    "workspaces",
})

#: A file whose presence says "a universe lived here". Any one is enough.
_UNIVERSE_MARKERS = (
    "soul.md",
    "soul.json",
    "universe.json",
    "dispatcher.json",
    "premise.md",
    "status.json",
    ".tinyassets.db",
    "checkpoints.db",
)

#: What every past prune named the pile of UNIVERSES it moved aside instead
#: of deleting. `_backup` is deliberately NOT here: a migration backup is not a
#: universe, and `docs/host-actions.md` says of the seven existing ones "do not
#: delete -- they are migration backups". Treating the prefix as a universe
#: signal would have cut `_backup_subject_migration_20260829T055340Z` on a
#: blanket --apply (Codex code review round 2, P0).
_ARCHIVE_PREFIXES = ("_removed", "_legacy")


def _universe_signal(path: Path) -> str:
    """Why this directory is believed to have been a universe, or ``""``.

    The empty string is a REFUSAL to remove. A prune acts on former universes;
    a directory it cannot recognise is somebody else's, and the right response
    to "I do not know what this is" is to leave it alone and say so.
    """
    name = path.name
    for prefix in _ARCHIVE_PREFIXES:
        if name.startswith(prefix):
            return "an archive a past prune left behind"
    for marker in _UNIVERSE_MARKERS:
        try:
            if (path / marker).exists():
                return f"carries {marker}"
        except OSError:
            continue
    return ""

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
    universe_signal: str = ""

    @property
    def removable(self) -> bool:
        """Unowned, not infrastructure, AND recognisably a former universe.

        A directory with ANY owner is somebody's universe and is never
        removable by this path. A directory with no universe signal is not
        this tool's business at all -- that is what keeps an operational store
        nobody remembered to list out of the cut.
        """
        return (
            not self.owners
            and not self.is_infrastructure
            and bool(self.universe_signal)
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "owners": list(self.owners),
            "is_infrastructure": self.is_infrastructure,
            "file_count": self.file_count,
            "byte_count": self.byte_count,
            "notable_files": list(self.notable_files),
            "universe_signal": self.universe_signal,
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
            # Dotted names are never universes, which also covers the
            # `.pruning-*` staging names a removal moves a directory through.
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
            universe_signal=_universe_signal(child),
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
    from tinyassets.daemon_server import owned_universe_id, universe_owners

    base = Path(base_path)
    removed: list[str] = []
    refused: list[dict[str, Any]] = []

    for name in names:
        target = base / name
        if name.startswith(".") or "/" in name or "\\" in name or name in ("", ".", ".."):
            refused.append({"name": name, "reason": "not a simple directory name"})
            continue
        # THE NAME ON DISK IS THE NAME THAT DECIDES (Codex code review
        # 2026-09-02, P1). On Windows `WIKI`, `wiki.` and `wiki ` all open the
        # same directory, so a spelling the caller chose could walk straight
        # past both the infrastructure list and the ownership query. Only an
        # exact real child name is accepted.
        try:
            real_children = {p.name for p in base.iterdir() if p.is_dir()}
        except OSError as exc:
            refused.append({"name": name, "reason": f"could not read the data root: {exc}"})
            continue
        if name not in real_children:
            refused.append({
                "name": name,
                "reason": "no directory under the data root is spelled exactly that",
            })
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
        if not owners:
            # A directory restored as `U-Mine` is the same directory as the
            # ACL's `u-mine` on a case-insensitive filesystem. One definition
            # of that, shared with the listing and the resolvers.
            resolved = owned_universe_id(base, name)
            if resolved:
                owners = universe_owners(base, universe_id=resolved)
        if owners:
            refused.append({
                "name": name,
                "reason": "owned",
                "owners": owners,
            })
            continue
        # ...and a positive reason to believe this was ever a universe, read
        # from disk here rather than taken from a plan the caller passed in.
        signal = _universe_signal(target)
        if not signal:
            refused.append({
                "name": name,
                "reason": "not a universe directory",
            })
            continue
        if not apply:
            removed.append(name)
            continue
        # THE CLAIM CANNOT LAND BETWEEN THE CHECK AND THE DELETE.
        #
        # Reading owners and then calling rmtree leaves a window: a grant
        # written in between is lost with the directory (Codex code review
        # round 2, P0). So the id is FREED first -- the directory moves aside
        # under a name nothing can grant on -- and ownership is read again. A
        # claim that landed before the move is seen now and the directory goes
        # back. A claim that lands after it is a claim on an id with no
        # directory, and creation grants before it materializes, so the next
        # read of that id sees an owner and a fresh empty universe rather than
        # this one's contents.
        staged = base / f".pruning-{name}-{uuid.uuid4().hex[:12]}"
        try:
            target.rename(staged)
        except OSError as exc:
            refused.append({"name": name, "reason": f"could not stage: {exc}"})
            continue
        late_resolved = owned_universe_id(base, name) or name
        late_owners = universe_owners(base, universe_id=late_resolved)
        if late_owners:
            try:
                staged.rename(target)
            except OSError as exc:  # pragma: no cover - the restore must be loud
                refused.append({
                    "name": name,
                    "reason": (
                        f"claimed during removal and could NOT be put back "
                        f"({exc}); it is at {staged}"
                    ),
                    "owners": late_owners,
                })
                continue
            refused.append({
                "name": name,
                "reason": "owned",
                "owners": late_owners,
            })
            continue
        try:
            shutil.rmtree(staged)
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

"""Where a universe's platform state lives: one resolver, one registry.

Change ``universe-runtime-state`` (harness S3c). The universe agent gets its
whole root folder to write, the way a coding agent gets its project. That is
only safe if nothing the daemon TRUSTS is stored at that root: a consent
database, a credential vault or a run store the agent can plant is a forged
grant. So every platform-owned name of a universe lives under
``.runtime/state/`` and is reached through :func:`platform_path`, and nowhere
else.

:data:`PLATFORM_NAMES` is the only list of those names. Four consumers derive
from it and from nothing else, because a hand-assembled inventory of this set
missed a quarter of it the first time:

* the migration below, which moves exactly these names;
* the source gate (``tests/test_universe_platform_paths.py``), which refuses a
  registry name joined onto a path anywhere but here;
* storage accounting, which counts ``.runtime/state/`` like the root it came
  from, so moving a store never changes what its owner is charged;
* the operator reset, which classifies ``.runtime/state/`` by each name's
  ``reset`` disposition.

Migration is lazy, blocking and per universe. :func:`platform_path` calls
:func:`ensure_migrated`, which holds ``.runtime/state/.migrate.lock`` while it
renames every legacy entry still at the root, and only then writes the marker.
Every reader in every process waits on that lock until the marker exists, so no
store is ever opened half-moved, and a universe created or restored later
migrates on its first resolve. There is no fallback to the old location: a read
that falls back to the root once the new file is absent is exactly the hole
that lets an agent-planted root file be trusted.

Nothing is deleted, and nothing is guessed. A root entry whose destination
already exists, or that is a link, refuses the whole migration: nothing moves,
no marker is written, and every resolve of that universe fails loudly until an
operator decides. Each moved name leaves a tombstone, a read-only directory
at its old name, so a reader the conversion missed fails loudly
instead of creating and trusting a store at the root.

``workspaces/`` and ``.workspace-staging/`` are platform directories that stay
at the root (:data:`ROOT_PLATFORM_DIRS`): their lease rows hold absolute paths
that drive deletion. The jails mask them instead.
"""

from __future__ import annotations

import contextlib
import logging
import os
import stat
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "LAYOUT_FILENAME",
    "MARKER",
    "PLATFORM_NAMES",
    "ROOT_PLATFORM_DIRS",
    "STATE_DIR",
    "STATE_LAYOUT",
    "MigrationRefused",
    "MigrationStep",
    "PlatformName",
    "PlatformPathError",
    "ensure_migrated",
    "is_migrated",
    "is_tombstone",
    "migrated_platform_path",
    "migration_plan",
    "platform_name_for",
    "platform_path",
    "record_layout",
    "tombstones",
]

#: The platform's directory inside a universe, relative to the universe root.
STATE_DIR = Path(".runtime") / "state"
#: Written last, after every move is durable. Its presence is the only thing
#: that lets a reader through.
MARKER = ".migrated-v1"
_LOCK_NAME = ".migrate.lock"
#: The migration's own files inside the state directory. Never resettable,
#: never a platform store.
MIGRATION_FILES = frozenset({MARKER, _LOCK_NAME})
#: The data layout this code writes. A rollback must never start an image
#: whose layout is below the data's (``deploy/deploy_fail_safe.sh``).
STATE_LAYOUT = 2
#: At the data root: the layout the data has been migrated to.
LAYOUT_FILENAME = ".state-layout"
#: Platform directories that stay at the root, masked from every jail.
ROOT_PLATFORM_DIRS: tuple[str, ...] = ("workspaces", ".workspace-staging")
#: A tombstone is a read-only directory holding exactly this file.
TOMBSTONE_FILE = ".universe-runtime-state-tombstone"
_TOMBSTONE_MODE = 0o555
#: SQLite's sidecars. They move with their database and are never left behind.
_SQLITE_SIDECARS = ("-wal", "-shm", "-journal")

_FILE = "file"
_DIR = "dir"
_SQLITE = "sqlite"
_PREFIX = "prefix"

#: Reset dispositions, one for one with what ``scoped_reset`` decided for the
#: same name at the root: a credential or an audit store blocks a scoped reset,
#: an operational store has no reset adapter and blocks, and the rest go with
#: the home.
RESET_CREDENTIAL = "credential"
RESET_AUDIT = "audit"
RESET_OPERATIONAL = "operational"
RESET_RESETTABLE = "resettable"


@dataclass(frozen=True)
class PlatformName:
    """One platform-owned name in a universe.

    ``kind`` is ``file``, ``dir``, ``sqlite`` (the database plus its sidecars)
    or ``prefix`` (every root entry whose name starts with ``name``).
    ``reset`` is what a scoped operator reset does about it. ``legacy`` is
    where it lived before, relative to the universe root, when that was not
    the root itself.
    """

    name: str
    kind: str
    reset: str
    legacy: str | None = None

    @property
    def legacy_relpath(self) -> str:
        return self.legacy or self.name


def _entries(*names: PlatformName) -> dict[str, PlatformName]:
    return {entry.name: entry for entry in names}


#: THE registry of a universe's platform-owned names.
PLATFORM_NAMES: dict[str, PlatformName] = _entries(
    # Credentials: the vault, materialized provider homes, refresh locks.
    PlatformName(".credential-vault.json", _FILE, RESET_CREDENTIAL),
    PlatformName(".credentials", _DIR, RESET_CREDENTIAL),
    PlatformName(".oauth-refresh", _DIR, RESET_OPERATIONAL),
    # Conversations, asks, sign-ins, grants, usage.
    PlatformName(".conversation_memory.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName(".conversation_memory.db.bak-premigrate-", _PREFIX, RESET_OPERATIONAL),
    PlatformName(".pending_requests.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName(".subscription_state.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName(".effector_consents.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName(".usage_ledger.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName(".authoring.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName(
        ".wiki_write_back_destination_markers.db", _SQLITE, RESET_OPERATIONAL,
        legacy="wiki/.wiki_write_back_destination_markers.db",
    ),
    # Effects and runs.
    PlatformName(".external_write_receipts.db", _SQLITE, RESET_AUDIT),
    PlatformName(".idempotency.db", _SQLITE, RESET_AUDIT),
    PlatformName(".runs.db", _SQLITE, RESET_AUDIT),
    PlatformName(".langgraph_runs.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName("outbound.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName("auto_ship_attempts.jsonl", _FILE, RESET_AUDIT),
    PlatformName("auto_ship_attempts.jsonl.lock", _FILE, RESET_AUDIT),
    # Domain stores and indexes.
    PlatformName("story.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName("knowledge.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName("checkpoints.db", _SQLITE, RESET_OPERATIONAL),
    PlatformName("lancedb", _DIR, RESET_OPERATIONAL),
    # Platform json state.
    PlatformName("provider_definitions.json", _FILE, RESET_RESETTABLE),
    PlatformName("ledger.json", _FILE, RESET_RESETTABLE),
    PlatformName("status.json", _FILE, RESET_RESETTABLE),
    PlatformName(".runtime_status.json", _FILE, RESET_RESETTABLE),
    PlatformName(".engine_mcp_config.json", _FILE, RESET_RESETTABLE),
    PlatformName(".idle_cycle_stamp.json", _FILE, RESET_RESETTABLE),
    PlatformName("branch_tasks.json", _FILE, RESET_RESETTABLE),
    PlatformName("branch_tasks_archive.json", _FILE, RESET_RESETTABLE),
    PlatformName(".pause", _FILE, RESET_OPERATIONAL),
    # Locks.
    PlatformName(".idle_cycle.lock", _FILE, RESET_OPERATIONAL),
    PlatformName(".provider-assignment-admission.lock", _FILE, RESET_OPERATIONAL),
    PlatformName(".soul.lock", _FILE, RESET_OPERATIONAL),
    PlatformName("branch_tasks.json.lock", _FILE, RESET_OPERATIONAL),
    # Supervisor heartbeats: one file per worker. No tombstones (unbounded).
    PlatformName(".worker_supervisor.", _PREFIX, RESET_RESETTABLE),
)


class PlatformPathError(OSError):
    """A platform path was refused: an unknown name, a link where the state
    directory should be, or a migration that could not finish. An ``OSError``
    so callers that already treat filesystem failure as failure stay closed."""


class MigrationRefused(PlatformPathError):
    """The migration found something it must not decide alone: a root entry
    whose destination already exists, or a root entry that is a link. Nothing
    was moved; an operator chooses which copy is authoritative."""


def platform_name_for(entry_name: str) -> PlatformName | None:
    """The registry entry an on-disk name inside ``.runtime/state/`` belongs
    to, sidecars and prefixes included, or ``None``."""
    base = entry_name
    for suffix in _SQLITE_SIDECARS:
        if base.endswith(suffix):
            base = base.removesuffix(suffix)
            break
    found = PLATFORM_NAMES.get(base) or PLATFORM_NAMES.get(entry_name)
    if found is not None:
        return found
    for entry in PLATFORM_NAMES.values():
        if entry.kind == _PREFIX and entry_name.startswith(entry.name):
            return entry
    return None


# --------------------------------------------------------------------------- #
# The state directory
# --------------------------------------------------------------------------- #


def _refuse_link(path: Path) -> None:
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or _is_junction(path):
        raise PlatformPathError(f"refusing a link where platform state lives: {path}")
    if not stat.S_ISDIR(info.st_mode):
        raise PlatformPathError(f"platform state path is not a directory: {path}")


def _is_junction(path: Path) -> bool:
    isjunction = getattr(os.path, "isjunction", None)
    if isjunction is None:
        return False
    try:
        return bool(isjunction(path))
    except OSError:
        return False


def _state_dir(universe_dir: Path, *, create: bool) -> Path:
    """``<universe>/.runtime/state``, each level made without following a
    link and refused if it is one."""
    current = universe_dir
    _refuse_link(current)
    for part in STATE_DIR.parts:
        current = current / part
        _refuse_link(current)
        if create:
            with contextlib.suppress(FileExistsError):
                os.mkdir(current, 0o700)
            _refuse_link(current)
    return current


def _universe_root(universe_dir: str | Path) -> Path:
    root = Path(universe_dir)
    if not root.is_absolute():
        root = root.absolute()
    return root


#: Directories under the data root that are never universes. Migrating one
#: would move a backup's databases or a lease's files into a state directory.
_NOT_UNIVERSES = frozenset({
    "wiki", "scratch", "daemon_wikis", "cloud-automation-inputs",
    "lance", "output", "runs",
})
#: Files only the DATA ROOT has. Their presence means "this is not a universe":
#: a data root holds its own ``.runs.db``, ``outbound.db`` and ``ledger.json``,
#: and migrating it would move the whole platform's stores.
_DATA_ROOT_MARKERS = (".tinyassets.db", ".auth.db", ".storage_accounting.db")


def _refuse_non_universe(root: Path) -> None:
    name = root.name
    if not name or name.startswith((".", "_")) or name in _NOT_UNIVERSES:
        raise PlatformPathError(f"not a universe directory: {root}")
    for marker in _DATA_ROOT_MARKERS:
        if os.path.lexists(root / marker):
            raise PlatformPathError(f"refusing to treat the data root as a universe: {root}")


# --------------------------------------------------------------------------- #
# The lock
# --------------------------------------------------------------------------- #


@contextlib.contextmanager
def _exclusive(lock_path: Path) -> Iterator[None]:
    """A held file lock. A migrator that dies releases it with its process."""
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(lock_path, flags, 0o600)
    try:
        if os.name == "nt":
            import msvcrt

            if os.fstat(fd).st_size == 0:
                os.write(fd, b"\0")
            os.lseek(fd, 0, os.SEEK_SET)
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
                    break
                except OSError:
                    time.sleep(0.05)
            try:
                yield
            finally:
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _fsync_dir(path: Path) -> None:
    if os.name == "nt":
        return  # no directory handles to sync; NTFS journals the rename
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


# --------------------------------------------------------------------------- #
# Migration
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MigrationStep:
    """One rename the migration will make.

    ``action`` is ``move`` (to its registry location), or one of the two
    refusals: ``conflict`` (the destination already exists) and ``link`` (the
    root entry is a link). A plan holding any refusal moves nothing."""

    source: Path
    destination: Path
    action: str
    tombstone: bool


def is_tombstone(path: str | Path) -> bool:
    """What the migration leaves at a name it moved: a read-only directory
    holding only :data:`TOMBSTONE_FILE`. Never followed, never a store."""
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return False
    if not stat.S_ISDIR(info.st_mode):
        return False
    try:
        return os.listdir(path) == [TOMBSTONE_FILE]
    except OSError:
        return False


def _make_tombstone(path: Path) -> None:
    os.mkdir(path, 0o700)
    fd = os.open(path / TOMBSTONE_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o444)
    os.close(fd)
    os.chmod(path, _TOMBSTONE_MODE)


def _legacy_candidates(root: Path) -> Iterator[tuple[Path, str, bool]]:
    """Every legacy platform entry still outside ``.runtime/state``, as
    ``(path, name inside the state dir, leaves a tombstone)``. Sidecars of a
    SQLite database are found on their own, so a run that died after moving
    the database still moves the ``-wal`` it left behind."""
    try:
        listing = sorted(os.listdir(root))
    except FileNotFoundError:
        return
    for entry in PLATFORM_NAMES.values():
        if entry.kind == _PREFIX:
            for name in listing:
                if name.startswith(entry.name):
                    yield root / name, name, False
            continue
        legacy_parent = (root / entry.legacy_relpath).parent
        names = [entry.name]
        if entry.kind == _SQLITE:
            names += [entry.name + suffix for suffix in _SQLITE_SIDECARS]
        for name in names:
            source = legacy_parent / name
            if os.path.lexists(source) and not is_tombstone(source):
                yield source, name, name == entry.name


def migration_plan(universe_dir: str | Path) -> list[MigrationStep]:
    """What :func:`ensure_migrated` would do, without touching anything.

    The dry-run inventory: run it against production before the build
    deploys (it must hold no refusal), and again after (it must be empty)."""
    root = _universe_root(universe_dir)
    state = root / STATE_DIR
    steps: list[MigrationStep] = []
    for source, name, tombstone in _legacy_candidates(root):
        destination = state / name
        if os.path.islink(source) or _is_junction(source):
            action = "link"
        elif os.path.lexists(destination):
            action = "conflict"
        else:
            action = "move"
        steps.append(MigrationStep(source, destination, action, tombstone))
    return steps


def tombstones(universe_dir: str | Path) -> list[Path]:
    """Every tombstone in the universe: the paths the jails must mask."""
    root = _universe_root(universe_dir)
    found: list[Path] = []
    for entry in PLATFORM_NAMES.values():
        if entry.kind == _PREFIX:
            continue
        path = root / entry.legacy_relpath
        if is_tombstone(path):
            found.append(path)
    return found


def is_migrated(universe_dir: str | Path) -> bool:
    """Whether the universe's marker exists. The tool jail binds the root
    read-write only when it does."""
    root = _universe_root(universe_dir)
    marker = root / STATE_DIR / MARKER
    try:
        return stat.S_ISREG(os.lstat(marker).st_mode)
    except FileNotFoundError:
        return False


_confirmed: set[str] = set()
_confirmed_lock = threading.Lock()


def ensure_migrated(universe_dir: str | Path) -> Path:
    """Migrate ``universe_dir`` if it has not been, and return its state dir.

    Blocks while another process migrates the same universe. Safe to call on
    every resolve: once confirmed, a universe is remembered for the life of
    the process, because migration is one-way.
    """
    root = _universe_root(universe_dir)
    key = os.path.normcase(str(root))
    if key in _confirmed:
        return root / STATE_DIR
    if not os.path.lexists(root):
        # No universe yet: nothing to migrate and nothing to read. A caller
        # that goes on to create the store makes the directories itself, and
        # the first resolve after that writes the marker.
        return root / STATE_DIR
    _refuse_non_universe(root)
    state = _state_dir(root, create=True)
    with _exclusive(state / _LOCK_NAME):
        if not is_migrated(root):
            _migrate(root, state)
    with _confirmed_lock:
        _confirmed.add(key)
    return state


def _migrate(root: Path, state: Path) -> None:
    steps = migration_plan(root)
    refused = [step for step in steps if step.action != "move"]
    if refused:
        detail = "; ".join(f"{step.action}: {step.source}" for step in refused)
        logger.error("universe-runtime-state: refusing to migrate %s: %s", root, detail)
        raise MigrationRefused(
            f"the universe at {root} cannot migrate until an operator resolves: {detail}"
        )
    for step in steps:
        os.rename(step.source, step.destination)
        if step.tombstone:
            _make_tombstone(step.source)
    _fsync_dir(state)
    for parent in sorted({step.source.parent for step in steps}):
        _fsync_dir(parent)
    _fsync_dir(root)
    marker = state / MARKER
    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        os.write(fd, f"{len(steps)} entries moved\n".encode())
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_dir(state)
    if steps:
        logger.info("universe-runtime-state: migrated %s (%d entries)", root, len(steps))


def record_layout(data_root: str | Path) -> None:
    """Raise the data root's layout to :data:`STATE_LAYOUT`. Never lowers it.

    Called by daemon start after it migrates every universe; the rollback
    paths read it to refuse an image older than the data."""
    data_root = Path(data_root)
    path = data_root / LAYOUT_FILENAME
    try:
        current = int(path.read_text(encoding="ascii").strip() or 0)
    except (FileNotFoundError, ValueError):
        current = 0
    if current >= STATE_LAYOUT:
        return
    tmp = path.with_name(f"{LAYOUT_FILENAME}.{os.getpid()}.tmp")
    tmp.write_text(f"{STATE_LAYOUT}\n", encoding="ascii")
    os.replace(tmp, path)
    _fsync_dir(data_root)


# --------------------------------------------------------------------------- #
# The resolver
# --------------------------------------------------------------------------- #


def platform_path(universe_dir: str | Path, name: str) -> Path:
    """Where the platform-owned ``name`` of ``universe_dir`` lives.

    ``name`` must be in :data:`PLATFORM_NAMES` (for a prefix entry, any name
    starting with it). The universe is migrated first if it has not been, and
    the state directory is refused if it is a link. The returned path is under
    ``<universe>/.runtime/state/``; the old root location is never returned.
    """
    if platform_name_for(name) is None or "/" in name or "\\" in name or name in (".", ".."):
        raise PlatformPathError(f"not a platform name of a universe: {name!r}")
    state = ensure_migrated(universe_dir)
    if os.path.lexists(state.parent.parent):
        _state_dir(state.parent.parent, create=False)
    return state / name


def migrated_platform_path(universe_dir: str | Path, name: str) -> Path | None:
    """``name``'s location in an ALREADY-migrated universe, or ``None``.

    For readers that enumerate directories under the data root: they must
    never migrate (or create ``.runtime/state`` in) a directory just because
    it sits there -- a backup, the wiki or the scratch pool would have its
    contents moved. Daemon start migrates every registered universe first.
    """
    if platform_name_for(name) is None or "/" in name or "\\" in name:
        raise PlatformPathError(f"not a platform name of a universe: {name!r}")
    root = _universe_root(universe_dir)
    if not is_migrated(root):
        return None
    _state_dir(root, create=False)
    return root / STATE_DIR / name

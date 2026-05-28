"""Bounded-context storage layers for the multiplayer engine.

Second canonical Module Layout subpackage (after ``workflow/bid/``) per
PLAN.md §Module Layout. Replaces the 3,575-LOC ``workflow/daemon_server.py``
god-module with per-context submodules:

- ``accounts`` — user accounts + auth + sessions + capabilities
- ``universes_branches`` — universes + branches + snapshots + ACLs
- ``daemons`` — daemon (author) definitions + forks + runtime instances
- ``requests_votes`` — user requests + vote windows + ballots + action records
- ``notes_work_targets`` — universe notes + work-targets + hard priorities
- ``goals_gates`` — goals + gate-claims + leaderboard reads

This ``__init__.py`` hosts the shared primitives every context module
needs: path helpers, the ``_connect()`` factory, and the constants +
JSON + slug utilities that were previously at the top of
``daemon_server.py``.

R7 ship sequence (see
``docs/exec-plans/active/2026-04-19-storage-package-split.md``):

- Commit 1 (this commit): shared helpers + constants. ``daemon_server.py``
  imports the helpers back from here rather than duplicating them.
- Commits 2-6: per-bounded-context split.

Per the foundation-end-state rule (``CLAUDE_LEAD_OPS.md
§Foundation End-State``): each commit is itself end-state-shaped —
the helpers move to their final path in commit 1, not to a temporary
intermediate file.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------

DB_FILENAME = ".workflow.db"
_LEGACY_DB_FILENAME = ".author_server.db"
_SQLITE_SIBLING_SUFFIXES = ("-wal", "-shm")
DEFAULT_BRANCH_MODE = "no_fixed_mainline"
DEFAULT_QUICK_VOTE_SECONDS = 300
SESSION_PREFIX = "fa_session_"

CAP_READ_PUBLIC_UNIVERSE = "read_public_universe"
CAP_SUBMIT_REQUEST = "submit_request"
CAP_FORK_BRANCH = "fork_branch"
CAP_PROPOSE_AUTHOR_FORK = "propose_author_fork"
CAP_SPAWN_RUNTIME_CAPACITY = "spawn_runtime_capacity"
CAP_ASSIGN_RUNTIME_PROVIDER = "assign_runtime_provider"
CAP_PAUSE_RESUME_SERVER = "pause_resume_server"
CAP_ROLLBACK_BRANCH = "rollback_branch"
CAP_PROMOTE_BRANCH = "promote_branch"
CAP_SUPERSEDE_BRANCH = "supersede_branch"
CAP_EDIT_UNIVERSE_RULES = "edit_universe_rules"
CAP_GRANT_CAPABILITIES = "grant_capabilities"
CAP_RESOLVE_VOTE = "resolve_vote"
CAP_SET_GOAL_SELECTOR = "set_goal_selector"
CAP_SET_CANONICAL_BRANCH = "set_canonical_branch"
CAP_DEFINE_GATE_LADDER = "define_gate_ladder"
CAP_RETRACT_GATE_CLAIM = "retract_gate_claim"

ALL_CAPABILITIES: tuple[str, ...] = (
    CAP_READ_PUBLIC_UNIVERSE,
    CAP_SUBMIT_REQUEST,
    CAP_FORK_BRANCH,
    CAP_PROPOSE_AUTHOR_FORK,
    CAP_SPAWN_RUNTIME_CAPACITY,
    CAP_ASSIGN_RUNTIME_PROVIDER,
    CAP_PAUSE_RESUME_SERVER,
    CAP_ROLLBACK_BRANCH,
    CAP_PROMOTE_BRANCH,
    CAP_SUPERSEDE_BRANCH,
    CAP_EDIT_UNIVERSE_RULES,
    CAP_GRANT_CAPABILITIES,
    CAP_RESOLVE_VOTE,
    CAP_SET_GOAL_SELECTOR,
    CAP_SET_CANONICAL_BRANCH,
    CAP_DEFINE_GATE_LADDER,
    CAP_RETRACT_GATE_CLAIM,
)

DEFAULT_USER_CAPABILITIES: tuple[str, ...] = (
    CAP_READ_PUBLIC_UNIVERSE,
    CAP_SUBMIT_REQUEST,
    CAP_FORK_BRANCH,
    CAP_PROPOSE_AUTHOR_FORK,
)


# -------------------------------------------------------------------
# JSON + slug helpers
# -------------------------------------------------------------------


def _now() -> float:
    return time.time()


def _json_dumps(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _json_loads(payload: str | None, default: Any) -> Any:
    if not payload:
        return default
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return default


def _slugify(text: str, fallback: str = "item") -> str:
    cleaned = [
        ch.lower() if ch.isalnum() else "-"
        for ch in text.strip()
    ]
    slug = "".join(cleaned).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug or fallback


# -------------------------------------------------------------------
# Path resolution
# -------------------------------------------------------------------


def _looks_like_windows_path(raw: str) -> bool:
    """Return True if ``raw`` looks like a Windows drive-letter path.

    Matches ``C:\\...``, ``c:/...``, ``D:\\...`` etc. Used to detect
    cross-OS env-var leakage: a host machine setting
    ``WORKFLOW_WIKI_PATH=C:\\Users\\Jonathan\\...`` that then reaches a
    Linux container joins against CWD on POSIX (``Path("C:\\Users\\...")``
    is NOT absolute on POSIX) and yields nonsense like
    ``/app/C:\\Users\\Jonathan\\Projects\\Wiki``.
    """
    if len(raw) < 3:
        return False
    if not raw[0].isalpha() or raw[1] != ":":
        return False
    return raw[2] in ("\\", "/")


def _reject_windows_path_on_posix(raw: str, var_name: str) -> None:
    """Raise with a specific error if ``raw`` is a Windows path on POSIX.

    Per AGENTS.md hard rule #8 (fail loudly, never silently): a silent
    fallback would hide the deploy misconfig that originally leaked a
    Windows path into the container. The error names the env var and
    the current runtime so the fix is obvious from the traceback.
    """
    import os
    if os.name == "nt":
        return
    if _looks_like_windows_path(raw):
        raise ValueError(
            f"{var_name}={raw!r} looks like a Windows drive-letter path "
            f"but the runtime is POSIX ({os.name!r}). Refusing: joining "
            f"this against the current working directory would produce "
            f"nonsense like '/app/{raw}'. Unset the variable to use the "
            f"platform default, or set it to a POSIX absolute path "
            f"(e.g. '/data/wiki')."
        )


def data_dir() -> Path:
    """Return the on-disk root for all Workflow daemon state.

    Canonical env var: ``WORKFLOW_DATA_DIR``.

    Resolution order (first match wins):
      1. ``$WORKFLOW_DATA_DIR`` if set and non-empty.
      2. Platform default:
         - Windows: ``%APPDATA%\\Workflow`` if ``APPDATA`` is set, else
           ``Path.home() / 'AppData' / 'Roaming' / 'Workflow'``.
         - macOS / Linux / container: ``~/.workflow``.

    Always returns an absolute, resolved Path. Callers should NOT re-resolve
    or re-expand; this function is the single source of truth for the
    daemon's on-disk root so that a containerized deploy setting
    ``WORKFLOW_DATA_DIR=/data`` gets all writes inside the bind-mount.

    The previous shape defaulted to CWD-relative ``"output"`` and produced
    the 2026-04-19 container CWD-drift bug: running the daemon from ``/app``
    wrote to ``/app/output`` instead of ``/data``. This function eliminates
    that class by refusing to return CWD-relative paths.

    Notes
    -----
    - This is the *root* for all on-disk state, not the universe dir.
      Per-universe directories sit under this root. The previous
      root setting conflated the two; the contract is that
      ``WORKFLOW_DATA_DIR`` is the root (e.g., ``/data``) and universes are
      subdirectories (e.g., ``/data/my-universe``).
    - The directory is not created here. Callers that write into it
      are responsible for ``mkdir(parents=True, exist_ok=True)``.
    """
    import os
    explicit = os.environ.get("WORKFLOW_DATA_DIR", "").strip()
    if explicit:
        _reject_windows_path_on_posix(explicit, "WORKFLOW_DATA_DIR")
        return Path(explicit).expanduser().resolve()

    # Platform default.
    appdata = os.environ.get("APPDATA", "").strip()
    if appdata and os.name == "nt":
        return (Path(appdata) / "Workflow").resolve()
    if os.name == "nt":
        # Windows without APPDATA (unusual) — fall back to the standard
        # user path rather than ~/.workflow.
        return (Path.home() / "AppData" / "Roaming" / "Workflow").resolve()
    return (Path.home() / ".workflow").resolve()


def active_universe_id(base: Path | None = None) -> str:
    """Return the dynamic active universe marker when it points at a real universe.

    ``UNIVERSE_SERVER_DEFAULT_UNIVERSE`` is a boot/default setting. The
    runtime ``switch_universe`` MCP action writes ``.active_universe`` under
    the data root, so read that marker before falling back to static defaults.
    Invalid marker contents are ignored instead of becoming path traversal.
    """
    root = base or data_dir()
    marker = root / ".active_universe"
    try:
        uid = marker.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    if not uid or "/" in uid or "\\" in uid or uid.startswith("."):
        return ""
    if not (root / uid).is_dir():
        return ""
    return uid


def wiki_path() -> Path:
    """Return the on-disk root for the knowledge wiki.

    Canonical env var: ``WORKFLOW_WIKI_PATH``.

    Resolution order (first match wins):
      1. ``$WORKFLOW_WIKI_PATH`` if set and non-empty.
      2. Platform default: ``data_dir() / "wiki"`` — inherits the
         canonical data root's platform handling (Windows
         ``%APPDATA%\\Workflow\\wiki``; Linux/macOS ``~/.workflow/wiki``).

    Pre-2026-04-20 the wiki fallback was hardcoded
    ``r"C:\\Users\\Jonathan\\Projects\\Wiki"`` in
    ``workflow/universe_server.py`` — broke every non-host deploy +
    leaked the developer's username into docs. Using this resolver
    closes that class the same way ``data_dir`` did for universe state.

    If a Windows-style path leaks into a POSIX runtime, this resolver raises
    ``ValueError`` rather than silently returning a nonsense path.

    Returns an absolute, resolved Path. Does not create the directory;
    callers mkdir on first write.
    """
    import os
    explicit = os.environ.get("WORKFLOW_WIKI_PATH", "").strip()
    if explicit:
        _reject_windows_path_on_posix(explicit, "WORKFLOW_WIKI_PATH")
        return Path(explicit).expanduser().resolve()

    # Platform default — inherit data_dir's platform handling.
    return (data_dir() / "wiki").resolve()


def _sqlite_db_siblings(db_file: Path) -> tuple[Path, ...]:
    return tuple(
        db_file.with_name(f"{db_file.name}{suffix}")
        for suffix in _SQLITE_SIBLING_SUFFIXES
    )


def _replace_if_exists(source: Path, target: Path) -> bool:
    if not source.exists():
        return False
    os.replace(source, target)
    return True


def _legacy_backup_path(legacy_db_path: Path) -> Path:
    timestamp = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    base = legacy_db_path.with_name(f"{legacy_db_path.name}.legacy-{timestamp}")
    candidate = base
    counter = 1
    while candidate.exists() or any(
        sibling.exists() for sibling in _sqlite_db_siblings(candidate)
    ):
        candidate = legacy_db_path.with_name(
            f"{base.name}-{counter}"
        )
        counter += 1
    return candidate


def _move_db_with_sqlite_siblings(source: Path, target: Path) -> list[str]:
    moved = []
    if _replace_if_exists(source, target):
        moved.append(source.name)
    for source_sibling, target_sibling in zip(
        _sqlite_db_siblings(source), _sqlite_db_siblings(target),
        strict=True,
    ):
        if _replace_if_exists(source_sibling, target_sibling):
            moved.append(source_sibling.name)
    return moved


def _migrate_legacy_db_filename(base_path: str | Path) -> None:
    base = Path(base_path)
    legacy_db = base / _LEGACY_DB_FILENAME
    canonical_db = base / DB_FILENAME

    if not legacy_db.exists():
        return

    if canonical_db.exists():
        backup = _legacy_backup_path(legacy_db)
        moved = _move_db_with_sqlite_siblings(legacy_db, backup)
        _logger.warning(
            "Both %s and %s existed in %s; using %s and backed up legacy "
            "SQLite files to %s (%s)",
            canonical_db.name,
            legacy_db.name,
            base,
            canonical_db.name,
            backup.name,
            ", ".join(moved) if moved else "no files moved",
        )
        return

    moved = _move_db_with_sqlite_siblings(legacy_db, canonical_db)
    if moved:
        _logger.info(
            "Migrated legacy SQLite filename in %s from %s to %s (%s)",
            base,
            legacy_db.name,
            canonical_db.name,
            ", ".join(moved),
        )


def db_path(base_path: str | Path) -> Path:
    _migrate_legacy_db_filename(base_path)
    return Path(base_path) / DB_FILENAME


# -------------------------------------------------------------------
# Bootstrap env-readability probe (closes 2026-04-22 Concern)
# -------------------------------------------------------------------

_WORKFLOW_ENV_PATH = Path("/etc/workflow/env")

_logger = __import__("logging").getLogger(__name__)


def probe_env_readability(
    env_path: Path = _WORKFLOW_ENV_PATH,
) -> bool:
    """Check that the operator env file is readable by the current process.

    Returns True when the file is readable (or absent — absent is fine,
    the env file is only provisioned in cloud/container deploys). Returns
    False when the file exists but cannot be read, and emits a WARNING
    log with the observed mode bits and the fix command so the operator
    can recover without hunting through docs.

    This is a non-crashing probe — degraded operation with a visible
    warning is preferable to a dead daemon. Callers should invoke this
    once at startup so the warning appears in the initial log burst where
    operators are most likely to see it.
    """
    if not env_path.exists():
        return True

    try:
        env_path.open("r").close()
        return True
    except PermissionError:
        try:
            import stat as _stat
            mode = env_path.stat().st_mode
            mode_str = _stat.filemode(mode)
        except OSError:
            mode_str = "(unknown)"
        _logger.warning(
            "Bootstrap env file %s exists but is NOT readable by the current "
            "process (mode=%s). Daemon will start in degraded mode — secrets "
            "from env file are unavailable. Fix: chmod 644 %s",
            env_path,
            mode_str,
            env_path,
        )
        return False
    except OSError as exc:
        _logger.warning(
            "Bootstrap env file %s could not be opened: %s. "
            "Daemon will start in degraded mode.",
            env_path,
            exc,
        )
        return False


# -------------------------------------------------------------------
# Storage utilization observability (BUG-023 Phase 1)
# -------------------------------------------------------------------


# Per-subsystem paths, relative to data_dir(). Each path may be either
# a file (size from stat) or a directory (recursive walk). Missing paths
# resolve to 0 bytes rather than error — observability must never break
# the probe surface it rides on.
_SUBSYSTEM_PATHS: tuple[tuple[str, str, bool], ...] = (
    # (name, relative path, is_directory)
    ("run_transcripts", "runs", True),
    ("knowledge_db",   "knowledge.db", False),
    ("story_db",       "story.db", False),
    ("lance_indexes",  "lance", True),
    ("checkpoint_db",  "checkpoints.db", False),
    ("wiki",           "wiki", True),
    ("activity_log",   "activity.log", False),
    ("universe_outputs", "output", True),
)

_PRESSURE_WARN_THRESHOLD = 0.80
_PRESSURE_CRITICAL_THRESHOLD = 0.95


def path_size_bytes(path: Path) -> int:
    """Return the on-disk size of ``path`` in bytes.

    - Missing paths → 0 (not an error; a subsystem may be uninitialized).
    - Files → ``stat().st_size``.
    - Directories → recursive sum of regular-file sizes; OSError on a
      single child does not abort the walk.
    """
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    if not path.is_dir():
        return 0
    total = 0
    for child in path.rglob("*"):
        try:
            if child.is_file():
                total += child.stat().st_size
        except OSError:
            continue
    return total


def _pressure_level_from_percent(percent: float) -> str:
    """Classify ``percent`` (0.0-1.0) into an alert tier."""
    if percent >= _PRESSURE_CRITICAL_THRESHOLD:
        return "critical"
    if percent >= _PRESSURE_WARN_THRESHOLD:
        return "warn"
    return "ok"


def inspect_storage_utilization() -> dict[str, Any]:
    """Return a snapshot of daemon storage state.

    Phase-1 surface for BUG-023: gives an MCP-reachable operator a way
    to see per-subsystem byte counts + root-volume pressure before the
    wall is hit. Pairs with ``get_status.storage_utilization`` so the
    uptime canary can page on ``pressure_level`` in {warn, critical}.

    Shape (stable contract — consumed by get_status + tests):
        {
          volume_percent: float,  # 0.0-1.0, root volume usage
          volume_bytes_total: int,
          volume_bytes_free: int,
          per_subsystem: {
            <name>: {bytes: int, path: str},
            ...
          },
          growth_estimate: {
            bytes_per_day_recent: int,
            days_until_full_at_recent_rate: float | null
          } | null,
          pressure_level: 'ok' | 'warn' | 'critical'
        }

    Invariants:
      - Read-only; no writes.
      - Missing subsystem paths yield ``bytes=0``, never raise.
      - Windows-path-on-POSIX guard inherited from ``data_dir()``.
    """
    import shutil as _shutil

    root = data_dir()

    try:
        usage = _shutil.disk_usage(str(root if root.exists() else root.parent))
        volume_bytes_total = int(usage.total)
        volume_bytes_free = int(usage.free)
        volume_percent = (
            0.0 if volume_bytes_total == 0
            else 1.0 - (volume_bytes_free / volume_bytes_total)
        )
    except OSError:
        volume_bytes_total = 0
        volume_bytes_free = 0
        volume_percent = 0.0

    per_subsystem: dict[str, dict[str, Any]] = {}
    for name, rel_path, _is_dir in _SUBSYSTEM_PATHS:
        abs_path = root / rel_path
        per_subsystem[name] = {
            "bytes": path_size_bytes(abs_path),
            "path": str(abs_path),
        }

    # Phase-3 subsystem cap snapshot — consumers (uptime canary, alert
    # rules) can see which caps are configured + where each subsystem
    # sits relative to its soft/hard thresholds. Inspect-level subsystem
    # names map to cap-level ones (caps owns its own vocabulary:
    # checkpoints / logs / run_artifacts; inspect uses file-path names).
    try:
        from workflow.storage.caps import subsystem_cap_snapshot
        cap_input = {
            "checkpoints": per_subsystem.get("checkpoint_db", {}).get("bytes", 0),
            "logs": per_subsystem.get("activity_log", {}).get("bytes", 0),
            "run_artifacts": per_subsystem.get("run_transcripts", {}).get("bytes", 0),
        }
        subsystem_caps = subsystem_cap_snapshot(cap_input)
    except Exception:  # noqa: BLE001 — observability must not break probe
        subsystem_caps = {}

    return {
        "volume_percent": round(volume_percent, 4),
        "volume_bytes_total": volume_bytes_total,
        "volume_bytes_free": volume_bytes_free,
        "per_subsystem": per_subsystem,
        "subsystem_caps": subsystem_caps,
        # No historical timeseries store yet — growth_estimate lands in a
        # later phase when run-transcript rotation emits size-at-time
        # samples. Null is the spec-mandated shape for the no-data case.
        "growth_estimate": None,
        "pressure_level": _pressure_level_from_percent(volume_percent),
    }


def base_path_from_universe(universe_path: str | Path) -> Path:
    return Path(universe_path).resolve().parent


def universe_id_from_path(universe_path: str | Path) -> str:
    return Path(universe_path).resolve().name


# -------------------------------------------------------------------
# SQLite connection factory
# -------------------------------------------------------------------


def _connect(base_path: str | Path) -> sqlite3.Connection:
    path = db_path(base_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


__all__ = [
    # Constants
    "DB_FILENAME",
    "DEFAULT_BRANCH_MODE",
    "DEFAULT_QUICK_VOTE_SECONDS",
    "SESSION_PREFIX",
    "CAP_READ_PUBLIC_UNIVERSE",
    "CAP_SUBMIT_REQUEST",
    "CAP_FORK_BRANCH",
    "CAP_PROPOSE_AUTHOR_FORK",
    "CAP_SPAWN_RUNTIME_CAPACITY",
    "CAP_ASSIGN_RUNTIME_PROVIDER",
    "CAP_PAUSE_RESUME_SERVER",
    "CAP_ROLLBACK_BRANCH",
    "CAP_PROMOTE_BRANCH",
    "CAP_SUPERSEDE_BRANCH",
    "CAP_EDIT_UNIVERSE_RULES",
    "CAP_GRANT_CAPABILITIES",
    "CAP_RESOLVE_VOTE",
    "CAP_SET_GOAL_SELECTOR",
    "CAP_SET_CANONICAL_BRANCH",
    "CAP_DEFINE_GATE_LADDER",
    "CAP_RETRACT_GATE_CLAIM",
    "ALL_CAPABILITIES",
    "DEFAULT_USER_CAPABILITIES",
    # Helpers
    "_now",
    "_json_dumps",
    "_json_loads",
    "_slugify",
    "base_path_from_universe",
    "data_dir",
    "db_path",
    "inspect_storage_utilization",
    "universe_id_from_path",
    "wiki_path",
    "_connect",
    # Accounts bounded context
    "_account_id_for_username",
    "actor_has_capability",
    "create_or_update_account",
    "create_session",
    "ensure_host_account",
    "get_account",
    "grant_capabilities",
    "list_accounts",
    "list_capabilities",
    "resolve_bearer_token",
]


# -------------------------------------------------------------------
# Bounded-context re-exports — lazy via PEP-562 ``__getattr__``
# -------------------------------------------------------------------
#
# Rationale (docs/design-notes/2026-04-19-storage-init-stale-bytecode-
# mitigation.md Option A): eager re-exports at module-body tail created
# a circular-import window (``accounts.py`` top-imports constants from
# ``workflow.storage``; this file end-imports functions from
# ``accounts``). Worked by accident of ordering. The 2026-04-19 P0
# exposed the fragility when R7a symbol additions raced process restart.
#
# The lazy shape below means a fresh ``from workflow.storage.accounts
# import ...`` runs only at first attribute access, AFTER the package
# body has fully bound its constants. Same public API (``from
# workflow.storage import ensure_host_account`` etc. still works per
# Python's ``from`` import resolution protocol).
#
# ``__all__`` still enumerates every re-export so that ``import *``,
# static analyzers, and the import-graph smoke test can discover them.


_LAZY_IMPORTS = {
    # name -> (submodule, attr). Submodule path is relative to
    # ``workflow.storage``; attr is the name to look up on the submodule.
    "_account_id_for_username": ("accounts", "_account_id_for_username"),
    "actor_has_capability":     ("accounts", "actor_has_capability"),
    "create_or_update_account": ("accounts", "create_or_update_account"),
    "create_session":           ("accounts", "create_session"),
    "ensure_host_account":      ("accounts", "ensure_host_account"),
    "get_account":              ("accounts", "get_account"),
    "grant_capabilities":       ("accounts", "grant_capabilities"),
    "list_accounts":            ("accounts", "list_accounts"),
    "list_capabilities":        ("accounts", "list_capabilities"),
    "resolve_bearer_token":     ("accounts", "resolve_bearer_token"),
}


def __getattr__(name: str) -> Any:  # PEP-562
    """Resolve re-exported names against the current submodule state.

    Cache the resolved value on the package so subsequent accesses are
    O(1) and participate in ``dir()`` discovery. Missing names raise
    ``AttributeError`` (standard module-attribute contract).
    """
    if name in _LAZY_IMPORTS:
        import importlib
        submodule, attr = _LAZY_IMPORTS[name]
        mod = importlib.import_module(f"workflow.storage.{submodule}")
        try:
            value = getattr(mod, attr)
        except AttributeError as exc:
            raise AttributeError(
                f"module 'workflow.storage' lazy-import target "
                f"'workflow.storage.{submodule}' has no attribute {attr!r}"
            ) from exc
        globals()[name] = value  # cache for subsequent accesses
        return value
    raise AttributeError(f"module 'workflow.storage' has no attribute {name!r}")


def __dir__() -> list[str]:  # PEP-562 pair — supports ``dir(workflow.storage)``
    return sorted(set(globals()) | set(_LAZY_IMPORTS))

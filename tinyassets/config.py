"""Per-universe config.yaml reader.

Each universe can have an optional ``config.yaml`` at its root with
overrides for provider preferences, temperature, timeout, and
structural limits.  Missing file or missing keys use defaults.

See AGENTS.md Input Files table.
"""

from __future__ import annotations

import contextlib
import errno
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from tinyassets.exceptions import ProviderUnavailableError

logger = logging.getLogger(__name__)


@dataclass
class UniverseConfig:
    """Per-universe configuration with defaults for all fields.

    Loaded from ``{universe_path}/config.yaml``.  Any field not
    specified in the YAML file uses the default value.
    """

    # Provider preferences
    preferred_writer: str = ""
    """Preferred writer provider name (e.g. 'claude-code'). Empty = use
    default fallback chain."""

    preferred_judge: str = ""
    """Preferred judge provider. Empty = use all available."""

    allowed_providers: list[str] | None = None
    """Persistent per-universe provider-destination ceiling.

    ``None`` is the legacy/unassigned state and is rejected for explicit-
    universe execution. ``[]`` is an assigned-but-held or quarantined state.
    A non-empty list is the strict destination ceiling; the router filters
    every fallback chain (writer/judge/extract) and the judge ensemble down to
    providers whose name appears here. If the filter empties a chain, the call
    hard-fails with
    ``AllProvidersExhaustedError`` rather than silently leaking to a
    disallowed third-party provider.

    Bare/global legacy callers retain their backwards-compatible ``None``
    behavior; they do not represent an explicit universe assignment.

    Composes with ``TINYASSETS_PIN_WRITER``: the pin sets the chain to a
    single provider first, then the allowlist filter applies; if the
    pinned provider is not in the allowlist the call hard-fails.

    See ``docs/design-notes/2026-04-27-q63-third-party-provider-privacy.md``
    and ``.claude/agent-memory/navigator/q63_section4_dispositions.md``
    for the design rationale."""

    engine_assignment_state: str = ""
    """Durable engine-assignment transaction state.

    ``ready`` means the persisted provider ceiling may be evaluated. ``pending``
    quarantines provider execution while a cross-file config/vault update is in
    progress. Empty or any other value is legacy/invalid and fails closed at the
    explicit-universe provider boundary.
    """

    # Engine source (how this universe's intelligence is powered) — set by
    # `universe action=set_engine`. The founder chooses at onboard.
    engine_source: str = "byo_api_key"
    """How this universe sources its engine: ``byo_api_key`` (default; a BYO API
    key in the vault) / ``self_hosted_endpoint`` / ``market_rented`` /
    ``host_daemon``. The BYO-API-key path is fully wired end-to-end; the others
    persist the founder's choice (deeper market-matching / endpoint-routing
    runtime is post-M1 hardening)."""

    engine_endpoint: str = ""
    """Self-hosted engine endpoint (e.g. an ``OLLAMA_HOST`` / ``ANTHROPIC_BASE_URL``
    URL) when ``engine_source=self_hosted_endpoint``."""

    market_model: str = ""
    """Model to rent from the market (e.g. ``glm-5.2``) when
    ``engine_source=market_rented``."""

    market_rate: float = 0.0
    """Per-unit market rate the founder accepts for a rented engine."""

    spending_cap: float = 0.0
    """Spending cap for a market-rented engine (0 = unset)."""

    # Model parameters
    temperature: float = 0.7
    """LLM temperature for creative generation."""

    timeout: int = 300
    """Subprocess / HTTP timeout in seconds."""

    max_tokens: int | None = None
    """Optional token cap for provider calls."""

    # Structural limits
    chapters_target: int = 1
    """Target number of chapters per book."""

    scenes_target: int = 3
    """Target number of scenes per chapter."""

    revision_limit: int = 1
    """Maximum second-draft revisions per scene (0 = no revisions)."""

    # Word count bounds
    min_words_per_scene: int = 200
    """Minimum word count for scene acceptance."""

    max_words_per_scene: int = 3000
    """Maximum word count for scene acceptance."""

    # Evaluation
    judge_count: int = 0
    """Number of judges for ensemble evaluation.  0 = all available."""

    debate_enabled: bool = True
    """Whether Tier 3 debate escalation is enabled."""

    # Custom overrides (catch-all for future extensions)
    extra: dict[str, Any] = field(default_factory=dict)
    """Any additional key-value pairs from config.yaml not mapped to
    a named field."""


def load_universe_config(universe_path: str | Path) -> UniverseConfig:
    """Load config.yaml from a universe directory.

    Parameters
    ----------
    universe_path : str or Path
        Root directory of the universe.

    Returns
    -------
    UniverseConfig
        Parsed config with defaults for missing fields.  Returns
        a default config if the file doesn't exist or can't be parsed.
    """
    config_file = Path(universe_path) / "config.yaml"
    if not config_file.exists():
        logger.debug("No config.yaml in %s; using defaults", universe_path)
        return UniverseConfig()

    try:
        import yaml
    except ImportError:
        logger.warning(
            "PyYAML not installed; cannot read config.yaml. "
            "Install with: pip install pyyaml"
        )
        return UniverseConfig()

    try:
        raw = config_file.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception as e:
        logger.warning("Failed to parse config.yaml: %s", e)
        return UniverseConfig()

    if not isinstance(data, dict):
        logger.warning("config.yaml is not a mapping; using defaults")
        return UniverseConfig()

    return _build_config(data)


def _build_config(data: dict[str, Any]) -> UniverseConfig:
    """Build a UniverseConfig from parsed YAML data.

    Known keys are mapped to typed fields; unknown keys go into
    ``extra``.
    """
    known_fields = {f.name for f in UniverseConfig.__dataclass_fields__.values()}
    known_fields.discard("extra")

    kwargs: dict[str, Any] = {}
    extra: dict[str, Any] = {}

    for key, value in data.items():
        if key in known_fields:
            kwargs[key] = value
        else:
            extra[key] = value

    if extra:
        kwargs["extra"] = extra

    try:
        return UniverseConfig(**kwargs)
    except (TypeError, ValueError) as e:
        logger.warning("Invalid config.yaml values: %s; using defaults", e)
        return UniverseConfig()


def write_universe_config_fields(
    universe_path: str | Path, **fields: Any
) -> None:
    """Merge *fields* into ``{universe_path}/config.yaml`` (atomic).

    Loads the existing config.yaml (if any), updates the given top-level keys,
    and writes the merged mapping back atomically (temp file + rename). Existing
    keys not named in *fields* are preserved. This is the write path for
    per-universe engine assignment (``preferred_writer`` /
    ``allow_api_key_providers`` set by ``universe action=set_engine``).

    Fails loudly (raises) if PyYAML is unavailable or the write fails — a
    silently-dropped engine assignment would leave the universe on the wrong
    engine (Hard Rule #8).
    """
    import os
    import tempfile

    import yaml

    config_file = Path(universe_path) / "config.yaml"
    data: dict[str, Any] = {}
    if config_file.exists():
        try:
            loaded = yaml.safe_load(config_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data = loaded
        except Exception as e:  # noqa: BLE001 - fall back to empty, log below
            logger.warning(
                "Existing config.yaml at %s unreadable (%s); rewriting fresh",
                config_file, e,
            )
    data.update(fields)

    config_file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(config_file.parent), prefix=".config.", suffix=".yaml.tmp"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            yaml.safe_dump(data, fh, default_flow_style=False, sort_keys=True)
        os.replace(tmp_path, config_file)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


ENGINE_ASSIGNMENT_LOCK_FILENAME = ".engine-assignment.lock"
_ENGINE_ASSIGNMENT_LOCK_CONTENTION_ERRNOS = {
    errno.EACCES,
    errno.EAGAIN,
    errno.EWOULDBLOCK,
    errno.EDEADLK,
}


class _EngineAssignmentLockBusy(BlockingIOError):
    """The nonblocking assignment try-lock found another active holder."""


def _lock_windows_file(fd: int, *, blocking: bool, shared: bool) -> None:
    """Acquire a true Win32 shared or exclusive byte-range lock."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    lock_file_ex = ctypes.WinDLL("kernel32", use_last_error=True).LockFileEx
    lock_file_ex.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    ]
    lock_file_ex.restype = wintypes.BOOL
    flags = 0
    if not blocking:
        flags |= 0x00000001  # LOCKFILE_FAIL_IMMEDIATELY
    if not shared:
        flags |= 0x00000002  # LOCKFILE_EXCLUSIVE_LOCK
    overlapped = Overlapped()
    if not lock_file_ex(
        wintypes.HANDLE(msvcrt.get_osfhandle(fd)),
        flags,
        0,
        1,
        0,
        ctypes.byref(overlapped),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


def _unlock_windows_file(fd: int) -> None:
    """Release a Win32 byte-range lock acquired by ``_lock_windows_file``."""
    import ctypes
    import msvcrt
    from ctypes import wintypes

    class Overlapped(ctypes.Structure):
        _fields_ = [
            ("Internal", ctypes.c_size_t),
            ("InternalHigh", ctypes.c_size_t),
            ("Offset", wintypes.DWORD),
            ("OffsetHigh", wintypes.DWORD),
            ("hEvent", wintypes.HANDLE),
        ]

    unlock_file_ex = ctypes.WinDLL("kernel32", use_last_error=True).UnlockFileEx
    unlock_file_ex.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.POINTER(Overlapped),
    ]
    unlock_file_ex.restype = wintypes.BOOL
    overlapped = Overlapped()
    if not unlock_file_ex(
        wintypes.HANDLE(msvcrt.get_osfhandle(fd)),
        0,
        1,
        0,
        ctypes.byref(overlapped),
    ):
        raise ctypes.WinError(ctypes.get_last_error())


@contextlib.contextmanager
def engine_assignment_lock(
    universe_dir: str | Path,
    *,
    blocking: bool = True,
    shared: bool = False,
) -> Iterator[None]:
    """Hold the universe's cross-process engine-assignment reader/writer lock.

    The sidecar remains on disk between operations so every process opens the
    same inode. Windows uses a one-byte ``LockFileEx`` lock; POSIX uses
    ``flock``. The Win32 API is required because the CRT's read-lock constants
    are aliases for exclusive locks and cannot admit concurrent readers.
    Assignment writers use the default exclusive lock. Validation readers use
    a shared lock so they can coexist while still excluding assignment writes.
    Blocking callers retry only genuine contention. Nonblocking callers make
    one try and receive ``BlockingIOError``-compatible contention immediately;
    every other lock error propagates unchanged.
    """
    universe = Path(universe_dir)
    universe.mkdir(parents=True, exist_ok=True)
    lock_path = universe / ENGINE_ASSIGNMENT_LOCK_FILENAME
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o644)
    try:
        while True:
            try:
                if sys.platform == "win32":
                    _lock_windows_file(fd, blocking=blocking, shared=shared)
                else:
                    import fcntl

                    mode = fcntl.LOCK_SH if shared else fcntl.LOCK_EX
                    if not blocking:
                        mode |= fcntl.LOCK_NB
                    fcntl.flock(fd, mode)
                break
            except OSError as exc:
                if exc.errno not in _ENGINE_ASSIGNMENT_LOCK_CONTENTION_ERRNOS:
                    raise
                if not blocking:
                    raise _EngineAssignmentLockBusy(
                        exc.errno,
                        "engine assignment lock is held",
                    ) from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            if sys.platform == "win32":
                try:
                    _unlock_windows_file(fd)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
    finally:
        os.close(fd)


@contextlib.contextmanager
def validated_engine_assignment(
    universe_dir: str | Path,
    provider_name: str | None = None,
) -> Iterator[UniverseConfig]:
    """Yield a fresh valid assignment while holding its universe lock.

    Explicit-universe provider work is admitted only from durable ``ready``
    state with a well-typed provider ceiling. When *provider_name* is supplied,
    that exact candidate must be inside the freshly loaded ceiling.
    """
    try:
        with engine_assignment_lock(universe_dir, blocking=False, shared=True):
            config = load_universe_config(universe_dir)
            allowed = config.allowed_providers
            valid_ceiling = isinstance(allowed, list) and all(
                isinstance(candidate, str) for candidate in allowed
            )
            if config.engine_assignment_state != "ready" or not valid_ceiling:
                raise ProviderUnavailableError(
                    "explicit universe engine assignment is not ready; "
                    "setup or repair is required"
                )
            if provider_name is not None and provider_name not in allowed:
                raise ProviderUnavailableError(
                    f"provider {provider_name!r} is outside the universe's "
                    "engine-assignment ceiling"
                )
            yield config
    except _EngineAssignmentLockBusy as exc:
        raise ProviderUnavailableError(
            "explicit universe engine assignment is in progress; retry later"
        ) from exc

"""One OS jail for every provider CLI launched on a universe's behalf.

Why this exists
---------------
A provider CLI (``claude -p``, ``codex exec``, any future command adapter) is a
model with tools. Before 2026-09-24 a workflow node launched it in the daemon's
own working directory (``/app``, the platform source) as the daemon's user, so
its shell and file tools could list ``/data`` -- every user's universe -- and
read ``/proc/1/environ``, the daemon's platform secrets. A tool deny list does
not fix that: it is a per-vendor flag naming the tools one CLI version knows
about, and a hook, a subagent or a renamed tool walks around it.

What it does
------------
Every provider subprocess spawned through
:func:`tinyassets.providers.owned_process.aspawn_owned` while a universe is
bound (:func:`provider_launch_scope`) runs inside bubblewrap. The jail holds:

* the owning universe's own directory, read-write at its own path, so every
  path the provider environment already points at (``HOME``, ``TMPDIR``,
  ``CLAUDE_CONFIG_DIR``, ``CODEX_HOME``, the universe's ``.claude`` settings)
  resolves unchanged;
* over it, an empty ``tmpfs`` on ``.runtime/provider-launch-credentials``, with
  ONLY this launch's own credential snapshot bound back -- a concurrent launch's
  snapshot for another provider is not readable;
* the provider's own install tree, read-only, plus a fixed list of system
  paths (``/usr``, ``/bin``, ``/lib*``, CA certificates, name resolution);
* a private ``/tmp``, ``/dev`` and a ``/proc`` of its own pid namespace;
* the host network (``--share-net``): API calls and web tools keep working.

Nothing else. Not ``/data`` or another universe, not ``/app``, not the daemon's
``/proc``, not the host credential homes. Everything the CLI starts -- hooks
from the universe's ``.claude/settings.json``, an MCP stdio server, a shell
tool -- is a descendant inside the same namespaces.

The key is the OWNING UNIVERSE, not the vendor. The router binds it around every
provider call (``provider_launch_scope``), and the shared spawn point reads it,
so a provider inherits the jail by spawning through ``aspawn_owned`` and needs
no code of its own. An adapter MAY narrow what the universe looks like inside
the jail (:class:`UniverseView`: codex's chat turn sees an empty workspace), but
every bind it asks for must come from inside the owning universe, so it can
never widen the jail.

Fail closed
-----------
* No bubblewrap, or a host where the probe cannot create a namespace (including
  every non-Linux host): :class:`ProviderConfinementError` before anything is
  spawned. There is no unconfined fallback.
* A provider launch the router made with NO owning universe (a host-authority
  call such as a leaderboard selector run) is refused the same way. Such a call
  ran published, possibly foreign, graph content with the host's credentials
  and every tool; there is no universe to confine it to.
* A process spawned outside any scope (not a provider call made through the
  router: the tests of this module's process-family machinery) is unchanged.
"""

from __future__ import annotations

import contextlib
import os
import shutil
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path

from tinyassets.exceptions import ProviderAuthorityHeldError

__all__ = [
    "BWRAP_RESOLVER",
    "JailMount",
    "ProviderConfinementError",
    "UniverseView",
    "confine_launch",
    "default_view",
    "jail_argv",
    "provider_launch_scope",
]


class ProviderConfinementError(ProviderAuthorityHeldError):
    """A provider launch was refused because it could not be jailed.

    Raised BEFORE any process exists, so it is never evidence about the
    provider or its credential: the router re-raises it without a cooldown and
    releases what it reserved. A subclass of :class:`ProviderAuthorityHeldError`
    because that is the contract every caller already honours for "this call
    may not run here": it is never folded into a fallback response.
    """

    failure_class = "provider_confinement_unavailable"
    #: Every raise starts with this, so a stored error string stays classifiable.
    MESSAGE = "provider launch refused: it cannot be confined to its universe"


@dataclass(frozen=True, slots=True)
class _LaunchScope:
    universe_dir: Path | None
    credential_dir: Path | None


_SCOPE: ContextVar[_LaunchScope | None] = ContextVar(
    "tinyassets_provider_launch_scope", default=None,
)


@contextlib.contextmanager
def provider_launch_scope(
    universe_dir: str | Path | None,
    *,
    credential_dir: str | Path | None = None,
) -> Iterator[None]:
    """Bind the universe that owns every provider process launched inside.

    ``universe_dir=None`` is a binding too: it says "this provider call has no
    owning universe", and any process it tries to launch is refused. The router
    enters this around each ``provider.complete``; a context variable carries it
    to the spawn point through ``await`` and into tasks the call creates.
    """
    scope = _LaunchScope(
        universe_dir=None if universe_dir is None else Path(universe_dir),
        credential_dir=None if credential_dir is None else Path(credential_dir),
    )
    token = _SCOPE.set(scope)
    try:
        yield
    finally:
        _SCOPE.reset(token)


@dataclass(frozen=True, slots=True)
class JailMount:
    """One bubblewrap mount operation: ``bind``, ``ro-bind`` or ``tmpfs``."""

    op: str
    dest: str
    source: Path | None = None


@dataclass(frozen=True, slots=True)
class UniverseView:
    """What the owning universe looks like inside the jail.

    Every ``bind``/``ro-bind`` source must resolve inside ``universe_dir``; the
    jail refuses the launch otherwise. ``setenv`` overrides the provider env
    inside the jail only (e.g. a credential home mounted at a fixed path).
    """

    universe_dir: Path
    mounts: tuple[JailMount, ...]
    chdir: str | None = None
    setenv: tuple[tuple[str, str], ...] = ()


#: Read-only system paths every CLI may need to execute and reach the network.
#: Public by construction: binaries, libraries, CA bundles, resolver config and
#: the account database (``/etc/passwd`` carries no secret; ``/etc/shadow`` is
#: not here). Missing paths are skipped.
_SYSTEM_RO_PATHS: tuple[str, ...] = (
    "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32",
    "/etc/alternatives", "/etc/ssl/certs", "/etc/resolv.conf", "/etc/hosts",
    "/etc/nsswitch.conf", "/etc/host.conf", "/etc/gai.conf", "/etc/passwd",
    "/etc/group", "/etc/localtime", "/etc/ld.so.cache",
)

#: Roots a view may never mount over, and install mounts may never sit under
#: or above.
_RESERVED_DESTS: tuple[str, ...] = (
    "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/etc",
    "/proc", "/dev",
)

#: Where every universe keeps its per-launch credential snapshots.
_LAUNCH_CREDENTIALS = Path(".runtime") / "provider-launch-credentials"

#: Environment variables naming a CA bundle file the provider child keeps
#: (see ``providers.base._PROVIDER_CHILD_CA_FILE_ENV_VARS``).
_CA_FILE_ENV_VARS: tuple[str, ...] = (
    "SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE",
    "NODE_EXTRA_CA_CERTS", "CODEX_CA_CERTIFICATE",
)


def _refuse(detail: str) -> ProviderConfinementError:
    return ProviderConfinementError(f"{ProviderConfinementError.MESSAGE}: {detail}")


def _resolve_bwrap() -> str:
    """The bubblewrap path this host proved it can jail with, or refuse."""
    from tinyassets.providers.base import get_sandbox_status

    status = get_sandbox_status() or {}
    if not status.get("bwrap_available"):
        raise _refuse(f"no OS sandbox on this host ({status.get('reason') or 'bwrap unavailable'})")
    path = status.get("bwrap_path") or shutil.which("bwrap")
    if not path:
        raise _refuse("bwrap passed the probe but is not on PATH")
    return str(path)


#: Resolves the bubblewrap binary for a jailed launch. Substituted by tests
#: (injection, not an env switch); production never replaces it.
BWRAP_RESOLVER: Callable[[], str] = _resolve_bwrap


def _within(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _overlaps(a: Path, b: Path) -> bool:
    return _within(a, b) or _within(b, a)


def _covered(path: str, roots: Iterable[str]) -> bool:
    return any(path == root or path.startswith(root.rstrip("/") + "/") for root in roots)


def default_view(
    universe_dir: Path,
    *,
    credential_dir: Path | None = None,
    cwd: str | None = None,
) -> UniverseView:
    """The universe read-write at its own path, other launch snapshots masked."""
    root = universe_dir.resolve(strict=False)
    mounts = [JailMount("bind", str(root), root)]
    launch_root = root / _LAUNCH_CREDENTIALS
    if launch_root.is_dir():
        mounts.append(JailMount("tmpfs", str(launch_root)))
    if credential_dir is not None:
        own = credential_dir.resolve(strict=False)
        if own.is_dir() and _within(own, root):
            # Bound back read-write: the CLI writes its lock / session files
            # beside the credential exactly as it did before the jail.
            mounts.append(JailMount("bind", str(own), own))
    chdir = str(root)
    if cwd:
        resolved_cwd = Path(cwd).resolve(strict=False)
        if _within(resolved_cwd, root):
            chdir = str(resolved_cwd)
    return UniverseView(universe_dir=root, mounts=tuple(mounts), chdir=chdir)


def _validated_view(view: UniverseView) -> UniverseView:
    root = view.universe_dir.resolve(strict=False)
    for mount in view.mounts:
        if mount.op not in ("bind", "ro-bind", "tmpfs"):
            raise _refuse(f"unknown mount operation {mount.op!r}")
        dest = mount.dest
        if not dest.startswith("/") or dest.rstrip("/") == "" or _covered(dest, _RESERVED_DESTS):
            raise _refuse(f"a view may not mount at {dest!r}")
        if mount.op == "tmpfs":
            continue
        if mount.source is None:
            raise _refuse("a bind needs a source")
        try:
            source = mount.source.resolve(strict=True)
        except OSError:
            raise _refuse("a bind source does not exist") from None
        if not _within(source, root):
            raise _refuse("a view may only bind paths inside its own universe")
    for name, _value in view.setenv:
        if not name or "=" in name:
            raise _refuse("invalid jail environment name")
    return view


def _command_install_paths(argv0: str, env: Mapping[str, str] | None) -> list[Path]:
    """Where the command lives: its own directory and its resolved package tree."""
    located = argv0 if "/" in argv0 else shutil.which(argv0, path=(env or {}).get("PATH"))
    if not located:
        return []
    wrapper = Path(os.path.abspath(located))
    paths = [wrapper.parent]
    try:
        real = wrapper.resolve(strict=True)
    except OSError:
        return paths
    tree = real.parent
    for ancestor in real.parents:
        if ancestor.name == "node_modules":
            tree = ancestor.parent
            break
    paths.append(tree)
    return paths


def _forbidden_install_roots(view: UniverseView) -> list[Path]:
    """Trees an install mount must never reach: every universe and the source."""
    import tinyassets
    from tinyassets.storage import data_dir

    roots = [
        Path(tinyassets.__file__).resolve().parent.parent,
        view.universe_dir.resolve(strict=False).parent,
    ]
    try:
        roots.append(Path(data_dir()).resolve(strict=False))
    except Exception:  # noqa: BLE001 - an unresolvable data dir adds no root
        pass
    return roots


def _install_binds(
    paths: Iterable[Path], view: UniverseView, already: list[str],
) -> list[str]:
    forbidden = _forbidden_install_roots(view)
    argv: list[str] = []
    for raw in paths:
        try:
            path = Path(raw).resolve(strict=True)
        except OSError:
            continue
        text = str(path)
        if text == "/" or _covered(text, already):
            continue
        if any(_overlaps(path, root) for root in forbidden):
            raise _refuse("a provider install path overlaps universe data or platform source")
        if _covered(text, ("/etc", "/proc", "/dev")):
            raise _refuse("a provider install path sits under a reserved system root")
        argv.extend(("--ro-bind", text, text))
        already.append(text)
    return argv


def _ca_file_binds(
    env: Mapping[str, str] | None, view: UniverseView, already: list[str],
) -> list[str]:
    """A CA bundle the provider env names, read-only, when not already visible.

    Public certificate files only; one that would sit in a universe or the
    source tree is left out rather than exposing that tree.
    """
    forbidden = _forbidden_install_roots(view)
    argv: list[str] = []
    for name in _CA_FILE_ENV_VARS:
        value = (env or {}).get(name)
        if not value or not os.path.isabs(value) or not os.path.isfile(value):
            continue
        path = Path(value).resolve(strict=False)
        text = str(path)
        if _covered(text, already) or _covered(text, ("/proc", "/dev")):
            continue
        if any(_within(path, root) for root in forbidden):
            continue
        argv.extend(("--ro-bind", text, text))
        already.append(text)
    return argv


def jail_argv(
    argv: Sequence[str],
    view: UniverseView,
    *,
    bwrap_path: str,
    install_paths: Iterable[Path] = (),
    env: Mapping[str, str] | None = None,
) -> list[str]:
    """The bubblewrap argv that runs ``argv`` inside ``view``. Pure of policy.

    Order matters and is fixed: namespaces, a private ``/tmp``, the system
    paths, the provider install tree, then the universe view (so a view mount
    under ``/tmp`` lands on the private tmpfs, and a mask lands on the bind it
    masks), then the environment overrides and the working directory.
    """
    view = _validated_view(view)
    out: list[str] = [
        bwrap_path,
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--share-net",
        "--dev", "/dev",
        "--proc", "/proc",
        "--tmpfs", "/tmp",
    ]
    bound: list[str] = []
    for system_path in _SYSTEM_RO_PATHS:
        if os.path.lexists(system_path):
            out.extend(("--ro-bind", system_path, system_path))
            bound.append(system_path)
    out.extend(_install_binds(install_paths, view, bound))
    out.extend(_ca_file_binds(env, view, bound))
    for mount in view.mounts:
        if mount.op == "tmpfs":
            out.extend(("--tmpfs", mount.dest))
        else:
            source = str(mount.source.resolve(strict=True))  # validated above
            out.extend((f"--{mount.op}", source, mount.dest))
    for name, value in view.setenv:
        out.extend(("--setenv", name, value))
    out.extend(("--chdir", view.chdir or str(view.universe_dir)))
    out.append("--")
    out.extend(argv)
    return out


def confine_launch(
    argv: Sequence[str],
    *,
    cwd: str | os.PathLike[str] | None = None,
    env: Mapping[str, str] | None = None,
    view: UniverseView | None = None,
    install_mounts: Callable[[], Iterable[Path]] | None = None,
) -> list[str] | None:
    """The jailed argv for this launch, ``None`` when no jail applies, or refuse.

    Called by the shared spawn point for EVERY provider process. The decision
    reads only the bound scope and the adapter's optional view -- never the
    vendor, the config or the command.
    """
    scope = _SCOPE.get()
    if scope is None and view is None:
        return None
    if scope is not None and scope.universe_dir is None:
        raise _refuse(
            "this provider call has no owning universe, so there is no "
            "directory to confine it to; it will not run on the host"
        )
    if view is None:
        view = default_view(
            scope.universe_dir,
            credential_dir=scope.credential_dir,
            cwd=None if cwd is None else os.fspath(cwd),
        )
    elif scope is not None and (
        view.universe_dir.resolve(strict=False)
        != scope.universe_dir.resolve(strict=False)
    ):
        raise _refuse("the adapter's view names a different universe than its call")
    if not view.universe_dir.resolve(strict=False).is_dir():
        raise _refuse("the owning universe directory does not exist")
    bwrap_path = BWRAP_RESOLVER()
    install_paths = [*_command_install_paths(str(argv[0]), env)] if argv else []
    if install_mounts is not None:
        install_paths.extend(install_mounts())
    return jail_argv(
        argv, view, bwrap_path=bwrap_path, install_paths=install_paths, env=env,
    )

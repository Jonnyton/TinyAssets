"""Staging and command construction for the provisioning resolver (design D3).

This module decides **what** the resolver will run and **which bytes** it will
run against; it never runs anything. No process is started, no network address
is opened, and no ambient configuration is read -- the caller executes the argv
this returns, inside the resolver jail, with the environment this returns. Doing
it here keeps the part that can be tested exhaustively away from the part that
needs a jail and a network.

Staging is where the digest earns its keep. An admitted plan carries the exact
text that was validated; :func:`stage_python_plan` and :func:`stage_node_plan`
write that text, **read it back**, and refuse unless the sha256 of the bytes now
on disk equals the plan's digest. Anything between admission and the installer
-- a truncated write, a full disk, a symlinked staging path, a second writer --
becomes a loud failure instead of an install of something nobody admitted.

Every argv element is checked before it is returned. A path that begins with a
dash is refused rather than emitted, because ``pip`` and ``npm`` would read it
as an option: a cache directory called ``--index-url`` is not a directory, it is
an argument injection. Only the fixed flags these builders themselves emit may
begin with a dash (:data:`FIXED_FLAGS`); everything else must be an absolute,
NUL-free path.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

__all__ = [
    "FIXED_FLAGS",
    "NULL_DEVICE",
    "PYTHON_MANIFEST_NAME",
    "ResolverError",
    "StagedManifest",
    "StagedNodeManifests",
    "npm_fetch_argv",
    "npm_offline_install_argv",
    "pip_download_argv",
    "pip_offline_install_argv",
    "resolver_environment",
    "stage_node_plan",
    "stage_python_plan",
]

#: The admitted requirement text, under a name no manifest in a repository uses,
#: so nothing in a checkout can be mistaken for it.
PYTHON_MANIFEST_NAME: Final[str] = "requirements.canonical.txt"
NODE_MANIFEST_NAME: Final[str] = "package.json"
NODE_LOCKFILE_NAME: Final[str] = "package-lock.json"

DEFAULT_INDEX_URL: Final[str] = "https://pypi.org/simple"
NPM_REGISTRY_URL: Final[str] = "https://registry.npmjs.org"

#: ``npm`` is told to read its user config from the null device rather than the
#: home directory: the resolver jail has a home, and a config file appearing in
#: it must not be able to add a registry.
NULL_DEVICE: Final[str] = "NUL" if os.name == "nt" else "/dev/null"

#: Every dash-leading token these builders emit. An argv element starting with a
#: dash and not in this set is an injected option wearing a path's clothes.
FIXED_FLAGS: Final[frozenset[str]] = frozenset(
    {
        "-m",
        "-r",
        "--isolated",
        "--no-config",
        "--only-binary=:all:",
        "--require-hashes",
        "--index-url",
        "--dest",
        "--no-index",
        "--find-links",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        "--cache",
        "--userconfig",
        "--registry",
        "--prefix",
        "--offline",
    }
)

_MAX_PATH_CHARS: Final[int] = 4096


class ResolverError(RuntimeError):
    """A staging or command-construction invariant failed.

    Not a user-facing refusal: by the time this module runs, the manifest was
    already admitted. This is the platform failing to hand the installer what
    the plan says, which is a bug or an interference, and either way not
    something to continue past.
    """


@dataclass(frozen=True)
class StagedManifest:
    """The admitted Python text on disk, and the digest the bytes there hash to."""

    path: Path
    digest: str


@dataclass(frozen=True)
class StagedNodeManifests:
    """The admitted Node manifests on disk, and the digest binding the pair."""

    directory: Path
    package_json: Path
    lockfile: Path
    digest: str


# --------------------------------------------------------------------------------------
# Staging
# --------------------------------------------------------------------------------------


def _staging_directory(staging_dir: Path | str) -> Path:
    directory = Path(staging_dir)
    if not directory.is_absolute():
        raise ResolverError(f"staging directory must be absolute: {directory!s}")
    resolved = Path(os.path.realpath(str(directory)))
    if not resolved.is_dir():
        raise ResolverError(f"staging directory does not exist: {directory!s}")
    return resolved


def _staged_path(directory: Path, name: str) -> Path:
    target = Path(os.path.realpath(str(directory / name)))
    root = str(directory)
    if str(target) != root and not str(target).startswith(root + os.sep):
        raise ResolverError(f"staged file escapes the staging directory: {name}")
    return target


def _write_exact(target: Path, data: bytes) -> bytes:
    """Create *target* exclusively, write *data*, and read back what landed.

    Exclusive creation: staging is fresh per job, so a file already there is
    either a second writer or something planted, and both are refusals. The
    read-back is what makes the digest check mean "the installer will see these
    bytes" rather than "we intended these bytes".
    """
    flags = (
        os.O_WRONLY | os.O_CREAT | os.O_EXCL
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_BINARY", 0)
    )
    try:
        handle = os.open(str(target), flags, 0o600)
    except FileExistsError as exc:
        raise ResolverError(f"staged file already exists: {target.name}") from exc
    except OSError as exc:
        raise ResolverError(f"cannot stage {target.name}: {exc}") from exc
    try:
        written = 0
        while written < len(data):
            written += os.write(handle, data[written:])
    finally:
        os.close(handle)
    return target.read_bytes()


def stage_python_plan(plan: Any, staging_dir: Path | str) -> StagedManifest:
    """Write the admitted requirement text, or refuse.

    The digest is recomputed from the bytes on disk and compared with the plan's:
    the offline install is bound to what admission validated, and that binding is
    only real if the file the installer reads is the file that was hashed.
    """
    directory = _staging_directory(staging_dir)
    target = _staged_path(directory, PYTHON_MANIFEST_NAME)
    landed = _write_exact(target, plan.normalized_text.encode("utf-8"))
    digest = hashlib.sha256(landed).hexdigest()
    if digest != plan.digest:
        raise ResolverError(
            f"staged requirements digest {digest} does not match the admitted plan "
            f"{plan.digest}: the installer would read something that was not admitted"
        )
    return StagedManifest(path=target, digest=digest)


def stage_node_plan(plan: Any, staging_dir: Path | str) -> StagedNodeManifests:
    """Write the admitted package.json and lockfile, or refuse."""
    directory = _staging_directory(staging_dir)
    manifest_path = _staged_path(directory, NODE_MANIFEST_NAME)
    lockfile_path = _staged_path(directory, NODE_LOCKFILE_NAME)
    manifest_bytes = _write_exact(
        manifest_path, plan.normalized_package_json.encode("utf-8")
    )
    lockfile_bytes = _write_exact(
        lockfile_path, plan.normalized_lockfile.encode("utf-8")
    )
    digest = hashlib.sha256(manifest_bytes + b"\x00" + lockfile_bytes).hexdigest()
    if digest != plan.digest:
        raise ResolverError(
            f"staged node digest {digest} does not match the admitted plan "
            f"{plan.digest}: the installer would read something that was not admitted"
        )
    return StagedNodeManifests(
        directory=directory,
        package_json=manifest_path,
        lockfile=lockfile_path,
        digest=digest,
    )


# --------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------


def _check_path(value: Path | str, label: str) -> str:
    """An absolute, NUL-free path that cannot be read as an option."""
    text = str(value)
    if not text:
        raise ResolverError(f"{label} is empty")
    if chr(0) in text:
        raise ResolverError(f"{label} contains a NUL byte")
    if len(text) > _MAX_PATH_CHARS:
        raise ResolverError(f"{label} is longer than {_MAX_PATH_CHARS} characters")
    if text.startswith("-"):
        raise ResolverError(
            f"{label} begins with a dash and would be read as an option: {text!r}"
        )
    if not Path(text).is_absolute():
        raise ResolverError(f"{label} must be absolute: {text!r}")
    return text


def _check_program(value: Path | str, label: str) -> str:
    """An executable: an absolute path, or a bare name for the jail's PATH.

    A bare name is admitted because that is how ``npm`` and the interpreter are
    normally invoked and :func:`resolver_environment` is what decides the PATH
    it resolves against. What is never admitted is a name carrying a directory
    separator without being absolute (``../npm``) or a dash-leading name.
    """
    text = str(value)
    if not text:
        raise ResolverError(f"{label} is empty")
    if chr(0) in text:
        raise ResolverError(f"{label} contains a NUL byte")
    if text.startswith("-"):
        raise ResolverError(
            f"{label} begins with a dash and would be read as an option: {text!r}"
        )
    candidate = Path(text)
    if candidate.is_absolute():
        return _check_path(text, label)
    if "/" in text or "\\" in text:
        raise ResolverError(
            f"{label} must be absolute or a bare program name, got {text!r}"
        )
    return text


def _check_url(value: str, label: str, *, expected: str) -> str:
    if value != expected:
        raise ResolverError(f"{label} must be exactly {expected!r}, got {value!r}")
    return value


def _admitted_argv(argv: list[str]) -> list[str]:
    """The last gate: nothing dash-leading that this module did not choose."""
    for element in argv:
        if not isinstance(element, str) or not element:
            raise ResolverError(f"argv holds an empty element: {argv!r}")
        if chr(0) in element:
            raise ResolverError("argv holds a NUL byte")
        if element.startswith("-") and element not in FIXED_FLAGS:
            raise ResolverError(
                f"argv element {element!r} begins with a dash and is not one of the "
                "flags these builders emit"
            )
    return argv


def pip_download_argv(
    staged: StagedManifest,
    cache_dir: Path | str,
    *,
    python: Path | str,
    index_url: str = DEFAULT_INDEX_URL,
) -> list[str]:
    """Fetch every wheel the plan pins, into *cache_dir*, and nothing else.

    ``--only-binary=:all:`` means no sdist is downloaded and therefore no build
    backend ever executes. ``--require-hashes`` is emitted **without**
    ``--no-deps``: pip requires a hash for every file it downloads, so the plan
    must pin the whole closure. That is pip's rule, not ours, and it is the
    reason a plan naming only its direct dependencies fails here rather than
    quietly fetching an unpinned transitive one.
    """
    return _admitted_argv(
        [
            _check_program(python, "python"),
            "-m",
            "pip",
            "download",
            "--isolated",
            "--no-config",
            "--only-binary=:all:",
            "--require-hashes",
            "--index-url",
            _check_url(index_url, "index url", expected=DEFAULT_INDEX_URL),
            "--dest",
            _check_path(cache_dir, "cache directory"),
            "-r",
            _check_path(staged.path, "staged requirements"),
        ]
    )


def pip_offline_install_argv(
    staged: StagedManifest,
    cache_dir: Path | str,
    venv_python: Path | str,
) -> list[str]:
    """Install from the cache with no index at all: the network is not reachable."""
    return _admitted_argv(
        [
            _check_program(venv_python, "venv python"),
            "-m",
            "pip",
            "install",
            "--isolated",
            "--no-config",
            "--no-index",
            "--find-links",
            _check_path(cache_dir, "cache directory"),
            "--require-hashes",
            "--only-binary=:all:",
            "-r",
            _check_path(staged.path, "staged requirements"),
        ]
    )


def _npm_argv(
    staged: StagedNodeManifests,
    cache_dir: Path | str,
    *,
    npm: Path | str,
    offline: bool,
) -> list[str]:
    argv = [
        _check_program(npm, "npm"),
        "ci",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        "--cache",
        _check_path(cache_dir, "cache directory"),
        "--userconfig",
        NULL_DEVICE,
        "--registry",
        _check_url(NPM_REGISTRY_URL, "registry url", expected=NPM_REGISTRY_URL),
        "--prefix",
        _check_path(staged.directory, "staged directory"),
    ]
    if offline:
        argv.append("--offline")
    return _admitted_argv(argv)


def npm_fetch_argv(
    staged: StagedNodeManifests,
    cache_dir: Path | str,
    *,
    npm: Path | str = "npm",
) -> list[str]:
    """Populate the cache from the registry, running no lifecycle script."""
    return _npm_argv(staged, cache_dir, npm=npm, offline=False)


def npm_offline_install_argv(
    staged: StagedNodeManifests,
    cache_dir: Path | str,
    *,
    npm: Path | str = "npm",
) -> list[str]:
    """Install from the cache only; ``--offline`` makes a registry read an error."""
    return _npm_argv(staged, cache_dir, npm=npm, offline=True)


def resolver_environment(home: Path | str, path: str) -> dict[str, str]:
    """The resolver jail's environment, built from empty.

    Nothing is inherited and nothing is read from this process: the returned
    mapping is the whole of what the child sees. The three tool settings are
    there so neither installer decides on its own to phone home for a version
    check, block on a prompt, or write an update notice into the cache.
    """
    return {
        "HOME": _check_path(home, "home"),
        "PATH": _check_search_path(path),
        "LANG": "C.UTF-8",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "PIP_NO_INPUT": "1",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
    }


def _check_search_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        raise ResolverError("PATH must be a non-empty string")
    if chr(0) in path:
        raise ResolverError("PATH contains a NUL byte")
    for entry in path.split(os.pathsep):
        if not entry:
            raise ResolverError(f"PATH holds an empty entry: {path!r}")
        if not Path(entry).is_absolute():
            raise ResolverError(f"PATH entry must be absolute: {entry!r}")
    return path

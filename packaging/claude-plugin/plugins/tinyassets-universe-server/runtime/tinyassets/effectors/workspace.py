"""The ``workspace`` effect sink: check out, push and discard a repository.

Every credentialed git operation happens in a spawned worker against a
worker-private staging directory that is never mounted into a jail. This
adapter is the host side: it checks the connection grant's scope and the typed
consent, admits the job against the pool, creates the lease directory through a
no-follow directory handle, and populates it from the bundle the worker made --
credential-free, into a fresh repository, so the workspace's ``.git`` holds no
remote, no host path and no credential.

Design D0/D1/D4/D5/D6 of the ``workspace-node`` change. Never raises: every
refusal is a secret-free evidence dict carrying one actionable ``error_kind``.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from tinyassets.storage.workspace_authority import (
    CONSENT_CHECKOUT,
    CONSENT_PROVISION,
    CONSENT_PUSH,
    WORKSPACE_SINK,
    GitScopeError,
    has_git_scope,
    normalize_repo,
    workspace_consent_destination,
)

logger = logging.getLogger(__name__)

#: One path-safe branch segment. The remote ref is built, never taken: a slug
#: with a slash, a space or a leading dash would name a different branch than
#: the packet appears to.
_SLUG_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,80}$")

#: The sink name. One spelling, owned by the authority module, so the rail that
#: WRITES a consent and the sink that READS it cannot drift apart.
EXTERNAL_WRITE_SINK_WORKSPACE = WORKSPACE_SINK

#: The operations the sink offers, and the consent each one needs.
_CONSENT_FOR_OP = {
    "checkout": CONSENT_CHECKOUT,
    "push": CONSENT_PUSH,
    "discard": "",  # discarding what you already hold needs no new consent
}

#: The connection scope each operation requires, bound to (host, owner/name).
_SCOPE_FOR_OP = {"checkout": "git_read", "push": "git_write"}

#: (sink, verb) pairs that could NOT have changed the far side. A checkout
#: reads a repository and a discard only drops local state; a push is a write.
WORKSPACE_READ_EFFECTS = frozenset(
    {
        (EXTERNAL_WRITE_SINK_WORKSPACE, "checkout"),
        (EXTERNAL_WRITE_SINK_WORKSPACE, "discard"),
    }
)

_HOST = "github.com"
_MAX_BUNDLE_BYTES = 512 * 1024 * 1024
#: What one checkout may move before the pool refuses it (D4's lease bound).
_DEFAULT_MAX_CHECKOUT_BYTES = 4 * 1024 * 1024 * 1024
_JAIL_EXPORT_DIR = ".tiny-export"


class _Refused(Exception):
    """An operation refused with one actionable kind. Never leaves this module."""

    def __init__(self, kind: str, error: str, **extra: Any) -> None:
        self.kind = kind
        self.error = error
        self.extra = extra
        super().__init__(error)


# --------------------------------------------------------------------------- #
# Packet
# --------------------------------------------------------------------------- #


def _parse_packet(value: Any) -> dict[str, Any] | None:
    """Return the packet iff ``value`` is a workspace packet, else None."""
    if isinstance(value, dict):
        packet = value
    elif isinstance(value, str):
        stripped = value.strip()
        if not stripped or not stripped.startswith("{"):
            return None
        try:
            packet = json.loads(stripped)
        except (TypeError, ValueError):
            return None
        if not isinstance(packet, dict):
            return None
    else:
        return None
    if packet.get("sink") != EXTERNAL_WRITE_SINK_WORKSPACE:
        return None
    return packet


def _find_packet(
    *, output_keys: list[str], run_state: dict[str, Any]
) -> tuple[str | None, dict[str, Any] | None]:
    for key in output_keys or []:
        if not isinstance(key, str) or key not in run_state:
            continue
        packet = _parse_packet(run_state.get(key))
        if packet is not None:
            return key, packet
    return None, None


def packet_op(*, output_keys: list[str], run_state: dict[str, Any]) -> str | None:
    """The op a node's workspace packet declares, for the dispatcher's
    classification of an effect refused before the wire."""
    _key, packet = _find_packet(output_keys=output_keys, run_state=run_state)
    if packet is None:
        return None
    op = _str_field(packet, "op")
    return op or None


def _str_field(source: Any, key: str) -> str:
    if not isinstance(source, dict):
        return ""
    value = source.get(key)
    return value.strip() if isinstance(value, str) else ""


def _split_repo(repo: str) -> tuple[str, str]:
    """``owner/name`` -> the two halves, through the authority module's grammar.

    ``normalize_repo`` is the ONE parser. A second reading of what counts as a
    repository is how a scope bound to one repo comes to cover another, so this
    module does not have its own.
    """
    try:
        normalized = normalize_repo(repo)
    except GitScopeError as exc:
        raise _Refused("invalid_packet", f"packet.repo is not 'owner/name': {exc}") from None
    owner, _, name = normalized.partition("/")
    return owner, name


def repo_key_for(host: str, owner: str, name: str) -> str:
    """The pool's path-safe key for one repository."""
    return f"{host}--{owner}--{name}".replace("/", "-")


# --------------------------------------------------------------------------- #
# Authority
# --------------------------------------------------------------------------- #


def _universe_id(base_path: str | Path | None) -> str:
    if base_path is None:
        return ""
    try:
        return Path(base_path).name.strip()
    except (TypeError, ValueError):
        return ""


def _ledger_db_path(base_path: str | Path | None) -> Path | None:
    if base_path is None:
        return None
    try:
        return Path(base_path).parent / "outbound.db"
    except (TypeError, ValueError):
        return None


def _universe_short(universe_id: str) -> str:
    """The branch-name component for a universe. Path-safe by construction."""
    cleaned = "".join(c for c in universe_id if c.isalnum() or c in "-_")
    return (cleaned[:12] or "universe").lower()


def _read_connection(
    *, db_path: Path, connection_id: str, universe_id: str, grant_id: str
) -> tuple[Any, Any]:
    """The grant and the trusted connection resource, or a refusal.

    Mirrors ``authenticated_external_call``'s isolation gate exactly: the grant
    must exist, be live, and be bound to the RUNNING universe. The resource
    (not the redacted view) is needed for the credential REFERENCE -- never the
    secret, which only the worker child resolves.
    """
    from tinyassets.storage.outbound_connections import ConnectionLedger

    ledger = ConnectionLedger(db_path)
    grant = ledger.get_grant(grant_id)
    if grant is None:
        raise _Refused("unknown_grant", "connection authority refused: unknown_grant")
    if getattr(grant, "revoked_at", None) is not None:
        raise _Refused("revoked_grant", "connection authority refused: revoked_grant")
    if getattr(grant, "universe_id", "") != universe_id:
        raise _Refused(
            "grant_not_for_universe", "connection authority refused: grant_not_for_universe"
        )
    if getattr(grant, "connection_id", "") != connection_id:
        raise _Refused(
            "grant_connection_mismatch",
            "connection authority refused: grant_connection_mismatch",
        )
    resource = ledger._get_connection_resource(connection_id)
    if resource is None:
        raise _Refused("unknown_connection", "connection authority refused: unknown_connection")
    if getattr(resource, "revoked_at", None) is not None:
        raise _Refused("revoked_connection", "connection authority refused: revoked_connection")
    return grant, resource


def _require_scope(resource: Any, op: str, host: str, repo: str) -> None:
    """The connection must carry the op's git scope bound to this repository.

    ``has_git_scope`` owns the grammar (``git_read:owner/name``), the exact
    repo binding, the host check and the revoked-connection rule. This module
    does not re-implement any of it: two readings of one scope string is how a
    scope silently widens.
    """
    needed = _SCOPE_FOR_OP.get(op, "")
    if not needed:
        return
    if not has_git_scope(resource, needed, repo):
        raise _Refused(
            "scope_not_granted",
            f"the connection does not carry {needed} for this repository",
        )
    del host


def _consent_destination(consent: str, repo: str, connection_id: str, host: str) -> str:
    """The consent key, built by the authority module and never here.

    The key is `(operation, connection, repo)`: the same repository through a
    DIFFERENT connection is a different consent, because the credential behind
    it is different.
    """
    return workspace_consent_destination(
        consent, repo, connection_id=connection_id, host=host
    )


def _require_consent(
    universe_dir: Path, op: str, host: str, repo: str, connection_id: str
) -> None:
    consent = _CONSENT_FOR_OP.get(op, "")
    if not consent:
        return
    try:
        destination = _consent_destination(consent, repo, connection_id, host)
    except GitScopeError as exc:
        raise _Refused("invalid_packet", f"consent destination could not be built: {exc}")
    try:
        from tinyassets.storage.effector_consents import is_consent_active

        active = is_consent_active(
            universe_dir, sink=WORKSPACE_SINK, destination=destination
        )
    except Exception:
        logger.exception("workspace consent lookup crashed")
        active = False
    if not active:
        raise _Refused(
            "missing_consent",
            f"no active {consent} consent for {destination}",
            destination=destination,
            consent=consent,
        )


def _check_provision_consent(
    universe_dir: Path, host: str, repo: str, connection_id: str
) -> bool:
    """Provisioning is separately consented; its absence is NOT a checkout
    failure (D-spec scenario: the checkout completes, provisioning does not)."""
    try:
        from tinyassets.storage.effector_consents import is_consent_active

        return is_consent_active(
            universe_dir,
            sink=WORKSPACE_SINK,
            destination=_consent_destination(CONSENT_PROVISION, repo, connection_id, host),
        )
    except Exception:
        logger.exception("workspace provision consent lookup crashed")
        return False


# --------------------------------------------------------------------------- #
# Filesystem seams (the pool lane owns these; imported lazily so this module
# does not break while that branch is unmerged, and so tests can inject)
# --------------------------------------------------------------------------- #


def _fs():
    from tinyassets import workspace_fs

    return workspace_fs


def _make_lease_dir(lease_path: Path) -> Any:
    """Create the lease directory under a handle resolved without links."""
    fs = _fs()
    parent_fd = fs.open_dir_nofollow(str(lease_path.parent))
    return fs.create_lease_dir(parent_fd, lease_path.name)


def _make_repo_dir(lease_fd: Any, repo_dir: Path) -> Any:
    """Create ``<lease>/repo`` through the lease handle and return ITS handle.

    NOT ``create_lease_dir``: that one is for a name in the SHARED pool root
    and requires an unguessable one, which ``'repo'`` is not. The parent here
    is the private lease directory it just made, so the subdirectory helper is
    the honest call.
    """
    return _fs().create_workspace_subdir(lease_fd, repo_dir.name)


def _descriptor_or_none(handle: Any) -> int | None:
    """A real POSIX descriptor, or None.

    The pool's handles are ints on Linux, which is where this runs. On a
    non-POSIX dev host there is no descriptor to pin to, and
    ``unbundle_into_fresh_repo`` refuses one -- so the population falls back to
    the path there. That is a dev-host difference, stated rather than hidden:
    production is Linux and always takes the descriptor.
    """
    if os.name != "posix":
        return None
    return handle if isinstance(handle, int) and not isinstance(handle, bool) else None


# --------------------------------------------------------------------------- #
# Operations
# --------------------------------------------------------------------------- #


def _staging_root(base_path: Path, run_id: str, node_id: str) -> Path:
    """The worker's private staging dir. Created by the PARENT, never by the
    jail, and never inside a lease."""
    safe_node = "".join(c for c in node_id if c.isalnum() or c in "-_") or "node"
    safe_run = "".join(c for c in str(run_id) if c.isalnum() or c in "-_") or "run"
    staging = base_path / ".workspace-staging" / safe_run / safe_node
    staging.mkdir(parents=True, exist_ok=True)
    return staging


def _pool_db(base_path: Path) -> Path:
    from tinyassets import runs

    return runs.runs_db_path(base_path)


def _checkout(
    *,
    packet: dict[str, Any],
    node_id: str,
    base_path: Path,
    run_id: str,
    universe_id: str,
    resource: Any,
    chain: Any,
    host: str,
    repo: str,
    execute: Any,
) -> dict[str, Any]:
    from tinyassets import workspace_pool
    from tinyassets.workspace_git import populate_workspace_from_bundle

    owner, name = _split_repo(repo)
    ref = _str_field(packet, "ref") or "HEAD"
    storage = _str_field(packet, "storage") or "scratch"
    if storage not in ("scratch", "universe"):
        raise _Refused("invalid_packet", "packet.storage must be 'scratch' or 'universe'")
    repo_key = repo_key_for(host, owner, name)
    db = _pool_db(base_path)
    data_root = base_path.parent

    # The startup barrier: finish every outbox entry an earlier process left
    # before admitting anything new. Once per process and cheap after that, but
    # a run that is the FIRST thing to touch the runs DB must still not admit
    # past an unreconciled entry.
    try:
        from tinyassets import runs as _runs

        _runs.ensure_workspace_reconciled(base_path)
    except Exception:
        logger.exception("workspace startup reconciliation failed")

    def _admit() -> Any:
        return workspace_pool.admit(
            db,
            universe_id=universe_id,
            connection_id=str(getattr(resource, "connection_id", "")),
            repo_key=repo_key,
            storage_class=storage,
            run_id=str(run_id),
            max_bytes=int(packet.get("max_bytes") or _DEFAULT_MAX_CHECKOUT_BYTES),
            pool_root=data_root / "scratch",
            universe_root=base_path / "workspaces",
            **_universe_quota_kwargs(storage, base_path),
        )

    try:
        lease = _admit()
    except Exception as exc:
        kind = _pool_error_kind(exc)
        if kind not in _SWEEPABLE_REFUSALS:
            raise _Refused(kind, f"workspace not admitted: {_pool_detail(exc)}") from None
        # A lock or a pool slot held by a run that has already finished is
        # owed to the outbox, not genuinely in use. Sweep ONCE and retry ONCE:
        # a loop here would turn a real contention into a stall, and the
        # periodic sweeper is what handles everything this misses.
        try:
            from tinyassets import runs as _runs

            _runs._workspace_sweep_once(base_path, claimant=f"adapter:{run_id}")
        except Exception:
            logger.exception("workspace sweep before retry failed")
            raise _Refused(kind, f"workspace not admitted: {_pool_detail(exc)}") from None
        try:
            lease = _admit()
        except Exception as retry_exc:
            raise _Refused(
                _pool_error_kind(retry_exc),
                f"workspace not admitted: {_pool_detail(retry_exc)}",
            ) from None

    staging = _staging_root(base_path, run_id, node_id)
    answer = execute(
        {
            "op": "checkout",
            "universe_dir": str(base_path),
            "credential_ref": str(getattr(resource, "credential_ref", "")),
            "host": host,
            "owner_repo": repo,
            "ref": ref,
            "staging_dir": str(staging),
        }
    )
    if not answer.get("ok"):
        raise _Refused(
            "workspace_checkout_failed",
            str(answer.get("error") or "checkout failed"),
            stderr_class=str(answer.get("stderr_class") or ""),
        )

    bundle = staging / str(answer.get("bundle_name") or "out.bundle")
    lease_fd = _make_lease_dir(Path(lease.path))
    repo_dir = Path(lease.path) / "repo"
    # The repository directory is created THROUGH the lease handle and its own
    # descriptor is what git is pointed at, so the destination cannot be
    # swapped between creating it and writing into it.
    repo_fd = _make_repo_dir(lease_fd, repo_dir)
    home = staging / "populate-home"
    home.mkdir(parents=True, exist_ok=True)
    checkout_ref = f"tiny/{_universe_short(universe_id)}/checkout"
    try:
        populate_workspace_from_bundle(
            bundle,
            repo_dir,
            str(answer.get("ref_name") or "refs/tiny/export"),
            checkout_ref,
            home_dir=home,
            path=_git_path(),
            dest_fd=_descriptor_or_none(repo_fd),
        )
    except Exception as exc:
        raise _Refused("workspace_checkout_failed", f"workspace could not be populated: {exc}")

    measured = int(answer.get("bytes") or 0)
    try:
        workspace_pool.reconcile_bytes(db, lease.lease_id, measured)
    except Exception:
        logger.exception("workspace byte reconciliation failed for %s", lease.lease_id)

    replaced = None
    if storage == "universe":
        replaced = _publish(db, lease, universe_id=universe_id, repo_key=repo_key, run_id=run_id)

    # The repository's OWN descriptor travels with the mount: the jail binds
    # through it, and the chain closes it at revoke and at settle.
    _register_mount(
        chain,
        node_id,
        lease=lease,
        repo_dir=repo_dir,
        lease_fd=lease_fd,
        repo_fd=repo_fd,
    )

    evidence: dict[str, Any] = {
        "op": "checkout",
        "repo": repo,
        "ref": ref,
        "resolved_sha": str(answer.get("resolved_sha") or ""),
        "bytes": measured,
        "storage": storage,
        "lease_generation": lease.generation,
    }
    if replaced is not None:
        evidence["replaced_generation"] = replaced
    if _str_field(packet, "provision") or packet.get("provision"):
        connection_id = str(getattr(resource, "connection_id", ""))
        if not _check_provision_consent(base_path, host, repo, connection_id):
            # The checkout still completed: provisioning is its own consent.
            evidence["provision"] = "workspace_provision_refused"
            evidence["provision_hint"] = (
                "grant workspace_provision for "
                f"{_consent_destination(CONSENT_PROVISION, repo, connection_id, host)}"
            )
    return evidence


def _universe_quota_kwargs(storage: str, base_path: Path) -> dict[str, Any]:
    if storage != "universe":
        return {}
    from tinyassets import workspace_pool

    return {
        "universe_quota_bytes": int(_DEFAULT_MAX_CHECKOUT_BYTES * 4),
        "universe_used_bytes_fn": lambda _uid: _universe_used_bytes(base_path, workspace_pool),
    }


def _universe_used_bytes(base_path: Path, _pool: Any) -> int:
    """Bytes the universe's permanent workspaces already hold. Called INSIDE
    the admission transaction, so it must not open the pool database."""
    root = base_path / "workspaces"
    if not root.is_dir():
        return 0
    total = 0
    for path in root.rglob("*"):
        try:
            if path.is_file() and not path.is_symlink():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def _publish(db: Path, lease: Any, *, universe_id: str, repo_key: str, run_id: str) -> int | None:
    """Switch the authoritative generation and owe the previous one a discard."""
    from tinyassets import workspace_pool

    conn = workspace_pool._connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        replaced = workspace_pool.publish_generation(
            conn,
            universe_id=universe_id,
            repo_key=repo_key,
            generation=lease.generation,
            path=lease.path,
        )
        if replaced is not None:
            workspace_pool.enqueue_discard(
                conn,
                run_id=str(run_id),
                universe_id=universe_id,
                storage_class="universe",
                repo_key=repo_key,
                generation=replaced,
            )
        conn.commit()
        return replaced
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _push(
    *,
    packet: dict[str, Any],
    node_id: str,
    base_path: Path,
    run_id: str,
    universe_id: str,
    resource: Any,
    chain: Any,
    host: str,
    repo: str,
    execute: Any,
) -> dict[str, Any]:
    commit_sha = _str_field(packet, "commit_sha")
    slug = _str_field(packet, "branch_slug")
    if not commit_sha:
        raise _Refused("invalid_packet", "packet.commit_sha is required for a push")
    if not _SLUG_RE.match(slug) or ".." in slug or slug.endswith(".lock"):
        raise _Refused("invalid_packet", "packet.branch_slug must be a single path-safe segment")
    mount = _resolve_mount(chain, packet, node_id)
    remote_ref = f"refs/heads/tiny/{_universe_short(universe_id)}/{slug}"

    staging = _staging_root(base_path, run_id, node_id)
    destination = staging / "in.bundle"
    relative = f"repo/{_JAIL_EXPORT_DIR}/{commit_sha}.bundle"
    try:
        copied = _fs().copy_regular_file_beneath(
            mount.lease_fd, relative, destination, max_bytes=_MAX_BUNDLE_BYTES
        )
    except Exception as exc:
        raise _Refused(
            "workspace_push_refused", f"the export bundle could not be read: {exc}"
        )

    answer = execute(
        {
            "op": "push",
            "universe_dir": str(base_path),
            "credential_ref": str(getattr(resource, "credential_ref", "")),
            "host": host,
            "owner_repo": repo,
            "remote_ref": remote_ref,
            "commit_sha": commit_sha,
            "bundle_path": str(destination),
            "staging_dir": str(staging),
        }
    )
    if not answer.get("ok"):
        raise _Refused(
            "workspace_push_refused",
            str(answer.get("error") or "push refused"),
            stderr_class=str(answer.get("stderr_class") or ""),
            observed_sha=str(answer.get("observed_sha") or ""),
            remote_ref=remote_ref,
        )
    return {
        "op": "push",
        "repo": repo,
        "remote_ref": remote_ref,
        "sha": commit_sha,
        "bytes": int(answer.get("bytes") or copied or 0),
        "reconciled": bool(answer.get("reconciled")),
    }


def _discard(
    *,
    packet: dict[str, Any],
    node_id: str,
    base_path: Path,
    run_id: str,
    universe_id: str,
    chain: Any,
) -> dict[str, Any]:
    from tinyassets import workspace_pool

    mount = _resolve_mount(chain, packet, node_id)
    # Revoke FIRST: the capability must be gone before the bytes are owed, so
    # nothing can open the workspace between the two.
    _revoke_mount(chain, mount.node_id)
    db = _pool_db(base_path)
    conn = workspace_pool._connect(db)
    try:
        conn.execute("BEGIN IMMEDIATE")
        workspace_pool.enqueue_discard(
            conn,
            run_id=str(run_id),
            universe_id=universe_id,
            storage_class=mount.storage_class,
            lease=mount.lease if mount.storage_class == "scratch" else None,
            repo_key=mount.repo_key,
            generation=mount.generation,
        )
        conn.commit()
    except Exception as exc:
        conn.rollback()
        raise _Refused("workspace_discard_failed", f"discard could not be recorded: {exc}")
    finally:
        conn.close()
    return {
        "op": "discard",
        "repo": mount.repo_key,
        "storage": mount.storage_class,
        "lease_generation": mount.generation,
    }


# --------------------------------------------------------------------------- #
# The chain's workspace registry
# --------------------------------------------------------------------------- #


def _register_mount(
    chain: Any,
    node_id: str,
    *,
    lease: Any,
    repo_dir: Path,
    lease_fd: Any,
    repo_fd: Any = None,
) -> None:
    from tinyassets.effectors import WorkspaceMount

    mount = WorkspaceMount(
        node_id=node_id,
        bind_source=str(repo_dir),
        lease_fd=lease_fd,
        repo_fd=repo_fd,
        lease=lease,
        storage_class=lease.storage_class,
        repo_key=lease.repo_key,
        generation=lease.generation,
    )
    register = getattr(chain, "register_workspace", None)
    if register is None:
        raise _Refused("workspace_checkout_failed", "this run cannot hold a workspace")
    register(node_id, mount)


def _resolve_mount(chain: Any, packet: dict[str, Any], node_id: str) -> Any:
    """The workspace a push/discard names, through the run's effect chain ONLY.

    Never through state and never through ``$ta.ref``: a capability that can be
    named in state is a capability user text can forge.
    """
    target = _str_field(packet, "workspace")
    if not target:
        raise _Refused("invalid_packet", "packet.workspace must name the checkout node")
    # The registry answers "absent" with None under either name; what to DO
    # about absent is the caller's, and an effect adapter's answer is a
    # structured refusal, never a raise into the completion path.
    lookup = getattr(chain, "workspace_mount_or_none", None)
    mount = lookup(target) if lookup is not None else None
    if mount is None:
        raise _Refused(
            "no_matching_packet",
            f"node '{node_id}' names workspace '{target}', which this run does not hold",
        )
    return mount


def _revoke_mount(chain: Any, node_id: str) -> None:
    revoke = getattr(chain, "revoke_workspace", None)
    if revoke is not None:
        revoke(node_id)


# --------------------------------------------------------------------------- #
# Pool error mapping
# --------------------------------------------------------------------------- #

#: The pool already refuses with exactly the D6 kinds, so its code passes
#: through unchanged. Translating it would only be a place for the two
#: vocabularies to drift -- and a mistranslation reads as the wrong advice
#: ("you are over quota" when the truth is "another run holds the lock").
_POOL_KINDS = frozenset(
    {"workspace_busy", "workspace_pool_busy", "workspace_quota_exceeded"}
)

#: Refusals a sweep can clear: a lock or a pool slot still recorded against a
#: run that already finished. A quota is NOT here -- being over budget is not
#: something cleanup fixes, and retrying would just fail twice.
_SWEEPABLE_REFUSALS = frozenset({"workspace_busy", "workspace_pool_busy"})


def _pool_error_kind(exc: Exception) -> str:
    code = str(getattr(exc, "code", "") or "").strip()
    if code in _POOL_KINDS:
        return code
    # An unrecognised refusal is not silently called a quota problem.
    return "workspace_checkout_failed"


def _pool_detail(exc: Exception) -> str:
    detail = str(getattr(exc, "detail", "") or "").strip()
    return detail or f"{type(exc).__name__}"


def _git_path() -> str:
    import shutil

    found = shutil.which("git")
    if not found:
        raise _Refused("workspace_checkout_failed", "git is not available on this host")
    return str(Path(found).parent)


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def run_workspace_effector(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None = None,
    run_id: str = "",
    dry_run: bool | None = None,
    allowed_state_keys: list[str] | set[str] | None = None,
    prior_effects: dict[str, Any] | None = None,
    chain: Any = None,
    execute: Any = None,
) -> dict[str, Any]:
    """Dispatch one ``workspace`` packet. NEVER raises.

    ``chain`` and ``execute`` are injected by tests; in production the chain is
    the run's active :class:`EffectChain` and ``execute`` spawns the worker.
    """
    del allowed_state_keys, prior_effects
    try:
        return _run(
            node_id=node_id,
            output_keys=output_keys,
            run_state=run_state,
            base_path=base_path,
            run_id=run_id,
            dry_run=dry_run,
            chain=chain,
            execute=execute,
        )
    except _Refused as refused:
        return {"error": refused.error, "error_kind": refused.kind, **refused.extra}
    except Exception as exc:  # noqa: BLE001 - never raise from the completion path
        logger.exception("workspace effector crashed for node %s", node_id)
        return {"error": f"effector crashed: {exc}", "error_kind": "effector_crashed"}


def _run(
    *,
    node_id: str,
    output_keys: list[str],
    run_state: dict[str, Any],
    base_path: str | Path | None,
    run_id: str,
    dry_run: bool | None,
    chain: Any,
    execute: Any,
) -> dict[str, Any]:
    matched_key, packet = _find_packet(output_keys=output_keys, run_state=run_state)
    if packet is None:
        return {
            "error": (
                f"node '{node_id}' declared effects=[{EXTERNAL_WRITE_SINK_WORKSPACE}] but no "
                "output_key held a parseable workspace packet"
            ),
            "error_kind": "no_matching_packet",
        }
    op = _str_field(packet, "op")
    if op not in _CONSENT_FOR_OP:
        raise _Refused("invalid_packet", f"packet.op must be checkout, push or discard: {op!r}")

    repo = _str_field(packet, "repo")
    universe_id = _universe_id(base_path)
    db_path = _ledger_db_path(base_path)
    if not universe_id or db_path is None or base_path is None:
        return {
            "error": "no universe authority is bound to this run",
            "error_kind": "no_universe_authority",
            "matched_output_key": matched_key,
        }
    universe_dir = Path(base_path)
    host = _str_field(packet, "host") or _HOST

    if chain is None:
        from tinyassets.effectors import active_effect_chain

        chain = active_effect_chain(str(run_id))

    if op == "discard":
        if dry_run:
            return {"dry_run": True, "op": op, "reason": "dry_run"}
        return _discard(
            packet=packet,
            node_id=node_id,
            base_path=universe_dir,
            run_id=run_id,
            universe_id=universe_id,
            chain=chain,
        )

    if not repo:
        raise _Refused("invalid_packet", "packet.repo is required")
    _split_repo(repo)
    connection_id = _str_field(packet, "connection_id")
    grant_id = _str_field(packet, "grant_id")
    if not connection_id:
        raise _Refused("invalid_packet", "packet.connection_id is required")
    if not grant_id:
        raise _Refused("invalid_packet", "packet.grant_id is required")

    _grant, resource = _read_connection(
        db_path=db_path,
        connection_id=connection_id,
        universe_id=universe_id,
        grant_id=grant_id,
    )
    _require_scope(resource, op, host, repo)
    _require_consent(universe_dir, op, host, repo, connection_id)

    if dry_run:
        # Describe, never spawn. Every gate above has already run, so a dry run
        # reports the refusal a live run would hit rather than a clean plan.
        return {
            "dry_run": True,
            "op": op,
            "repo": repo,
            "host": host,
            "storage": _str_field(packet, "storage") or "scratch",
            "matched_output_key": matched_key,
        }

    if execute is None:
        from tinyassets.workspace_worker import execute_workspace_operation

        execute = execute_workspace_operation

    common = {
        "packet": packet,
        "node_id": node_id,
        "base_path": universe_dir,
        "run_id": run_id,
        "universe_id": universe_id,
        "resource": resource,
        "chain": chain,
        "host": host,
        "repo": repo,
        "execute": execute,
    }
    evidence = _checkout(**common) if op == "checkout" else _push(**common)
    evidence["matched_output_key"] = matched_key
    return evidence

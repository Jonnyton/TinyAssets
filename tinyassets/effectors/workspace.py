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

import contextlib
import hashlib
import json
import logging
import os
import re
import secrets
import shutil
from pathlib import Path
from typing import Any

from tinyassets.storage.workspace_authority import (
    CONSENT_CHECKOUT,
    CONSENT_PROVISION,
    CONSENT_PUSH,
    GIT_SCOPE_HOST,
    WORKSPACE_SINK,
    GitScopeError,
    connection_allows_git_scopes,
    connection_hosts,
    has_git_scope,
    normalize_repo,
    workspace_consent_destination,
)
from tinyassets.workspace_intents import record_push_intent, settle_push_intent

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

#: (sink, verb) pairs that could NOT have changed the far side. Only a
#: checkout: it reads a repository and changes nothing anywhere.
#:
#: ``discard`` is deliberately NOT here (Codex round 2, #12). It destroys a
#: generation and enqueues an irreversible wipe -- local, but a change, and the
#: settlement asks "could this run have changed anything", not "did it touch
#: the network".
WORKSPACE_READ_EFFECTS = frozenset(
    {(EXTERNAL_WRITE_SINK_WORKSPACE, "checkout")}
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


def scratch_pool_root(universe_dir: Path) -> Path:
    """The shared scratch pool: ``<data>/scratch``, beside the universes.

    Exported because the pool ADMITS against this path and ``runs.py`` CREATES
    against it; two spellings of one directory is a lease admitted in one place
    and written in another.
    """
    return Path(universe_dir).parent / "scratch"


def universe_workspace_root(universe_dir: Path) -> Path:
    """The universe root the pool derives permanent paths FROM.

    ``workspace_pool.universe_paths`` appends ``workspaces/<repo-key>/<gen>``
    itself, so this is the universe directory -- passing
    ``<universe>/workspaces`` here produced ``workspaces/workspaces/...``.
    """
    return Path(universe_dir)


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


def transport_host_for(resource: Any) -> str:
    """The git host this connection may reach, from the STORED connection.

    Never from the packet. The packet used to supply ``host`` while the scope
    check ignored it, so a packet could point a scoped credential at a host the
    owner never allowlisted (Codex round 3, P0 #1). The connection's declared
    endpoints are the authority; a github pipe with no endpoints falls back to
    the one host a git scope is allowed on at all, which
    ``endpoints_allow_git_scopes`` has already agreed to.
    """
    hosts = {host for host in connection_hosts(resource) if host}
    if not hosts:
        if not connection_allows_git_scopes(resource):
            raise _Refused(
                "host_not_allowlisted",
                "the connection declares no host a git scope may reach",
            )
        return GIT_SCOPE_HOST
    if len(hosts) > 1:
        raise _Refused(
            "host_not_allowlisted",
            "the connection declares several hosts; a git transport needs exactly one",
        )
    return hosts.pop()


def _require_packet_host_agrees(packet: dict[str, Any], host: str) -> None:
    """A packet may restate the derived host, never choose a different one."""
    stated = _str_field(packet, "host")
    if stated and stated.lower() != host.lower():
        raise _Refused(
            "invalid_packet",
            "packet.host names a different host than the connection allows",
        )


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


def _close_handles(*handles: Any) -> None:
    """Close whatever descriptors these are, once, never raising.

    Every failure path after a handle is opened comes through here: a lease
    whose descriptors stay open is a lease the outbox cannot reclaim.
    """
    for handle in handles:
        if isinstance(handle, int) and not isinstance(handle, bool):
            try:
                os.close(handle)
            except OSError:
                pass


def _posix_only(exc: NotImplementedError) -> _Refused:
    """The no-follow layer refuses off POSIX; say so as a workspace refusal.

    It is a real, permanent property of the host -- not a crash. Letting a
    ``NotImplementedError`` reach the dispatcher reports ``effector_crashed``,
    which reads as a bug in the sink rather than "this host cannot run
    workspaces at all".
    """
    return _Refused(
        "workspace_checkout_failed",
        f"the workspace sink needs POSIX openat semantics; this host is "
        f"{os.name!r} ({exc})",
    )


@contextlib.contextmanager
def _fs_refusals(what: str):
    """No-follow layer failures while *what* are refusals, never crashes.

    The layer refuses by RAISING: ``UnsafePoolPath`` (an ``OSError``) for a
    link, a traversal, a name it will not create or a directory that is not the
    one it made, and ``ValueError`` for a name that is not one safe component.
    Every one of those means "this run cannot have a workspace", which the
    contract already has a recoverable code for. Letting them reach the
    dispatcher reports ``effector_crashed``, which tells the graph author their
    sink is broken when in fact their checkout was refused -- and that is how
    the generation-directory bug surfaced on Ubuntu CI (run 33355481278).

    ``NotImplementedError`` keeps its own mapping: that one says the HOST
    cannot run workspaces at all, which is a different sentence to write.
    """
    try:
        yield
    except _Refused:
        raise
    except NotImplementedError as exc:
        raise _posix_only(exc) from None
    except (OSError, ValueError) as exc:
        raise _Refused(
            "workspace_checkout_failed",
            f"the workspace directory could not be created ({what}): "
            f"{type(exc).__name__}: {exc}",
        ) from None


def _open_permanent_parent(universe_dir: Path, lease_path: Path) -> Any:
    """Open ``workspaces/<repo-key>``, creating it, and return ITS handle.

    A universe's FIRST permanent checkout has neither directory, and the
    no-follow layer refuses a missing parent -- so without this the first one
    always failed (Codex round 3, P0 #3). Each component is made through the
    handle of the one above it: ``mkdir(parents=True)`` would resolve the whole
    path by name, which is the swap the descriptors exist to prevent.

    The LAST handle is returned rather than closed, so the generation directory
    beneath it is created through a descriptor this process walked open itself
    -- re-opening the parent by path afterwards would hand back the window
    every step above just closed. Every handle above it has done its job and is
    closed here; the caller owns the one it gets.

    Idempotent: an existing component is opened rather than re-created.
    """
    fs = _fs()
    relative = lease_path.parent.relative_to(universe_dir)
    opened: list[Any] = []
    with _fs_refusals(f"opening {relative.as_posix()!r}"):
        try:
            opened.append(fs.open_dir_nofollow(str(universe_dir)))
            for component in relative.parts:
                try:
                    child = fs.create_workspace_subdir(opened[-1], component)
                except FileExistsError:
                    # An already-created component is OPENED through the same
                    # no-follow openat, never re-resolved by path.
                    child = fs.open_subdir_nofollow(opened[-1], component)
                opened.append(child)
        except BaseException:
            _close_handles(*opened)
            raise
    _close_handles(*opened[:-1])
    return opened[-1]


def _make_permanent_generation_dir(universe_dir: Path, lease_path: Path) -> Any:
    """Create ``workspaces/<repo-key>/<generation>`` and return its handle.

    NOT ``create_lease_dir``. That helper's rule -- a name of at least 16
    random hex characters -- is what makes a directory in the SHARED scratch
    pool root untargetable by another universe. A generation is a small integer
    inside this universe's own tree, under a parent this process just walked
    open through its own descriptors, so the rule protects nothing there and
    refuses everything: ``'1'`` is not 16 hex characters, and every permanent
    checkout failed on Linux until this split (Ubuntu CI run 33355481278; the
    Windows double was permissive enough to hide it).

    Same shape as ``<lease>/repo``, and for the same reason.
    """
    parent_fd = _open_permanent_parent(universe_dir, lease_path)
    try:
        with _fs_refusals(f"creating generation {lease_path.name!r}"):
            return _fs().create_workspace_subdir(parent_fd, lease_path.name)
    finally:
        _close_handles(parent_fd)


def _make_scratch_lease_dir(lease_path: Path) -> Any:
    """Create a lease directory in the SHARED pool root, under a no-follow handle.

    This is the one the entropy rule is for: the parent is shared between
    universes, so the name has to be one nobody could have created or targeted
    first. ``create_lease_dir`` enforces that, and this call site is the only
    place it is used.

    The PARENT handle is closed here: it was only needed to create the child
    safely, and leaking one per checkout exhausts the descriptor table on a
    long-lived daemon (Codex round 2, #7).
    """
    fs = _fs()
    with _fs_refusals(f"opening the pool root {lease_path.parent.name!r}"):
        parent_fd = fs.open_dir_nofollow(str(lease_path.parent))
    try:
        with _fs_refusals(f"creating lease {lease_path.name!r}"):
            return fs.create_lease_dir(parent_fd, lease_path.name)
    finally:
        _close_handles(parent_fd)


def _operation_id(run_id: str, node_id: str, op: str) -> str:
    """A DETERMINISTIC id for one ledger operation.

    Deterministic so a retried push charges the hour once: the pool's
    reservation is idempotent per operation id, and a random one would let two
    attempts of the same node bill twice.
    """
    return f"{run_id}:{node_id}:{op}"


def _reserve_operation(
    base_path: Path,
    *,
    universe_id: str,
    run_id: str,
    operation_id: str,
    max_bytes: int,
    refusal: str,
) -> None:
    """Charge the hourly ledger BEFORE the operation moves anything.

    A push and a discard hold no lease, so nothing else charges for them; an
    operation that cannot be admitted must not proceed.
    """
    from tinyassets import workspace_pool

    try:
        workspace_pool.reserve_operation_bytes(
            _pool_db(base_path),
            universe_id=universe_id,
            run_id=str(run_id),
            operation_id=operation_id,
            max_bytes=int(max_bytes),
        )
    except Exception as exc:
        kind = _pool_error_kind(exc)
        raise _Refused(
            kind if kind in _POOL_KINDS else refusal,
            f"the operation was not admitted: {_pool_detail(exc)}",
        ) from None


def _reconcile_operation(base_path: Path, operation_id: str, measured: int) -> None:
    """Settle the reservation down to what actually moved. Never raises: an
    unreconciled operation keeps its maximum, which is the strict side."""
    from tinyassets import workspace_pool

    try:
        workspace_pool.reconcile_operation_bytes(
            _pool_db(base_path), operation_id, max(0, int(measured))
        )
    except Exception:
        logger.exception("could not reconcile operation %s", operation_id)


@contextlib.contextmanager
def _acquired(chain: Any, node_key: str):
    """Hold the capability for the length of ONE use.

    ``acquire_workspace`` hands back a mount holding ``os.dup``s of the
    descriptors, which is what makes this worth doing: a parallel ``discard``
    closes the ORIGINALS, the next checkout opens directories and gets the same
    fd numbers back, and a holder still using them would be reading another
    branch's repository. A dup cannot be reused while it is held.

    ``None`` means never delivered or already revoked, decided inside the
    chain's lock so an acquisition cannot straddle a revoke.
    """
    acquired = chain.acquire_workspace(node_key)
    if acquired is None:
        raise _Refused(
            "no_matching_packet",
            f"the workspace '{node_key}' was revoked before this operation",
        )
    try:
        yield acquired.mount
    finally:
        acquired.release()


def _owe_wipe(base_path: Path, lease: Any, *, run_id: str, universe_id: str) -> None:
    """Enqueue the lease for wipe after a checkout failed past admission.

    Never raises: this runs on a failure path, and losing the ORIGINAL refusal
    to a bookkeeping error would report the wrong problem.
    """
    from tinyassets import workspace_pool

    try:
        conn = workspace_pool._connect(_pool_db(base_path))
        try:
            conn.execute("BEGIN IMMEDIATE")
            workspace_pool.enqueue_discard(
                conn,
                run_id=str(run_id),
                universe_id=universe_id,
                storage_class=getattr(lease, "storage_class", "scratch"),
                lease=lease,
                repo_key=getattr(lease, "repo_key", None),
                generation=getattr(lease, "generation", None),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception:
        logger.exception("could not enqueue the failed checkout's lease for wipe")


def _make_repo_dir(lease_fd: Any, repo_dir: Path) -> Any:
    """Create ``<lease>/repo`` through the lease handle and return ITS handle.

    NOT ``create_lease_dir``: that one is for a name in the SHARED pool root
    and requires an unguessable one, which ``'repo'`` is not. The parent here
    is the private lease directory it just made, so the subdirectory helper is
    the honest call.
    """
    with _fs_refusals(f"creating {repo_dir.name!r} in the lease"):
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


def _staging_id(value: str) -> str:
    """An INJECTIVE, path-safe id for a graph node or run id.

    Stripping unsafe characters is not injective: ``a/b`` and ``ab`` collapse
    to the same name, so two different nodes would share a staging directory
    and a broker socket path (Codex round 3, P2 #11). A digest of the EXACT
    id cannot collide by construction.
    """
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]


def _staging_root(base_path: Path, run_id: str, node_id: str) -> Path:
    """The worker's private staging dir. Created by the PARENT, never by the
    jail, and never inside a lease.

    A per-operation nonce keeps two operations of the SAME node (a checkout
    then a push, or a retry) from sharing a directory a previous one may still
    be tearing down.
    """
    staging = (
        base_path
        / ".workspace-staging"
        / _staging_id(run_id)
        / f"{_staging_id(node_id)}-{secrets.token_hex(4)}"
    )
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

    # The startup barrier: finish every outbox entry an earlier process left
    # before admitting anything new. Once per process and cheap after that, but
    # a run that is the FIRST thing to touch the runs DB must still not admit
    # past an unreconciled entry.
    try:
        from tinyassets import runs as _runs

        _runs.ensure_workspace_reconciled(base_path)
    except Exception as exc:
        # Fail CLOSED. Admitting past a barrier that could not run is admitting
        # on top of whatever an earlier process left owed.
        logger.exception("workspace startup reconciliation failed")
        raise _Refused(
            "workspace_pool_busy",
            f"startup reconciliation failed: {type(exc).__name__}",
        ) from None

    def _admit() -> Any:
        return workspace_pool.admit(
            db,
            universe_id=universe_id,
            connection_id=str(getattr(resource, "connection_id", "")),
            repo_key=repo_key,
            storage_class=storage,
            run_id=str(run_id),
            # The lease bound is the platform's, never the packet's: a
            # packet-chosen reservation is a packet choosing its own quota.
            max_bytes=_DEFAULT_MAX_CHECKOUT_BYTES,
            pool_root=scratch_pool_root(base_path),
            universe_root=universe_workspace_root(base_path),
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

    # ONE owner for everything created after admission (Codex round 3, P1 #7).
    # `owned` holds what this call opened; the mount takes them ONLY after a
    # successful registration, and anything still owned at the end is closed.
    # An unpublished failure also owes the lease a wipe -- a lease nobody holds
    # and nobody wipes is a leak the pool cannot see.
    owned: list[Any] = []
    published = False
    try:
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
        if storage == "universe":
            # A permanent generation lives inside this universe's own tree
            # (whose parents may not exist yet), so it is a SUBDIRECTORY under
            # a handle we walked open -- not a lease in the shared pool root.
            lease_fd = _make_permanent_generation_dir(base_path, Path(lease.path))
        else:
            lease_fd = _make_scratch_lease_dir(Path(lease.path))
        owned.append(lease_fd)
        repo_dir = Path(lease.path) / "repo"
        # The repository directory is created THROUGH the lease handle and its
        # own descriptor is what git is pointed at AND what the jail binds --
        # binding the lease root would put the repository one level down from
        # /workspace.
        repo_fd = _make_repo_dir(lease_fd, repo_dir)
        owned.append(repo_fd)
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
        except _Refused:
            raise
        except Exception as exc:
            raise _Refused(
                "workspace_checkout_failed", f"workspace could not be populated: {exc}"
            ) from None

        # Staging held the credentialed clone, the bundle and the git homes. It
        # is deleted BEFORE the capability is published, and the deletion is
        # CHECKED: a workspace published while staging survives is a workspace
        # published next to the material it was supposed to replace.
        try:
            shutil.rmtree(staging)
            if staging.exists():
                raise OSError(f"{staging} still exists after rmtree")
        except OSError as exc:
            raise _Refused(
                "workspace_checkout_failed",
                f"staging could not be removed, so nothing was published: {exc}",
            ) from None

        measured = int(answer.get("bytes") or 0)
        try:
            workspace_pool.reconcile_bytes(db, lease.lease_id, measured)
        except Exception:
            logger.exception("workspace byte reconciliation failed for %s", lease.lease_id)

        replaced = None
        if storage == "universe":
            replaced = _publish(
                db, lease, universe_id=universe_id, repo_key=repo_key, run_id=run_id
            )

        connection_id = str(getattr(resource, "connection_id", ""))
        mount = _register_mount(
            chain,
            node_id,
            lease=lease,
            repo_dir=repo_dir,
            lease_fd=lease_fd,
            repo_fd=repo_fd,
            host=host,
            repo=repo,
            connection_id=connection_id,
            grant_id=_str_field(packet, "grant_id"),
        )
        # Ownership transfers to the mount ONLY now: from here the chain closes
        # them (on revoke or at settle), and this call must not.
        published = True
        owned.clear()
    finally:
        if not published:
            _close_handles(*owned)
            _owe_wipe(base_path, lease, run_id=run_id, universe_id=universe_id)

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
    if packet.get("provision"):
        # The admission grammar exists (workspace_provision.py) but nothing
        # installs from it yet. Say THAT, not "you lack a consent" -- a hint
        # naming a consent implies granting it would make provisioning run.
        evidence["provision"] = "workspace_provision_refused"
        evidence["provision_detail"] = (
            "provisioning is not available in this release (admission only)"
        )
    del mount
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
    prior_effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    commit_sha = _str_field(packet, "commit_sha")
    slug = _str_field(packet, "branch_slug")
    if not commit_sha:
        raise _Refused("invalid_packet", "packet.commit_sha is required for a push")
    if not _SLUG_RE.match(slug) or ".." in slug or slug.endswith(".lock"):
        raise _Refused("invalid_packet", "packet.branch_slug must be a single path-safe segment")
    mount = _resolve_mount(chain, packet, node_id, prior_effects=prior_effects)
    # The DESTINATION and the AUTHORITY come from the capability, never from
    # the packet: the checkout is what was consented to, and a packet naming a
    # different repository is a packet trying to reuse this credential
    # somewhere else (Codex round 2, #6).
    host = mount.host or host
    repo = mount.repo or repo
    _require_packet_agrees_with_mount(packet, mount)
    resource = _connection_for_mount(base_path, mount, fallback=resource)
    remote_ref = f"refs/heads/tiny/{_universe_short(universe_id)}/{slug}"

    staging = _staging_root(base_path, run_id, node_id)
    destination = staging / "in.bundle"
    relative = f"repo/{_JAIL_EXPORT_DIR}/{commit_sha}.bundle"

    # The hourly ledger sees the push BEFORE any bytes move: a push holds no
    # lease, so without this it charged nothing at all (Codex round 3, P1 #4).
    operation_id = _operation_id(run_id, node_id, "push")
    _reserve_operation(
        base_path,
        universe_id=universe_id,
        run_id=run_id,
        operation_id=operation_id,
        max_bytes=_MAX_BUNDLE_BYTES,
        refusal="workspace_push_refused",
    )

    # Hold the capability across the copy: a discard racing this must not be
    # able to close the descriptor mid-read.
    with _acquired(chain, mount.node_id) as held:
        try:
            copied = _fs().copy_regular_file_beneath(
                held.lease_fd, relative, destination, max_bytes=_MAX_BUNDLE_BYTES
            )
        except NotImplementedError as exc:
            # Same permanent host property, reported against push's own class.
            raise _Refused(
                "workspace_push_refused",
                f"the workspace sink needs POSIX openat semantics; this host is "
                f"{os.name!r} ({exc})",
            ) from None
        except Exception as exc:
            raise _Refused(
                "workspace_push_refused", f"the export bundle could not be read: {exc}"
            )

    intent = record_push_intent(
        base_path,
        run_id=str(run_id),
        node_id=node_id,
        connection_id=mount.connection_id,
        repo=repo,
        remote_ref=remote_ref,
        sha=commit_sha,
        host=host,
        grant_id=mount.grant_id,
        universe_id=universe_id,
        expected_old_sha=_str_field(packet, "expected_old_sha") or None,
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
    # A TIMEOUT is not a failure: the send may have landed. It stays claimable
    # as `unknown` and the startup reconciler asks the remote (P1 #5).
    if answer.get("ok"):
        state = "done"
    elif str(answer.get("stderr_class") or "") == "timeout":
        state = "unknown"
    else:
        state = "failed"
    settle_push_intent(
        base_path, intent, state, observed_sha=str(answer.get("observed_sha") or "") or None
    )
    _reconcile_operation(base_path, operation_id, int(answer.get("bytes") or copied or 0))
    if not answer.get("ok"):
        raise _Refused(
            "workspace_push_refused",
            str(answer.get("error") or "push refused"),
            stderr_class=str(answer.get("stderr_class") or ""),
            observed_sha=str(answer.get("observed_sha") or ""),
            remote_ref=remote_ref,
            intent_state=state,
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
    prior_effects: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from tinyassets import workspace_pool

    mount = _resolve_mount(chain, packet, node_id, prior_effects=prior_effects)
    _require_packet_agrees_with_mount(packet, mount)
    # A discard holds no lease reservation of its own once it starts, so the
    # hourly ledger sees it here -- before anything is mutated.
    _reserve_operation(
        base_path,
        universe_id=universe_id,
        run_id=run_id,
        operation_id=_operation_id(run_id, node_id, "discard"),
        max_bytes=0,
        refusal="workspace_discard_failed",
    )
    # ACQUIRE, then revoke, then owe the bytes. Acquiring first means the facts
    # the outbox entry is built from are read off a capability this call HOLDS,
    # so a parallel discard cannot retire it underneath; revoking inside the
    # hold blocks any new acquisition while the originals stay open until this
    # release, and only then are the bytes owed.
    with _acquired(chain, mount.node_id) as held:
        _revoke_mount(chain, held.node_id or mount.node_id)
        db = _pool_db(base_path)
        conn = workspace_pool._connect(db)
        try:
            conn.execute("BEGIN IMMEDIATE")
            workspace_pool.enqueue_discard(
                conn,
                run_id=str(run_id),
                universe_id=universe_id,
                storage_class=held.storage_class,
                lease=held.lease if held.storage_class == "scratch" else None,
                repo_key=held.repo_key,
                generation=held.generation,
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            raise _Refused(
                "workspace_discard_failed", f"discard could not be recorded: {exc}"
            ) from None
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
    repo_fd: Any,
    host: str,
    repo: str,
    connection_id: str,
    grant_id: str,
) -> Any:
    """Publish the capability, bound to the authority it was created under.

    The bind source is the REPOSITORY's descriptor, not the lease root's:
    ``/workspace`` must BE the repository. The lease handle is kept too,
    because push reads ``repo/.tiny-export/<sha>.bundle``, a path beneath the
    lease rather than beneath the repo.
    """
    from tinyassets.effectors import WorkspaceMount

    descriptor = _descriptor_or_none(repo_fd)
    mount = WorkspaceMount(
        node_id=node_id,
        bind_source=(
            f"/proc/self/fd/{descriptor}" if descriptor is not None else str(repo_dir)
        ),
        pass_fds=(descriptor,) if descriptor is not None else (),
        repo_fd=repo_fd,
        lease_fd=lease_fd,
        lease=lease,
        storage_class=lease.storage_class,
        repo_key=lease.repo_key,
        generation=lease.generation,
        host=host,
        repo=repo,
        connection_id=connection_id,
        grant_id=grant_id,
    )
    register = getattr(chain, "register_workspace", None)
    if register is None:
        raise _Refused("workspace_checkout_failed", "this run cannot hold a workspace")
    register(node_id, mount)
    return mount


def _require_packet_agrees_with_mount(packet: dict[str, Any], mount: Any) -> None:
    """A packet may restate the capability's repo/connection, never change it.

    Silently preferring the mount would be safe but confusing; refusing says
    the packet is wrong about what it is operating on.
    """
    stated_repo = _str_field(packet, "repo")
    if stated_repo and mount.repo:
        try:
            if normalize_repo(stated_repo) != normalize_repo(mount.repo):
                raise _Refused(
                    "invalid_packet",
                    "packet.repo names a different repository than the workspace",
                )
        except GitScopeError:
            raise _Refused("invalid_packet", "packet.repo is not 'owner/name'") from None
    stated_connection = _str_field(packet, "connection_id")
    if stated_connection and mount.connection_id and stated_connection != mount.connection_id:
        raise _Refused(
            "invalid_packet",
            "packet.connection_id names a different connection than the workspace",
        )


def _connection_for_mount(base_path: Path, mount: Any, *, fallback: Any) -> Any:
    """The connection the CHECKOUT ran under, re-read and re-checked.

    Re-read rather than remembered: a connection revoked between the checkout
    and the push must stop the push.
    """
    if not mount.connection_id or not mount.grant_id:
        return fallback
    db_path = _ledger_db_path(base_path)
    if db_path is None:
        return fallback
    _grant, resource = _read_connection(
        db_path=db_path,
        connection_id=mount.connection_id,
        universe_id=_universe_id(base_path),
        grant_id=mount.grant_id,
    )
    return resource


def _resolve_mount(
    chain: Any,
    packet: dict[str, Any],
    node_id: str,
    *,
    prior_effects: dict[str, Any] | None = None,
) -> Any:
    """The workspace a push/discard names, through the run's effect chain ONLY.

    Never through state and never through ``$ta.ref``: a capability that can be
    named in state is a capability user text can forge.

    And it must be an ANCESTOR. The chain is run-global, so without this a node
    on a parallel branch could name a workspace it has no graph relationship
    to; ``prior_effects`` is already the ancestor-scoped view the dispatcher
    hands every adapter (``None`` means no ancestry is known -- legacy
    post-run dispatch -- and is not treated as a refusal).
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
    if prior_effects is not None and target not in prior_effects:
        raise _Refused(
            "no_matching_packet",
            f"node '{node_id}' names workspace '{target}', which is not one of its "
            "graph ancestors",
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
    del allowed_state_keys
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
            prior_effects=prior_effects,
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
    prior_effects: dict[str, Any] | None = None,
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
    host = ""

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
            prior_effects=prior_effects,
        )

    if op == "push":
        # The capability is the authority, so a packet that disagrees with it
        # is refused HERE -- before the connection and scope gates, which would
        # otherwise report the contradiction as "scope not granted" and send
        # the reader looking for a missing grant that is not the problem.
        early = _resolve_mount(chain, packet, node_id, prior_effects=prior_effects)
        _require_packet_agrees_with_mount(packet, early)
        if early.repo:
            repo = early.repo
        if early.host:
            host = early.host

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
    # The credentialed host comes from the STORED connection, not the packet.
    # A packet may restate it; naming a different one is a refusal.
    host = transport_host_for(resource)
    _require_packet_host_agrees(packet, host)
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
        "prior_effects": prior_effects,
    }
    if op == "checkout":
        evidence = _checkout(**{k: v for k, v in common.items() if k != "prior_effects"})
    else:
        evidence = _push(**common)
    evidence["matched_output_key"] = matched_key
    return evidence

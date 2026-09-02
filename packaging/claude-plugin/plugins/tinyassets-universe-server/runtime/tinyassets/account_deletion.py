"""Self-service account deletion.

Google Play requires any app that lets people create an account to offer a
deletion path inside the app AND on a public web page; ``/legal`` promises the
same erasure. ``delete_account`` is that path.

**The row set is derived from the schema, not from a list.** The first draft
carried a hand-written table list, which is the "two definitions of one fact"
failure this repo has paid for repeatedly: ``scoped_reset``'s reviewed inventory
already names 45 root tables, other modules create ~30 more it has never heard
of, and any list would rot at the next migration while silently under-deleting.
So deletion reads the live schema: a table with a ``universe_id`` loses the
deleted universe's rows, a table with one of :data:`PRINCIPAL_KEYS` loses the
deleted person's rows, and the only hand-maintained parts are the short,
reviewable exception sets below — :data:`PRESERVED_TABLES` (commons and ledgers
that are not personal data), :data:`REDACTED_TABLES` (audit rows that survive
without the person or the content) and :data:`BLOCKING_TABLES` (money that is
not ours to discard). A migration that adds a universe- or person-keyed table is
covered the day it lands; ``tests/test_account_deletion.py`` fails if a new
column name means a person's rows would be missed.

**What refuses.** The foreign-ownership and active-work analysis is the operator
path's, reused query for query: another founder bound to the same home, a
foreign grant or foreign-actor row inside it, a live daemon, an open vote, an
in-flight request or task. Those refuse loudly rather than destroying someone
else's rows or racing running work — the platform's one hard invariant is that a
user's action never reaches another user's data. The deliberate divergence is
dependent request rows (``request_admissions``, ``request_admission_events``,
``branch_tasks_v2``): a *reset* preserves them because it keeps the account, a
*deletion* removes the person's own and blocks only on foreign ones, because a
user's own admitted request is their data and leaving it would make "we deleted
your data" false.

**Order.** The home directory is renamed out of the way first (atomic — a crash
leaves a clearly named orphan under ``.deleting/``, never a half-deleted live
universe), then every root-database row in one transaction, then the satellite
databases, then the directory, then billing, then identity. Each phase is
isolated: a failure in one never prevents the next, because the phase that must
not be skipped is the one that stops the money. Anything unfinished is written
to a durable receipt under ``.account-deletions/`` and logged at ERROR — never
swallowed (Hard Rule 8).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import stat
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable

logger = logging.getLogger(__name__)

_WORKOS_USER_ID = re.compile(r"user_[A-Za-z0-9]+\Z")
_WORKOS_BASE_URL = "https://api.workos.com"
_STAGING_DIR = ".deleting"
_RECEIPT_DIR = ".account-deletions"

#: What deletion deliberately leaves behind. The retention sentences on
#: ``/legal`` and ``/account`` say exactly this — change all three together.
RETAINED = (
    "audit records, with the actor replaced by an opaque id and their summary, "
    "target and payload emptied",
    "commons and ledger rows that are not personal data: published author and "
    "branch definitions, goals, and settlement history",
    "invoices held by the payment processor (Stripe)",
    "server backups, until they age out on the configured retention schedule",
)

#: Column names that mean "this row belongs to a person". Applied only to
#: tables that are NOT universe-scoped — see :func:`deletion_plan`.
#:
#: ``created_by`` is deliberately absent: it is authorship attribution, not
#: ownership. Sweeping it would delete the branches and snapshots this person
#: authored inside *someone else's* universe, which is the one thing the
#: platform must never do.
PRINCIPAL_KEYS = (
    "founder_sub",
    "user_id",
    "actor_id",
    "owner_user_id",
    "owner_actor",
    "owner_actor_id",
    "bound_by_actor_id",
    "authorizing_principal_id",
    "principal_id",
    "remixed_by_user_id",
)

#: The universe column. A table carrying it loses the deleted universe's rows —
#: and ONLY those. A person-keyed row inside another universe is that universe's
#: operational state, not this account's to delete.
UNIVERSE_KEY = "universe_id"

#: Universe-scoped tables that ALSO hold a person-keyed row worth removing
#: everywhere: an access grant is this account's access, so deleting the account
#: revokes it wherever it points. Removing it takes nothing from the universe
#: that granted it — only the deleted person's ability to reach it.
PERSON_KEYED_DESPITE_UNIVERSE = MappingProxyType({"universe_acl": "actor_id"})

#: Reached through a parent rather than by their own key, and/or entangled in
#: two-way ON DELETE CASCADE. Deleted explicitly and counted before any of them
#: is touched — see ``_delete_root_rows``.
INDIRECTLY_SCOPED_TABLES = frozenset({
    "branch_heads",
    "vote_ballots",
    "request_admissions",
    "request_admission_events",
    "branch_tasks_v2",
})

#: Not personal data: published commons, provenance, and money already settled.
#: These keep their rows even when they carry a principal column.
PRESERVED_TABLES = frozenset({
    "author_definitions",
    "branch_definitions",
    "goals",
    "goal_canonicals",
    "gate_claims",
    "transaction_log",
    "take_rate_log",
    "payout_wallet",
    "escrow_balance",
    "treasury_balance",
    "settlement_batch",
    "pending_settlement",
    "bounty_pool_balance",
    "royalty_payout",
    "scoped_reset_leases",
    "scoped_reset_operations",
    "deleted_principals",
})

#: Audit rows survive as evidence that something happened, stripped of who did
#: it and what it said — which is what makes the ``/legal`` retention sentence
#: ("content-free audit records keyed by an opaque id") true rather than a hope.
REDACTED_TABLES = frozenset({"action_records"})

#: Money the person is a party to. Refuse the deletion rather than discard it:
#: an unresolved stake is the host's to settle first.
BLOCKING_TABLES = frozenset({"escrow_locks", "staker_escrow_budget"})


class AccountDeletionError(RuntimeError):
    """Deletion refused. The message never carries a secret."""


class AccountDeletionBlocked(AccountDeletionError):
    """Refused because someone else's data, or live work, is in scope."""


def _fingerprint(principal: str) -> str:
    return hashlib.sha256(principal.encode("utf-8")).hexdigest()[:16]


def _rmtree(path: Path) -> None:
    def _onerror(func: Any, target: Any, _exc: Any) -> None:
        os.chmod(target, stat.S_IWRITE)
        func(target)

    try:
        shutil.rmtree(path, onexc=_onerror)  # type: ignore[call-arg]  # 3.12+
    except TypeError:
        shutil.rmtree(path, onerror=_onerror)


def _rmdir_if_empty(path: Path) -> None:
    try:
        path.rmdir()
    except OSError:
        pass  # another deletion is staged in it, or it is already gone


# --------------------------------------------------------------------------- #
# filesystem
# --------------------------------------------------------------------------- #


def _home_dir(root: Path, home: str) -> Path:
    """The home directory inside ``root`` — refuses traversal and odd names."""
    candidate = (root / home).resolve(strict=False)
    if candidate.parent != root or candidate.name != home:
        raise AccountDeletionError("home path escapes the data root")
    return candidate


def _stage_home(root: Path, home: str) -> Path | None:
    """Rename the home directory under ``.deleting/`` (atomic) and return the
    staged path, or None when there is no directory to remove."""
    target = _home_dir(root, home)
    if not target.exists() and not target.is_symlink():
        return None
    if target.is_symlink() or not target.is_dir():
        raise AccountDeletionError("home path is not a plain directory")
    staging = root / _STAGING_DIR
    staging.mkdir(exist_ok=True)
    staged = staging / f"{home}-{int(time.time())}-{secrets.token_hex(4)}"
    target.rename(staged)
    return staged


# --------------------------------------------------------------------------- #
# schema helpers
# --------------------------------------------------------------------------- #


def _tables(conn: sqlite3.Connection) -> list[str]:
    return sorted(
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        if not str(row[0]).startswith("sqlite_")
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _count(conn: sqlite3.Connection, sql: str, params: tuple[Any, ...]) -> int:
    row = conn.execute(sql, params).fetchone()
    return int(row[0]) if row else 0


def _delete(
    conn: sqlite3.Connection,
    counts: dict[str, int],
    table: str,
    where: str,
    params: tuple[Any, ...],
) -> None:
    deleted = conn.execute(f'DELETE FROM "{table}" WHERE {where}', params).rowcount
    if deleted:
        counts[table] = counts.get(table, 0) + int(deleted)


def deletion_plan(
    conn: sqlite3.Connection, *, principal: str, home: str
) -> dict[str, list[tuple[str, str]]]:
    """What the schema says belongs to this account: ``{table: [(column, kind)]}``
    with kind ``universe`` or ``principal``. Read-only; the same function the
    tests read, so what is asserted is what runs."""
    plan: dict[str, list[tuple[str, str]]] = {}
    for table in _tables(conn):
        if table in PRESERVED_TABLES or table in REDACTED_TABLES:
            continue
        if table in INDIRECTLY_SCOPED_TABLES:
            continue  # deleted through its parent, by home only
        cols = _columns(conn, table)
        if UNIVERSE_KEY in cols:
            # Universe-scoped: this account owns only its own universe's rows.
            # Its rows in someone else's universe stay with that universe.
            matched = []
            if home:
                matched.append((UNIVERSE_KEY, "universe"))
            extra = PERSON_KEYED_DESPITE_UNIVERSE.get(table)
            if extra and extra in cols:
                matched.append((extra, "principal"))
            if matched:
                plan[table] = matched
            continue
        matched = [(key, "principal") for key in PRINCIPAL_KEYS if key in cols]
        if matched:
            plan[table] = matched
    return plan


# --------------------------------------------------------------------------- #
# what refuses
# --------------------------------------------------------------------------- #


def deletion_blockers(
    conn: sqlite3.Connection, *, principal: str, home: str
) -> list[str]:
    """Reasons this account may not be deleted right now.

    Foreign-ownership and active-work analysis reuses the operator path's
    queries (``scoped_reset._inspect_database``) so the two agree about whose
    rows are whose and about what "still running" means.
    """
    from tinyassets.scoped_reset import (
        _ACTIVE_DAEMON_STATES,
        _ACTIVE_REQUEST_STATES,
        _ACTIVE_ROLLOUT_STATES,
        _ACTIVE_TASK_STATES,
    )

    blockers: list[str] = []
    tables = set(_tables(conn))

    for table in sorted(BLOCKING_TABLES & tables):
        cols = _columns(conn, table)
        for key in PRINCIPAL_KEYS + ("staker_id",):
            if key in cols and _count(
                conn, f'SELECT COUNT(*) FROM "{table}" WHERE "{key}" = ?', (principal,)
            ):
                blockers.append(f"unsettled financial state in {table}")
                break

    if not home:
        return blockers

    checks = (
        ("another founder is bound to this universe",
         "SELECT COUNT(*) FROM founder_home WHERE universe_id = ? AND founder_sub <> ?",
         (home, principal)),
        ("another person holds access to this universe",
         "SELECT COUNT(*) FROM universe_acl WHERE universe_id = ? AND actor_id <> ?",
         (home, principal)),
        ("another person's requests live in this universe",
         "SELECT COUNT(*) FROM user_requests WHERE universe_id = ? AND user_id <> ?",
         (home, principal)),
        ("another person authored branches here",
         "SELECT COUNT(*) FROM branches WHERE universe_id = ? "
         "AND created_by NOT IN (?, 'system')",
         (home, principal)),
        ("another person authored snapshots here",
         "SELECT COUNT(*) FROM universe_snapshots WHERE universe_id = ? "
         "AND created_by NOT IN (?, 'system')",
         (home, principal)),
        ("another person opened votes here",
         "SELECT COUNT(*) FROM vote_windows WHERE universe_id = ? "
         "AND created_by NOT IN (?, 'system')",
         (home, principal)),
        ("another person cast ballots here",
         "SELECT COUNT(*) FROM vote_ballots AS ballot "
         "JOIN vote_windows AS vote ON vote.vote_id = ballot.vote_id "
         "WHERE vote.universe_id = ? AND ballot.user_id <> ?",
         (home, principal)),
        ("another person's admitted work depends on requests here",
         "SELECT COUNT(*) FROM request_admissions AS dep "
         "JOIN user_requests AS request ON request.request_id = dep.request_id "
         "WHERE request.universe_id = ? AND request.user_id <> ?",
         (home, principal)),
        ("another person's tasks depend on requests here",
         "SELECT COUNT(*) FROM branch_tasks_v2 AS dep "
         "JOIN user_requests AS request ON request.request_id = dep.request_id "
         "WHERE request.universe_id = ? AND request.user_id <> ?",
         (home, principal)),
        ("a daemon is still running for this universe",
         "SELECT COUNT(*) FROM author_runtime_instances WHERE universe_id = ? "
         f"AND lower(status) IN ({','.join('?' for _ in _ACTIVE_DAEMON_STATES)})",
         (home, *sorted(_ACTIVE_DAEMON_STATES))),
        ("a request is still in flight",
         "SELECT COUNT(*) FROM user_requests WHERE universe_id = ? "
         f"AND lower(status) IN ({','.join('?' for _ in _ACTIVE_REQUEST_STATES)})",
         (home, *sorted(_ACTIVE_REQUEST_STATES))),
        ("a vote is still open",
         "SELECT COUNT(*) FROM vote_windows WHERE universe_id = ? "
         "AND lower(status) = 'open'",
         (home,)),
        ("a task is still in flight",
         "SELECT COUNT(*) FROM branch_tasks_v2 WHERE universe_id = ? "
         f"AND lower(status) IN ({','.join('?' for _ in _ACTIVE_TASK_STATES)})",
         (home, *sorted(_ACTIVE_TASK_STATES))),
        ("a rollout is still active",
         "SELECT COUNT(*) FROM request_admission_rollouts WHERE universe_id = ? "
         f"AND lower(state) IN ({','.join('?' for _ in _ACTIVE_ROLLOUT_STATES)})",
         (home, *sorted(_ACTIVE_ROLLOUT_STATES))),
    )
    for reason, sql, params in checks:
        table = sql.split(" FROM ")[1].split()[0]
        if table not in tables:
            continue
        try:
            if _count(conn, sql, params):
                blockers.append(reason)
        except sqlite3.OperationalError:
            # A renamed column must fail loudly, not read as "nothing matched".
            blockers.append(f"cannot evaluate {table} — schema changed")
    return blockers


# --------------------------------------------------------------------------- #
# the row work
# --------------------------------------------------------------------------- #


def _delete_root_rows(
    conn: sqlite3.Connection, *, principal: str, home: str, counts: dict[str, int]
) -> None:
    tables = set(_tables(conn))
    fingerprint = _fingerprint(principal)

    # Dependents first. Queue Epoch 2 rows cascade in BOTH directions —
    # deleting a request takes its tasks, deleting a task takes its admission —
    # so a plain delete-and-count reports whichever one it happened to reach
    # first and silently under-reports the rest. Count every entangled table
    # BEFORE touching any of them, then delete: the receipt has to say what
    # actually went, or "we deleted your data" is unverifiable.
    explicit = (
        ("request_admission_events",
         "request_id IN (SELECT request_id FROM user_requests WHERE universe_id = ?)"),
        ("request_admissions",
         "request_id IN (SELECT request_id FROM user_requests WHERE universe_id = ?)"),
        ("branch_tasks_v2", "universe_id = ?"),
        ("branch_heads",
         "branch_id IN (SELECT branch_id FROM branches WHERE universe_id = ?)"),
        ("vote_ballots",
         "vote_id IN (SELECT vote_id FROM vote_windows WHERE universe_id = ?)"),
    )
    if home:
        present = [(t, w) for t, w in explicit if t in tables]
        for table, where in present:
            found = _count(conn, f'SELECT COUNT(*) FROM "{table}" WHERE {where}', (home,))
            if found:
                counts[table] = counts.get(table, 0) + found
        for table, where in present:
            conn.execute(f'DELETE FROM "{table}" WHERE {where}', (home,))

    for table, keys in deletion_plan(conn, principal=principal, home=home).items():
        for column, kind in keys:
            value = home if kind == "universe" else principal
            _delete(conn, counts, table, f'"{column}" = ?', (value,))

    # Audit rows survive, stripped of the person and the content. This is what
    # makes the retention sentence on /legal true rather than aspirational.
    if "action_records" in tables:
        cols = _columns(conn, "action_records")
        sets: list[str] = []
        set_params: list[Any] = []
        if "actor_id" in cols:
            sets.append("actor_id = ?")
            set_params.append(f"deleted:{fingerprint}")
        for blanked in ("summary", "target_id"):
            if blanked in cols:
                sets.append(f"{blanked} = ''")
        if "payload_json" in cols:
            sets.append("payload_json = '{}'")
        where: list[str] = []
        where_params: list[Any] = []
        if "actor_id" in cols:
            where.append("actor_id = ?")
            where_params.append(principal)
        if home and UNIVERSE_KEY in cols:
            where.append("universe_id = ?")
            where_params.append(home)
        if sets and where:
            redacted = conn.execute(
                f"UPDATE action_records SET {', '.join(sets)} "
                f"WHERE {' OR '.join(where)}",
                (*set_params, *where_params),
            ).rowcount
            if redacted:
                counts["action_records (redacted)"] = int(redacted)

    if "deleted_principals" in tables:
        conn.execute(
            "INSERT INTO deleted_principals (founder_sub, deleted_at) VALUES (?, ?) "
            "ON CONFLICT(founder_sub) DO UPDATE SET deleted_at = excluded.deleted_at",
            (principal, time.time()),
        )


def _delete_satellite_rows(
    path: Path, *, principal: str, home: str, counts: dict[str, int], label: str
) -> None:
    """Apply the same schema-derived rule to a database beside the root one
    (``outbound.db``, ``.auth.db``): universe-keyed and person-keyed rows go."""
    if not path.is_file():
        return
    conn = sqlite3.connect(str(path), timeout=30.0)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA foreign_keys = ON")
        local: dict[str, int] = {}
        with conn:
            plan = deletion_plan(conn, principal=principal, home=home)
            # Child rows whose own columns name neither the person nor the
            # universe, but whose parent is going.
            if "outbound_connector_artifact_edges" in plan or (
                "outbound_connector_artifacts" in plan
            ):
                for side in ("parent_artifact_id", "child_artifact_id"):
                    try:
                        _delete(
                            conn, local, "outbound_connector_artifact_edges",
                            f"{side} IN (SELECT artifact_id FROM "
                            "outbound_connector_artifacts WHERE owner_user_id = ?)",
                            (principal,),
                        )
                    except sqlite3.OperationalError:
                        break
            for table, keys in plan.items():
                for column, kind in keys:
                    value = home if kind == "universe" else principal
                    _delete(conn, local, table, f'"{column}" = ?', (value,))
        for table, n in local.items():
            counts[f"{label}:{table}"] = counts.get(f"{label}:{table}", 0) + n
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# billing + identity (injectable; defaults talk to Stripe and WorkOS)
# --------------------------------------------------------------------------- #


def cancel_stripe_billing(home: str) -> str:
    """Cancel the home's subscription NOW. Returns ``cancelled`` / ``none`` /
    ``not_configured`` / ``unavailable``; raises on a Stripe failure."""
    from tinyassets.billing import BillingUnavailable
    from tinyassets.billing.stripe_adapter import (
        billing_enabled,
        cancel_subscription,
        find_active_subscription,
    )

    if not home or not billing_enabled():
        return "not_configured"
    try:
        subscription_id = find_active_subscription(home)
    except BillingUnavailable:
        return "unavailable"
    if not subscription_id:
        return "none"
    cancel_subscription(subscription_id, immediately=True)
    return "cancelled"


def delete_workos_user(
    user_id: str, *, request: Callable[..., Any] | None = None
) -> str:
    """Delete the WorkOS user record — which is also what ends sessions this
    process cannot enumerate: another device's refresh handle is opaque here, so
    upstream deletion, not local sweeping, is what stops it renewing. Returns
    ``deleted`` / ``not_configured`` / ``not_applicable``; raises
    :class:`AccountDeletionError` (secret-free) on an API failure."""
    api_key = os.environ.get("WORKOS_API_KEY", "").strip()
    if not api_key:
        return "not_configured"
    if _WORKOS_USER_ID.fullmatch(user_id) is None:
        return "not_applicable"
    req = urllib.request.Request(
        f"{_WORKOS_BASE_URL}/user_management/users/{urllib.parse.quote(user_id, safe='')}",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
            "User-Agent": "tinyassets-account-deletion/1.0",
        },
        method="DELETE",
    )
    opener = request or urllib.request.urlopen
    try:
        with opener(req, timeout=20) as response:
            status = int(getattr(response, "status", 200) or 200)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return "deleted"  # already gone — the outcome the caller wanted
        raise AccountDeletionError(
            f"WorkOS user deletion failed (HTTP {exc.code})"
        ) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AccountDeletionError("WorkOS user deletion request failed") from None
    if status in (200, 202, 204):
        return "deleted"
    raise AccountDeletionError(f"WorkOS user deletion returned HTTP {status}")


# --------------------------------------------------------------------------- #
# the operation
# --------------------------------------------------------------------------- #


def _write_unfinished_receipt(root: Path, receipt: dict[str, Any]) -> str:
    """Persist a receipt for a deletion that did not finish every phase, so the
    host can complete it. Content-free: a fingerprint, never a principal."""
    try:
        directory = root / _RECEIPT_DIR
        directory.mkdir(exist_ok=True)
        path = directory / f"{receipt['principal_fingerprint']}-{int(time.time())}.json"
        path.write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
        return str(path)
    except OSError as exc:  # the log is then the only record, and it is loud
        logger.error(
            "account deletion %s: could not write the unfinished-work receipt: %s",
            receipt.get("principal_fingerprint"), exc.__class__.__name__,
        )
        return ""


def pending_deletions(base_path: str | Path) -> list[dict[str, Any]]:
    """Receipts for deletions that left a phase unfinished (host-facing)."""
    directory = Path(base_path) / _RECEIPT_DIR
    if not directory.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        try:
            out.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return out


def delete_account(
    base_path: str | Path,
    *,
    founder_sub: str,
    cancel_billing: Callable[[str], str] | None = None,
    delete_identity: Callable[[str], str] | None = None,
) -> dict[str, Any]:
    """Delete everything the platform holds for ``founder_sub`` and return a
    content-free receipt.

    Raises :class:`AccountDeletionError` before changing anything when the
    principal is empty/anonymous or the bound home path is unsafe, and
    :class:`AccountDeletionBlocked` when someone else's data or live work is in
    scope. Once the home directory has been staged the account is gone; each
    later phase runs independently, so a failure in one never stops the phase
    that cancels the money, and anything unfinished lands in a durable receipt.
    """
    from tinyassets.daemon_server import _connect, get_founder_home, initialize_author_server

    principal = (founder_sub or "").strip()
    if not principal or principal == "anonymous":
        raise AccountDeletionError("no authenticated principal to delete")
    root = Path(base_path).resolve(strict=False)
    fingerprint = _fingerprint(principal)
    counts: dict[str, int] = {}

    initialize_author_server(root)
    home = get_founder_home(root, principal) or ""
    if home:
        _home_dir(root, home)  # refuse an unsafe binding before touching anything

    with _connect(root) as conn:
        blockers = deletion_blockers(conn, principal=principal, home=home)
    if blockers:
        raise AccountDeletionBlocked("; ".join(blockers))

    staged = _stage_home(root, home) if home else None
    failures: list[str] = []

    def _phase(name: str, run: Callable[[], Any]) -> Any:
        try:
            return run()
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            failures.append(name)
            logger.error(
                "account deletion %s: phase %s failed: %s",
                fingerprint, name, exc.__class__.__name__,
            )
            return None

    def _root_rows() -> None:
        with _connect(root) as conn:
            _delete_root_rows(conn, principal=principal, home=home, counts=counts)

    _phase("root_rows", _root_rows)
    for label, filename in (("outbound", "outbound.db"), ("auth", ".auth.db")):
        _phase(
            label,
            lambda f=filename, la=label: _delete_satellite_rows(
                root / f, principal=principal, home=home, counts=counts, label=la
            ),
        )

    home_removed = staged is None
    staged_path = ""
    if staged is not None:
        def _remove() -> None:
            nonlocal home_removed
            _rmtree(staged)
            home_removed = True
            _rmdir_if_empty(staged.parent)

        _phase("home_directory", _remove)
        if not home_removed:
            staged_path = str(staged)

    billing = "not_configured"
    if home:
        billing = _phase(
            "billing", lambda: (cancel_billing or cancel_stripe_billing)(home)
        ) or "error"
    identity = _phase(
        "identity", lambda: (delete_identity or delete_workos_user)(principal)
    ) or "error"

    receipt: dict[str, Any] = {
        "principal_fingerprint": fingerprint,
        "home_id": home,
        "home_removed": home_removed,
        "home_staged_path": staged_path,
        "rows_deleted": dict(sorted(counts.items())),
        "billing": billing,
        "identity": identity,
        "unfinished_phases": sorted(failures),
        "retained": list(RETAINED),
    }
    if failures:
        receipt["host_receipt_path"] = _write_unfinished_receipt(root, receipt)
    logger.info(
        "account deleted %s: home=%s removed=%s rows=%s billing=%s identity=%s unfinished=%s",
        fingerprint, bool(home), home_removed, sum(counts.values()),
        billing, identity, sorted(failures),
    )
    return receipt


__all__ = [
    "BLOCKING_TABLES",
    "PRESERVED_TABLES",
    "PRINCIPAL_KEYS",
    "REDACTED_TABLES",
    "RETAINED",
    "AccountDeletionBlocked",
    "AccountDeletionError",
    "cancel_stripe_billing",
    "delete_account",
    "deletion_blockers",
    "deletion_plan",
    "delete_workos_user",
    "pending_deletions",
]

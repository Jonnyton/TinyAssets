"""Self-service account deletion.

Google Play requires any app that lets people create an account to offer a
deletion path inside the app AND on a public web page; ``/legal`` promises the
same erasure. ``delete_account`` is that path. It is a runtime, per-request
operation for the signed-in principal only — unlike ``scoped_reset``, which is
the host-operator's offline, roster-gated, reviewed-plan tool — but it deletes
the same reviewed set of rows, so the two never disagree about what a home is.

One account on this platform (as built, 2026-09-02) is:

* the ``founder_home`` binding (WorkOS ``sub`` -> home universe id) in the root
  ``.tinyassets.db``;
* the home universe directory under the data root — soul, memory, conversation
  history, the credential vault and every per-universe store (``.runs.db``,
  ``.idempotency.db``, ``.subscription_state.db``, ``knowledge.db`` ...);
* root-db rows keyed by that home (universes, rules, notes, work targets, hard
  priorities, snapshots, branches + heads, user requests, vote windows +
  ballots, webhook hooks/admissions/inflight) and ``universe_acl`` grants keyed
  by the principal;
* outbound connections, grants and connector artifacts the principal owns
  (root-level ``outbound.db``);
* daemon-issued OAuth tokens and codes keyed by the principal (``.auth.db``);
* the Stripe subscription bound to the home — cancelled immediately, not at
  period end, because a deleted account must not keep billing;
* the WorkOS user record itself, deleted through the management API when
  ``WORKOS_API_KEY`` is configured.

Kept on purpose, and said so on ``/legal``: ``action_records`` and the other
audit/provenance rows keyed by an opaque actor or universe id; Stripe's own
invoices; the nightly backups until they rotate out.

Order matters. The home directory is renamed out of the way FIRST (atomic — a
crash leaves a clearly named orphan under ``.deleting/``, never a half-deleted
live universe), then every database row goes in one transaction, then the
staged directory is removed, then billing, then identity. A failure in the last
three steps is written into the receipt and logged at ERROR — never swallowed
(Hard Rule 8) — while the account itself is already unreachable.
"""

from __future__ import annotations

import hashlib
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
from typing import Any, Callable

logger = logging.getLogger(__name__)

_WORKOS_USER_ID = re.compile(r"user_[A-Za-z0-9]+\Z")
_WORKOS_BASE_URL = "https://api.workos.com"
_STAGING_DIR = ".deleting"

#: What deletion deliberately leaves behind. Mirrors the retention sentence on
#: ``/legal`` — change both together.
RETAINED = (
    "audit and provenance records keyed by an opaque actor or universe id",
    "invoices held by the payment processor (Stripe)",
    "nightly backups, until they rotate out on their retention schedule",
)

# Root-db tables keyed by the home universe, in delete order (children first).
# The first two are keyed through their parent; the rest carry ``universe_id``.
_HOME_TABLES = (
    "universe_hard_priorities",
    "universe_notes",
    "universe_work_targets",
    "universe_snapshots",
    "user_requests",
    "branches",
    "vote_windows",
    "webhook_inflight",
    "webhook_admissions",
    "webhook_hooks",
    "universe_acl",
    "universe_rules",
    "universes",
)


class AccountDeletionError(RuntimeError):
    """Deletion refused or a step failed. The message never carries a secret."""


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


# --------------------------------------------------------------------------- #
# filesystem
# --------------------------------------------------------------------------- #


def _home_dir(root: Path, home: str) -> Path:
    """The home directory inside ``root`` — refuses traversal, links and non-dirs."""
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
# databases
# --------------------------------------------------------------------------- #


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
    }


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _delete(
    conn: sqlite3.Connection,
    counts: dict[str, int],
    tables: set[str],
    table: str,
    where: str,
    params: tuple[Any, ...],
) -> None:
    if table not in tables:
        return
    deleted = conn.execute(f'DELETE FROM "{table}" WHERE {where}', params).rowcount
    if deleted:
        counts[table] = counts.get(table, 0) + int(deleted)


def _delete_root_rows(
    conn: sqlite3.Connection, *, principal: str, home: str, counts: dict[str, int]
) -> None:
    tables = _tables(conn)
    if home:
        _delete(
            conn, counts, tables, "branch_heads",
            "branch_id IN (SELECT branch_id FROM branches WHERE universe_id = ?)", (home,),
        )
        _delete(
            conn, counts, tables, "vote_ballots",
            "vote_id IN (SELECT vote_id FROM vote_windows WHERE universe_id = ?)", (home,),
        )
        for table in _HOME_TABLES:
            _delete(conn, counts, tables, table, "universe_id = ?", (home,))
    # The principal's own rows outside their home: ballots and requests they
    # cast elsewhere are their personal data; grants on other universes are
    # theirs to lose; the binding row is the account itself.
    _delete(conn, counts, tables, "vote_ballots", "user_id = ?", (principal,))
    _delete(conn, counts, tables, "user_requests", "user_id = ?", (principal,))
    _delete(conn, counts, tables, "universe_acl", "actor_id = ?", (principal,))
    _delete(conn, counts, tables, "founder_home", "founder_sub = ?", (principal,))


def _delete_outbound_rows(root: Path, *, principal: str, home: str, counts: dict[str, int]) -> None:
    path = root / "outbound.db"
    if not path.is_file():
        return
    conn = sqlite3.connect(str(path), timeout=30.0)
    try:
        conn.execute("PRAGMA busy_timeout = 30000")
        tables = _tables(conn)
        with conn:
            _delete(
                conn, counts, tables, "outbound_connector_artifact_edges",
                "remixed_by_user_id = ? OR parent_artifact_id IN "
                "(SELECT artifact_id FROM outbound_connector_artifacts WHERE owner_user_id = ?)"
                " OR child_artifact_id IN "
                "(SELECT artifact_id FROM outbound_connector_artifacts WHERE owner_user_id = ?)",
                (principal, principal, principal),
            )
            _delete(
                conn, counts, tables, "outbound_connector_artifacts",
                "owner_user_id = ?", (principal,),
            )
            grant_where = (
                "owner_user_id = ? OR connection_id IN "
                "(SELECT connection_id FROM outbound_connections WHERE owner_user_id = ?)"
            )
            grant_params: tuple[Any, ...] = (principal, principal)
            if home:
                grant_where += " OR universe_id = ?"
                grant_params += (home,)
            _delete(
                conn, counts, tables, "outbound_connection_grants", grant_where, grant_params,
            )
            _delete(conn, counts, tables, "outbound_connections", "owner_user_id = ?", (principal,))
    finally:
        conn.close()


def _delete_auth_rows(root: Path, *, principal: str, counts: dict[str, int]) -> None:
    """Every row in the daemon's own OAuth store keyed by this user (tokens,
    codes, and any table a migration adds with a ``user_id`` column)."""
    path = root / ".auth.db"
    if not path.is_file():
        return
    conn = sqlite3.connect(str(path), timeout=10.0)
    try:
        tables = _tables(conn)
        with conn:
            for table in sorted(tables):
                if "user_id" in _columns(conn, table):
                    _delete(conn, counts, tables, table, "user_id = ?", (principal,))
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
    """Delete the WorkOS user record. Returns ``deleted`` / ``not_configured`` /
    ``not_applicable`` (the principal is not a WorkOS user id); raises
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
    principal is empty/anonymous or the bound home path is unsafe. Once the
    home directory has been staged the account is gone; later step failures
    (directory removal, billing, identity) are recorded in the receipt under
    ``home_removed`` / ``billing`` / ``identity`` and logged at ERROR.
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

    staged = _stage_home(root, home) if home else None

    with _connect(root) as conn:
        _delete_root_rows(conn, principal=principal, home=home, counts=counts)
    _delete_outbound_rows(root, principal=principal, home=home, counts=counts)
    _delete_auth_rows(root, principal=principal, counts=counts)

    home_removed = staged is None
    staged_path = ""
    if staged is not None:
        try:
            _rmtree(staged)
            home_removed = True
        except OSError as exc:
            staged_path = str(staged)
            logger.error(
                "account deletion %s: home directory staged but not removed (%s): %s",
                fingerprint, staged, exc.__class__.__name__,
            )

    billing = "not_configured"
    if home:
        try:
            billing = (cancel_billing or cancel_stripe_billing)(home)
        except Exception as exc:  # noqa: BLE001 - reported, never swallowed
            billing = "error"
            logger.error(
                "account deletion %s: billing cancellation failed: %s",
                fingerprint, exc.__class__.__name__,
            )

    try:
        identity = (delete_identity or delete_workos_user)(principal)
    except Exception as exc:  # noqa: BLE001 - reported, never swallowed
        identity = "error"
        logger.error(
            "account deletion %s: identity deletion failed: %s",
            fingerprint, exc.__class__.__name__,
        )

    receipt = {
        "principal_fingerprint": fingerprint,
        "home_id": home,
        "home_removed": home_removed,
        "home_staged_path": staged_path,
        "rows_deleted": dict(sorted(counts.items())),
        "billing": billing,
        "identity": identity,
        "retained": list(RETAINED),
    }
    logger.info(
        "account deleted %s: home=%s removed=%s rows=%s billing=%s identity=%s",
        fingerprint, bool(home), home_removed, sum(counts.values()), billing, identity,
    )
    return receipt


__all__ = [
    "RETAINED",
    "AccountDeletionError",
    "cancel_stripe_billing",
    "delete_account",
    "delete_workos_user",
]

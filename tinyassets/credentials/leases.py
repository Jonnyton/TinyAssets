"""Fenced exclusive per-ref refresh leases + an exclusive mutation lock.

The refresh lease exists to guarantee **exactly one** provider refresh exchange
per ref (the concurrent-refresh CVE class — Better Auth GHSA-392p-2q2v-4372;
rotating-refresh providers revoke the whole token family on replay). A plain
TTL-delete lease is NOT sufficient: when a holder's operation exceeds the TTL a
second holder can steal the lease and overlap. We therefore use **fencing**:

  * every acquire assigns a monotonically increasing fence token per ref;
  * stealing an expired lease bumps the fence, logically evicting the prior
    holder;
  * a holder verifies its fence is still current before the provider call, and
    the commit CAS-checks the fence — a stale holder cannot commit.

So even if two holders briefly overlap, exactly one can commit; the evicted
holder aborts before burning the one-time refresh token.

Functions take an explicit ``sqlite3.Connection`` so the fence check can run in
the SAME transaction as the record write (atomic). ``RefreshLeaseManager`` wraps
a connection factory for acquire/heartbeat/release and provides the exclusive
``mutation_lock`` used by the file-backed local CAS.
"""

from __future__ import annotations

import contextlib
import sqlite3
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass

from .errors import CredentialUnavailable, VaultErrorCode


def require_cas_pairing(replace: str | None, expected_version: int | None) -> None:
    """``replace`` and ``expected_version`` must be supplied together or not at all.

    A replace without a CAS guard silently permits lost updates (v1->v2->v3); an
    expected_version without a replace is a caller mistake. Reject both inverses.
    """
    if replace is not None and expected_version is None:
        raise ValueError("put(replace=...) requires expected_version for a safe CAS")
    if replace is None and expected_version is not None:
        raise ValueError("put(expected_version=...) is only valid with replace=...")


LEASE_SCHEMA = """
CREATE TABLE IF NOT EXISTS vault_refresh_leases (
    ref         TEXT PRIMARY KEY,
    holder      TEXT NOT NULL,
    fence       INTEGER NOT NULL,
    acquired_at REAL NOT NULL,
    expires_at  REAL NOT NULL
);

-- Atomic consume-before-mint: one durable claim per (ref, version). The claim
-- is the exclusive RIGHT to redeem the refresh token of that version at the
-- provider. Only the process that wins the INSERT may call the provider; a
-- crash before the version advances leaves the claim in place (fail closed —
-- the wedged version needs re-authorization, never a second redemption).
CREATE TABLE IF NOT EXISTS vault_refresh_claims (
    ref        TEXT NOT NULL,
    version    INTEGER NOT NULL,
    holder     TEXT NOT NULL,
    claimed_at REAL NOT NULL,
    PRIMARY KEY (ref, version)
);
"""


def claim_refresh(
    conn: sqlite3.Connection, ref: str, version: int, holder: str, now: float
) -> bool:
    """Atomically claim the exclusive right to redeem ``(ref, version)``.

    Returns True iff THIS caller won the claim (may now call the provider). A
    False means the version was already claimed by someone (possibly a crashed
    holder) — the caller MUST NOT call the provider and should re-read the store.
    Must run inside an open transaction.
    """
    try:
        conn.execute(
            "INSERT INTO vault_refresh_claims(ref, version, holder, claimed_at) "
            "VALUES(?,?,?,?)",
            (ref, int(version), holder, now),
        )
    except sqlite3.IntegrityError:
        return False
    return True

def claim_held(conn: sqlite3.Connection, ref: str, version: int, holder: str) -> bool:
    """True iff ``holder`` holds the durable claim for ``(ref, version)``.

    Used to bind a refresh COMPLETION to the ticket: a CAS that completes a
    refresh must present a ticket whose claim is on record — no bypass.
    """
    row = conn.execute(
        "SELECT holder FROM vault_refresh_claims WHERE ref = ? AND version = ?",
        (ref, int(version)),
    ).fetchone()
    return row is not None and row["holder"] == holder


# NOTE: claims are NEVER pruned on advance. Deleting a consumed claim reopens a
# window where a slow straggler that still holds version N as "current" could
# re-claim (ref, N) and redeem T_N a SECOND time — exactly the token-reuse CVE.
# The table grows one row per successful refresh (small, bounded by refresh
# count); a safe long-retention GC of ancient claims is a future operational
# concern, never a same-token deletion.


def acquire_fenced(
    conn: sqlite3.Connection, ref: str, holder: str, ttl: float, now: float
) -> int | None:
    """Acquire the lease for ``ref`` inside an open BEGIN IMMEDIATE transaction.

    Returns the fence token, or ``None`` if a live lease is held by someone else
    (caller should back off and retry). Stealing an EXPIRED lease bumps the
    fence.
    """
    row = conn.execute(
        "SELECT holder, fence, expires_at FROM vault_refresh_leases WHERE ref = ?",
        (ref,),
    ).fetchone()
    if row is None:
        fence = 1
        conn.execute(
            "INSERT INTO vault_refresh_leases(ref, holder, fence, acquired_at, expires_at) "
            "VALUES(?,?,?,?,?)",
            (ref, holder, fence, now, now + ttl),
        )
        return fence
    if float(row["expires_at"]) > now:
        return None  # live lease held by another holder
    fence = int(row["fence"]) + 1  # steal expired lease, evict prior holder
    conn.execute(
        "UPDATE vault_refresh_leases SET holder = ?, fence = ?, acquired_at = ?, "
        "expires_at = ? WHERE ref = ?",
        (holder, fence, now, now + ttl, ref),
    )
    return fence


def verify_fence(
    conn: sqlite3.Connection, ref: str, holder: str, fence: int, now: float
) -> bool:
    """True iff ``holder``'s fenced lease for ``ref`` is still current and live."""
    row = conn.execute(
        "SELECT holder, fence, expires_at FROM vault_refresh_leases WHERE ref = ?",
        (ref,),
    ).fetchone()
    if row is None:
        return False
    return (
        row["holder"] == holder
        and int(row["fence"]) == fence
        and float(row["expires_at"]) > now
    )


def renew_fenced(
    conn: sqlite3.Connection, ref: str, holder: str, fence: int, ttl: float, now: float
) -> bool:
    cur = conn.execute(
        "UPDATE vault_refresh_leases SET expires_at = ? "
        "WHERE ref = ? AND holder = ? AND fence = ? AND expires_at > ?",
        (now + ttl, ref, holder, fence, now),
    )
    return cur.rowcount == 1


def release_fenced(
    conn: sqlite3.Connection, ref: str, holder: str, fence: int
) -> None:
    conn.execute(
        "DELETE FROM vault_refresh_leases WHERE ref = ? AND holder = ? AND fence = ?",
        (ref, holder, fence),
    )


@dataclass(frozen=True)
class RefreshTicket:
    """Proof that the holder won the exclusive right to redeem ``(ref, version)``.

    Returned by ``begin_refresh`` after it atomically authenticated the current
    record and claimed its version. The completion write must CAS on
    ``expected_version == version``.
    """

    ref: str
    version: int
    holder: str


@dataclass
class RefreshLease:
    """A held, fenced refresh lease. Verify + release go through the manager."""

    ref: str
    holder: str
    fence: int
    _manager: "RefreshLeaseManager"

    def still_held(self) -> bool:
        return self._manager._still_held(self.ref, self.holder, self.fence)

    def renew(self, ttl: float = 30.0) -> bool:
        return self._manager._renew(self.ref, self.holder, self.fence, ttl)

    def release(self) -> None:
        self._manager._release(self.ref, self.holder, self.fence)

    def __enter__(self) -> "RefreshLease":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()


class RefreshLeaseManager:
    """Fenced-lease + mutation-lock operations over one control SQLite DB."""

    def __init__(self, connect: Callable[[], sqlite3.Connection]) -> None:
        self._connect = connect

    def ensure_schema(self) -> None:
        conn = self._connect()
        try:
            conn.executescript(LEASE_SCHEMA)
        finally:
            conn.close()

    @contextlib.contextmanager
    def acquire(
        self,
        ref: str,
        holder: str,
        *,
        ttl: float = 30.0,
        wait: float = 30.0,
        poll: float = 0.02,
    ) -> Iterator[RefreshLease]:
        self.ensure_schema()
        deadline = time.monotonic() + wait
        fence: int | None = None
        while True:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
                fence = acquire_fenced(conn, ref, holder, ttl, time.time())
                if fence is not None:
                    conn.execute("COMMIT")
                else:
                    conn.execute("ROLLBACK")
            except BaseException:
                with contextlib.suppress(sqlite3.Error):
                    conn.execute("ROLLBACK")
                raise
            finally:
                conn.close()
            if fence is not None:
                break
            if time.monotonic() >= deadline:
                raise CredentialUnavailable(VaultErrorCode.LEASE_TIMEOUT, ref)
            time.sleep(poll)
        lease = RefreshLease(ref=ref, holder=holder, fence=fence, _manager=self)
        try:
            yield lease
        finally:
            lease.release()

    @contextlib.contextmanager
    def mutation_lock(
        self, *, wait: float = 30.0, poll: float = 0.02
    ) -> Iterator[sqlite3.Connection]:
        """Hold an exclusive DB write lock for an atomic read-check-write.

        Yields the open connection (inside BEGIN IMMEDIATE) so the caller can
        ``verify_fence`` and read/write in the same critical section. Commits on
        clean exit, rolls back on error.
        """
        self.ensure_schema()
        deadline = time.monotonic() + wait
        while True:
            conn = self._connect()
            try:
                conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError:
                conn.close()
                if time.monotonic() >= deadline:
                    raise CredentialUnavailable(VaultErrorCode.LEASE_TIMEOUT) from None
                time.sleep(poll)
                continue
            break
        try:
            yield conn
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # -- RefreshLease callbacks (own connection each) -------------------
    def _still_held(self, ref: str, holder: str, fence: int) -> bool:
        conn = self._connect()
        try:
            return verify_fence(conn, ref, holder, fence, time.time())
        finally:
            conn.close()

    def _renew(self, ref: str, holder: str, fence: int, ttl: float) -> bool:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            ok = renew_fenced(conn, ref, holder, fence, ttl, time.time())
            conn.execute("COMMIT")
            return ok
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    def _release(self, ref: str, holder: str, fence: int) -> None:
        conn = self._connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            release_fenced(conn, ref, holder, fence)
            conn.execute("COMMIT")
        except BaseException:
            with contextlib.suppress(sqlite3.Error):
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

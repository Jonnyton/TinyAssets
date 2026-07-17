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
import hashlib
import hmac
import secrets
import sqlite3
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import NoReturn

from .errors import CredentialUnavailable, VaultErrorCode
from .secret_bytes import SecretBytes

_CAPABILITY_BYTES = 32


def mint_capability() -> bytes:
    """Random unforgeable secret the broker mints for a refresh claim."""
    return secrets.token_bytes(_CAPABILITY_BYTES)


def capability_hash(secret: bytes) -> str:
    return hashlib.sha256(secret).hexdigest()


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

-- Consume-before-mint, HIGH-WATER model: ONE row per ref holding the highest
-- version ever claimed + the hash of an UNFORGEABLE broker-minted capability.
-- A claim for version V succeeds only if V is strictly higher than the stored
-- ``claimed_version`` (monotonic), so a retired (lower) version can NEVER be
-- re-claimed — retirement (advance) can't reopen the re-redeem window, and the
-- table stays bounded to one row per ref (no unbounded growth). Only the caller
-- presenting the exact minted capability (checked against ``capability_hash``)
-- may complete the refresh.
CREATE TABLE IF NOT EXISTS vault_refresh_claims (
    ref             TEXT PRIMARY KEY,
    claimed_version INTEGER NOT NULL,
    capability_hash TEXT NOT NULL,
    holder          TEXT NOT NULL,
    claimed_at      REAL NOT NULL
);
"""


def claim_refresh(
    conn: sqlite3.Connection,
    ref: str,
    version: int,
    holder: str,
    now: float,
    cap_hash: str,
) -> bool:
    """Atomically claim the redemption right for ``ref`` at ``version``.

    Succeeds iff ``version`` is strictly higher than any previously-claimed
    version for this ref (monotonic high-water) — a lower/equal version (a
    straggler or a re-redeem attempt) is refused. On success the single per-ref
    row advances to ``version`` and stores the capability hash. Must run in an
    open transaction.
    """
    row = conn.execute(
        "SELECT claimed_version FROM vault_refresh_claims WHERE ref = ?", (ref,)
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO vault_refresh_claims(ref, claimed_version, capability_hash, "
            "holder, claimed_at) VALUES(?,?,?,?,?)",
            (ref, int(version), cap_hash, holder, now),
        )
        return True
    if int(version) > int(row["claimed_version"]):
        conn.execute(
            "UPDATE vault_refresh_claims SET claimed_version = ?, capability_hash = ?, "
            "holder = ?, claimed_at = ? WHERE ref = ?",
            (int(version), cap_hash, holder, now, ref),
        )
        return True
    return False


def capability_valid(
    conn: sqlite3.Connection, ref: str, version: int, holder: str, secret: bytes
) -> bool:
    """True iff ``secret`` matches the minted capability for ``ref@version``.

    Binds a refresh COMPLETION to the unforgeable minted capability: a
    reconstructed ticket without the exact secret cannot pass. Constant-time
    compare over the stored hash.
    """
    row = conn.execute(
        "SELECT claimed_version, capability_hash, holder FROM vault_refresh_claims "
        "WHERE ref = ?",
        (ref,),
    ).fetchone()
    if row is None:
        return False
    if int(row["claimed_version"]) != int(version) or row["holder"] != holder:
        return False
    return hmac.compare_digest(row["capability_hash"], capability_hash(secret))


def retire_claim(conn: sqlite3.Connection, ref: str) -> None:
    """Drop the claim row for a DELETED ref.

    Safe because a SecretRef is a one-time 256-bit random value that is never
    reused, so freeing the row cannot let a future ref re-redeem an old token.
    Bounds the table; does NOT free a version slot for a live ref (that would
    reopen the re-redeem window — see the high-water invariant).
    """
    conn.execute("DELETE FROM vault_refresh_claims WHERE ref = ?", (ref,))


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


def _refuse(*_a: object, **_k: object) -> NoReturn:
    raise TypeError("RefreshTicket carries a bearer capability and cannot be copied/serialized")


class RefreshTicket:
    """Proof that the holder won the exclusive right to redeem ``ref@version``.

    Returned by ``begin_refresh``. The minted capability is stored in a PRIVATE,
    slotted :class:`SecretBytes` — this is deliberately NOT a dataclass, so
    ``dataclasses.asdict`` and ``vars`` (which bypass ``repr``/``pickle``
    protections) cannot extract it. The capability is usable only via the
    broker's constant-time compare (``_reveal_capability`` is internal); it never
    appears in a repr/str/format, and the object cannot be copied or pickled.
    """

    __slots__ = ("ref", "version", "holder", "_capability")

    def __init__(self, *, ref: str, version: int, holder: str, secret: bytes) -> None:
        self.ref = ref
        self.version = version
        self.holder = holder
        self._capability = SecretBytes(secret)

    def _reveal_capability(self) -> bytes:
        """Internal: the broker reveals the capability only for a hashed compare."""
        return self._capability.reveal()

    def __repr__(self) -> str:
        return f"RefreshTicket(ref={self.ref!r}, capability=<redacted>)"

    __str__ = __repr__

    def __format__(self, _spec: str) -> str:
        return self.__repr__()

    __reduce__ = _refuse
    __reduce_ex__ = _refuse
    __getstate__ = _refuse
    __copy__ = _refuse
    __deepcopy__ = _refuse


@dataclass(repr=False)
class RefreshLease:
    """A held, fenced refresh lease. Verify + release go through the manager.

    ``repr`` redacts holder/fence (internal coordination metadata).
    """

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

    def __repr__(self) -> str:
        return f"RefreshLease(ref={self.ref!r})"

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

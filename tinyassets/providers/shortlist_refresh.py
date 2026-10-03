"""Per-source shortlist cache, warmed off the request path.

A picker read must never wait on discovery. Before this, every read called
``discover_native_models_sync`` inline, per accepted member, so one slow or
expired source delayed selecting a DIFFERENT accepted source and its execution
(``docs/concerns/2026-09-16-model-picker-global-discovery-delay.md``).

Two properties that concern asks for, both structural here rather than tuned:

* **Per-source freshness.** The cache is keyed per
  ``(base, owner, universe, provider)``. One source being cold, stale or
  broken says nothing about any other, because nothing is shared between keys
  except the lock that guards the dict.
* **Discovery isolation.** A read NEVER runs discovery. It takes whatever is
  warm and asks for a refresh in the background. So the slowest source costs
  a dict lookup, not its own latency.

What this deliberately does NOT do: serve stale choices. An entry past
:data:`USABLE_AGE` is withheld and reported as refreshing, because
``NativeDiscoverySnapshot.assert_fresh`` would refuse it at execution anyway —
offering it would be a choice that fails on use, which is worse than a
truthful "not yet". That is also the concern's own warning: this is not solved
by "enabling stale choices globally".

Execution is untouched. ``prepare_selected_model`` still discovers fresh at
launch, with its own custody and freshness checks, so nothing here participates
in an authority decision. This module holds advisory display metadata and a
custody REFERENCE for revalidation, never credential bytes.
"""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path

_LOG = logging.getLogger("universe_server.shortlist_refresh")

#: Oldest entry a read will serve. Under the five minutes
#: ``NativeDiscoverySnapshot.assert_fresh`` allows, so anything handed out has
#: headroom to survive the owner reading it and then choosing.
USABLE_AGE = 150.0

#: How old an entry may get before a read asks for a refresh. Below
#: ``USABLE_AGE`` so the warm window is replaced before it expires rather than
#: after, which is what keeps a read from ever finding nothing but stale.
REFRESH_AGE = 60.0

#: Ceiling on tracked sources. A bound, not a policy: the key space is
#: (owner, universe, provider) and this stops an unbounded dict if something
#: upstream ever enumerates more than a person could have connected.
MAX_TRACKED = 4096

#: One worker, so a slow executor delays only the refresh queue and never a
#: read. Discovery is already bounded at 30s by the transport.
_POOL_SIZE = 2


@dataclass(frozen=True, slots=True)
class _Key:
    base: str
    owner: str
    universe: str
    provider: str


@dataclass(slots=True)
class _Entry:
    snapshot: object | None = None
    #: Monotonic stamp of the last COMPLETED attempt, successful or not. Used
    #: for scheduling only; freshness for use comes from `observed`.
    attempted: float = 0.0
    #: Monotonic stamp of the snapshot currently held.
    observed: float = 0.0
    inflight: bool = False
    #: Why the last attempt failed, as a fixed reason, or "" when it succeeded.
    reason: str = ""


class ShortlistCache:
    """Warm per-source catalogues. Reads are lookups; refreshes are background."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[_Key, _Entry] = {}
        self._pool: ThreadPoolExecutor | None = None
        self._clock = time.monotonic

    # -- reads ----------------------------------------------------------

    def get(self, *, base, owner, universe_id, provider):
        """The warm snapshot for this source, or ``(None, reason)``.

        Never blocks and never discovers. A cold or aged-out entry schedules a
        refresh and reports a truthful pending reason, so the caller can keep
        the source's own default usable while saying the catalogue is not in
        yet -- rather than inventing availability or hanging the read.
        """
        key = _Key(str(base), owner, universe_id, provider)
        now = self._clock()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                if len(self._entries) >= MAX_TRACKED:
                    return None, "catalogue_refresh_unavailable"
                entry = self._entries.setdefault(key, _Entry())
            usable = (entry.snapshot is not None
                      and now - entry.observed <= USABLE_AGE)
            needs = (entry.snapshot is None
                     or now - entry.observed >= REFRESH_AGE)
            reason = entry.reason
        if needs:
            self.schedule(base=base, owner=owner, universe_id=universe_id,
                          provider=provider)
        if usable:
            return entry.snapshot, ""
        # A failed attempt reports ITS reason; a cold one reports pending. The
        # two are different facts and a client should not have to guess which.
        return None, reason or "catalogue_refresh_pending"

    # -- refresh --------------------------------------------------------

    def schedule(self, *, base, owner, universe_id, provider):
        """Queue one background refresh, unless this source already has one."""
        key = _Key(str(base), owner, universe_id, provider)
        with self._lock:
            entry = self._entries.setdefault(key, _Entry())
            if entry.inflight:
                return False
            entry.inflight = True
            if self._pool is None:
                self._pool = ThreadPoolExecutor(
                    max_workers=_POOL_SIZE, thread_name_prefix="shortlist-refresh",
                )
            pool = self._pool
        try:
            pool.submit(self._run, key)
        except RuntimeError:
            # Interpreter shutdown: release the claim so a later process can
            # retry, rather than leaving the source permanently "inflight".
            with self._lock:
                self._entries[key].inflight = False
            return False
        return True

    def refresh_now(self, *, base, owner, universe_id, provider):
        """Synchronous refresh for callers that are already off the request path.

        The on-connect warm uses this; a picker read never does.
        """
        self._run(_Key(str(base), owner, universe_id, provider), claim=True)
        key = _Key(str(base), owner, universe_id, provider)
        with self._lock:
            entry = self._entries.get(key)
            return None if entry is None else entry.snapshot

    def _run(self, key: _Key, *, claim: bool = False) -> None:
        from tinyassets.exceptions import ProviderError
        from tinyassets.providers.native_discovery import discover_native_models_sync

        if claim:
            with self._lock:
                self._entries.setdefault(key, _Entry()).inflight = True
        snapshot, reason = None, ""
        try:
            snapshot = discover_native_models_sync(
                base_path=Path(key.base), owner_user_id=key.owner,
                universe_id=key.universe, provider=key.provider,
            )
            if snapshot is None:
                reason = "native_enumeration_unsupported"
        except ProviderError:
            reason = "native_catalogue_unavailable"
        except Exception as exc:  # noqa: BLE001 - a background thread must not die
            # Never let an unexpected failure kill the worker or leave the
            # source wedged inflight. Logged with its type only: no upstream
            # prose, path or account material reaches a log line.
            _LOG.warning("shortlist refresh failed: %s", type(exc).__name__)
            reason = "catalogue_refresh_unavailable"
        now = self._clock()
        with self._lock:
            entry = self._entries.setdefault(key, _Entry())
            entry.inflight = False
            entry.attempted = now
            entry.reason = reason
            if snapshot is not None:
                entry.snapshot = snapshot
                entry.observed = now
            elif reason:
                # A failure does NOT discard a still-usable warm snapshot: a
                # transient refresh error should not empty a picker that was
                # working a minute ago. It ages out on its own.
                pass

    # -- lifecycle ------------------------------------------------------

    def forget(self, *, base, owner, universe_id, provider=None):
        """Drop cached catalogues for an owner's universe, or one source of it.

        Called when custody changes: a snapshot pins the credential reference
        it was read under, so keeping it across a reconnect would hold a
        catalogue nobody can revalidate.
        """
        base = str(base)
        with self._lock:
            for key in [
                k for k in self._entries
                if k.base == base and k.owner == owner and k.universe == universe_id
                and (provider is None or k.provider == provider)
            ]:
                del self._entries[key]

    def shutdown(self, *, wait: bool = False) -> None:
        with self._lock:
            pool, self._pool = self._pool, None
            self._entries.clear()
        if pool is not None:
            pool.shutdown(wait=wait, cancel_futures=True)

    def stats(self) -> dict:
        """Read-only view for tests and status; never a client payload."""
        with self._lock:
            return {
                "tracked": len(self._entries),
                "warm": sum(1 for e in self._entries.values() if e.snapshot is not None),
                "inflight": sum(1 for e in self._entries.values() if e.inflight),
            }


#: One cache per process. Discovery is per-process work and a snapshot is only
#: valid against the custody this process can still read, so there is nothing
#: to share across processes and no store to keep consistent.
SHORTLIST_CACHE = ShortlistCache()


def warm_connected_shortlists(*, base_path, universe_dir, owner_user_id, universe_id):
    """Warm every native source this owner has deposited, off the request path.

    The on-connect seam. Reads the deposit table rather than taking a provider
    list from a caller, so it can only ever warm sources this owner actually
    connected. Best-effort by contract: a failure here must not affect the
    action that triggered it, and the next picker read schedules its own
    refresh anyway.
    """
    from tinyassets.provider_serving_binding import _PROVIDER_SERVICE
    from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

    try:
        with SQLiteProviderWorkAuthorityStore(base_path).connection() as conn:
            exists = conn.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'llm_credential_deposit_owners'",
            ).fetchone()
            if exists is None:
                return 0
            services = {
                row[0] for row in conn.execute(
                    "SELECT service FROM llm_credential_deposit_owners "
                    "WHERE universe_id = ? AND owner_user_id = ?",
                    (universe_id, owner_user_id),
                ).fetchall()
            }
    except Exception as exc:  # noqa: BLE001 - warming is never the caller's error
        _LOG.warning("shortlist warm skipped: %s", type(exc).__name__)
        return 0
    queued = 0
    for provider, service in _PROVIDER_SERVICE.items():
        if service in services and SHORTLIST_CACHE.schedule(
            base=base_path, owner=owner_user_id, universe_id=universe_id,
            provider=provider,
        ):
            queued += 1
    return queued

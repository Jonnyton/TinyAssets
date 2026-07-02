"""Multi-tenant concurrency + isolation proof (§14 load-test gate).

Host requirement (2026-07-02): "many other users all should be able to make
their own universes ... they all get their own universe tied to them." This is
the deterministic proof of that guarantee, separate from the host-gated live
deploy.

N distinct founders (distinct WorkOS ``sub`` identities, one per token)
concurrently create universes against a SINGLE shared ``TINYASSETS_DATA_DIR``
(one shared ``.tinyassets.db``). We assert:

  * every founder gets a DISTINCT universe serial (no ULID collision, no two
    founders sharing a universe);
  * each founder's ``founder_home`` binding points to the universe THAT founder
    created (no cross-binding);
  * each created universe's ACL grants ``admin`` to exactly its owning founder
    and to no other founder (tenant ownership boundary);
  * the concurrent SQLite writes complete with no lock errors / corruption
    (WAL + ``busy_timeout=30000`` + per-call connections);
  * a concurrent per-founder ``get_status`` read resolves each founder to THEIR
    OWN home universe, never a neighbour's.

Identity is request-local via a ``ContextVar`` (``_current_identity``).
``ThreadPoolExecutor`` workers each get their own context, so every worker sets
its own identity first — exactly as the HTTP transport does per request. That
is the property under test: concurrent requests never leak actors.
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from tinyassets.auth.middleware import auth_middleware, set_provider
from tinyassets.auth.provider import AuthProvider, DevAuthProvider, Identity

_RESERVED = {"wiki", "output", "runs", "lance"}
_FOUNDER_CAPS = ["read", "write", "costly", "submit_request", "list"]
_N_FOUNDERS = 12


class _MultiTenantProvider(AuthProvider):
    """Resolve-always provider (like WorkOS) mapping token ``tok-<sub>`` to a
    distinct founder identity. Anonymous reads, authed founder writes.
    """

    def resolve_token(self, token: str) -> Identity | None:
        if not token or not token.startswith("tok-"):
            return None
        sub = token[len("tok-"):]
        return Identity(user_id=sub, username=sub, capabilities=list(_FOUNDER_CAPS))

    def is_auth_required(self) -> bool:
        return False

    def resolve_always_writes(self) -> bool:
        return True

    def register_client(self, metadata: dict) -> dict:
        return {"client_id": "t", **metadata}

    def create_authorization(self, *a, **k) -> str:  # noqa: ANN002, ANN003
        return "c"

    def exchange_code(self, *a, **k):  # noqa: ANN002, ANN003, ANN201
        return None


@pytest.fixture
def shared_base(tmp_path: Path, monkeypatch) -> Path:
    """One shared data dir + DB for all founders, provider wired once."""
    from tinyassets.daemon_server import initialize_author_server

    base = tmp_path / "data"
    base.mkdir()
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(base))
    set_provider(_MultiTenantProvider())
    # Pre-create the schema once so concurrent workers never race on
    # ``CREATE TABLE``/``executescript`` inside their first write.
    initialize_author_server(base)
    yield base
    set_provider(DevAuthProvider())
    auth_middleware(None)


def _universe_dirs(base: Path) -> list[Path]:
    return [
        p for p in base.iterdir()
        if p.is_dir() and not p.name.startswith(".") and p.name not in _RESERVED
    ]


def _create_as(sub: str) -> tuple[str, dict]:
    """Runs in a worker thread: authenticate as ``sub`` then create a universe.

    Sets identity FIRST (as the transport does per request), so the worker's
    ContextVar carries this founder and cannot leak a neighbour's.
    """
    from tinyassets.api import permissions
    from tinyassets.api import universe as universe_api

    auth_middleware(f"tok-{sub}")
    # In-thread sanity: identity resolved to this founder, not a neighbour.
    assert permissions.current_actor_id() == sub
    out = json.loads(universe_api._universe_impl(action="create_universe"))
    return sub, out


def _status_as(sub: str) -> tuple[str, dict]:
    """Runs in a worker thread: authenticate as ``sub`` then read status."""
    from tinyassets.api.status import get_status

    auth_middleware(f"tok-{sub}")
    return sub, json.loads(get_status())


def test_concurrent_founders_each_get_own_universe(shared_base):
    from tinyassets.daemon_server import get_founder_home, list_universe_acl
    from tinyassets.ids import is_universe_serial

    subs = [f"founder-{i:02d}" for i in range(_N_FOUNDERS)]

    # ── Concurrent create: N founders, one shared DB, all at once. ──────────
    with ThreadPoolExecutor(max_workers=_N_FOUNDERS) as pool:
        results = list(pool.map(_create_as, subs))

    by_sub = {}
    for sub, out in results:
        # No lock error, no crash, no error payload — WAL handled the writes.
        assert out.get("error") is None, (sub, out)
        uid = out["universe_id"]
        assert is_universe_serial(uid), (sub, uid)
        by_sub[sub] = uid

    uids = list(by_sub.values())

    # 1. Every founder got a DISTINCT universe — no collision, no sharing.
    assert len(set(uids)) == _N_FOUNDERS, by_sub
    # 2. N distinct universe dirs actually landed on disk.
    on_disk = {p.name for p in _universe_dirs(shared_base)}
    assert set(uids) <= on_disk
    assert len(on_disk) == _N_FOUNDERS, sorted(on_disk)

    for sub, uid in by_sub.items():
        # 3. Home binding points to the universe THIS founder created.
        assert get_founder_home(shared_base, sub) == uid, (sub, uid)

        # 4. ACL grants admin to exactly this founder, no other founder.
        acl = list_universe_acl(shared_base, universe_id=uid)
        admins = {row["actor_id"] for row in acl if row["permission"] == "admin"}
        assert admins == {sub}, (sub, uid, acl)
        # No OTHER founder's sub appears anywhere in this universe's ACL.
        other_subs = set(by_sub) - {sub}
        assert not (other_subs & {row["actor_id"] for row in acl}), (sub, acl)


def test_concurrent_status_reads_resolve_each_founder_to_own_home(shared_base):
    """After concurrent creation, concurrent per-founder status reads each
    return that founder's OWN home — never a neighbour's (the create-time
    ``.active_universe`` marker must not leak across founders)."""
    from tinyassets.daemon_server import get_founder_home

    subs = [f"reader-{i:02d}" for i in range(_N_FOUNDERS)]

    with ThreadPoolExecutor(max_workers=_N_FOUNDERS) as pool:
        created = dict(pool.map(_create_as, subs))
    for sub, out in created.items():
        assert out.get("error") is None, (sub, out)

    homes = {sub: get_founder_home(shared_base, sub) for sub in subs}
    assert len(set(homes.values())) == _N_FOUNDERS, homes

    with ThreadPoolExecutor(max_workers=_N_FOUNDERS) as pool:
        reads = list(pool.map(_status_as, subs))

    for sub, snap in reads:
        # Each founder has a living home, so status is the full snapshot for
        # THEIR universe — not a first_contact card, not a neighbour's id.
        assert snap.get("universe_id") == homes[sub], (sub, snap.get("universe_id"))
        assert "first_contact" not in snap, (sub, snap)

"""Tests for the per-branch inbound webhook token store (Floor 1)."""

from __future__ import annotations

from typing import Any

import pytest

from tinyassets.storage import webhook_hooks as hooks


def test_mint_then_resolve_returns_the_binding(tmp_path):
    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    assert isinstance(token, str) and len(token) >= 32
    got = hooks.resolve(tmp_path, token=token)
    # A plain per-branch webhook has no source binding (source_id is None).
    assert got == {"universe_id": "u-a", "branch_def_id": "b-1", "source_id": None}


def test_the_raw_token_is_never_stored_at_rest(tmp_path):
    # Codex #6: a read-only DB disclosure must not recover an invocation token.
    import sqlite3

    from tinyassets.storage import db_path

    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    conn = sqlite3.connect(db_path(tmp_path))
    try:
        rows = conn.execute(
            "SELECT token_hash, token_prefix FROM webhook_hooks"
        ).fetchall()
    finally:
        conn.close()
    stored_hash, stored_prefix = rows[0]
    assert token not in stored_hash                # the full token is never on disk
    assert stored_hash == hooks._hash_token(token)  # only its hash is
    assert stored_prefix == token[:hooks._PREFIX_LEN] and len(stored_prefix) < len(token)


def test_tokens_are_unguessable_and_unique(tmp_path):
    t1 = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    t2 = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    assert t1 != t2


def test_unknown_revoked_and_empty_tokens_all_resolve_to_none(tmp_path):
    assert hooks.resolve(tmp_path, token="nope") is None
    assert hooks.resolve(tmp_path, token="") is None
    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    assert hooks.revoke(tmp_path, token=token) is True
    assert hooks.resolve(tmp_path, token=token) is None      # revoked -> None (indistinct)
    assert hooks.revoke(tmp_path, token=token) is False      # already revoked


def test_a_token_binds_exactly_one_universe_and_branch(tmp_path):
    ta = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-a")
    tb = hooks.mint(tmp_path, universe_id="u-b", branch_def_id="b-b")
    assert hooks.resolve(tmp_path, token=ta)["universe_id"] == "u-a"
    assert hooks.resolve(tmp_path, token=tb)["universe_id"] == "u-b"


def test_list_is_scoped_to_one_universe(tmp_path):
    hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-2")
    hooks.mint(tmp_path, universe_id="u-b", branch_def_id="b-3")
    a = hooks.list_for_universe(tmp_path, universe_id="u-a")
    assert {r["branch_def_id"] for r in a} == {"b-1", "b-2"}
    # list returns the non-secret prefix, NEVER the raw token (Codex #6).
    assert all("token" not in r and r["token_prefix"] for r in a)


def test_mint_rejects_empty_or_overlong_ids(tmp_path):
    with pytest.raises(ValueError):
        hooks.mint(tmp_path, universe_id="", branch_def_id="b")
    with pytest.raises(ValueError):
        hooks.mint(tmp_path, universe_id="u", branch_def_id="x" * (hooks.MAX_ID_LEN + 1))


# ── Durable admission (Codex #3) ────────────────────────────────────────────────

def test_admission_caps_per_token_and_survives_restart(tmp_path):
    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    now = 1000.0
    admitted = sum(
        hooks.admit(tmp_path, token=token, universe_id="u-a",
                    token_max=5, universe_max=1000, window_s=60.0, now=now)
        for _ in range(8)
    )
    assert admitted == 5                              # per-token cap
    hooks._initialized.clear()                        # simulate a process restart
    assert not hooks.admit(tmp_path, token=token, universe_id="u-a",
                           token_max=5, universe_max=1000, window_s=60.0, now=now)
    # window advances -> admitted again
    assert hooks.admit(tmp_path, token=token, universe_id="u-a",
                       token_max=5, universe_max=1000, window_s=60.0, now=now + 61)


def test_admission_caps_per_universe_across_tokens(tmp_path):
    toks = [hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1") for _ in range(4)]
    now = 2000.0
    admitted = 0
    for i in range(20):
        if hooks.admit(tmp_path, token=toks[i % 4], universe_id="u-a",
                       token_max=100, universe_max=6, window_s=60.0, now=now):
            admitted += 1
    assert admitted == 6                              # per-universe aggregate cap binds


# ── Atomic server-side replay dedupe (Codex #4) ─────────────────────────────────

def test_claim_delivery_is_once_per_key_and_survives_restart(tmp_path):
    now = 3000.0
    assert hooks.claim_delivery(tmp_path, dedupe_key="k1", window_s=600.0, now=now)   # new
    assert hooks.claim_delivery(tmp_path, dedupe_key="k2", window_s=600.0, now=now)   # new
    assert not hooks.claim_delivery(tmp_path, dedupe_key="k1", window_s=600.0, now=now)  # replay
    hooks._initialized.clear()                        # restart: claim is durable
    assert not hooks.claim_delivery(tmp_path, dedupe_key="k1", window_s=600.0, now=now)
    # release un-claims so a legitimate retry proceeds
    hooks.release_delivery(tmp_path, dedupe_key="k1")
    assert hooks.claim_delivery(tmp_path, dedupe_key="k1", window_s=600.0, now=now)
    # window advances -> the key is free again
    assert hooks.claim_delivery(tmp_path, dedupe_key="k1", window_s=600.0, now=now + 601)


def test_claim_delivery_is_atomic_under_concurrency(tmp_path):
    # N threads claim the SAME key at once -> exactly ONE wins (INSERT-under-PK race).
    import threading

    hooks._connect(tmp_path).close()                  # pre-init schema (avoid init race)
    wins: list[bool] = []
    lock = threading.Lock()

    def worker():
        got = hooks.claim_delivery(tmp_path, dedupe_key="same", window_s=600.0, now=7000.0)
        with lock:
            wins.append(got)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sum(wins) == 1                              # exactly one claim across 16 racers


# ── Atomic in-flight reservation (Codex #5) ─────────────────────────────────────

def test_reserve_dispatch_enforces_the_cap_and_active_check(tmp_path):
    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    kw = dict(token=token, universe_id="u-a", cap=2, ttl_s=120.0, now=8000.0)
    r1, s1 = hooks.reserve_dispatch(tmp_path, **kw)
    r2, s2 = hooks.reserve_dispatch(tmp_path, **kw)
    r3, s3 = hooks.reserve_dispatch(tmp_path, **kw)
    assert s1 == "ok" and s2 == "ok" and s3 == "busy" and r3 is None
    # releasing one frees a slot
    hooks.release_dispatch(tmp_path, reservation_id=r1)
    r4, s4 = hooks.reserve_dispatch(tmp_path, **kw)
    assert s4 == "ok"
    # a revoked token cannot reserve at all
    hooks.revoke(tmp_path, token=token)
    r5, s5 = hooks.reserve_dispatch(tmp_path, **kw)
    assert r5 is None and s5 == "revoked"


def test_reserve_dispatch_reconciles_terminated_and_abandoned(tmp_path):
    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    r1, _ = hooks.reserve_dispatch(tmp_path, token=token, universe_id="u-a",
                                   cap=1, ttl_s=120.0, now=9000.0)
    hooks.link_dispatch(tmp_path, reservation_id=r1, run_id="run-1")
    # cap is full, but reconciling run-1 (now terminal) frees the slot
    r2, s2 = hooks.reserve_dispatch(tmp_path, token=token, universe_id="u-a",
                                    cap=1, ttl_s=120.0, terminal_run_ids={"run-1"}, now=9001.0)
    assert s2 == "ok" and r2 is not None
    # an UNLINKED reservation past its TTL is reclaimed as abandoned
    r3, s3 = hooks.reserve_dispatch(tmp_path, token=token, universe_id="u-a",
                                    cap=1, ttl_s=120.0, now=9001.0 + 200)
    assert s3 == "ok"


def test_reserve_dispatch_is_atomic_under_concurrency(tmp_path):
    import threading

    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    hooks._connect(tmp_path).close()
    outcomes: list[str] = []
    lock = threading.Lock()

    def worker():
        _rid, status = hooks.reserve_dispatch(
            tmp_path, token=token, universe_id="u-a", cap=5, ttl_s=120.0, now=9500.0)
        with lock:
            outcomes.append(status)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert outcomes.count("ok") == 5                   # never overshoot the cap under 20 racers
    assert outcomes.count("busy") == 15


def test_a_concurrent_revoke_and_reserve_never_both_win(tmp_path):
    # The atomic reserve serializes with revoke: after a revoke commits, no reserve for that
    # token can succeed. Race them; assert consistency (no reserve survives a completed revoke).
    import threading

    token = hooks.mint(tmp_path, universe_id="u-a", branch_def_id="b-1")
    hooks._connect(tmp_path).close()
    barrier = threading.Barrier(2)
    results: dict[str, Any] = {}

    def revoker():
        barrier.wait()
        results["revoked"] = hooks.revoke(tmp_path, token=token)

    def reserver():
        barrier.wait()
        _rid, results["reserve_status"] = hooks.reserve_dispatch(
            tmp_path, token=token, universe_id="u-a", cap=10, ttl_s=120.0, now=9800.0)

    tr = threading.Thread(target=revoker)
    ts = threading.Thread(target=reserver)
    for t in (tr, ts):
        t.start()
    for t in (tr, ts):
        t.join()
    # After the dust settles the token is revoked; a fresh reserve must be refused.
    _rid, status = hooks.reserve_dispatch(
        tmp_path, token=token, universe_id="u-a", cap=10, ttl_s=120.0, now=9801.0)
    assert status == "revoked"


# ── Token-hash migration (Codex round-2) ────────────────────────────────────────

def test_migrates_a_legacy_plaintext_token_table(tmp_path):
    import sqlite3

    from tinyassets.storage import db_path

    # Simulate the PRIOR committed schema: raw token PK, no token_hash, no source_id.
    path = db_path(tmp_path)
    conn = sqlite3.connect(path)
    conn.executescript(
        "CREATE TABLE webhook_hooks (token TEXT PRIMARY KEY, universe_id TEXT NOT NULL,"
        " branch_def_id TEXT NOT NULL, created_at REAL NOT NULL, revoked_at REAL);"
    )
    conn.execute(
        "INSERT INTO webhook_hooks VALUES (?,?,?,?,?)",
        ("legacy-token-value", "u-a", "b-1", 1.0, None),
    )
    conn.commit()
    conn.close()
    hooks._initialized.clear()                         # force the migration on next connect

    # The new code resolves the legacy token by hashing it, and the plaintext is gone.
    got = hooks.resolve(tmp_path, token="legacy-token-value")
    assert got == {"universe_id": "u-a", "branch_def_id": "b-1", "source_id": None}
    conn = sqlite3.connect(path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(webhook_hooks)")}
        assert "token_hash" in cols and "token" not in cols
        stored = conn.execute("SELECT token_hash FROM webhook_hooks").fetchone()[0]
        assert stored == hooks._hash_token("legacy-token-value")
    finally:
        conn.close()

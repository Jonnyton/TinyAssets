"""Negative + guard tests for the founder-scoped engine MCP hardening.

Covers the Codex-gated controls that keep `run_graph` safe for a single vetted
founder: the allowlist scope gate, the effect-spam rate limit, the served-budget
boot reconciliation (stuck-reservation release) and bounded retention, and the
per-request HTTP bearer auth on the loopback engine server.
"""
from __future__ import annotations

import importlib
import sqlite3

# ── per-request HTTP bearer auth (Codex #6) ──────────────────────────────────

def test_bearer_ok_rejects_missing_wrong_and_empty(monkeypatch):
    monkeypatch.setenv("TINYASSETS_ENGINE_GRAPH_ID", "u-tiny")
    import tinyassets.engine_mcp_server as ems
    ems = importlib.reload(ems)

    assert ems._bearer_ok("Bearer s3cret", "s3cret") is True
    assert ems._bearer_ok("Bearer wrong", "s3cret") is False
    assert ems._bearer_ok("", "s3cret") is False
    assert ems._bearer_ok(None, "s3cret") is False
    assert ems._bearer_ok("s3cret", "s3cret") is False  # missing the scheme
    assert ems._bearer_ok("Bearer x", "") is False  # no server secret -> never ok


# ── allowlist scope gate (Codex #2 single-founder confinement) ───────────────

def test_run_graph_allowlist_parses_and_defaults_dark(monkeypatch):
    from tinyassets import engine_mcp_http

    monkeypatch.delenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", raising=False)
    assert engine_mcp_http.run_graph_allowlist() == frozenset()  # dark by default

    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", " u-tiny , u-two ")
    assert engine_mcp_http.run_graph_allowlist() == frozenset({"u-tiny", "u-two"})


def test_run_graph_refuses_when_universe_not_allowlisted(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_ENGINE_ACTOR_ID", "founder-1")
    monkeypatch.setenv("TINYASSETS_ENGINE_GRAPH_ID", "u-not-allowed")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_ENGINE_RUN_GRAPH_UNIVERSES", "u-only-this")
    # Fresh import so module-level _GRAPH_ID picks up the env.
    import tinyassets.engine_mcp_server as ems
    ems = importlib.reload(ems)

    _fn = getattr(ems.run_graph, "fn", ems.run_graph)  # fastmcp keeps the func
    out = _fn(branch_def_id="b1")
    assert "not enabled for this universe" in out


# ── atomic effect-spam admission (Codex #5) ──────────────────────────────────

def test_engine_run_admit_caps_and_is_atomic(monkeypatch, tmp_path):
    monkeypatch.setenv("TINYASSETS_ENGINE_GRAPH_ID", "u-tiny")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    import tinyassets.engine_mcp_server as ems
    ems = importlib.reload(ems)

    admits = [ems._engine_run_admit() for _ in range(ems._RUN_GRAPH_RATE_MAX + 5)]
    assert admits.count(True) == ems._RUN_GRAPH_RATE_MAX  # exactly the cap
    assert admits[ems._RUN_GRAPH_RATE_MAX:] == [False] * 5  # then refused

    # A different universe has its own independent budget.
    monkeypatch.setenv("TINYASSETS_ENGINE_GRAPH_ID", "u-other")
    ems = importlib.reload(ems)
    assert ems._engine_run_admit() is True


def test_engine_run_admit_ages_out_old_admissions(monkeypatch, tmp_path):
    import time

    monkeypatch.setenv("TINYASSETS_ENGINE_GRAPH_ID", "u-tiny")
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    import tinyassets.engine_mcp_server as ems
    ems = importlib.reload(ems)

    # Pre-seed the cap's worth of OLD admissions (outside the window).
    db = tmp_path / ".engine_run_admissions.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE admissions (universe_id TEXT, ts REAL)")
    old = time.time() - ems._RUN_GRAPH_RATE_WINDOW_S - 10
    conn.executemany(
        "INSERT INTO admissions VALUES (?,?)",
        [("u-tiny", old) for _ in range(ems._RUN_GRAPH_RATE_MAX)],
    )
    conn.commit()
    conn.close()
    # Old admissions do not count -> a fresh run is admitted.
    assert ems._engine_run_admit() is True


# ── served-budget boot reconciliation + retention (Codex P1 / #7) ────────────

def _insert_reservation(conn, rid, state, tokens=100):
    conn.execute(
        "INSERT INTO served_provider_budget_reservations "
        "(reservation_id, binding_id, binding_generation, state, "
        "reserved_total_tokens, reserved_cost_microunits, "
        "actual_total_tokens, actual_cost_microunits) VALUES (?,?,?,?,?,?,?,?)",
        (rid, "pwb", 1, state, tokens, tokens * 100,
         None if state in ("reserved", "indeterminate") else tokens,
         None if state in ("reserved", "indeterminate") else tokens * 100),
    )


def test_boot_reconcile_settles_open_reservations(tmp_path):
    from tinyassets import provider_assignment as pa
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    store = SQLiteProviderWorkAuthorityStore(str(tmp_path))
    with store.connection() as conn:
        pa._ensure_served_budget_schema(conn)
        _insert_reservation(conn, "open1", "reserved")
        _insert_reservation(conn, "open2", "indeterminate")
        _insert_reservation(conn, "done1", "succeeded")
        conn.commit()

    released = pa.reconcile_orphaned_reservations_on_boot(str(tmp_path))
    assert released == 2

    with store.connection() as conn:
        rows = dict(conn.execute(
            "SELECT state, COUNT(*) FROM served_provider_budget_reservations "
            "GROUP BY state"
        ).fetchall())
    # No open rows remain; all are settled.
    assert rows.get("reserved", 0) == 0
    assert rows.get("indeterminate", 0) == 0
    assert rows.get("succeeded", 0) == 3


def test_boot_reconcile_prunes_settled_history(tmp_path):
    import time

    from tinyassets import provider_assignment as pa
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    ancient = time.time() - pa._RUNAWAY_WINDOW_S - 1000  # known-old, prunable
    store = SQLiteProviderWorkAuthorityStore(str(tmp_path))
    over = pa._SETTLED_RETENTION_ROWS + 25
    with store.connection() as conn:
        pa._ensure_served_budget_schema(conn)
        for i in range(over):
            _insert_reservation_at(conn, f"s{i}", "succeeded", ancient)
        conn.commit()

    pa.reconcile_orphaned_reservations_on_boot(str(tmp_path))
    with store.connection() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM served_provider_budget_reservations"
        ).fetchone()[0]
    assert remaining == pa._SETTLED_RETENTION_ROWS


def test_prune_never_evicts_null_timestamp_rows(tmp_path):
    """NULL created_at rows are counted IN-window by the runaway guard, so the
    prune must NOT delete them — else pruning to the retention cap silently
    re-admits a runaway (reproduced by the final Codex re-review 2026-08-19: an
    old/rollback binary's fast-settling NULL rows evaded the guard). Guard and
    prune must agree that NULL is present, not ancient.
    """
    from tinyassets import provider_assignment as pa
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    store = SQLiteProviderWorkAuthorityStore(str(tmp_path))
    over = pa._SETTLED_RETENTION_ROWS + 100
    with store.connection() as conn:
        pa._ensure_served_budget_schema(conn)
        for i in range(over):
            _insert_reservation_at(conn, f"n{i}", "succeeded", None)
        conn.commit()

    pa.reconcile_orphaned_reservations_on_boot(str(tmp_path))
    with store.connection() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM served_provider_budget_reservations"
        ).fetchone()[0]
    # Every NULL-timestamp row is retained — the guard still counts them all, so
    # a runaway of NULL rows stays blocked instead of pruning back under the cap.
    assert remaining == over


# ── rolling-window runaway guard + lease reconciliation (Codex reject #3/#4/#5) ─

def _insert_reservation_at(conn, rid, state, created_at, tokens=100,
                           lease_deadline=None):
    conn.execute(
        "INSERT INTO served_provider_budget_reservations "
        "(reservation_id, binding_id, binding_generation, state, "
        "reserved_total_tokens, reserved_cost_microunits, "
        "actual_total_tokens, actual_cost_microunits, created_at, "
        "lease_deadline) "
        "VALUES (?,?,?,?,?,?,?,?,?,?)",
        (rid, "pwb", 1, state, tokens, tokens * 100,
         None if state in ("reserved", "indeterminate") else tokens,
         None if state in ("reserved", "indeterminate") else tokens * 100,
         created_at, lease_deadline),
    )


def test_lease_reconciler_settles_only_past_deadline(tmp_path):
    import time

    from tinyassets import provider_assignment as pa
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    now = time.time()
    store = SQLiteProviderWorkAuthorityStore(str(tmp_path))
    with store.connection() as conn:
        pa._ensure_served_budget_schema(conn)
        # Holds PAST their own lease deadline (crashed/hung turn).
        _insert_reservation_at(conn, "stale_res", "reserved",
                               now - 5000, lease_deadline=now - 60)
        _insert_reservation_at(conn, "stale_ind", "indeterminate",
                               now - 5000, lease_deadline=now - 60)
        # A genuinely live turn under a HUGE (unbounded) timeout: created long ago
        # but its deadline is still in the future — must NOT be reclaimed early.
        _insert_reservation_at(conn, "live_long", "reserved",
                               now - 5000, lease_deadline=now + 3600)
        # An old row with NO lease_deadline (pre-migration / old binary) — left to
        # BOOT reconciliation, NOT settled by the periodic/opportunistic path.
        _insert_reservation_at(conn, "null_lease", "reserved",
                               now - 5000, lease_deadline=None)
        conn.commit()

    settled = pa.reconcile_served_budget_leases(str(tmp_path))
    assert settled == 2

    with store.connection() as conn:
        states = dict(conn.execute(
            "SELECT reservation_id, state FROM "
            "served_provider_budget_reservations"
        ).fetchall())
    assert states["stale_res"] == "succeeded"
    assert states["stale_ind"] == "succeeded"
    assert states["live_long"] == "reserved"  # deadline in future: untouched
    assert states["null_lease"] == "reserved"  # NULL deadline: boot's job only


def test_release_settles_no_spend_preserving_invocation_count(tmp_path):
    import time

    from tinyassets import provider_assignment as pa
    from tinyassets.provider_assignment import ServedProviderBudgetReservation
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    store = SQLiteProviderWorkAuthorityStore(str(tmp_path))
    with store.connection() as conn:
        pa._ensure_served_budget_schema(conn)
        _insert_reservation_at(conn, "unavail", "reserved", time.time())
        conn.commit()

    pa.release_served_provider_budget(
        str(tmp_path),
        ServedProviderBudgetReservation(
            reservation_id="unavail",
            binding_id="pwb",
            binding_generation=1,
            output_tokens=1,
            reserved_total_tokens=100,
            reserved_cost_microunits=10_000,
        ),
    )

    with store.connection() as conn:
        row = conn.execute(
            "SELECT state, actual_total_tokens, actual_cost_microunits "
            "FROM served_provider_budget_reservations WHERE reservation_id='unavail'"
        ).fetchone()
    # The row SURVIVES (invocation still counts toward the runaway window) but is
    # charged zero tokens — a provably-no-output call must not brick the binding
    # yet must not vanish from the launch count (Codex reject #5).
    assert row is not None
    assert row[0] == "succeeded"
    assert row[1] == 0
    assert row[2] == 0


def test_settled_history_prune_never_evicts_in_window_rows(tmp_path):
    import time

    from tinyassets import provider_assignment as pa
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    now = time.time()
    store = SQLiteProviderWorkAuthorityStore(str(tmp_path))
    with store.connection() as conn:
        pa._ensure_served_budget_schema(conn)
        # More recent-window rows than the retention cap: none may be pruned,
        # because the rolling-window runaway guard must count them all
        # independently of retention (Codex reject #3).
        in_window = pa._SETTLED_RETENTION_ROWS + 50
        for i in range(in_window):
            _insert_reservation_at(conn, f"w{i}", "succeeded", now - 5)
        conn.commit()

    pa.reconcile_orphaned_reservations_on_boot(str(tmp_path))
    with store.connection() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM served_provider_budget_reservations"
        ).fetchone()[0]
    # Every in-window row is retained despite exceeding the retention cap.
    assert remaining == pa._SETTLED_RETENTION_ROWS + 50

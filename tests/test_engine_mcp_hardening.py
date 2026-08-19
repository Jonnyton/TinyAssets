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
    from tinyassets import provider_assignment as pa
    from tinyassets.storage.provider_work_authority import (
        SQLiteProviderWorkAuthorityStore,
    )

    store = SQLiteProviderWorkAuthorityStore(str(tmp_path))
    over = pa._SETTLED_RETENTION_ROWS + 25
    with store.connection() as conn:
        pa._ensure_served_budget_schema(conn)
        for i in range(over):
            _insert_reservation(conn, f"s{i}", "succeeded")
        conn.commit()

    pa.reconcile_orphaned_reservations_on_boot(str(tmp_path))
    with store.connection() as conn:
        remaining = conn.execute(
            "SELECT COUNT(*) FROM served_provider_budget_reservations"
        ).fetchone()[0]
    assert remaining == pa._SETTLED_RETENTION_ROWS

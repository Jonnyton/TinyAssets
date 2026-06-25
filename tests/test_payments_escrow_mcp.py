"""Tests for payments escrow MCP actions: escrow_lock/release/refund/inspect.

Spec: Task #41 — Payments escrow MCP wiring.
Business logic lives in workflow/payments/actions.py; MCP wiring in universe_server.py.
"""

from __future__ import annotations

import json
from pathlib import Path

# ── helpers ───────────────────────────────────────────────────────────────────

def _init(base_path: Path) -> None:
    import sqlite3

    from workflow.daemon_server import initialize_author_server
    from workflow.payments.funding import credit_balance
    from workflow.storage import db_path
    initialize_author_server(base_path)
    # Escrow locks now require a funded staker budget; pre-fund the common test
    # stakers generously so lock/release/refund flows have spendable budget.
    conn = sqlite3.connect(db_path(base_path))
    conn.row_factory = sqlite3.Row
    try:
        for staker in ("alice", "bob", "staker-1", "daemon-bob", "anonymous"):
            credit_balance(
                conn,
                staker_id=staker,
                amount=1_000_000_000,
                now_iso="2026-06-08T00:00:00+00:00",
            )
        conn.commit()
    finally:
        conn.close()


def _ext(monkeypatch, tmp_path, *, paid_market: bool = True, user: str = "alice", **kwargs):
    """Call extensions() with env set up for escrow tests."""
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_PAID_MARKET", "on" if paid_market else "off")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", user)
    from workflow.universe_server import extensions
    return json.loads(extensions(**kwargs))


# ── escrow_lock ───────────────────────────────────────────────────────────────

class TestEscrowLock:
    def test_lock_success(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_lock",
                      node_id="node-1",
                      escrow_amount=5000)
        assert result["status"] == "ok"
        assert "lock_id" in result
        assert result["lock_id"].startswith("lock-")
        assert result["amount"] == 5000
        assert result["node_id"] == "node-1"
        assert result["claimer"] == "alice"

    def test_lock_requires_paid_market(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      paid_market=False,
                      action="escrow_lock",
                      node_id="node-1",
                      escrow_amount=500)
        assert result["status"] == "not_available"

    def test_lock_rejects_zero_amount(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_lock",
                      node_id="node-1",
                      escrow_amount=0)
        assert result["status"] == "rejected"
        assert "amount" in result["error"].lower()

    def test_lock_rejects_negative_amount(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_lock",
                      node_id="node-1",
                      escrow_amount=-100)
        assert result["status"] == "rejected"

    def test_lock_rejects_missing_node_id(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_lock",
                      escrow_amount=500)
        assert result["status"] == "rejected"
        assert "node_id" in result["error"].lower()

    def test_lock_rejects_duplicate_for_same_claimer(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path,
             action="escrow_lock",
             node_id="node-1",
             escrow_amount=1000)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_lock",
                      node_id="node-1",
                      escrow_amount=500)
        assert result["status"] == "rejected"
        assert "existing_lock_id" in result

    def test_lock_returns_locked_at_timestamp(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_lock",
                      node_id="node-2",
                      escrow_amount=200)
        assert result["status"] == "ok"
        assert "locked_at" in result
        assert "T" in result["locked_at"]  # ISO 8601

    def test_lock_invalid_currency_rejected(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_lock",
                      node_id="node-1",
                      escrow_amount=100,
                      escrow_currency="USD")
        assert result["status"] == "rejected"
        assert "currency" in result["error"].lower()


# ── escrow_release ────────────────────────────────────────────────────────────

class TestEscrowRelease:
    def _lock(self, monkeypatch, tmp_path, node_id="node-1", amount=1000):
        return _ext(monkeypatch, tmp_path,
                    action="escrow_lock",
                    node_id=node_id,
                    escrow_amount=amount)

    def test_release_success(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = self._lock(monkeypatch, tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_release",
                      lock_id=lock["lock_id"],
                      escrow_recipient_id="daemon-bob")
        assert result["status"] == "ok"
        assert result["disposition"] == "released"
        assert result["recipient_id"] == "daemon-bob"
        assert result["amount"] == 1000

    def test_release_requires_paid_market(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      paid_market=False,
                      action="escrow_release",
                      lock_id="any",
                      escrow_recipient_id="x")
        assert result["status"] == "not_available"

    def test_release_rejects_missing_lock_id(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_release",
                      escrow_recipient_id="daemon-bob")
        assert result["status"] == "rejected"
        assert "lock_id" in result["error"].lower()

    def test_release_rejects_missing_recipient(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = self._lock(monkeypatch, tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_release",
                      lock_id=lock["lock_id"])
        assert result["status"] == "rejected"
        assert "recipient_id" in result["error"].lower()

    def test_release_rejects_unknown_lock_id(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_release",
                      lock_id="lock-does-not-exist",
                      escrow_recipient_id="daemon-bob")
        assert result["status"] == "rejected"
        assert "lock-does-not-exist" in result["error"]

    def test_release_rejects_double_release(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = self._lock(monkeypatch, tmp_path)
        _ext(monkeypatch, tmp_path,
             action="escrow_release",
             lock_id=lock["lock_id"],
             escrow_recipient_id="daemon-bob")
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_release",
                      lock_id=lock["lock_id"],
                      escrow_recipient_id="daemon-bob")
        assert result["status"] == "rejected"
        assert "already" in result["error"].lower()

    def test_release_evidence_included_in_response(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = self._lock(monkeypatch, tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_release",
                      lock_id=lock["lock_id"],
                      escrow_recipient_id="daemon-bob",
                      escrow_evidence="https://example.com/proof")
        assert result["status"] == "ok"
        assert result["evidence"] == "https://example.com/proof"


# ── escrow_refund ─────────────────────────────────────────────────────────────

class TestEscrowRefund:
    def _lock(self, monkeypatch, tmp_path, node_id="node-r", amount=800):
        return _ext(monkeypatch, tmp_path,
                    action="escrow_lock",
                    node_id=node_id,
                    escrow_amount=amount)

    def test_refund_success(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = self._lock(monkeypatch, tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_refund",
                      lock_id=lock["lock_id"])
        assert result["status"] == "ok"
        assert result["disposition"] == "refunded"
        assert result["refunded_to"] == "alice"
        assert result["amount"] == 800

    def test_refund_requires_paid_market(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      paid_market=False,
                      action="escrow_refund",
                      lock_id="any")
        assert result["status"] == "not_available"

    def test_refund_rejects_missing_lock_id(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path, action="escrow_refund")
        assert result["status"] == "rejected"
        assert "lock_id" in result["error"].lower()

    def test_refund_rejects_unknown_lock_id(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_refund",
                      lock_id="lock-ghost")
        assert result["status"] == "rejected"

    def test_refund_rejects_already_refunded(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = self._lock(monkeypatch, tmp_path)
        _ext(monkeypatch, tmp_path,
             action="escrow_refund",
             lock_id=lock["lock_id"])
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_refund",
                      lock_id=lock["lock_id"])
        assert result["status"] == "rejected"
        assert "already" in result["error"].lower()

    def test_refund_rejects_already_released(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = self._lock(monkeypatch, tmp_path)
        _ext(monkeypatch, tmp_path,
             action="escrow_release",
             lock_id=lock["lock_id"],
             escrow_recipient_id="daemon-bob")
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_refund",
                      lock_id=lock["lock_id"])
        assert result["status"] == "rejected"

    def test_refund_reason_included_in_response(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = self._lock(monkeypatch, tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_refund",
                      lock_id=lock["lock_id"],
                      escrow_reason="abandoned after timeout")
        assert result["status"] == "ok"
        assert result["reason"] == "abandoned after timeout"


# ── escrow_inspect ────────────────────────────────────────────────────────────

class TestEscrowInspect:
    def test_inspect_by_lock_id(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = _ext(monkeypatch, tmp_path,
                    action="escrow_lock",
                    node_id="node-i",
                    escrow_amount=300)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_inspect",
                      lock_id=lock["lock_id"])
        assert result["status"] == "ok"
        assert result["lock"]["lock_id"] == lock["lock_id"]
        assert result["lock"]["amount"] == 300
        assert result["lock"]["status"] == "locked"

    def test_inspect_by_node_id_empty(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_inspect",
                      node_id="node-no-locks")
        assert result["status"] == "ok"
        assert result["locks"] == []
        assert result["total"] == 0

    def test_inspect_by_node_id_with_lock(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path,
             action="escrow_lock",
             node_id="node-j",
             escrow_amount=700)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_inspect",
                      node_id="node-j")
        assert result["status"] == "ok"
        assert result["total"] == 1
        assert result["locks"][0]["amount"] == 700

    def test_inspect_missing_both_params_rejected(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path, action="escrow_inspect")
        assert result["status"] == "rejected"

    def test_inspect_unknown_lock_id_rejected(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      action="escrow_inspect",
                      lock_id="lock-xyz-unknown")
        assert result["status"] == "rejected"

    def test_inspect_no_paid_market_gate(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path,
                      paid_market=False,
                      action="escrow_inspect",
                      node_id="node-k")
        assert result["status"] == "ok"
        assert result["locks"] == []


# ── Round-trip integration ────────────────────────────────────────────────────

class TestEscrowRoundTrip:
    def test_lock_release_roundtrip(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = _ext(monkeypatch, tmp_path,
                    action="escrow_lock",
                    node_id="node-rt",
                    escrow_amount=2000)
        assert lock["status"] == "ok"
        lock_id = lock["lock_id"]

        inspect = _ext(monkeypatch, tmp_path,
                       action="escrow_inspect",
                       lock_id=lock_id)
        assert inspect["lock"]["status"] == "locked"

        release = _ext(monkeypatch, tmp_path,
                       action="escrow_release",
                       lock_id=lock_id,
                       escrow_recipient_id="daemon-carol")
        assert release["status"] == "ok"
        assert release["disposition"] == "released"

        inspect2 = _ext(monkeypatch, tmp_path,
                        action="escrow_inspect",
                        lock_id=lock_id)
        assert inspect2["lock"]["status"] == "released"
        assert inspect2["lock"]["recipient_id"] == "daemon-carol"

    def test_lock_refund_roundtrip(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = _ext(monkeypatch, tmp_path,
                    action="escrow_lock",
                    node_id="node-rr",
                    escrow_amount=1500)
        lock_id = lock["lock_id"]

        refund = _ext(monkeypatch, tmp_path,
                      action="escrow_refund",
                      lock_id=lock_id,
                      escrow_reason="abandoned")
        assert refund["status"] == "ok"
        assert refund["disposition"] == "refunded"
        assert refund["refunded_to"] == "alice"

        inspect = _ext(monkeypatch, tmp_path,
                       action="escrow_inspect",
                       lock_id=lock_id)
        assert inspect["lock"]["status"] == "refunded"


# ── Cross-actor authorization (slice1a review CRITICAL 1) ──────────────────────

class TestCrossActorAuthorization:
    """Money escrow actions must act on the authenticated actor only — a caller
    cannot fund / set-wallet / withdraw against, or release, another actor's
    escrow by supplying a foreign staker_id / lock_id."""

    ADDR = "0x" + "a" * 40

    def test_fund_rejects_cross_actor_staker(self, tmp_path, monkeypatch):
        _init(tmp_path)
        # alice authenticated, tries to fund bob's budget — rejected.
        result = _ext(monkeypatch, tmp_path, user="alice",
                      action="escrow_fund", escrow_amount=5000,
                      escrow_staker_id="bob")
        assert result["status"] == "rejected"
        assert "cross-actor" in result["error"].lower()
        # bob's budget is untouched.
        bob_bal = _ext(monkeypatch, tmp_path, user="bob",
                       action="escrow_balance")
        assert bob_bal["total"] == 1_000_000_000  # only the _init pre-fund

    def test_fund_own_staker_allowed(self, tmp_path, monkeypatch):
        _init(tmp_path)
        # Supplying your OWN id is fine (matches authenticated actor).
        result = _ext(monkeypatch, tmp_path, user="alice",
                      action="escrow_fund", escrow_amount=5000,
                      escrow_staker_id="alice")
        assert result["status"] == "ok"
        assert result["staker_id"] == "alice"

    def test_set_wallet_rejects_cross_actor(self, tmp_path, monkeypatch):
        _init(tmp_path)
        result = _ext(monkeypatch, tmp_path, user="alice",
                      action="escrow_set_wallet",
                      escrow_wallet_address=self.ADDR,
                      escrow_staker_id="bob")
        assert result["status"] == "rejected"
        assert "cross-actor" in result["error"].lower()

    def test_withdraw_rejects_cross_actor(self, tmp_path, monkeypatch):
        _init(tmp_path)
        # bob registers a wallet + has funds; alice tries to withdraw bob's.
        _ext(monkeypatch, tmp_path, user="bob", action="escrow_set_wallet",
             escrow_wallet_address=self.ADDR)
        result = _ext(monkeypatch, tmp_path, user="alice",
                      action="escrow_withdraw", escrow_amount=1000,
                      escrow_staker_id="bob")
        assert result["status"] == "rejected"
        assert "cross-actor" in result["error"].lower()
        # bob's balance untouched.
        bob_bal = _ext(monkeypatch, tmp_path, user="bob",
                       action="escrow_balance")
        assert bob_bal["total"] == 1_000_000_000

    def test_release_rejects_non_owner(self, tmp_path, monkeypatch):
        _init(tmp_path)
        # alice locks escrow on node-x; bob (not the staker) tries to release
        # it to himself — rejected, alice's funds are not redirected.
        lock = _ext(monkeypatch, tmp_path, user="alice",
                    action="escrow_lock", node_id="node-x", escrow_amount=1000)
        assert lock["status"] == "ok"
        result = _ext(monkeypatch, tmp_path, user="bob",
                      action="escrow_release", lock_id=lock["lock_id"],
                      escrow_recipient_id="bob")
        assert result["status"] == "rejected"
        assert "release" in result["error"].lower()
        # Lock is still locked — not redirected.
        inspect = _ext(monkeypatch, tmp_path, user="alice",
                       action="escrow_inspect", lock_id=lock["lock_id"])
        assert inspect["lock"]["status"] == "locked"

    def test_release_owner_allowed(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = _ext(monkeypatch, tmp_path, user="alice",
                    action="escrow_lock", node_id="node-y", escrow_amount=1000)
        result = _ext(monkeypatch, tmp_path, user="alice",
                      action="escrow_release", lock_id=lock["lock_id"],
                      escrow_recipient_id="daemon-bob")
        assert result["status"] == "ok"
        assert result["disposition"] == "released"

    def test_host_may_act_cross_actor(self, tmp_path, monkeypatch):
        _init(tmp_path)
        # The configured host identity is allowed to fund another actor.
        monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "platform-host")
        result = _ext(monkeypatch, tmp_path, user="platform-host",
                      action="escrow_fund", escrow_amount=5000,
                      escrow_staker_id="bob")
        assert result["status"] == "ok"
        assert result["staker_id"] == "bob"

    def test_refund_rejects_non_owner(self, tmp_path, monkeypatch):
        # slice1a review CRITICAL — round 2: a write-scoped caller who knows
        # another actor's lock_id must NOT be able to cancel their escrow.
        _init(tmp_path)
        lock = _ext(monkeypatch, tmp_path, user="alice",
                    action="escrow_lock", node_id="node-r", escrow_amount=1000)
        assert lock["status"] == "ok"
        # bob (not the staker) tries to refund alice's lock — rejected.
        result = _ext(monkeypatch, tmp_path, user="bob",
                      action="escrow_refund", lock_id=lock["lock_id"])
        assert result["status"] == "rejected"
        assert "refund" in result["error"].lower()
        # Lock is still locked — not cancelled; alice's reservation intact.
        inspect = _ext(monkeypatch, tmp_path, user="alice",
                       action="escrow_inspect", lock_id=lock["lock_id"])
        assert inspect["lock"]["status"] == "locked"

    def test_refund_owner_allowed(self, tmp_path, monkeypatch):
        _init(tmp_path)
        lock = _ext(monkeypatch, tmp_path, user="alice",
                    action="escrow_lock", node_id="node-r2", escrow_amount=1000)
        result = _ext(monkeypatch, tmp_path, user="alice",
                      action="escrow_refund", lock_id=lock["lock_id"])
        assert result["status"] == "ok"
        assert result["disposition"] == "refunded"

    def test_refund_host_may_act_cross_actor(self, tmp_path, monkeypatch):
        _init(tmp_path)
        monkeypatch.setenv("UNIVERSE_SERVER_HOST_USER", "platform-host")
        lock = _ext(monkeypatch, tmp_path, user="alice",
                    action="escrow_lock", node_id="node-r3", escrow_amount=1000)
        # Host may refund another actor's lock on their behalf.
        result = _ext(monkeypatch, tmp_path, user="platform-host",
                      action="escrow_refund", lock_id=lock["lock_id"])
        assert result["status"] == "ok"
        assert result["disposition"] == "refunded"
        # Refund returns to the original staker (alice), not the host.
        assert result["refunded_to"] == "alice"


# ── Pure business logic unit tests ────────────────────────────────────────────

class TestPaymentsActionsUnit:
    def _conn(self, tmp_path):
        # storage._connect is a context manager (closes on exit); these unit
        # tests need a connection that stays open across multiple action calls,
        # so open a raw connection to the same DB path with matching pragmas.
        import sqlite3

        from workflow.daemon_server import initialize_author_server
        from workflow.payments.escrow import migrate_escrow_schema
        from workflow.storage import db_path
        initialize_author_server(tmp_path)
        conn = sqlite3.connect(str(db_path(tmp_path)), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        migrate_escrow_schema(conn)
        from workflow.payments.funding import credit_balance
        credit_balance(
            conn, staker_id="staker-1", amount=1_000_000,
            now_iso="2026-06-08T00:00:00+00:00",
        )
        return conn

    def test_action_lock_success(self, tmp_path):
        from workflow.payments.actions import action_escrow_lock
        conn = self._conn(tmp_path)
        result = action_escrow_lock(
            conn, node_id="n1", amount=100, claimer="staker-1"
        )
        assert result["status"] == "ok"
        assert result["amount"] == 100

    def test_action_lock_zero_rejected(self, tmp_path):
        from workflow.payments.actions import action_escrow_lock
        conn = self._conn(tmp_path)
        result = action_escrow_lock(
            conn, node_id="n1", amount=0, claimer="staker-1"
        )
        assert result["status"] == "rejected"

    def test_action_release_unknown_lock(self, tmp_path):
        from workflow.payments.actions import action_escrow_release
        conn = self._conn(tmp_path)
        result = action_escrow_release(
            conn, lock_id="no-such", recipient_id="r"
        )
        assert result["status"] == "rejected"

    def test_action_refund_unknown_lock(self, tmp_path):
        from workflow.payments.actions import action_escrow_refund
        conn = self._conn(tmp_path)
        result = action_escrow_refund(conn, lock_id="no-such")
        assert result["status"] == "rejected"

    def test_action_refund_rejects_non_owner(self, tmp_path):
        # CRITICAL round 2: caller_id that doesn't own the lock is rejected.
        from workflow.payments.actions import (
            action_escrow_lock,
            action_escrow_refund,
        )
        conn = self._conn(tmp_path)
        lock = action_escrow_lock(conn, node_id="n1", amount=100, claimer="staker-1")
        result = action_escrow_refund(
            conn, lock_id=lock["lock_id"], caller_id="attacker", host_id="host"
        )
        assert result["status"] == "rejected"
        assert "refund" in result["error"].lower()
        # Lock untouched.
        from workflow.payments.escrow import get_lock
        assert get_lock(conn, lock["lock_id"]).status == "locked"

    def test_action_refund_owner_allowed_with_caller_id(self, tmp_path):
        from workflow.payments.actions import (
            action_escrow_lock,
            action_escrow_refund,
        )
        conn = self._conn(tmp_path)
        lock = action_escrow_lock(conn, node_id="n2", amount=100, claimer="staker-1")
        result = action_escrow_refund(
            conn, lock_id=lock["lock_id"], caller_id="staker-1", host_id="host"
        )
        assert result["status"] == "ok"
        assert result["disposition"] == "refunded"

    def test_action_refund_no_caller_id_skips_auth(self, tmp_path):
        # Internal callers (caller_id=None) keep the pre-fix behavior.
        from workflow.payments.actions import (
            action_escrow_lock,
            action_escrow_refund,
        )
        conn = self._conn(tmp_path)
        lock = action_escrow_lock(conn, node_id="n3", amount=100, claimer="staker-1")
        result = action_escrow_refund(conn, lock_id=lock["lock_id"])
        assert result["status"] == "ok"

    def test_action_inspect_no_params(self, tmp_path):
        from workflow.payments.actions import action_escrow_inspect
        conn = self._conn(tmp_path)
        result = action_escrow_inspect(conn)
        assert result["status"] == "rejected"

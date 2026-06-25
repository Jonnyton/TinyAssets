"""E2E withdrawal-bridge tests through the extensions() MCP surface (Slice 1a).

set_wallet -> fund -> withdraw: spendable balance settles OUT via the configured
backend (internal marker by default; mock base_sepolia USDC under env), debiting
the off-chain balance and recording a settlement_batch + transaction_log entry.
No network — the base_sepolia backend uses the mock on-chain client.
"""

from __future__ import annotations

import json
from pathlib import Path

ADDR = "0x" + "1" * 40


def _init(base_path: Path) -> None:
    from workflow.daemon_server import initialize_author_server
    initialize_author_server(base_path)


def _ext(monkeypatch, tmp_path, *, user="alice", paid_market=True, backend=None, **kwargs):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_PAID_MARKET", "on" if paid_market else "off")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", user)
    if backend is not None:
        monkeypatch.setenv("WORKFLOW_SETTLEMENT_BACKEND", backend)
    else:
        monkeypatch.delenv("WORKFLOW_SETTLEMENT_BACKEND", raising=False)
    from workflow.universe_server import extensions
    return json.loads(extensions(**kwargs))


class TestWithdrawE2E:
    def test_set_wallet_fund_withdraw_internal(self, tmp_path, monkeypatch):
        _init(tmp_path)
        wallet = _ext(monkeypatch, tmp_path, action="escrow_set_wallet",
                      escrow_wallet_address=ADDR)
        assert wallet["status"] == "ok"
        assert wallet["address"] == ADDR

        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=1_000_000)
        wd = _ext(monkeypatch, tmp_path, action="escrow_withdraw", escrow_amount=600_000)
        assert wd["status"] == "ok"
        assert wd["backend"] == "internal"
        assert wd["tx_ref"].startswith("internal-")
        assert wd["amount"] == 600_000
        assert wd["recipient_wallet"] == ADDR
        assert wd["remaining_spendable"] == 400_000

        bal = _ext(monkeypatch, tmp_path, action="escrow_balance")
        assert bal["total"] == 400_000

    def test_withdraw_base_sepolia_mock(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path, action="escrow_set_wallet", escrow_wallet_address=ADDR)
        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=1_000_000)
        wd = _ext(monkeypatch, tmp_path, backend="base_sepolia",
                  action="escrow_withdraw", escrow_amount=1_000_000)
        assert wd["status"] == "ok"
        assert wd["backend"] == "base_sepolia"
        assert wd["settlement_status"] == "submitted"
        assert wd["tx_ref"].startswith("0xMOCK")
        assert wd["chain_id"] == 84532

    def test_withdraw_without_wallet_rejected(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=1_000_000)
        wd = _ext(monkeypatch, tmp_path, action="escrow_withdraw", escrow_amount=100)
        assert wd["status"] == "rejected"
        assert "payout wallet" in wd["error"].lower()

    def test_withdraw_insufficient_balance_rejected(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path, action="escrow_set_wallet", escrow_wallet_address=ADDR)
        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=100)
        wd = _ext(monkeypatch, tmp_path, action="escrow_withdraw", escrow_amount=1_000)
        assert wd["status"] == "rejected"
        assert "insufficient" in wd["error"].lower()
        # Balance untouched on rejection.
        bal = _ext(monkeypatch, tmp_path, action="escrow_balance")
        assert bal["total"] == 100

    def test_set_wallet_invalid_address_rejected(self, tmp_path, monkeypatch):
        _init(tmp_path)
        out = _ext(monkeypatch, tmp_path, action="escrow_set_wallet",
                   escrow_wallet_address="not-an-address")
        assert out["status"] == "rejected"
        assert "address" in out["error"].lower()

    def test_withdraw_requires_paid_market(self, tmp_path, monkeypatch):
        _init(tmp_path)
        out = _ext(monkeypatch, tmp_path, paid_market=False,
                   action="escrow_withdraw", escrow_amount=100)
        assert out["status"] == "not_available"


class TestWithdrawIdempotency:
    """slice1a review HIGH 4: a retry of a withdrawal (same idempotency key)
    must NOT debit balance or pay out twice."""

    def _count_batches(self, tmp_path, monkeypatch, batch_id):
        import sqlite3

        from workflow.storage import db_path
        conn = sqlite3.connect(str(db_path(tmp_path)))
        try:
            return conn.execute(
                "SELECT COUNT(*) FROM settlement_batch WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()[0]
        finally:
            conn.close()

    def test_retry_with_client_key_does_not_double_pay(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path, action="escrow_set_wallet",
             escrow_wallet_address=ADDR)
        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=1_000_000)

        first = _ext(monkeypatch, tmp_path, action="escrow_withdraw",
                     escrow_amount=600_000, escrow_idempotency_key="req-42")
        assert first["status"] == "ok"
        assert first.get("idempotent_replay") is False
        assert first["amount"] == 600_000

        bal_after_first = _ext(monkeypatch, tmp_path, action="escrow_balance")
        assert bal_after_first["total"] == 400_000

        # Client retries the SAME request (didn't see the first result).
        retry = _ext(monkeypatch, tmp_path, action="escrow_withdraw",
                     escrow_amount=600_000, escrow_idempotency_key="req-42")
        assert retry["status"] == "ok"
        assert retry["idempotent_replay"] is True
        assert retry["batch_id"] == first["batch_id"]
        assert retry["tx_ref"] == first["tx_ref"]

        # Balance debited exactly ONCE; one batch row only.
        bal_after_retry = _ext(monkeypatch, tmp_path, action="escrow_balance")
        assert bal_after_retry["total"] == 400_000
        assert self._count_batches(tmp_path, monkeypatch, first["batch_id"]) == 1

    def test_retry_without_client_key_dedups_same_shape(self, tmp_path, monkeypatch):
        """Without an explicit key, a same-shape retry (same actor/amount/
        wallet/chain) still maps to the same operation — the safe default."""
        _init(tmp_path)
        _ext(monkeypatch, tmp_path, action="escrow_set_wallet",
             escrow_wallet_address=ADDR)
        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=1_000_000)

        first = _ext(monkeypatch, tmp_path, action="escrow_withdraw",
                     escrow_amount=250_000)
        assert first["status"] == "ok"
        assert first.get("idempotent_replay") is False

        retry = _ext(monkeypatch, tmp_path, action="escrow_withdraw",
                     escrow_amount=250_000)
        assert retry["idempotent_replay"] is True
        assert retry["batch_id"] == first["batch_id"]

        bal = _ext(monkeypatch, tmp_path, action="escrow_balance")
        # Debited once (1_000_000 - 250_000), not twice.
        assert bal["total"] == 750_000

    def test_distinct_client_keys_allow_separate_withdrawals(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path, action="escrow_set_wallet",
             escrow_wallet_address=ADDR)
        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=1_000_000)

        a = _ext(monkeypatch, tmp_path, action="escrow_withdraw",
                 escrow_amount=200_000, escrow_idempotency_key="wd-a")
        b = _ext(monkeypatch, tmp_path, action="escrow_withdraw",
                 escrow_amount=200_000, escrow_idempotency_key="wd-b")
        assert a["status"] == "ok" and b["status"] == "ok"
        assert a["batch_id"] != b["batch_id"]
        assert b["idempotent_replay"] is False

        bal = _ext(monkeypatch, tmp_path, action="escrow_balance")
        # Two distinct withdrawals both debited.
        assert bal["total"] == 600_000


class TestWithdrawBackendFailureContract:
    """slice1a review HIGH — round 2: a withdrawal's response to a backend
    failure must depend on whether the payout was DEFINITIVELY-not-submitted
    (auto-refund + retryable) or UNKNOWN (in_doubt, never auto-refunded, retry
    never re-pays). These drive the action directly with an injected backend so
    we can simulate each failure mode without a network."""

    ADDR = "0x" + "c" * 40

    def _conn(self, tmp_path):
        import sqlite3

        from workflow.daemon_server import initialize_author_server
        from workflow.payments.escrow import migrate_escrow_schema
        from workflow.payments.funding import credit_balance
        from workflow.payments.wallets import set_payout_wallet
        from workflow.storage import db_path
        initialize_author_server(tmp_path)
        conn = sqlite3.connect(str(db_path(tmp_path)), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        migrate_escrow_schema(conn)
        credit_balance(
            conn, staker_id="alice", amount=1_000_000,
            now_iso="2026-06-08T00:00:00+00:00",
        )
        set_payout_wallet(
            conn, actor_id="alice", address=self.ADDR,
            now_iso="2026-06-08T00:00:00+00:00",
        )
        conn.commit()
        return conn

    def _inject_backend(self, monkeypatch, *, fail_mode):
        from workflow.payments import actions as actions_mod
        from workflow.payments.settlement_backend import (
            BaseSepoliaBackend,
            MockOnChainClient,
        )
        client = MockOnChainClient(fail_mode=fail_mode)
        backend = BaseSepoliaBackend(client=client)
        monkeypatch.setattr(actions_mod, "get_settlement_backend", lambda: backend)
        return client

    def _spendable(self, conn):
        from workflow.payments.funding import get_balance
        bal = get_balance(conn, staker_id="alice", currency="MicroToken")
        return bal.spendable_amount if bal else 0

    def test_definitive_failure_refunds_and_is_retryable(self, tmp_path, monkeypatch):
        from workflow.payments.actions import action_escrow_withdraw
        conn = self._conn(tmp_path)
        self._inject_backend(monkeypatch, fail_mode="not_submitted")

        out = action_escrow_withdraw(
            conn, actor_id="alice", amount=400_000,
            idempotency_key="wd-def",
        )
        assert out["status"] == "rejected"
        assert out["settlement_status"] == "not_submitted"
        assert out["refunded"] is True
        assert out["retryable"] is True
        # Balance fully restored — definitively no money moved.
        assert self._spendable(conn) == 1_000_000
        # No batch row left behind — a genuine retry can re-pay.
        assert conn.execute(
            "SELECT COUNT(*) FROM settlement_batch"
        ).fetchone()[0] == 0

        # Retry now succeeds (different backend that completes).
        from workflow.payments import actions as actions_mod
        from workflow.payments.settlement_backend import InternalBackend
        monkeypatch.setattr(
            actions_mod, "get_settlement_backend", lambda: InternalBackend()
        )
        retry = action_escrow_withdraw(
            conn, actor_id="alice", amount=400_000, idempotency_key="wd-def",
        )
        assert retry["status"] == "ok"
        assert self._spendable(conn) == 600_000

    def test_unknown_failure_goes_in_doubt_not_refunded(self, tmp_path, monkeypatch):
        from workflow.payments.actions import action_escrow_withdraw
        conn = self._conn(tmp_path)
        self._inject_backend(monkeypatch, fail_mode="unknown")

        out = action_escrow_withdraw(
            conn, actor_id="alice", amount=400_000, idempotency_key="wd-unk",
        )
        assert out["status"] == "in_doubt"
        assert out["settlement_status"] == "in_doubt"
        # NOT auto-refunded — balance stays debited pending reconciliation.
        assert self._spendable(conn) == 600_000
        # Batch row persists in in_doubt for reconciliation.
        row = conn.execute(
            "SELECT status FROM settlement_batch WHERE batch_id = ?",
            (out["batch_id"],),
        ).fetchone()
        assert row["status"] == "in_doubt"

    def test_unknown_failure_retry_does_not_double_pay(self, tmp_path, monkeypatch):
        from workflow.payments.actions import action_escrow_withdraw
        conn = self._conn(tmp_path)
        client = self._inject_backend(monkeypatch, fail_mode="unknown")

        first = action_escrow_withdraw(
            conn, actor_id="alice", amount=400_000, idempotency_key="wd-unk2",
        )
        assert first["status"] == "in_doubt"
        assert self._spendable(conn) == 600_000
        calls_after_first = len(client.calls)

        # A blind retry (even if the backend would now succeed) must NOT re-pay
        # or re-debit — it returns the in-doubt record unchanged.
        from workflow.payments import actions as actions_mod
        from workflow.payments.settlement_backend import (
            BaseSepoliaBackend,
            MockOnChainClient,
        )
        ok_client = MockOnChainClient()  # would succeed if called
        monkeypatch.setattr(
            actions_mod, "get_settlement_backend",
            lambda: BaseSepoliaBackend(client=ok_client),
        )
        retry = action_escrow_withdraw(
            conn, actor_id="alice", amount=400_000, idempotency_key="wd-unk2",
        )
        assert retry["status"] == "in_doubt"
        assert retry["idempotent_replay"] is True
        assert retry["batch_id"] == first["batch_id"]
        # No second debit.
        assert self._spendable(conn) == 600_000
        # The retry never reached the (would-succeed) backend.
        assert len(ok_client.calls) == 0
        # The original failing client saw exactly one submit attempt.
        assert len(client.calls) == calls_after_first
        # Still exactly one batch row.
        assert conn.execute(
            "SELECT COUNT(*) FROM settlement_batch WHERE batch_id = ?",
            (first["batch_id"],),
        ).fetchone()[0] == 1

    def test_committed_success_replay_dedups(self, tmp_path, monkeypatch):
        from workflow.payments import actions as actions_mod
        from workflow.payments.actions import action_escrow_withdraw
        from workflow.payments.settlement_backend import InternalBackend
        conn = self._conn(tmp_path)
        monkeypatch.setattr(
            actions_mod, "get_settlement_backend", lambda: InternalBackend()
        )

        first = action_escrow_withdraw(
            conn, actor_id="alice", amount=400_000, idempotency_key="wd-ok",
        )
        assert first["status"] == "ok"
        assert first["idempotent_replay"] is False
        assert self._spendable(conn) == 600_000

        replay = action_escrow_withdraw(
            conn, actor_id="alice", amount=400_000, idempotency_key="wd-ok",
        )
        assert replay["status"] == "ok"
        assert replay["idempotent_replay"] is True
        assert replay["batch_id"] == first["batch_id"]
        assert replay["tx_ref"] == first["tx_ref"]
        # Debited exactly once.
        assert self._spendable(conn) == 600_000

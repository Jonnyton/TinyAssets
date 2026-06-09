"""End-to-end off-chain money loop through the extensions() MCP surface.

Base-testnet money Slice 0 convergence: fund -> lock (reserve) -> release
(settle 1% + debit staker + credit recipient net) / refund (release reservation).
Proves the funding side (staker_escrow_budget) and the settlement side
(record_settlement + treasury) meet on one path, reflected by treasury_status.
"""

from __future__ import annotations

import json
from pathlib import Path


def _init(base_path: Path) -> None:
    from workflow.daemon_server import initialize_author_server
    initialize_author_server(base_path)


def _ext(monkeypatch, tmp_path, *, user: str = "alice", paid_market: bool = True, **kwargs):
    monkeypatch.setenv("WORKFLOW_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("WORKFLOW_PAID_MARKET", "on" if paid_market else "off")
    monkeypatch.setenv("UNIVERSE_SERVER_USER", user)
    from workflow.universe_server import extensions
    return json.loads(extensions(**kwargs))


class TestMoneyLoopE2E:
    def test_fund_lock_release_full_loop(self, tmp_path, monkeypatch):
        _init(tmp_path)

        # Fund alice's budget (off-chain / testnet faucet).
        fund = _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=1_000_000)
        assert fund["status"] == "ok"
        assert fund["total"] == 1_000_000
        assert fund["spendable"] == 1_000_000

        # Lock reserves the funded budget.
        lock = _ext(monkeypatch, tmp_path, action="escrow_lock",
                    node_id="node-1", escrow_amount=1_000_000)
        assert lock["status"] == "ok"
        bal = _ext(monkeypatch, tmp_path, action="escrow_balance")
        assert bal["reserved"] == 1_000_000
        assert bal["spendable"] == 0

        # Release: staker debited, recipient credited net, treasury takes 1%.
        rel = _ext(monkeypatch, tmp_path, action="escrow_release",
                   lock_id=lock["lock_id"], escrow_recipient_id="daemon-bob")
        assert rel["status"] == "ok"
        assert rel["net_amount"] == 990_000
        assert rel["treasury_fee"] == 10_000
        assert rel["bounty_share"] == 5_000
        assert rel["treasury_retained"] == 5_000

        # Staker's budget is now fully debited.
        alice = _ext(monkeypatch, tmp_path, action="escrow_balance")
        assert alice["total"] == 0
        assert alice["reserved"] == 0

        # Recipient earned the net into spendable budget (can re-stake).
        bob = _ext(monkeypatch, tmp_path, action="escrow_balance",
                   escrow_staker_id="daemon-bob")
        assert bob["total"] == 990_000
        assert bob["spendable"] == 990_000

        # treasury_status reflects the settlement + the platform take.
        from workflow.treasury.status import treasury_status
        status = treasury_status(str(tmp_path))
        assert status["cost_ledger"]["settlements"]["treasury_fee_total"] == 10_000
        assert status["cost_ledger"]["settlements"]["net_amount_total"] == 990_000
        assert status["treasury"]["fee_collected_total"] == 10_000
        assert status["treasury"]["bounty_pool_allocated_total"] == 5_000

    def test_fund_lock_refund_releases_reservation(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=1_000_000)
        lock = _ext(monkeypatch, tmp_path, action="escrow_lock",
                    node_id="node-1", escrow_amount=400_000)

        refund = _ext(monkeypatch, tmp_path, action="escrow_refund",
                      lock_id=lock["lock_id"], escrow_reason="abandoned")
        assert refund["status"] == "ok"
        assert refund["disposition"] == "refunded"

        # Reservation released; funds spendable again; no value left the budget.
        bal = _ext(monkeypatch, tmp_path, action="escrow_balance")
        assert bal["total"] == 1_000_000
        assert bal["reserved"] == 0
        assert bal["spendable"] == 1_000_000

        # No settlement / no treasury fee on a refund.
        from workflow.treasury.status import treasury_status
        status = treasury_status(str(tmp_path))
        assert status["cost_ledger"]["settlements"]["count_total"] == 0
        assert status["treasury"]["fee_collected_total"] == 0

    def test_lock_rejected_when_underfunded(self, tmp_path, monkeypatch):
        _init(tmp_path)
        _ext(monkeypatch, tmp_path, action="escrow_fund", escrow_amount=100)
        lock = _ext(monkeypatch, tmp_path, action="escrow_lock",
                    node_id="node-1", escrow_amount=1_000)
        assert lock["status"] == "rejected"
        assert "insufficient" in lock["error"].lower()
        # No lock created → budget untouched.
        bal = _ext(monkeypatch, tmp_path, action="escrow_balance")
        assert bal["reserved"] == 0
        assert bal["total"] == 100

    def test_fund_requires_paid_market(self, tmp_path, monkeypatch):
        _init(tmp_path)
        out = _ext(monkeypatch, tmp_path, paid_market=False,
                   action="escrow_fund", escrow_amount=1_000)
        assert out["status"] == "not_available"

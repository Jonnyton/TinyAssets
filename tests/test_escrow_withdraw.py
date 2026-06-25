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

"""Unit tests for the Slice 1 settlement backends (no network)."""

from __future__ import annotations

import pytest

from workflow.payments.settlement_backend import (
    BASE_SEPOLIA_CHAIN_ID,
    BaseSepoliaBackend,
    InternalBackend,
    MockOnChainClient,
    SettlementBackendError,
    get_settlement_backend,
)


class TestInternalBackend:
    def test_settle_returns_local_ref(self):
        out = InternalBackend().settle(
            recipient_wallet="0x" + "1" * 40, amount_base_units=990_000,
            currency="MicroToken", idempotency_key="wd-abc",
        )
        assert out["backend"] == "internal"
        assert out["status"] == "settled"
        assert out["tx_ref"] == "internal-wd-abc"
        assert out["amount"] == 990_000


class TestBaseSepoliaBackend:
    def test_mock_client_records_and_returns_tx_hash(self):
        client = MockOnChainClient()
        backend = BaseSepoliaBackend(client=client)
        out = backend.settle(
            recipient_wallet="0x" + "a" * 40, amount_base_units=500_000,
            currency="MicroToken", idempotency_key="wd-1",
        )
        assert out["backend"] == "base_sepolia"
        assert out["status"] == "submitted"
        assert out["tx_ref"].startswith("0xMOCK")
        assert out["chain_id"] == BASE_SEPOLIA_CHAIN_ID
        assert len(client.calls) == 1
        assert client.calls[0]["amount_base_units"] == 500_000
        assert client.calls[0]["to_address"] == "0x" + "a" * 40

    def test_requires_recipient_wallet(self):
        with pytest.raises(SettlementBackendError):
            BaseSepoliaBackend().settle(
                recipient_wallet="", amount_base_units=1, currency="MicroToken",
                idempotency_key="wd-x",
            )

    def test_deterministic_mock_hash(self):
        c = MockOnChainClient()
        h1 = c.send_erc20(to_address="0x" + "b" * 40, amount_base_units=1,
                          token_contract="0xUSDC", idempotency_key="same")
        c2 = MockOnChainClient()
        h2 = c2.send_erc20(to_address="0x" + "b" * 40, amount_base_units=1,
                           token_contract="0xUSDC", idempotency_key="same")
        assert h1 == h2


class TestBackendSelection:
    def test_default_internal(self, monkeypatch):
        monkeypatch.delenv("WORKFLOW_SETTLEMENT_BACKEND", raising=False)
        assert get_settlement_backend().name == "internal"

    def test_base_sepolia_selected(self, monkeypatch):
        monkeypatch.setenv("WORKFLOW_SETTLEMENT_BACKEND", "base_sepolia")
        backend = get_settlement_backend()
        assert backend.name == "base_sepolia"
        # Slice 1a: base_sepolia uses the mock client (no network).
        assert isinstance(backend, BaseSepoliaBackend)
        assert isinstance(backend.client, MockOnChainClient)

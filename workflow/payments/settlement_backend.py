"""Settlement backends — where an off-chain balance becomes a real payout.

Slice 0 keeps the off-chain ledger as source of truth. Slice 1 settles
accumulated balance OUT via a backend, selected by ``WORKFLOW_SETTLEMENT_BACKEND``:

  internal      (default) — ledger-only marker, no network. tx_ref = local id.
  base_sepolia            — ERC-20 USDC transfer on Base Sepolia. tx_ref = tx hash.

The backend is the only seam the on-chain world touches. In Slice 1a the
base_sepolia backend uses a MockOnChainClient (no web3, no network) so the whole
withdrawal path is testable; Slice 1b injects a real web3 client implementing the
same ``OnChainClient`` shape. ``internal`` mode never imports web3.

Amounts are integer base units. Base Sepolia USDC has 6 decimals, identical to
our MicroToken (1_000_000 / Token), so 1 MicroToken == 1 USDC base unit (1:1).
"""

from __future__ import annotations

import hashlib
import os
import uuid
from abc import ABC, abstractmethod
from typing import Any

# Circle official testnet USDC on Base Sepolia (chainId 84532), 6 decimals.
BASE_SEPOLIA_CHAIN_ID = 84532
BASE_SEPOLIA_USDC = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


class SettlementBackendError(Exception):
    """Raised when a settlement backend cannot complete a payout."""


class SettlementBackend(ABC):
    """Settles an amount to a recipient wallet, returning a tx reference."""

    name: str = "abstract"

    @abstractmethod
    def settle(
        self,
        *,
        recipient_wallet: str,
        amount_base_units: int,
        currency: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        """Return {tx_ref, backend, status, amount, recipient_wallet}."""


class InternalBackend(SettlementBackend):
    """Ledger-only settlement — no external network. The default backend."""

    name = "internal"

    def settle(
        self,
        *,
        recipient_wallet: str,
        amount_base_units: int,
        currency: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        return {
            "tx_ref": f"internal-{idempotency_key}",
            "backend": self.name,
            "status": "settled",
            "amount": amount_base_units,
            "recipient_wallet": recipient_wallet,
        }


class OnChainClient(ABC):
    """The on-chain transfer seam. Slice 1b provides a real web3 implementation;
    Slice 1a uses MockOnChainClient so the path is testable without a network."""

    @abstractmethod
    def send_erc20(
        self,
        *,
        to_address: str,
        amount_base_units: int,
        token_contract: str,
        idempotency_key: str,
    ) -> str:
        """Submit an ERC-20 transfer; return the transaction hash."""


class MockOnChainClient(OnChainClient):
    """No-network stand-in for the real web3 client. Records calls; returns a
    deterministic mock tx hash so tests assert without touching Base Sepolia."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def send_erc20(
        self,
        *,
        to_address: str,
        amount_base_units: int,
        token_contract: str,
        idempotency_key: str,
    ) -> str:
        self.calls.append(
            {
                "to_address": to_address,
                "amount_base_units": amount_base_units,
                "token_contract": token_contract,
                "idempotency_key": idempotency_key,
            }
        )
        digest = hashlib.sha256(
            f"{to_address}:{amount_base_units}:{idempotency_key}".encode()
        ).hexdigest()
        return f"0xMOCK{digest[:56]}"


class BaseSepoliaBackend(SettlementBackend):
    """Settles in testnet USDC on Base Sepolia via an OnChainClient.

    Slice 1a defaults to MockOnChainClient (no network). Slice 1b injects a real
    web3-backed client implementing OnChainClient.
    """

    name = "base_sepolia"

    def __init__(
        self,
        client: OnChainClient | None = None,
        *,
        token_contract: str = BASE_SEPOLIA_USDC,
    ) -> None:
        self.client = client or MockOnChainClient()
        self.token_contract = token_contract

    def settle(
        self,
        *,
        recipient_wallet: str,
        amount_base_units: int,
        currency: str,
        idempotency_key: str,
    ) -> dict[str, Any]:
        if not recipient_wallet:
            raise SettlementBackendError(
                "base_sepolia settlement requires a recipient wallet address."
            )
        tx_hash = self.client.send_erc20(
            to_address=recipient_wallet,
            amount_base_units=amount_base_units,
            token_contract=self.token_contract,
            idempotency_key=idempotency_key,
        )
        return {
            "tx_ref": tx_hash,
            "backend": self.name,
            "status": "submitted",
            "amount": amount_base_units,
            "recipient_wallet": recipient_wallet,
            "token_contract": self.token_contract,
            "chain_id": BASE_SEPOLIA_CHAIN_ID,
        }


def settlement_backend_name() -> str:
    """Read ``WORKFLOW_SETTLEMENT_BACKEND``. Default 'internal'."""
    return (os.environ.get("WORKFLOW_SETTLEMENT_BACKEND") or "internal").strip().lower()


def get_settlement_backend() -> SettlementBackend:
    """Return the configured backend. base_sepolia uses the mock client until
    Slice 1b injects a real web3 client."""
    name = settlement_backend_name()
    if name == "base_sepolia":
        return BaseSepoliaBackend()
    return InternalBackend()


def new_idempotency_key() -> str:
    """Generate a settlement idempotency key (also the withdrawal/batch id)."""
    return f"wd-{uuid.uuid4().hex}"

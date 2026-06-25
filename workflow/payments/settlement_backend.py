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
    """Raised when a settlement backend cannot complete a payout.

    The ``submitted`` flag encodes whether the payout transaction may have been
    submitted to the network before the error (slice1a review HIGH — round 2):

      * ``False`` — DEFINITIVELY not submitted. No money moved; the caller may
        safely auto-refund the debit and let a retry re-pay. Off-chain /
        local-only backends (internal marker, mock on-chain client, and
        pre-submit validation failures) use this.
      * ``None``  — UNKNOWN / ambiguous (e.g. a network timeout AFTER the
        broadcast). The payout MAY have landed. The caller must NOT auto-refund
        or blind-retry; the withdrawal goes to an ``in_doubt`` state for
        reconciliation. This is the safe default for a real on-chain backend.

    A real backend should only pass ``submitted=False`` when it is certain the
    transaction never reached the network (e.g. the request was rejected before
    broadcast). Any ambiguity must leave ``submitted`` as ``None``.
    """

    def __init__(self, *args: object, submitted: bool | None = None) -> None:
        super().__init__(*args)
        self.submitted = submitted


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
    deterministic mock tx hash so tests assert without touching Base Sepolia.

    ``fail_mode`` lets tests drive the failure contract (slice1a review HIGH —
    round 2):

      * ``None``                  — succeed (default).
      * ``"not_submitted"``       — raise DEFINITIVELY-not-submitted. Because the
        mock client never touches a network, a failure here cannot have
        broadcast anything, so this is the only honest signal the mock can give.
      * ``"unknown"``             — raise an ambiguous error (``submitted=None``)
        to exercise the in-doubt reconciliation path a real backend would hit.
    """

    def __init__(self, *, fail_mode: str | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.fail_mode = fail_mode

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
        if self.fail_mode == "not_submitted":
            # The mock client never reaches a network — a failure here is
            # certain to have moved no money, so it is safe to auto-refund.
            raise SettlementBackendError(
                "mock on-chain client: transaction was not submitted.",
                submitted=False,
            )
        if self.fail_mode == "unknown":
            # Simulate a real backend's ambiguous post-broadcast failure.
            raise SettlementBackendError(
                "mock on-chain client: settlement result is unknown.",
                submitted=None,
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
            # Pre-submit validation failure — nothing was broadcast, so this is
            # definitively-not-submitted and safe to auto-refund.
            raise SettlementBackendError(
                "base_sepolia settlement requires a recipient wallet address.",
                submitted=False,
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


def stable_idempotency_key(
    *,
    actor_id: str,
    amount: int,
    currency: str,
    chain_id: int,
    recipient_wallet: str,
    client_key: str | None = None,
) -> str:
    """Derive a STABLE withdrawal idempotency key from the request.

    A retry of an unknown-result withdrawal must map to the SAME key so a
    second debit/payout is detected and skipped (slice1a review HIGH 4). When
    the client supplies its own ``client_key`` (the recommended path), that is
    namespaced and used directly so distinct withdrawals of the same shape stay
    distinct. Without one, the key is derived deterministically from the request
    shape — same-shape requests are treated as the same operation, which is the
    safe default for "retry after I don't know if it landed".
    """
    if client_key:
        material = f"client:{client_key}"
    else:
        material = (
            f"{actor_id}|{amount}|{currency}|{chain_id}|{recipient_wallet}"
        )
    digest = hashlib.sha256(material.encode()).hexdigest()
    return f"wd-{digest[:48]}"

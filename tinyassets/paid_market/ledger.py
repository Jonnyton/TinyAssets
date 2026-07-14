"""Double-entry ledger core + settlement adapters — pure logic (Wave 2).

This is the seam where every market module meets persistence, and the
single most bug-prone surface in the whole system if hand-rolled per
call-site. The rules, enforced here so transport cannot break them:

  * **Every transaction zero-sums.** A transaction is a list of
    (account, delta) entries whose deltas sum to exactly zero. Money
    moves; it is never created or destroyed by a posting.
  * **No internal account goes negative.** Applying a transaction
    that would overdraw any internal account fails atomically (no
    partial application). Accounts under the ``external:`` prefix are
    SYSTEM-BOUNDARY contra accounts (fiat/chain on-ramps and
    off-ramps): money entering the system posts as a negative there,
    so they are exempt from the overdraft check by design — their
    (negative) balance is the audit total of net inflows.
  * **Escrow is an account, not a status flag.** Locking funds moves
    them into ``escrow:<id>``; settlement drains that account to
    exactly zero. A non-empty escrow after settlement is a caught
    fault, not a silent leak.
  * **Adapters, not hand-postings.** Every settlement dataclass in
    this package converts to postings via one adapter here. The
    adapters lean on the settlement types' own conservation
    invariants, then the ledger re-verifies zero-sum independently —
    two layers, both fail-loud.

Account naming convention (strings, hierarchical):
  ``user:<id>`` | ``escrow:<id>`` | ``collateral:<id>`` | ``treasury``
  | ``pool:<id>`` | ``external:funding`` (fiat/chain on-ramp source).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from tinyassets.paid_market.fabrication import PhysicalSettlement
from tinyassets.paid_market.forwards import Settlement
from tinyassets.paid_market.pool import PoolAccounting
from tinyassets.paid_market.training import TrainingSettlement

__all__ = [
    "LedgerError",
    "Ledger",
    "escrow_lock_entries",
    "forward_sale_entries",
    "forward_settlement_entries",
    "training_settlement_entries",
    "physical_settlement_entries",
    "pool_close_entries",
]


class LedgerError(ValueError):
    """Raised on invalid postings or overdraft."""


Entry = tuple[str, int]  # (account, delta_micros)


def _validate_entries(entries: list[Entry]) -> None:
    if not entries:
        raise LedgerError("transaction must contain entries")
    total = 0
    for acct, delta in entries:
        if not isinstance(acct, str) or not acct:
            raise LedgerError("account must be a non-empty string")
        if not isinstance(delta, int) or isinstance(delta, bool):
            raise LedgerError("delta must be int")
        total += delta
    if total != 0:
        raise LedgerError(f"transaction does not zero-sum (residual {total})")


@dataclass
class Ledger:
    """In-memory balance book. Transport persists transactions; this
    class defines what a VALID transaction is and applies atomically."""

    balances: dict[str, int] = field(default_factory=dict)

    def balance(self, account: str) -> int:
        return self.balances.get(account, 0)

    def apply(self, entries: list[Entry], memo: str = "") -> None:
        _validate_entries(entries)
        # Net per account first (a transaction may touch one account
        # multiple times), then check overdrafts against the NET result
        # so ordering inside a transaction cannot matter.
        net: dict[str, int] = {}
        for acct, delta in entries:
            net[acct] = net.get(acct, 0) + delta
        for acct, delta in net.items():
            if acct.startswith("external:"):
                continue  # boundary contra account: may go negative
            if self.balance(acct) + delta < 0:
                raise LedgerError(
                    f"overdraft on {acct!r} "
                    f"(balance {self.balance(acct)}, delta {delta}) [{memo}]"
                )
        for acct, delta in net.items():
            self.balances[acct] = self.balance(acct) + delta

    def assert_drained(self, account: str) -> None:
        """Escrow/collateral accounts must be exactly empty after
        settlement — a residue is a leaked-funds fault."""
        if self.balance(account) != 0:
            raise LedgerError(
                f"account {account!r} not drained: {self.balance(account)}"
            )


# ------------------------------------------------------------- adapters


def escrow_lock_entries(
    *, payer_account: str, escrow_account: str, amount_micros: int
) -> list[Entry]:
    if not isinstance(amount_micros, int) or isinstance(amount_micros, bool):
        raise LedgerError("amount_micros must be int")
    if amount_micros <= 0:
        raise LedgerError("amount_micros must be > 0")
    return [(payer_account, -amount_micros), (escrow_account, amount_micros)]


def forward_sale_entries(
    *,
    buyer_account: str,
    seller_account: str,
    goods_escrow: str,
    collateral_escrow: str,
    total_micros: int,
    collateral_micros: int,
) -> list[Entry]:
    """At purchase: buyer's price into goods escrow; seller's
    collateral into collateral escrow."""
    e = escrow_lock_entries(
        payer_account=buyer_account,
        escrow_account=goods_escrow,
        amount_micros=total_micros,
    )
    e += escrow_lock_entries(
        payer_account=seller_account,
        escrow_account=collateral_escrow,
        amount_micros=collateral_micros,
    )
    return e


def forward_settlement_entries(
    s: Settlement,
    *,
    goods_escrow: str,
    collateral_escrow: str,
    seller_account: str,
    buyer_account: str,
    treasury_account: str = "treasury",
) -> list[Entry]:
    """Drains both escrows exactly (the Settlement's own conservation
    invariants guarantee it; the ledger re-verifies zero-sum)."""
    s.check_invariants()
    return [
        (goods_escrow, -s.buyer_paid_total),
        (seller_account, s.seller_net),
        (treasury_account, s.treasury_fee),
        (buyer_account, s.buyer_refund),
        (collateral_escrow, -s.collateral_locked),
        (seller_account, s.collateral_released),
        (buyer_account, s.slash_to_buyer),
    ]


def training_settlement_entries(
    s: TrainingSettlement,
    *,
    goods_escrow: str,
    collateral_escrow: str,
    seller_account: str,
    buyer_account: str,
    treasury_account: str = "treasury",
) -> list[Entry]:
    s.check_invariants()
    return [
        (goods_escrow, -s.buyer_paid_total),
        (seller_account, s.seller_net),
        (treasury_account, s.treasury_fee),
        (buyer_account, s.buyer_refund),
        (collateral_escrow, -s.collateral_locked),
        (seller_account, s.collateral_released),
        (buyer_account, s.slash_to_buyer),
    ]


def physical_settlement_entries(
    s: PhysicalSettlement,
    *,
    escrow_account: str,
    seller_account: str,
    buyer_account: str,
    treasury_account: str = "treasury",
) -> list[Entry]:
    """Physical jobs escrow goods+shipping together; no collateral."""
    s.check_invariants()
    total_in = s.goods_paid_total + s.shipping_paid_total
    return [
        (escrow_account, -total_in),
        (seller_account, s.seller_net),
        (treasury_account, s.treasury_fee),
        (buyer_account, s.buyer_refund),
    ]


def pool_close_entries(
    acct: PoolAccounting,
    *,
    pool_account: str,
    escrow_prefix: str,
    user_prefix: str = "user:",
) -> list[Entry]:
    """Close a funding pool. Each contributor's escrow account
    (``<escrow_prefix><contributor>``) drains fully: accepted value to
    the pool account, refunds back to the user. Works for both filled
    and failed pools (a failed pool has empty ``accepted``)."""
    entries: list[Entry] = []
    contributors = sorted(set(acct.accepted) | set(acct.refunds))
    for who in contributors:
        a = acct.accepted.get(who, 0)
        r = acct.refunds.get(who, 0)
        entries.append((f"{escrow_prefix}{who}", -(a + r)))
        if a:
            entries.append((pool_account, a))
        if r:
            entries.append((f"{user_prefix}{who}", r))
    return entries

"""Typed identifiers and currency unit for the payments subsystem.

MicroToken is the smallest indivisible currency unit (like satoshis for BTC).
All amounts in the payment system use integer MicroTokens — no floats, ever.

Typed ID wrappers prevent mixing up run_id / node_id / actor_id in settlement
keys. They are str subclasses so they serialize naturally to JSON/SQLite.
"""

from __future__ import annotations

# ── Currency unit ─────────────────────────────────────────────────────────────

class MicroToken(int):
    """Smallest indivisible currency unit. Immutable int subclass.

    1 Token = 1_000_000 MicroTokens (same convention as USDC / most ERC-20s).
    Platform treasury fee = 1% of every settlement = amount // 100 MicroTokens.
    Batch settlement threshold = amounts < BATCH_THRESHOLD_MICROTOKENS are
    deferred to a batch rather than settled one-by-one.
    """

    MICROTOKENS_PER_TOKEN: int = 1_000_000
    TREASURY_FEE_BASIS_POINTS: int = 100  # 100 bp = 1%
    BATCH_THRESHOLD: int = 1_000_000  # defer settlements < 1 Token

    def __new__(cls, value: int) -> MicroToken:
        if value < 0:
            raise ValueError(f"MicroToken must be >= 0, got {value!r}")
        return super().__new__(cls, value)

    def treasury_fee(self) -> MicroToken:
        """Compute the 1% treasury fee for this amount."""
        fee = int(self) * self.TREASURY_FEE_BASIS_POINTS // 10_000
        return MicroToken(fee)

    def net_after_fee(self) -> MicroToken:
        """Amount after deducting treasury fee."""
        return MicroToken(int(self) - int(self.treasury_fee()))

    def is_batchable(self) -> bool:
        """True when amount is below the batch settlement threshold."""
        return int(self) < self.BATCH_THRESHOLD

    def __repr__(self) -> str:
        return f"MicroToken({int(self)})"

    def __add__(self, other: object) -> MicroToken:  # type: ignore[override]
        if isinstance(other, int):
            return MicroToken(int(self) + other)
        return NotImplemented

    def __sub__(self, other: object) -> MicroToken:  # type: ignore[override]
        if isinstance(other, int):
            result = int(self) - other
            if result < 0:
                raise ValueError(
                    f"MicroToken subtraction would go negative: "
                    f"{int(self)} - {other} = {result}"
                )
            return MicroToken(result)
        return NotImplemented


# ── Typed string IDs ──────────────────────────────────────────────────────────

class RunId(str):
    """Typed wrapper for a branch run identifier."""

    def __repr__(self) -> str:
        return f"RunId({str(self)!r})"


class NodeId(str):
    """Typed wrapper for a node definition identifier."""

    def __repr__(self) -> str:
        return f"NodeId({str(self)!r})"


class ActorId(str):
    """Typed wrapper for a daemon / user actor identifier.

    Used as both staker_id (the requester who offered payment) and
    recipient_id (the daemon that completed the work).
    """

    def __repr__(self) -> str:
        return f"ActorId({str(self)!r})"


class SettlementKey(str):
    """Composite key identifying a unique settlement event.

    Convention: ``<run_id>:<node_id>:<actor_id>:<event_type>``
    Callers build this via ``SettlementKey.build()``.
    """

    @classmethod
    def build(
        cls,
        run_id: str,
        node_id: str,
        actor_id: str,
        event_type: str,
    ) -> SettlementKey:
        parts = [run_id, node_id, actor_id, event_type]
        for i, p in enumerate(parts):
            if ":" in p:
                raise ValueError(
                    f"SettlementKey component at index {i} must not contain ':': {p!r}"
                )
        return cls(":".join(parts))

    def __repr__(self) -> str:
        return f"SettlementKey({str(self)!r})"

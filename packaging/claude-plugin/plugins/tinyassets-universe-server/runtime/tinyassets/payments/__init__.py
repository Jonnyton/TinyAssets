"""tinyassets.payments — Payment, escrow, and settlement primitives.

Escrow layer (escrow.py): budget-lock / release / refund for gate bonus staking.
Settlement layer (schema.py): escrow_balance / pending_settlement / batch / tx_log.
Identifiers (identifiers.py): MicroToken int newtype + typed ID wrappers.
MCP action wiring (universe_server.py extensions) comes in a follow-up
once universe_server.py exits the dirty-tree sweep.
"""

from tinyassets.payments.escrow import (
    ESCROW_SCHEMA,
    DuplicateLockError,
    EscrowError,
    EscrowLock,
    EscrowStatus,
    LockAlreadyResolvedError,
    LockNotFoundError,
    UnauthorizedUnstakeError,
    get_lock,
    get_lock_for_claim,
    list_locks_for_claim,
    lock_bonus,
    migrate_escrow_schema,
    refund_bonus,
    release_bonus,
)
from tinyassets.payments.identifiers import (
    ActorId,
    MicroToken,
    NodeId,
    RunId,
    SettlementKey,
)
from tinyassets.payments.schema import (
    SETTLEMENT_SCHEMA,
    BatchedTransaction,
    BatchStatus,
    EscrowBalanceStatus,
    EscrowEntry,
    Settlement,
    SettlementStatus,
    TransactionKind,
    migrate_settlement_schema,
)

__all__ = [
    # escrow.py — gate bonus staking
    "ESCROW_SCHEMA",
    "DuplicateLockError",
    "EscrowError",
    "EscrowLock",
    "EscrowStatus",
    "LockAlreadyResolvedError",
    "LockNotFoundError",
    "UnauthorizedUnstakeError",
    "get_lock",
    "get_lock_for_claim",
    "list_locks_for_claim",
    "lock_bonus",
    "migrate_escrow_schema",
    "refund_bonus",
    "release_bonus",
    # identifiers.py
    "ActorId",
    "MicroToken",
    "NodeId",
    "RunId",
    "SettlementKey",
    # schema.py — settlement layer
    "SETTLEMENT_SCHEMA",
    "BatchStatus",
    "BatchedTransaction",
    "EscrowBalanceStatus",
    "EscrowEntry",
    "Settlement",
    "SettlementStatus",
    "TransactionKind",
    "migrate_settlement_schema",
]

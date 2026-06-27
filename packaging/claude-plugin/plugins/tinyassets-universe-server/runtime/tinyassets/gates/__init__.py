"""tinyassets.gates — Gate bonus primitives.

Schema layer (this module): GateBonusClaim, migrate_gate_bonus_columns.
MCP action wiring (follow-up): claim/unstake/release helpers in gates.actions
(pending universe_server.py sweep).
"""

from tinyassets.gates.schema import (
    BONUS_COLUMNS,
    AttachmentScope,
    GateBonusClaim,
    migrate_gate_bonus_columns,
)

__all__ = [
    "AttachmentScope",
    "BONUS_COLUMNS",
    "GateBonusClaim",
    "migrate_gate_bonus_columns",
]

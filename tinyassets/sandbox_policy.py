"""Execution-scope contract shared by run and sandbox chokepoints.

This is the S5 side of the S3 ``ExecutionScope`` seam.  S3 owns the broader
sandbox policy module; keeping the type name, states, fields, and factories
identical makes the integration merge a direct import unification rather than a
third credential-gate mechanism.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class ScopeKind(str, Enum):
    """The three authoritative scope states."""

    BOUND = "bound"
    LEGACY_UNBOUND = "legacy_unbound"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class ExecutionScope:
    """Authoritative tenant scope carried explicitly to execution."""

    kind: ScopeKind
    universe_dir: str | None = None

    @classmethod
    def bound(cls, universe_dir: str | Any) -> "ExecutionScope":
        text = str(universe_dir).strip() if universe_dir is not None else ""
        if not text:
            return cls(kind=ScopeKind.UNKNOWN)
        return cls(kind=ScopeKind.BOUND, universe_dir=text)

    @classmethod
    def legacy_unbound(cls) -> "ExecutionScope":
        return cls(kind=ScopeKind.LEGACY_UNBOUND)

    @classmethod
    def unknown(cls) -> "ExecutionScope":
        return cls(kind=ScopeKind.UNKNOWN)

    @classmethod
    def coerce(cls, value: "ExecutionScope | None") -> "ExecutionScope":
        return value if isinstance(value, cls) else cls.unknown()

    @property
    def is_bound(self) -> bool:
        return self.kind is ScopeKind.BOUND

    @property
    def is_unknown(self) -> bool:
        return self.kind is ScopeKind.UNKNOWN

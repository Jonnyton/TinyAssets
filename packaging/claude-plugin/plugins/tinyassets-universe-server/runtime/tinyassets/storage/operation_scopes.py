"""User-defined operation scopes: what a kind of automation work may spend.

Why this is storage and not a constant
--------------------------------------
An automation declares which OPERATIONS it may perform
(``ProviderWorkBinding.allowed_operations``, chosen by whoever built it). Those
operation names then have to mean something in capability terms, and the first
version of that meaning was a dict in platform code — so the platform still
owned the vocabulary, and a user building a new kind of automation could not
express what it needed.

Host correction 2026-08-07: *"seems users should also be able to make operation
scopes."* So the mapping is data, owned per universe.

The ceiling, which is the whole safety argument
-----------------------------------------------
A user-defined scope is a self-declaration, and a self-declaration that can
confer anything is privilege escalation with extra steps. Two bounds, both
enforced at DEFINE time so the failure is loud and early rather than at some
later run:

1. Only scopes in :data:`DELEGABLE_SCOPES` may ever appear. A founder may confer
   on their own automations a subset of what a founder can do — never
   platform-operator scopes like ``cloud_worker``.
2. Definitions are per-universe and written through the authority-checked action
   layer, so a caller can only define scopes for a universe they own.

The workspace file tools deliberately cannot reach this. If a universe could
define its own operation scopes by writing a file in its own directory, an agent
with file access would be able to grant itself anything — the containment would
hold and the authority would leak straight through it.
"""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tinyassets.storage import db_path

_OPERATION = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")

#: Scopes a founder may confer on their OWN automations. Deliberately narrow:
#: everything here is something the founder could already do themselves, so a
#: definition can only ever re-express existing authority, never widen it.
#: Operator/infrastructure scopes (``cloud_worker``, ``desktop``, …) are absent
#: on purpose and adding one is a security decision, not a convenience.
DELEGABLE_SCOPES: frozenset[str] = frozenset(
    {
        "tinyassets.extensions.costly",
        # Authoring a branch is composing work, not spending compute. Separate
        # from `costly` on purpose: a founder may well want an agent that can
        # DESIGN automations but not run them, or the reverse.
        "tinyassets.extensions.write",
        "tinyassets.knowledge",
        "tinyassets.memory",
        "tinyassets.planning",
        "tinyassets.evaluation",
        "tinyassets.learning",
        "tinyassets.constraints",
    }
)

#: Shipped defaults. NOT policy — a starting vocabulary a user may extend or
#: override for their own universe, the same way a harness template seeds files.
BUILTIN_OPERATION_SCOPES: dict[str, tuple[str, ...]] = {
    "repository_spec_delivery": ("tinyassets.extensions.costly",),
    # Composing the work itself. A user who wants their agent to BUILD new
    # automations declares this; one who only wants it to run existing ones
    # does not.
    "branch_authoring": ("tinyassets.extensions.write",),
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS operation_scopes (
    universe_id TEXT NOT NULL,
    operation TEXT NOT NULL,
    scopes_json TEXT NOT NULL,
    defined_by TEXT NOT NULL,
    defined_at REAL NOT NULL,
    PRIMARY KEY (universe_id, operation)
);
"""


class OperationScopeError(ValueError):
    """The definition was refused. Message reaches the model — keep it useful."""


@dataclass(frozen=True, slots=True)
class OperationScope:
    universe_id: str
    operation: str
    scopes: tuple[str, ...]
    defined_by: str


class OperationScopeStore:
    """Per-universe operation vocabulary."""

    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path(self.base_path))
        conn.row_factory = sqlite3.Row
        return conn

    def define(
        self, *, universe_id: str, operation: str, scopes: list[str], defined_by: str
    ) -> OperationScope:
        """Define what one operation may spend, or raise.

        Refuses a non-delegable scope outright rather than silently dropping it:
        a definition that quietly loses half its scopes would run, fail later,
        and look like a platform fault.
        """
        uid = (universe_id or "").strip()
        name = (operation or "").strip().lower()
        actor = (defined_by or "").strip()
        if not uid or not actor:
            raise OperationScopeError("universe and definer are required")
        if _OPERATION.fullmatch(name) is None:
            raise OperationScopeError(
                "operation must be lowercase letters, digits and underscores"
            )
        if not isinstance(scopes, list) or not scopes:
            raise OperationScopeError("declare at least one scope")
        requested = []
        for scope in scopes:
            if not isinstance(scope, str) or not scope.strip():
                raise OperationScopeError("each scope must be a non-empty string")
            value = scope.strip()
            if value not in DELEGABLE_SCOPES:
                raise OperationScopeError(
                    f"scope {value!r} cannot be delegated to an automation; "
                    f"allowed: {', '.join(sorted(DELEGABLE_SCOPES))}"
                )
            requested.append(value)
        ordered = tuple(sorted(set(requested)))

        import time

        with self._connect() as conn:
            conn.execute(
                "INSERT INTO operation_scopes"
                " (universe_id, operation, scopes_json, defined_by, defined_at)"
                " VALUES (?,?,?,?,?)"
                " ON CONFLICT(universe_id, operation) DO UPDATE SET"
                " scopes_json=excluded.scopes_json, defined_by=excluded.defined_by,"
                " defined_at=excluded.defined_at",
                (uid, name, json.dumps(list(ordered)), actor, time.time()),
            )
        return OperationScope(
            universe_id=uid, operation=name, scopes=ordered, defined_by=actor
        )

    def scopes_for(self, *, universe_id: str, operation: str) -> tuple[str, ...]:
        """This universe's definition, else the shipped default, else nothing."""
        name = (operation or "").strip().lower()
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT scopes_json FROM operation_scopes"
                    " WHERE universe_id = ? AND operation = ?",
                    ((universe_id or "").strip(), name),
                ).fetchone()
        except sqlite3.Error:
            row = None
        if row is not None:
            try:
                stored = json.loads(row["scopes_json"])
            except (TypeError, ValueError):
                stored = []
            # Re-filter on read. A scope that was delegable when defined must not
            # keep working if it is removed from DELEGABLE_SCOPES later.
            return tuple(
                sorted(
                    s for s in stored
                    if isinstance(s, str) and s in DELEGABLE_SCOPES
                )
            )
        return BUILTIN_OPERATION_SCOPES.get(name, ())

    def list_for(self, *, universe_id: str) -> list[OperationScope]:
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT operation, scopes_json, defined_by FROM operation_scopes"
                    " WHERE universe_id = ? ORDER BY operation",
                    ((universe_id or "").strip(),),
                ).fetchall()
        except sqlite3.Error:
            rows = []
        defined = [
            OperationScope(
                universe_id=universe_id,
                operation=row["operation"],
                scopes=tuple(json.loads(row["scopes_json"])),
                defined_by=row["defined_by"],
            )
            for row in rows
        ]
        names = {item.operation for item in defined}
        for name, scopes in BUILTIN_OPERATION_SCOPES.items():
            if name not in names:
                defined.append(
                    OperationScope(
                        universe_id=universe_id, operation=name,
                        scopes=scopes, defined_by="builtin",
                    )
                )
        return sorted(defined, key=lambda item: item.operation)


__all__ = [
    "BUILTIN_OPERATION_SCOPES",
    "DELEGABLE_SCOPES",
    "OperationScope",
    "OperationScopeError",
    "OperationScopeStore",
]

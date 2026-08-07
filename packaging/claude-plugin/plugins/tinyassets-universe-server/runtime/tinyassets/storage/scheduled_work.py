"""Automations of ANY kind: schedule + branch + inputs + operations + delivery.

Why this exists
---------------
`api/cloud_automations.py` builds exactly one thing — a
`RepositorySpecWorkDefinition`, with `repository` / `accepted_spec_ref` /
`branch_version_id` all required. That makes the one shipped workflow buildable
and every other one impossible. Asked live on 2026-08-07 for a niche-watching
post-drafting automation, the agent made zero tool calls, because there was no
capability behind the request.

The fix is NOT a `CryptoWalletWorkDefinition` beside the repository one, then a
CRM one, then a social one. That is the same pre-built-complexity mistake a
domain wider. What a user actually needs is the smallest primitive that composes:

    kind + branch + inputs + cadence + declared operations

A branch is already the unit of work users build and remix, and `run_branch`
already executes one on the founder's own compute. So an automation of any kind
is "run this branch, on this schedule, with these inputs, spending exactly what
its declared operations allow". A crypto-trading automation and a CRM automation
differ in their BRANCH and their DECLARED OPERATIONS, not in platform code.

`kind` is a free label the user chooses. It is deliberately not an enum: the
moment the platform enumerates kinds, adding one becomes our job again.

Delivery
--------
``deliver_to`` is where the DELIVERABLE lands — a Slack channel or DM id today.
An automation whose output goes nowhere is a cron job nobody reads, and the
whole point is that a founder receives the thing in the app they already use.
The transport already exists (`app_outbound_adapter` + `build_slack_transport`,
the same path `deliver_app_event` posts replies through), so delivery is a
DESTINATION the automation declares, not new machinery.

The reply to a delivered artifact arrives back through the ordinary chat ingress
as a `message` event, which is what makes the loop closable: the founder answers
the deliverable in the same thread, and that answer is already an input the
universe receives. Tying that reply to the RUN that produced it is the next
piece — see the note in ideas/INBOX.md.

Authority
---------
`declared_operations` feeds the same `operation_scopes` translation the provider
bindings use, so a scheduled work item can only ever spend what its operations
were defined to spend — and those definitions are themselves ceiling-bounded.
Nothing here grants anything on its own.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from tinyassets.ids import new_ulid
from tinyassets.storage import db_path

_LABEL = re.compile(r"[a-z][a-z0-9_]{2,63}\Z")
_STATES = ("active", "paused")

#: Below a minute a "schedule" is a busy loop. Matches the repo-spec floor.
MIN_CADENCE_SECONDS = 60


class ScheduledWorkError(ValueError):
    """The request was refused. Message reaches the model — keep it actionable."""


@dataclass(frozen=True, slots=True)
class ScheduledWork:
    work_id: str
    universe_id: str
    name: str
    kind: str
    branch_def_id: str
    inputs_json: str
    cadence_seconds: int
    declared_operations: tuple[str, ...]
    state: str
    revision: int
    owner_id: str
    deliver_to: str = ""

    def as_dict(self) -> dict:
        return {
            "work_id": self.work_id,
            "name": self.name,
            "kind": self.kind,
            "branch_def_id": self.branch_def_id,
            "inputs_json": self.inputs_json,
            "cadence_seconds": self.cadence_seconds,
            "declared_operations": list(self.declared_operations),
            "deliver_to": self.deliver_to,
            "state": self.state,
            "revision": self.revision,
        }


_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_work (
    work_id TEXT PRIMARY KEY,
    universe_id TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    branch_def_id TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    cadence_seconds INTEGER NOT NULL CHECK (cadence_seconds >= 60),
    declared_operations_json TEXT NOT NULL,
    deliver_to TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL CHECK (state IN ('active','paused')),
    revision INTEGER NOT NULL CHECK (revision >= 1),
    owner_id TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    last_run_at REAL,
    last_run_id TEXT,
    UNIQUE (universe_id, name)
);
CREATE INDEX IF NOT EXISTS idx_scheduled_work_universe
    ON scheduled_work(universe_id, state);
"""


class ScheduledWorkStore:
    def __init__(self, base_path: str | Path) -> None:
        self.base_path = Path(base_path)
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(db_path(self.base_path))
        conn.row_factory = sqlite3.Row
        return conn

    def create(
        self, *, universe_id: str, name: str, kind: str, branch_def_id: str,
        inputs_json: str = "", cadence_seconds: int = 3600,
        declared_operations: list[str] | None = None, owner_id: str,
        deliver_to: str = "",
    ) -> ScheduledWork:
        uid = (universe_id or "").strip()
        label = (name or "").strip().lower()
        kind_label = (kind or "").strip().lower()
        branch = (branch_def_id or "").strip()
        owner = (owner_id or "").strip()
        if not uid or not owner:
            raise ScheduledWorkError("universe and owner are required")
        for value, field in ((label, "name"), (kind_label, "kind")):
            if _LABEL.fullmatch(value) is None:
                raise ScheduledWorkError(
                    f"{field} must be lowercase letters, digits and underscores"
                )
        if not branch:
            raise ScheduledWorkError(
                "branch_def_id is required — an automation runs a branch, and "
                "the branch is where the actual work lives"
            )
        try:
            cadence = int(cadence_seconds)
        except (TypeError, ValueError) as exc:
            raise ScheduledWorkError("cadence_seconds must be a number") from exc
        if cadence < MIN_CADENCE_SECONDS:
            raise ScheduledWorkError(
                f"cadence_seconds must be at least {MIN_CADENCE_SECONDS}"
            )
        payload = (inputs_json or "").strip() or "{}"
        try:
            parsed = json.loads(payload)
        except (TypeError, ValueError) as exc:
            raise ScheduledWorkError("inputs_json must be valid JSON") from exc
        if not isinstance(parsed, dict):
            raise ScheduledWorkError("inputs_json must be a JSON object")
        operations = tuple(
            sorted(
                {
                    str(op).strip().lower()
                    for op in (declared_operations or [])
                    if str(op).strip()
                }
            )
        )

        work_id = f"work_{new_ulid()}"
        now = time.time()
        try:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO scheduled_work (work_id, universe_id, name, kind,"
                    " branch_def_id, inputs_json, cadence_seconds,"
                    " declared_operations_json, deliver_to, state, revision,"
                    " owner_id, created_at, updated_at)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (work_id, uid, label, kind_label, branch, json.dumps(parsed),
                     cadence, json.dumps(list(operations)),
                     (deliver_to or "").strip(), "paused", 1, owner, now, now),
                )
        except sqlite3.IntegrityError as exc:
            raise ScheduledWorkError(
                f"an automation named {label!r} already exists here"
            ) from exc
        # Created PAUSED on purpose: something that starts spending the founder's
        # compute the instant it is described is a surprise, not a feature.
        return ScheduledWork(
            work_id=work_id, universe_id=uid, name=label, kind=kind_label,
            branch_def_id=branch, inputs_json=json.dumps(parsed),
            cadence_seconds=cadence, declared_operations=operations,
            state="paused", revision=1, owner_id=owner,
            deliver_to=(deliver_to or "").strip(),
        )

    def list_for(self, *, universe_id: str) -> list[ScheduledWork]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM scheduled_work WHERE universe_id = ? ORDER BY name",
                ((universe_id or "").strip(),),
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, *, universe_id: str, work_id: str) -> ScheduledWork | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM scheduled_work WHERE universe_id = ? AND work_id = ?",
                ((universe_id or "").strip(), (work_id or "").strip()),
            ).fetchone()
        return self._row(row) if row is not None else None

    def set_state(
        self, *, universe_id: str, work_id: str, state: str, expected_revision: int
    ) -> ScheduledWork:
        """Pause or resume, with optimistic concurrency.

        `expected_revision` is required for the same reason it is on the
        repo-spec surface: without it a control call silently no-ops while
        reporting a result.
        """
        target = (state or "").strip().lower()
        if target not in _STATES:
            raise ScheduledWorkError(f"state must be one of: {', '.join(_STATES)}")
        current = self.get(universe_id=universe_id, work_id=work_id)
        if current is None:
            raise ScheduledWorkError("no such automation in this universe")
        if int(expected_revision) != current.revision:
            raise ScheduledWorkError(
                f"revision conflict: it is at {current.revision}, you sent "
                f"{expected_revision} — re-read it and retry"
            )
        with self._connect() as conn:
            conn.execute(
                "UPDATE scheduled_work SET state = ?, revision = revision + 1,"
                " updated_at = ? WHERE universe_id = ? AND work_id = ?",
                (target, time.time(), current.universe_id, current.work_id),
            )
        updated = self.get(universe_id=universe_id, work_id=work_id)
        assert updated is not None
        return updated

    def record_run(self, *, universe_id: str, work_id: str, run_id: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE scheduled_work SET last_run_at = ?, last_run_id = ?"
                " WHERE universe_id = ? AND work_id = ?",
                (time.time(), run_id, universe_id, work_id),
            )

    @staticmethod
    def _row(row: sqlite3.Row) -> ScheduledWork:
        try:
            operations = tuple(json.loads(row["declared_operations_json"]))
        except (TypeError, ValueError):
            operations = ()
        return ScheduledWork(
            work_id=row["work_id"], universe_id=row["universe_id"],
            name=row["name"], kind=row["kind"],
            branch_def_id=row["branch_def_id"], inputs_json=row["inputs_json"],
            cadence_seconds=row["cadence_seconds"],
            declared_operations=operations, state=row["state"],
            revision=row["revision"], owner_id=row["owner_id"],
            deliver_to=(row["deliver_to"] if "deliver_to" in row.keys() else ""),
        )


__all__ = [
    "MIN_CADENCE_SECONDS",
    "ScheduledWork",
    "ScheduledWorkError",
    "ScheduledWorkStore",
]

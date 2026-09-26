"""Settle agent turns a dead daemon left mid-flight. Never resurrect one.

A deploy recreates the container, which kills whatever turn was running. The
journal keeps the last thing that process committed, so the row stays in a
progressing state forever: on 2026-09-26 a 22:31:54Z deploy killed the founder's
turn ``652a2f31e82546a1bb56b5d158b5490f`` and its row read ``native_started`` 35
minutes later, which the app's server-driven status line rendered as "your
universe is thinking ... for 34m 55s". It would have stayed that way until the
granted-turn cap (3600s) aged it out.

This settles such a row at startup, into the terminal state the journal ALREADY
has for "we cannot tell what ran":

======================  ==========================  ===============================
Row state               Transition                  Settled state
======================  ==========================  ===============================
``ready``               ``abandon``                 ``abandoned``
``inference_started``   ``finish_inference(None)``   ``held_transport``
``native_started``      ``finish_native`` /          ``held_native_unknown``
                        ``indeterminate``
``tools_pending``       ``finish_tool`` failure     ``held_tool_not_sent`` or
                                                    ``held_tool_unknown``
======================  ==========================  ===============================

No new state, and no transition this codebase did not already perform: each one
is what the coordinator itself writes when that step fails. The point is that
uncertainty is PRESERVED -- a killed native round becomes indeterminate, not
completed and not retryable -- so the surface shows the existing "we can't tell
whether actions ran" notice instead of a thinking indicator. Nothing here
replays an effect or lets a turn continue; a settled turn is over.

A ``planned`` tool is settled ``not_sent`` rather than ``unknown`` because the
journal PROVES it: a tool is recorded ``started`` before it is dispatched, so one
still ``planned`` was never sent.

Keyed on boot ownership (``storage.agent_turn_boot``), never on age: a turn this
boot is running must survive reconciliation even if it started before this call,
and every row a dead container left behind is settled however young it is.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from tinyassets.storage import db_path
from tinyassets.storage.agent_native_records import NativeTerminal
from tinyassets.storage.agent_turn_boot import BOOT, BootTurns
from tinyassets.storage.agent_turn_journal import (
    WORKING_STATES,
    AgentTurnJournal,
)

_LOG = logging.getLogger(__name__)

#: Recorded with every settlement. The journal rows carry no free-text field, so
#: the reason lives in the log and in this function's return value rather than
#: being wedged into a record shape that validates its own bytes.
REASON = "server restarted during this turn"


def _orphan_rows(path: Path, boot: BootTurns) -> list[tuple[str, str, str, str]]:
    """Scan for progressing rows no process in this boot is running.

    Observational, like the status projection: ``mode=rw`` opens an existing
    database and refuses to create one, and it runs no DDL, so a daemon whose
    journal has never been written brings nothing into being. Read-write rather
    than ``mode=ro`` because a WAL database missing its ``-shm`` file cannot be
    opened read-only at all, which is the state a restarted box is in.
    """
    conn = sqlite3.connect(
        path.as_uri() + "?mode=rw", uri=True, timeout=30.0, isolation_level=None,
    )
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout = 30000")
        if not conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'agent_turns'"
        ).fetchone():
            return []
        rows = conn.execute(
            "SELECT owner_user_id, universe_id, turn_id, state, created_at FROM agent_turns "
            f"WHERE state IN ({','.join('?' * len(WORKING_STATES))}) ORDER BY created_at",
            tuple(sorted(WORKING_STATES)),
        ).fetchall()
    finally:
        conn.close()
    return [
        (row["owner_user_id"], row["universe_id"], row["turn_id"], row["state"])
        for row in rows
        if not boot.holds(
            row["universe_id"], row["turn_id"], created_at=row["created_at"],
        )
    ]


def _settle(journal: AgentTurnJournal, owner: str, universe: str, turn_id: str) -> str:
    """Move one orphaned turn to its terminal state; returns the state reached.

    Re-reads the turn under the journal's own transaction and passes the
    generation it saw, so a turn that started progressing between the scan and
    here yields a ``conflict`` transition rather than a stolen step.
    """
    turn = journal.get(owner, universe, turn_id)
    if turn is None or turn.state not in WORKING_STATES:
        return "" if turn is None else turn.state
    ordinal = len(turn.rounds)
    if turn.state == "ready":
        transition = journal.abandon(
            owner, universe, turn_id, expected_generation=turn.generation,
        )
    elif turn.state == "native_started":
        transition = journal.finish_native(
            owner, universe, turn_id, expected_generation=turn.generation,
            ordinal=ordinal, terminal=NativeTerminal("indeterminate"),
        )
    elif turn.state == "inference_started":
        transition = journal.finish_inference(
            owner, universe, turn_id, expected_generation=turn.generation,
            ordinal=ordinal, reply=None,
        )
    else:
        transition = _settle_tool(journal, owner, universe, turn)
    if transition.status != "applied":
        raise RuntimeError(f"orphaned agent turn not settled: {transition.status}")
    return transition.snapshot.state


def _settle_tool(journal: AgentTurnJournal, owner: str, universe: str, turn):
    """Settle the one tool call a ``tools_pending`` turn stopped on."""
    tools = turn.rounds[-1].tools
    target = next(tool for tool in tools if tool.state != "completed")
    generation = turn.generation
    if target.state == "planned":
        # ``finish_tool`` only settles a started call. Starting it records no
        # dispatch -- the row it writes is what ``not_sent`` is then proven from.
        started = journal.start_tool(
            owner, universe, turn.turn_id, expected_generation=generation,
            ordinal=len(turn.rounds), call_ordinal=target.ordinal,
        )
        if started.status != "applied":
            raise RuntimeError(f"orphaned agent tool not settled: {started.status}")
        generation = started.snapshot.generation
    return journal.finish_tool(
        owner, universe, turn.turn_id, expected_generation=generation,
        ordinal=len(turn.rounds), call_ordinal=target.ordinal, request=target.request,
        failure="not_sent" if target.state == "planned" else "unknown",
    )


def reconcile_orphaned_turns(
    base_path: str | Path, *, boot: BootTurns = BOOT,
) -> list[dict[str, str]]:
    """Settle every progressing turn row this boot is not running.

    Returns one record per row it touched: ``universe_id``, ``turn_id``, the
    ``was`` state, and either the ``settled`` state or the ``error`` that stopped
    it. Per-row failures do not stop the sweep and do not raise: one turn whose
    owner's home was rebound (``CurrentHomeChanged``) must not leave every other
    universe's orphan painting a thinking indicator, and the projection guard in
    ``universe_working_turn`` covers whatever this could not settle.
    """
    path = db_path(Path(base_path))
    if not path.exists():
        return []
    journal = AgentTurnJournal(base_path)
    settled: list[dict[str, str]] = []
    for owner, universe, turn_id, state in _orphan_rows(path, boot):
        record = {"universe_id": universe, "turn_id": turn_id, "was": state}
        try:
            record["settled"] = _settle(journal, owner, universe, turn_id)
        except Exception as exc:  # noqa: BLE001 - one unreachable row is not the sweep
            record["error"] = type(exc).__name__
            _LOG.error(
                "orphaned agent turn %s (%s) could not be settled: %s",
                turn_id, state, type(exc).__name__, exc_info=True,
            )
        else:
            _LOG.warning(
                "orphaned agent turn %s settled %s -> %s: %s",
                turn_id, state, record["settled"], REASON,
            )
        settled.append(record)
    return settled

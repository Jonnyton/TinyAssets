"""Owner-scoped effect journal for the private interactive agent executor.

Every mutation commits before returning. A winning start is necessary but never
sufficient authority to dispatch: the executor must supply fresh live authority.
No timer, loader or stale worker can turn an uncertain effect back into a plan.
"""

from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from mcp.types import CallToolResult

from tinyassets.providers.agent_chat_codec import AgentReply, ToolRequest
from tinyassets.storage import agent_turn_records as records
from tinyassets.storage.agent_turn_records import (
    RoundInput,
    RoundSnapshot,
    ToolSnapshot,
    Transition,
    TurnSnapshot,
)
from tinyassets.storage.current_home import check_current_home
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

_SCOPE = "owner_user_id = ? AND universe_id = ? AND turn_id = ?"
_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS agent_turns (
      owner_user_id TEXT NOT NULL, universe_id TEXT NOT NULL, turn_id TEXT NOT NULL,
      version INTEGER NOT NULL CHECK(version = 1),
      generation INTEGER NOT NULL CHECK(generation > 0),
      state TEXT NOT NULL, round_ordinal INTEGER NOT NULL CHECK(round_ordinal >= 0),
      input_json TEXT NOT NULL, created_at TEXT NOT NULL,
      PRIMARY KEY(owner_user_id, universe_id, turn_id))""",
    """CREATE TABLE IF NOT EXISTS agent_turn_rounds (
      owner_user_id TEXT NOT NULL, universe_id TEXT NOT NULL, turn_id TEXT NOT NULL,
      ordinal INTEGER NOT NULL CHECK(ordinal > 0), version INTEGER NOT NULL CHECK(version = 1),
      state TEXT NOT NULL, candidate_json TEXT NOT NULL, reply_json TEXT,
      cost_microusd INTEGER CHECK(cost_microusd >= 0),
      PRIMARY KEY(owner_user_id, universe_id, turn_id, ordinal),
      FOREIGN KEY(owner_user_id, universe_id, turn_id)
        REFERENCES agent_turns(owner_user_id, universe_id, turn_id) ON DELETE CASCADE)""",
    """CREATE TABLE IF NOT EXISTS agent_turn_tools (
      owner_user_id TEXT NOT NULL, universe_id TEXT NOT NULL, turn_id TEXT NOT NULL,
      round_ordinal INTEGER NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal > 0),
      version INTEGER NOT NULL CHECK(version = 1), call_id TEXT NOT NULL, name TEXT NOT NULL,
      arguments_json TEXT NOT NULL, state TEXT NOT NULL, result_json TEXT,
      content_kind TEXT, is_error INTEGER CHECK(is_error IN (0, 1)),
      PRIMARY KEY(owner_user_id, universe_id, turn_id, round_ordinal, ordinal),
      FOREIGN KEY(owner_user_id, universe_id, turn_id, round_ordinal)
        REFERENCES agent_turn_rounds(owner_user_id, universe_id, turn_id, ordinal)
        ON DELETE CASCADE)""",
    """CREATE UNIQUE INDEX IF NOT EXISTS agent_turn_one_inference
      ON agent_turn_rounds(owner_user_id, universe_id, turn_id)
      WHERE state = 'inference_started'""",
)


class JournalUnavailable(RuntimeError):
    """Unreadable progress cannot be replaced with an executable default."""


def ensure_schema(conn: sqlite3.Connection) -> None:
    if conn.in_transaction:
        raise JournalUnavailable("agent turn schema requires an idle connection")
    for statement in _SCHEMA:
        conn.execute(statement)


def _scope(owner: str, universe: str, turn: str) -> tuple[str, str, str]:
    return tuple(records.identity(value) for value in (owner, universe, turn))


def _require_transaction(conn: sqlite3.Connection) -> None:
    if not conn.in_transaction:
        raise JournalUnavailable("agent turn mutation requires a transaction")


def _read(conn: sqlite3.Connection, scope: tuple[str, str, str]) -> TurnSnapshot | None:
    row = conn.execute(f"SELECT * FROM agent_turns WHERE {_SCOPE}", scope).fetchone()
    if row is None:
        return None
    try:
        if row["version"] != 1 or row["state"] not in records.STATES:
            raise records.invalid()
        generation = records.integer(row["generation"], minimum=1)
        frontier = records.integer(row["round_ordinal"])
        value = records.fields(
            records.document(row["input_json"]),
            {"version", "prompt", "system", "policy_generation"},
        )
        if not isinstance(value["prompt"], str) or not isinstance(value["system"], str):
            raise records.invalid()
        if value["policy_generation"] is not None:
            records.integer(value["policy_generation"])
        timestamp = row["created_at"]
        if not isinstance(timestamp, str) or not timestamp.endswith("Z"):
            raise records.invalid()
        datetime.fromisoformat(timestamp[:-1] + "+00:00")
        rounds = []
        for ordinal, rr in enumerate(
            conn.execute(
                f"SELECT * FROM agent_turn_rounds WHERE {_SCOPE} ORDER BY ordinal",
                scope,
            ),
            1,
        ):
            if (
                rr["version"] != 1
                or rr["ordinal"] != ordinal
                or rr["state"]
                not in {
                    "inference_started",
                    "received",
                    "failed",
                }
            ):
                raise records.invalid()
            candidate = RoundInput.from_json(rr["candidate_json"])
            reply = (
                None
                if rr["reply_json"] is None
                else records.load_reply(rr["reply_json"], candidate)
            )
            if (reply is not None) != (rr["state"] == "received"):
                raise records.invalid()
            cost = rr["cost_microusd"]
            if cost is not None:
                records.integer(cost)
                if reply is None:
                    raise records.invalid()
            tools = []
            for call_ordinal, tr in enumerate(
                conn.execute(
                    f"SELECT * FROM agent_turn_tools WHERE {_SCOPE} "
                    "AND round_ordinal = ? ORDER BY ordinal",
                    (*scope, ordinal),
                ),
                1,
            ):
                if (
                    tr["version"] != 1
                    or tr["ordinal"] != call_ordinal
                    or tr["state"]
                    not in {
                        "planned",
                        "started",
                        "completed",
                        "not_sent",
                        "unknown",
                    }
                ):
                    raise records.invalid()
                request = ToolRequest(tr["call_id"], tr["name"], tr["arguments_json"])
                if (
                    reply is None
                    or call_ordinal > len(reply.tool_requests)
                    or (reply.tool_requests[call_ordinal - 1] != request)
                ):
                    raise records.invalid()
                if tr["state"] == "completed":
                    _, kind, error = records.load_result(tr["result_json"])
                    if (
                        tr["content_kind"] != kind
                        or type(tr["is_error"]) is not int
                        or (tr["is_error"] != int(error))
                    ):
                        raise records.invalid()
                else:
                    kind = error = None
                    if any(
                        tr[key] is not None for key in ("result_json", "content_kind", "is_error")
                    ):
                        raise records.invalid()
                tools.append(
                    ToolSnapshot(call_ordinal, request, tr["state"], tr["result_json"], kind, error)
                )
            if len(tools) != (len(reply.tool_requests) if reply is not None else 0):
                raise records.invalid()
            # Only a completed prefix, then at most one started/held row, then plans.
            pending = False
            for tool in tools:
                if pending and tool.state != "planned":
                    raise records.invalid()
                if tool.state != "completed" or tool.content_kind == "non_text":
                    pending = True
            rounds.append(RoundSnapshot(ordinal, candidate, rr["state"], reply, tuple(tools), cost))
        if len(rounds) != frontier:
            raise records.invalid()
        for completed_round in rounds[:-1]:
            if _frontier(completed_round) != "ready" and not (
                completed_round.state == "failed"
                and completed_round.reply is None
                and not completed_round.tools
            ):
                raise records.invalid()
        expected_state = (
            _frontier(rounds[-1])
            if rounds
            else ("abandoned" if row["state"] == "abandoned" else "ready")
        )
        if row["state"] != expected_state:
            raise records.invalid()
        return TurnSnapshot(
            scope[2],
            generation,
            row["state"],
            value["prompt"],
            value["system"],
            value["policy_generation"],
            timestamp,
            tuple(rounds),
        )
    except (ValueError, TypeError, KeyError, OverflowError, RecursionError):
        raise JournalUnavailable("agent turn record unavailable") from None


def _frontier(round_snapshot: RoundSnapshot) -> str:
    if round_snapshot.state == "inference_started":
        return "inference_started"
    if round_snapshot.state == "failed":
        return "held_transport"
    reply = round_snapshot.reply
    if reply is None:
        raise records.invalid()
    if reply.stop != "tool_requests":
        return records.STOP_STATE[reply.stop]
    if not round_snapshot.tools:
        raise records.invalid()
    for tool in round_snapshot.tools:
        if tool.state == "unknown":
            return "held_tool_unknown"
        if tool.state == "not_sent":
            return "held_tool_not_sent"
        if tool.content_kind == "non_text":
            return "held_unsupported_result"
        if tool.state != "completed":
            return "tools_pending"
    return "ready"


def _advance(conn, scope, current, state, *, ordinal=None):
    _require_transaction(conn)
    if current.generation == records.MAX_INT:
        raise JournalUnavailable("agent turn generation exhausted")
    changed = conn.execute(
        f"UPDATE agent_turns SET generation = generation + 1, state = ?, round_ordinal = ? "
        f"WHERE {_SCOPE} AND generation = ?",
        (state, len(current.rounds) if ordinal is None else ordinal, *scope, current.generation),
    ).rowcount
    if changed != 1:
        raise JournalUnavailable("agent turn transition unavailable")
    return Transition("applied", _read(conn, scope))


def reset_blockers(conn: sqlite3.Connection, owner: str, universe: str) -> list[str]:
    """Preserve effect evidence; an offline reset cannot abandon executable/ambiguous work."""
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    expected = {"agent_turns", "agent_turn_rounds", "agent_turn_tools"}
    if not tables & expected:
        return []
    if not expected <= tables:
        return ["incomplete agent turn journal blocks scoped reset"]
    try:
        for row in conn.execute(
            "SELECT turn_id FROM agent_turns WHERE owner_user_id = ? AND universe_id = ?",
            (owner, universe),
        ):
            turn = _read(conn, (owner, universe, row[0]))
            if turn is not None and turn.state in {
                "ready",
                "inference_started",
                "tools_pending",
                "held_tool_unknown",
            }:
                return ["active or ambiguous agent turn references exact home"]
        return []
    except (JournalUnavailable, sqlite3.DatabaseError):
        return ["unreadable agent turn journal references exact home"]


class AgentTurnJournal:
    """Private persistence, not authentication. No callbacks run inside its transactions."""

    def __init__(self, base_path: str | Path) -> None:
        self._ledger = SQLiteProviderWorkAuthorityStore(base_path)

    @contextmanager
    def _transaction(self):
        with self._ledger.connection() as conn:
            ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
                conn.commit()
            except BaseException:
                conn.rollback()
                raise

    def create(
        self,
        owner: str,
        universe: str,
        *,
        prompt: str,
        system: str,
        policy_generation: int | None = None,
    ) -> TurnSnapshot:
        scope = _scope(owner, universe, uuid.uuid4().hex)
        if not isinstance(prompt, str) or not isinstance(system, str):
            raise records.invalid()
        if policy_generation is not None:
            records.integer(policy_generation)
        raw = records.dump(
            {
                "version": 1,
                "prompt": prompt,
                "system": system,
                "policy_generation": policy_generation,
            }
        )
        with self._transaction() as conn:
            check_current_home(conn, owner, universe)
            conn.execute(
                "INSERT INTO agent_turns VALUES (?, ?, ?, 1, 1, 'ready', 0, ?, ?)",
                (*scope, raw, self._ledger.timestamp()),
            )
            return _read(conn, scope)

    def get(self, owner: str, universe: str, turn_id: str) -> TurnSnapshot | None:
        scope = _scope(owner, universe, turn_id)
        with self._ledger.connection() as conn:
            ensure_schema(conn)
            conn.execute("BEGIN")  # consistent root/round/tool snapshot; no claim or retry
            return _read(conn, scope)

    @contextmanager
    def _mutation(self, owner, universe, turn_id, expected_generation):
        scope = _scope(owner, universe, turn_id)
        records.integer(expected_generation, minimum=1)
        with self._transaction() as conn:
            check_current_home(conn, owner, universe)
            current = _read(conn, scope)
            if current is None:
                raise JournalUnavailable("agent turn unavailable")
            yield conn, scope, current

    def begin_round(
        self,
        owner,
        universe,
        turn_id,
        *,
        expected_generation: int,
        candidate: RoundInput,
        after_failed_inference: bool = False,
    ) -> Transition:
        if type(candidate) is not RoundInput or type(after_failed_inference) is not bool:
            raise records.invalid()
        raw = candidate.canonical_json()
        with self._mutation(owner, universe, turn_id, expected_generation) as (
            conn,
            scope,
            current,
        ):
            retryable = (
                after_failed_inference
                and current.state == "held_transport"
                and current.rounds
                and current.rounds[-1].state == "failed"
                and current.rounds[-1].reply is None
                and not current.rounds[-1].tools
            )
            admissible = retryable if after_failed_inference else current.state == "ready"
            if current.generation != expected_generation or not admissible:
                return Transition("conflict", current)
            ordinal = len(current.rounds) + 1
            conn.execute(
                "INSERT INTO agent_turn_rounds VALUES (?, ?, ?, ?, 1, "
                "'inference_started', ?, NULL, NULL)",
                (*scope, ordinal, raw),
            )
            return _advance(conn, scope, current, "inference_started", ordinal=ordinal)

    def abandon(self, owner, universe, turn_id, *, expected_generation: int) -> Transition:
        """Close only a never-launched root; never discard an inference or effect."""
        with self._mutation(owner, universe, turn_id, expected_generation) as (
            conn,
            scope,
            current,
        ):
            if current.state == "abandoned" and not current.rounds:
                return Transition("already_applied", current)
            if (
                current.generation != expected_generation
                or current.state != "ready"
                or current.rounds
            ):
                return Transition("conflict", current)
            return _advance(conn, scope, current, "abandoned")

    def finish_inference(
        self,
        owner,
        universe,
        turn_id,
        *,
        expected_generation: int,
        ordinal: int,
        reply: AgentReply | None,
        cost_microusd: int | None = None,
    ) -> Transition:
        records.integer(ordinal, minimum=1)
        if cost_microusd is not None:
            records.integer(cost_microusd)
            if reply is None:
                raise records.invalid()
        with self._mutation(owner, universe, turn_id, expected_generation) as (
            conn,
            scope,
            current,
        ):
            if ordinal > len(current.rounds):
                return Transition("conflict", current)
            target = current.rounds[ordinal - 1]
            raw = None if reply is None else records.reply_json(reply, target.candidate)
            existing = (
                None if target.reply is None else records.reply_json(target.reply, target.candidate)
            )
            if target.state != "inference_started":
                same = (raw, cost_microusd) == (existing, target.cost_microusd)
                return Transition("already_applied" if same else "conflict", current)
            if current.generation != expected_generation or ordinal != len(current.rounds):
                return Transition("conflict", current)
            conn.execute(
                f"UPDATE agent_turn_rounds SET state = ?, reply_json = ?, cost_microusd = ? "
                f"WHERE {_SCOPE} AND ordinal = ?",
                ("failed" if reply is None else "received", raw, cost_microusd, *scope, ordinal),
            )
            for call_ordinal, request in enumerate(() if reply is None else reply.tool_requests, 1):
                conn.execute(
                    "INSERT INTO agent_turn_tools VALUES (?, ?, ?, ?, ?, 1, ?, ?, ?, "
                    "'planned', NULL, NULL, NULL)",
                    (
                        *scope,
                        ordinal,
                        call_ordinal,
                        request.call_id,
                        request.name,
                        request.arguments_json,
                    ),
                )
            state = "held_transport" if reply is None else records.STOP_STATE[reply.stop]
            return _advance(conn, scope, current, state)

    def start_tool(
        self, owner, universe, turn_id, *, expected_generation: int, ordinal: int, call_ordinal: int
    ) -> Transition:
        records.integer(ordinal, minimum=1)
        records.integer(call_ordinal, minimum=1)
        with self._mutation(owner, universe, turn_id, expected_generation) as (
            conn,
            scope,
            current,
        ):
            if (
                current.generation != expected_generation
                or current.state != "tools_pending"
                or (ordinal != len(current.rounds))
            ):
                return Transition("conflict", current)
            tools = current.rounds[-1].tools
            if (
                call_ordinal > len(tools)
                or tools[call_ordinal - 1].state != "planned"
                or any(tool.state != "completed" for tool in tools[: call_ordinal - 1])
            ):
                return Transition("conflict", current)
            conn.execute(
                f"UPDATE agent_turn_tools SET state = 'started' WHERE {_SCOPE} "
                "AND round_ordinal = ? AND ordinal = ?",
                (*scope, ordinal, call_ordinal),
            )
            return _advance(conn, scope, current, "tools_pending")

    def finish_tool(
        self,
        owner,
        universe,
        turn_id,
        *,
        expected_generation: int,
        ordinal: int,
        call_ordinal: int,
        request: ToolRequest,
        result: CallToolResult | None = None,
        failure: str | None = None,
    ) -> Transition:
        records.integer(ordinal, minimum=1)
        records.integer(call_ordinal, minimum=1)
        if (
            type(request) is not ToolRequest
            or (result is None) == (failure is None)
            or (failure is not None and failure not in {"not_sent", "unknown"})
        ):
            raise records.invalid()
        raw, kind, error = (None, None, None) if result is None else records.result_json(result)
        state = failure or "completed"
        with self._mutation(owner, universe, turn_id, expected_generation) as (
            conn,
            scope,
            current,
        ):
            if ordinal > len(current.rounds) or call_ordinal > len(
                current.rounds[ordinal - 1].tools
            ):
                return Transition("conflict", current)
            target = current.rounds[ordinal - 1].tools[call_ordinal - 1]
            if target.request != request:
                return Transition("conflict", current)
            if target.state in {"completed", "not_sent", "unknown"}:
                same = (target.state, target.result_json, target.content_kind, target.is_error) == (
                    state,
                    raw,
                    kind,
                    error,
                )
                return Transition("already_applied" if same else "conflict", current)
            if (
                current.generation != expected_generation
                or target.state != "started"
                or (current.state != "tools_pending" or ordinal != len(current.rounds))
            ):
                return Transition("conflict", current)
            conn.execute(
                f"UPDATE agent_turn_tools SET state = ?, result_json = ?, "
                f"content_kind = ?, is_error = ? WHERE {_SCOPE} "
                "AND round_ordinal = ? AND ordinal = ?",
                (
                    state,
                    raw,
                    kind,
                    None if error is None else int(error),
                    *scope,
                    ordinal,
                    call_ordinal,
                ),
            )
            frontier = (
                "held_tool_" + failure
                if failure
                else "held_unsupported_result"
                if kind == "non_text"
                else "ready"
                if call_ordinal == len(current.rounds[-1].tools)
                else "tools_pending"
            )
            return _advance(conn, scope, current, frontier)

"""Durable deduplication for private custom-agent no-progress alarms."""

from __future__ import annotations

import json
import sqlite3

from tinyassets.agent_runtime_health import AgentRuntimeNoProgressAlarm

_SCHEMA = """
CREATE TABLE IF NOT EXISTS agent_runtime_no_progress_alarms (
    alarm_id TEXT PRIMARY KEY,
    invocation_id TEXT NOT NULL,
    useful_progress_digest TEXT NOT NULL,
    threshold_seconds INTEGER NOT NULL CHECK (threshold_seconds >= 1),
    record_json TEXT NOT NULL,
    UNIQUE (invocation_id, useful_progress_digest, threshold_seconds)
);
"""


class SQLiteAgentRuntimeHealthStore:
    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        conn.executescript(_SCHEMA)

    @staticmethod
    def _raise_alarm_in_transaction(
        conn: sqlite3.Connection,
        alarm: AgentRuntimeNoProgressAlarm,
    ) -> AgentRuntimeNoProgressAlarm:
        if not conn.in_transaction:
            raise ValueError("no-progress alarm requires an active transaction")
        row = conn.execute(
            "SELECT * FROM agent_runtime_no_progress_alarms "
            "WHERE invocation_id = ? AND useful_progress_digest = ? "
            "AND threshold_seconds = ?",
            (
                alarm.invocation_id,
                alarm.useful_progress_digest,
                alarm.threshold_seconds,
            ),
        ).fetchone()
        if row is not None:
            payload = json.loads(str(row["record_json"]))
            persisted = AgentRuntimeNoProgressAlarm(**payload)
            if (
                persisted.alarm_id != row["alarm_id"]
                or persisted.invocation_id != row["invocation_id"]
                or persisted.useful_progress_digest
                != row["useful_progress_digest"]
                or persisted.threshold_seconds != row["threshold_seconds"]
                or persisted != alarm
            ):
                raise ValueError("persisted no-progress alarm failed integrity checks")
            return persisted
        record_json = json.dumps(
            alarm.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        conn.execute(
            "INSERT INTO agent_runtime_no_progress_alarms VALUES (?, ?, ?, ?, ?)",
            (
                alarm.alarm_id,
                alarm.invocation_id,
                alarm.useful_progress_digest,
                alarm.threshold_seconds,
                record_json,
            ),
        )
        return alarm


__all__ = ["SQLiteAgentRuntimeHealthStore"]

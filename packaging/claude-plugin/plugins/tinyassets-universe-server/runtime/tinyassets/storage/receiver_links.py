"""Owner-scoped receiver/link records; IDs are addresses, never bearer grants.

Callers supply server-authenticated principals, not payload identities. The API
service also checks current universe/graph authority. Future delivery acceptance
must call resolve_link_in_transaction in its acceptance transaction, not use a
previous read as authority. This module does not enqueue or transfer files.
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from tinyassets.runs import runs_db_path

_SCHEMA = """
CREATE TABLE IF NOT EXISTS graph_receivers (
    receiver_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    branch_def_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    generation INTEGER NOT NULL CHECK(generation > 0),
    description TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    senders_json TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    source_sha256 TEXT NOT NULL,
    snapshot_sha256 TEXT NOT NULL,
    created_at REAL NOT NULL,
    revoked_at REAL
);
CREATE INDEX IF NOT EXISTS graph_receivers_owner
    ON graph_receivers(owner_id, universe_id);
CREATE TABLE IF NOT EXISTS graph_output_links (
    link_id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    universe_id TEXT NOT NULL,
    branch_def_id TEXT NOT NULL,
    node_id TEXT NOT NULL,
    receiver_id TEXT NOT NULL REFERENCES graph_receivers(receiver_id),
    receiver_generation INTEGER NOT NULL,
    mapping_json TEXT NOT NULL,
    created_at REAL NOT NULL,
    disconnected_at REAL
);
CREATE INDEX IF NOT EXISTS graph_output_links_owner
    ON graph_output_links(owner_id, universe_id);
"""


class ReceiverAccessDenied(PermissionError):
    def __init__(self) -> None:
        super().__init__("receiver_or_link_not_found")


class ReceiverConflict(ValueError):
    """An authorized caller must inspect the current generation and retry."""


def _name(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or value == "*":
        raise ValueError("a non-empty exact principal/resource name is required")
    return value


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


@contextmanager
def transaction(base_path: str | Path) -> Iterator[sqlite3.Connection]:
    """Use the runs DB, not the author store used by legacy webhook tokens."""
    path = runs_db_path(base_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(_SCHEMA)
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _owned_receiver(conn, receiver_id, owner_id, universe_id):
    row = conn.execute(
        "SELECT * FROM graph_receivers WHERE receiver_id=? AND owner_id=? AND universe_id=?",
        (receiver_id, owner_id, universe_id),
    ).fetchone()
    if row is None:
        raise ReceiverAccessDenied()
    return row


def _permitted_receiver(conn, receiver_id, sender_id):
    row = conn.execute(
        "SELECT * FROM graph_receivers WHERE receiver_id=?", (receiver_id,)
    ).fetchone()
    if (
        row is None
        or row["revoked_at"] is not None
        or sender_id not in json.loads(row["senders_json"])
    ):
        raise ReceiverAccessDenied()
    return row


def _receiver_view(row, *, private=False):
    view = {
        "receiver_id": row["receiver_id"],
        "owner_id": row["owner_id"],
        "generation": row["generation"],
        "description": row["description"],
        "contract": json.loads(row["contract_json"]),
        "revoked": row["revoked_at"] is not None,
    }
    if private:
        view.update(
            {
                "universe_id": row["universe_id"],
                "branch_def_id": row["branch_def_id"],
                "node_id": row["node_id"],
                "allowed_senders": json.loads(row["senders_json"]),
                "source_sha256": row["source_sha256"],
                "snapshot_sha256": row["snapshot_sha256"],
            }
        )
    return view


def save_receiver(
    base_path,
    *,
    owner_id,
    universe_id,
    branch_def_id,
    projection,
    contract,
    allowed_senders,
    description="",
    receiver_id=None,
    expected_generation=None,
):
    for name in (owner_id, universe_id, branch_def_id):
        _name(name)
    if not isinstance(allowed_senders, list):
        raise ValueError("allowed_senders must be an explicit list")
    senders = sorted({_name(sender) for sender in allowed_senders})
    if not isinstance(description, str):
        raise ValueError("description must be text")
    with transaction(base_path) as conn:
        if receiver_id is None:
            if expected_generation is not None:
                raise ValueError("new receiver has no expected generation")
            receiver_id = uuid.uuid4().hex
            conn.execute(
                "INSERT INTO graph_receivers VALUES (?,?,?,?,?,1,?,?,?,?,?,?,?,NULL)",
                (
                    receiver_id,
                    owner_id,
                    universe_id,
                    branch_def_id,
                    projection.entry_node_id,
                    description,
                    _json(contract),
                    _json(senders),
                    projection.snapshot_json,
                    projection.source_sha256,
                    projection.snapshot_sha256,
                    time.time(),
                ),
            )
        else:
            row = _owned_receiver(conn, receiver_id, owner_id, universe_id)
            if row["revoked_at"] is not None:
                raise ReceiverConflict("receiver_revoked")
            if type(expected_generation) is not int or row["generation"] != expected_generation:
                raise ReceiverConflict("receiver_generation_changed")
            conn.execute(
                "UPDATE graph_receivers SET branch_def_id=?, node_id=?, generation=generation+1, "
                "description=?, contract_json=?, senders_json=?, snapshot_json=?, source_sha256=?, "
                "snapshot_sha256=? WHERE receiver_id=? AND generation=?",
                (
                    branch_def_id,
                    projection.entry_node_id,
                    description,
                    _json(contract),
                    _json(senders),
                    projection.snapshot_json,
                    projection.source_sha256,
                    projection.snapshot_sha256,
                    receiver_id,
                    expected_generation,
                ),
            )
        return _receiver_view(
            _owned_receiver(conn, receiver_id, owner_id, universe_id), private=True
        )


def inspect_receiver(base_path, *, receiver_id, principal_id, owner_universe_id=None):
    _name(principal_id)
    with transaction(base_path) as conn:
        if owner_universe_id is not None:
            row = _owned_receiver(conn, receiver_id, principal_id, owner_universe_id)
            return _receiver_view(row, private=True)
        return _receiver_view(_permitted_receiver(conn, receiver_id, principal_id))


def revoke_receiver(base_path, *, receiver_id, owner_id, universe_id, expected_generation):
    _name(owner_id)
    with transaction(base_path) as conn:
        row = _owned_receiver(conn, receiver_id, owner_id, universe_id)
        if type(expected_generation) is not int or row["generation"] != expected_generation:
            raise ReceiverConflict("receiver_generation_changed")
        if row["revoked_at"] is None:
            conn.execute(
                "UPDATE graph_receivers SET revoked_at=? WHERE receiver_id=?",
                (time.time(), receiver_id),
            )
        return {"receiver_id": receiver_id, "revoked": True, "generation": row["generation"]}


def connect_output(
    base_path,
    *,
    owner_id,
    universe_id,
    branch_def_id,
    node_id,
    receiver_id,
    expected_generation,
    mapping,
):
    for name in (owner_id, universe_id, branch_def_id, node_id):
        _name(name)
    if not isinstance(mapping, dict):
        raise ValueError("output mapping must be an object")
    for source, target in mapping.items():
        _name(source)
        _name(target)
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("two outputs cannot map to the same receiver input")
    with transaction(base_path) as conn:
        receiver = _permitted_receiver(conn, receiver_id, owner_id)
        if type(expected_generation) is not int or receiver["generation"] != expected_generation:
            raise ReceiverConflict("receiver_generation_changed")
        contract = json.loads(receiver["contract_json"])
        accepted = {item["name"] for item in contract}
        required = {item["name"] for item in contract if item["required"]}
        mapped = set(mapping.values())
        if mapped - accepted or required - mapped:
            raise ValueError("mapping does not satisfy receiver contract")
        link_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO graph_output_links VALUES (?,?,?,?,?,?,?,?,?,NULL)",
            (
                link_id,
                owner_id,
                universe_id,
                branch_def_id,
                node_id,
                receiver_id,
                expected_generation,
                _json(mapping),
                time.time(),
            ),
        )
        return {
            "link_id": link_id,
            "receiver_id": receiver_id,
            "receiver_generation": expected_generation,
        }


def _owned_link(conn, link_id, owner_id, universe_id):
    row = conn.execute(
        "SELECT * FROM graph_output_links WHERE link_id=? AND owner_id=? AND universe_id=?",
        (link_id, owner_id, universe_id),
    ).fetchone()
    if row is None:
        raise ReceiverAccessDenied()
    return row


def disconnect_output(base_path, *, link_id, owner_id, universe_id):
    _name(owner_id)
    with transaction(base_path) as conn:
        _owned_link(conn, link_id, owner_id, universe_id)
        conn.execute(
            "UPDATE graph_output_links SET disconnected_at=COALESCE(disconnected_at,?) "
            "WHERE link_id=?",
            (time.time(), link_id),
        )
        return {"link_id": link_id, "disconnected": True}


def resolve_link_in_transaction(conn, *, link_id, owner_id, universe_id):
    """INTERNAL acceptance check. Never return its private snapshot to a sender."""
    _name(owner_id)
    link = _owned_link(conn, link_id, owner_id, universe_id)
    if link["disconnected_at"] is not None:
        raise ReceiverAccessDenied()
    receiver = _permitted_receiver(conn, link["receiver_id"], owner_id)
    if receiver["generation"] != link["receiver_generation"]:
        raise ReceiverConflict("receiver_generation_changed")
    return dict(link), dict(receiver)

"""Run-owned envelope foundation; legacy delivery-worker migration remains separate."""

from __future__ import annotations

import hashlib
import json
import sqlite3

import pytest

from tinyassets.storage import run_input_admissions as admissions


@pytest.fixture
def conn(tmp_path):
    connection = sqlite3.connect(tmp_path / "runs.db")
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute(
        "CREATE TABLE runs(run_id TEXT PRIMARY KEY, owner_user_id TEXT, "
        "queue_universe_id TEXT, branch_def_id TEXT, inputs_json TEXT, status TEXT, "
        "error TEXT DEFAULT '', finished_at REAL)"
    )
    connection.execute(
        "CREATE TABLE branch_versions(branch_version_id TEXT PRIMARY KEY, "
        "branch_def_id TEXT, snapshot_json TEXT, content_hash TEXT)"
    )
    connection.execute("CREATE TABLE run_cancels(run_id TEXT PRIMARY KEY, requested_at REAL)")
    connection.execute(
        "INSERT INTO runs(run_id,owner_user_id,queue_universe_id,branch_def_id,inputs_json,status) "
        "VALUES('run','owner','universe','branch','{\"unchanged\":true}','queued')"
    )
    admissions.ensure_schema(connection)
    connection.commit()
    connection.execute("BEGIN IMMEDIATE")
    yield connection
    connection.close()


def accept(conn, **kwargs):
    parameters = dict(
        run_id="run",
        owner_id="owner",
        universe_id="universe",
        snapshot={
            "branch_def_id": "branch",
            "entry_point": "chosen",
            "io_manifest": {"inputs": [], "outputs": []},
        },
    )
    parameters.update(kwargs)
    return admissions.accept_in_transaction(conn, **parameters)


def test_run_envelope_survives_personal_receipt_erasure(conn):
    conn.execute("CREATE TABLE graph_deliveries(delivery_id TEXT PRIMARY KEY, sender_id TEXT)")
    conn.execute("INSERT INTO graph_deliveries VALUES('personal','sender')")
    accept(conn)
    conn.execute("DELETE FROM graph_deliveries")
    loaded = admissions.load_in_transaction(
        conn, run_id="run", owner_id="owner", universe_id="universe"
    )
    assert loaded["snapshot"]["entry_point"] == "chosen"
    assert loaded["inputs"] == {"unchanged": True}
    columns = {row[1] for row in conn.execute("PRAGMA table_info(run_input_admissions)")}
    assert "inputs_json" not in columns
    assert "sender_id" not in columns
    assert loaded["execution_started_at"] is None


def test_changed_acceptance_and_spoofed_owner_refuse(conn):
    accept(conn)
    assert accept(conn)["run_id"] == "run"
    with pytest.raises(admissions.RunInputRefused, match="conflict"):
        accept(conn, snapshot={"branch_def_id": "branch", "entry_point": "different"})
    for identity in ({"owner_id": "other"}, {"universe_id": "other"}, {"owner_id": ""}):
        with pytest.raises(admissions.RunInputRefused, match="not_found"):
            accept(conn, **identity)


def test_load_rechecks_persisted_owner_before_deserializing(conn):
    accept(conn)
    conn.execute("UPDATE run_input_admissions SET snapshot_json='malformed'")
    with pytest.raises(admissions.RunInputRefused, match="not_found"):
        admissions.load_in_transaction(
            conn, run_id="run", owner_id="foreign", universe_id="universe"
        )
    with pytest.raises(admissions.RunInputRefused, match="integrity"):
        admissions.load_in_transaction(conn, run_id="run", owner_id="owner", universe_id="universe")


def test_version_reference_is_not_duplicated_and_pins_hash(conn):
    snapshot = {"branch_def_id": "branch", "entry_point": "chosen"}
    encoded = json.dumps(snapshot, sort_keys=True)
    digest = hashlib.sha256(encoded.encode()).hexdigest()
    conn.execute("INSERT INTO branch_versions VALUES('version','branch',?,?)", (encoded, digest))
    accept(conn, snapshot=None, branch_version_id="version")
    row = conn.execute("SELECT * FROM run_input_admissions").fetchone()
    assert row["snapshot_json"] is None
    assert row["branch_version_id"] == "version"
    assert (
        admissions.load_in_transaction(
            conn, run_id="run", owner_id="owner", universe_id="universe"
        )["snapshot"]
        == snapshot
    )
    conn.execute("UPDATE branch_versions SET snapshot_json='{}'")
    with pytest.raises(admissions.RunInputRefused, match="integrity"):
        admissions.load_in_transaction(conn, run_id="run", owner_id="owner", universe_id="universe")


def test_snapshot_and_version_are_exclusive_and_branch_must_match(conn):
    with pytest.raises(admissions.RunInputRefused):
        accept(conn, branch_version_id="version")
    with pytest.raises(admissions.RunInputRefused):
        accept(conn, snapshot=None)
    with pytest.raises(admissions.RunInputRefused, match="branch"):
        accept(conn, snapshot={"branch_def_id": "foreign"})


def test_envelope_requires_callers_transaction(conn):
    conn.commit()
    with pytest.raises(ValueError, match="transaction"):
        accept(conn)

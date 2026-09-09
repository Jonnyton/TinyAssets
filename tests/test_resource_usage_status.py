"""Private resource observations must not bootstrap, migrate or admit work."""

import json
import sqlite3

import pytest

from tinyassets import engine_admissions as ea
from tinyassets import workspace_pool as wp
from tinyassets.api import permissions
from tinyassets.api import resource_usage as usage
from tinyassets.storage import DB_FILENAME

NOW = 10_000.0
UID = "test-universe"


@pytest.fixture
def meters(tmp_path, monkeypatch):
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "owner")
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    (tmp_path / UID).mkdir()
    with sqlite3.connect(tmp_path / DB_FILENAME) as conn:
        conn.execute("CREATE TABLE universe_acl (universe_id,actor_id,permission)")
        conn.execute("INSERT INTO universe_acl VALUES (?,?,?)", (UID, "owner", "admin"))
    conn.close()
    with sqlite3.connect(tmp_path / ea.LEDGER_NAME) as conn:
        ea._ensure_schema(conn)
        conn.executemany(
            "INSERT INTO admissions (universe_id,ts,kind) VALUES (?,?,?)",
            [(UID, NOW - 10, ea.KIND_READ), (UID, NOW - 20, ea.KIND_WRITE),
             (UID, NOW - 30, ea.KIND_ENGINE), ("foreign", NOW, ea.KIND_WRITE),
             (UID, NOW - 3601, ea.KIND_WRITE), (UID, NOW + 1, ea.KIND_WRITE)],
        )
    conn.close()
    with sqlite3.connect(tmp_path / UID / ".runs.db") as conn:
        wp.ensure_schema(conn)
        conn.executemany(
            "INSERT INTO workspace_ledger "
            "(universe_id,kind,amount,reserved,run_id,created_at) VALUES (?,?,?,1,'r',?)",
            [(UID, wp.KIND_JOBS, 11, NOW - 20), (UID, wp.KIND_BYTES, 100, NOW - 10),
             ("foreign", wp.KIND_BYTES, 9999, NOW),
             (UID, wp.KIND_BYTES, 9999, NOW - 3601)],
        )
        for name, state, universe in [
            ("held", wp.STATE_ACTIVE, UID), ("free", wp.STATE_AVAILABLE, UID),
            ("foreign", wp.STATE_ACTIVE, "foreign"),
        ]:
            conn.execute(
                "INSERT INTO workspace_leases VALUES "
                "(?,?, 'secret-connection', 'secret-repo', 'scratch', 1, ?, 50, "
                "NULL, 'private-run', 'private-path', 'quarantine-path', ?, ?)",
                (name, universe, state, NOW, NOW),
            )
    conn.close()
    return tmp_path


def snapshot(root):
    return {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_observes_existing_scoped_meters_without_mutating(meters):
    before = snapshot(meters)
    result = usage.for_authorized_status(meters, UID, now=NOW)
    assert snapshot(meters) == before
    activity = result["activity"]
    assert activity["availability"] == "observed"
    assert (activity["total"], activity["read_runs"], activity["write_runs"],
            activity["engine_mutations"]) == (3, 1, 1, 1)
    assert activity["limits"] == {"total": 900, "write_runs": 300}
    assert activity["engine_mutations"] == 1  # observed category, not a separate quota
    assert activity["next_charge_expires_at"] == usage._utc(NOW - 30 + 3600)
    workspace = result["workspace"]
    assert workspace["availability"] == "observed"
    assert workspace["jobs_observed"] == 11
    assert workspace["job_count_is_a_limit"] is False
    assert workspace["transfer_charged_or_reserved_bytes"] == 100
    assert workspace["allocations"] == [
        {"storage": "scratch", "state": "ACTIVE", "leases": 1, "reserved_bytes": 50},
    ]
    assert result["retained_storage"]["availability"] == "unavailable"
    assert "total_storage_not_measured" in json.dumps(result)
    for private in ("foreign", "private-", "secret-", "quarantine-path"):
        assert private not in json.dumps(result)


@pytest.mark.parametrize("actor,authenticated", [("", True), ("canary", True),
                                                  ("foreign", True), ("owner", False)])
def test_other_or_unauthenticated_principals_see_no_usage(
    meters, monkeypatch, actor, authenticated,
):
    monkeypatch.setattr(permissions, "current_actor_id", lambda: actor)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: authenticated)
    before = snapshot(meters)
    assert usage.for_authorized_status(meters, UID, now=NOW) is None
    assert snapshot(meters) == before


@pytest.mark.parametrize("permission", ["read", "write", "", "ADMIN"])
def test_requires_exact_admin_grant(meters, permission):
    with sqlite3.connect(meters / DB_FILENAME) as conn:
        conn.execute("UPDATE universe_acl SET permission=?", (permission,))
    assert usage.for_authorized_status(meters, UID, now=NOW) is None


def test_cached_storage_does_not_bypass_current_admin_gate(meters, monkeypatch):
    calls = []
    monkeypatch.setattr(usage.storage_observations, "observe",
                        lambda *a, **kw: calls.append(1) or {"availability": "observed"})
    assert usage.for_authorized_status(meters, UID)["retained_storage"]["footprint"]
    with sqlite3.connect(meters / DB_FILENAME) as conn:
        conn.execute("UPDATE universe_acl SET permission='read'")
    conn.close()
    assert usage.for_authorized_status(meters, UID) is None
    assert calls == [1]


@pytest.mark.parametrize("name", [DB_FILENAME, ea.LEDGER_NAME, f"{UID}/.runs.db"])
@pytest.mark.parametrize("damage", ["missing", "corrupt", "legacy"])
def test_unavailable_data_is_not_created_repaired_or_reported_as_zero(meters, name, damage):
    path = meters / name
    path.unlink()
    if damage == "corrupt":
        path.write_bytes(b"not sqlite")
    elif damage == "legacy":
        with sqlite3.connect(path) as conn:
            conn.execute("CREATE TABLE old_schema (value)")
    before = snapshot(meters)
    result = usage.for_authorized_status(meters, UID, now=NOW)
    assert snapshot(meters) == before
    if name == DB_FILENAME:
        assert result is None
    else:
        category = "activity" if name == ea.LEDGER_NAME else "workspace"
        assert result[category]["availability"] == "unavailable"
        assert "total" not in result[category]
        assert "jobs_observed" not in result[category]


@pytest.mark.parametrize("uid", ["", "../foreign", "/foreign", "."])
def test_escaped_or_invalid_universe_has_no_usage(meters, uid):
    assert usage.for_authorized_status(meters, uid, now=NOW) is None


@pytest.mark.parametrize("name", [DB_FILENAME, ea.LEDGER_NAME, f"{UID}/.runs.db"])
def test_symlinked_database_is_not_read(meters, name):
    path = meters / name
    target = path.with_name(path.name + ".target")
    path.rename(target)
    try:
        path.symlink_to(target)
    except OSError:
        pytest.skip("symlink creation unavailable on this platform")
    result = usage.for_authorized_status(meters, UID, now=NOW)
    if name == DB_FILENAME:
        assert result is None
    else:
        category = "activity" if name == ea.LEDGER_NAME else "workspace"
        assert result[category]["availability"] == "unavailable"


def test_quiescent_wal_is_read_without_mutating_records(meters):
    path = meters / ea.LEDGER_NAME
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    before = path.read_bytes()
    result = usage.for_authorized_status(meters, UID, now=NOW)
    assert result["activity"]["total"] == 3
    assert path.read_bytes() == before


def test_production_connection_factories_leave_readable_quiescent_stores(tmp_path, monkeypatch):
    from tinyassets import runs, storage

    monkeypatch.setattr(permissions, "current_actor_id", lambda: "owner")
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    with storage._connect(tmp_path) as conn:
        conn.execute("CREATE TABLE universe_acl (universe_id,actor_id,permission)")
        conn.execute("INSERT INTO universe_acl VALUES (?,?,?)", (UID, "owner", "admin"))
    with runs._connect(tmp_path / UID) as conn:
        wp.ensure_schema(conn)
    databases = (tmp_path / DB_FILENAME, tmp_path / UID / ".runs.db")
    before = {db: db.read_bytes() for db in databases}
    for db in databases:
        assert before[db][18:20] == b"\x02\x02"
        assert not db.with_name(db.name + "-wal").exists()
        assert not db.with_name(db.name + "-shm").exists()
    result = usage.for_authorized_status(tmp_path, UID, now=NOW)
    assert result is not None
    assert result["workspace"]["availability"] == "observed"
    assert result["workspace"]["jobs_observed"] == 0
    assert result["activity"]["availability"] == "unavailable"
    assert {db: db.read_bytes() for db in databases} == before


def test_reader_does_not_write_schema_or_records(meters):
    with usage._readonly(meters / DB_FILENAME) as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("UPDATE universe_acl SET permission='read'")
        with pytest.raises(sqlite3.OperationalError):
            conn.execute("CREATE TABLE status_created_this (value)")


def test_acl_change_committed_before_read_is_not_ignored(meters, monkeypatch):
    """A writer may create a WAL after the path checks but before the query."""
    path = meters / DB_FILENAME
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.close()
    original = usage.sqlite3.connect
    held = []

    def connect_after_revocation(database, *args, **kwargs):
        if str(database).startswith(path.as_uri()):
            writer = original(path)
            writer.execute("PRAGMA wal_autocheckpoint=0")
            writer.execute("UPDATE universe_acl SET permission='read'")
            writer.commit()
            held.append(writer)
        assert "immutable" not in str(database)
        return original(database, *args, **kwargs)

    monkeypatch.setattr(usage.sqlite3, "connect", connect_after_revocation)
    try:
        assert usage.for_authorized_status(meters, UID, now=NOW) is None
    finally:
        for writer in held:
            writer.close()


def test_live_wal_snapshot_includes_uncheckpointed_committed_rows(meters):
    conn = sqlite3.connect(meters / ea.LEDGER_NAME)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("INSERT INTO admissions (universe_id,ts,kind) VALUES (?,?,?)",
                     (UID, NOW, ea.KIND_WRITE))
        conn.commit()
        result = usage.for_authorized_status(meters, UID, now=NOW)
        assert result["activity"]["total"] == 4
    finally:
        conn.close()


def test_canonical_status_exposes_owner_usage(founder_home):
    from tinyassets.api.status import get_status

    result = json.loads(get_status(founder_home.name))
    assert result["resource_usage"]["read_only"] is True
    assert result["resource_usage"]["retained_storage"]["availability"] == "unavailable"

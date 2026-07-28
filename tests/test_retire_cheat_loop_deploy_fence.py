"""Focused tests for the transitional retire-cheat-loop task 2.1 deploy fence."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from scripts.retire_cheat_loop_deploy_fence import (
    DAEMON_SERVICE,
    EXPECTED_CONTAINERS,
    RESTART_RACER_UNITS,
    FenceError,
    inventory_queue_risk,
    receipt_snapshot,
    resolve_receipt_store,
    safe_fleet_matches,
)


def _create_receipt_db(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE wiki_trigger_attempts (
                trigger_attempt_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                request_kind TEXT NOT NULL,
                request_page TEXT NOT NULL,
                status TEXT NOT NULL,
                attempted_at TEXT NOT NULL,
                goal_id TEXT,
                branch_def_id TEXT,
                queued_at TEXT,
                run_id TEXT,
                dispatcher_request_id TEXT,
                error_class TEXT,
                error_message TEXT
            );
            """
        )


def test_absent_receipt_snapshot_has_defined_read_only_shape(tmp_path: Path):
    assert receipt_snapshot(tmp_path / "missing.db") == {
        "exists": False,
        "quick_check": ["absent"],
        "schema": [],
        "row_count": 0,
        "status_counts": {},
        "max_attempted_at": None,
        "logical_digest": (
            "e3b0c44298fc1c149afbf4c8996fb924"
            "27ae41e4649b934ca495991b7852b855"
        ),
    }


def test_receipt_snapshot_records_schema_counts_max_and_logical_digest(tmp_path: Path):
    path = tmp_path / "wiki_trigger_attempts.db"
    _create_receipt_db(path)
    with sqlite3.connect(path) as connection:
        connection.executemany(
            """
            INSERT INTO wiki_trigger_attempts (
                trigger_attempt_id, request_id, request_kind, request_page,
                status, attempted_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                ("attempt-2", "BUG-2", "bug", "pages/bugs/two.md", "queued", "2026-02-02"),
                ("attempt-1", "BUG-1", "bug", "pages/bugs/one.md", "pending", "2026-01-01"),
            ],
        )

    first = receipt_snapshot(path)
    second = receipt_snapshot(path)

    assert first == second
    assert first["quick_check"] == ["ok"]
    assert first["row_count"] == 2
    assert first["status_counts"] == {"pending": 1, "queued": 1}
    assert first["max_attempted_at"] == "2026-02-02"
    assert first["schema"]
    assert len(first["logical_digest"]) == 64


def test_receipt_snapshot_rejects_corrupt_or_unexpected_schema(tmp_path: Path):
    corrupt = tmp_path / "corrupt.db"
    corrupt.write_bytes(b"not sqlite")
    with pytest.raises(FenceError, match="receipt sqlite unreadable"):
        receipt_snapshot(corrupt)

    wrong = tmp_path / "wrong.db"
    with sqlite3.connect(wrong) as connection:
        connection.execute("CREATE TABLE unrelated (value TEXT)")
    with pytest.raises(FenceError, match="exact receipt schema"):
        receipt_snapshot(wrong)


def test_queue_inventory_finds_v1_pending_and_running_only(tmp_path: Path):
    universe = tmp_path / "universes" / "one"
    universe.mkdir(parents=True)
    (universe / "branch_tasks.json").write_text(
        json.dumps(
            [
                {"task_id": "pending", "request_type": "bug_investigation", "status": "pending"},
                {"task_id": "running", "request_type": "bug_investigation", "status": "running"},
                {"task_id": "done", "request_type": "bug_investigation", "status": "succeeded"},
                {"task_id": "generic", "request_type": "branch_run", "status": "pending"},
            ]
        ),
        encoding="utf-8",
    )

    assert inventory_queue_risk(tmp_path) == [
        {
            "id": "pending",
            "status": "pending",
            "store": "universes/one/branch_tasks.json",
            "version": "v1",
        },
        {
            "id": "running",
            "status": "running",
            "store": "universes/one/branch_tasks.json",
            "version": "v1",
        },
    ]


def test_queue_inventory_v2_joins_authoritative_user_request_type(tmp_path: Path):
    universe = tmp_path / "universes" / "two"
    universe.mkdir(parents=True)
    db = universe / ".tinyassets.db"
    with sqlite3.connect(db) as connection:
        connection.executescript(
            """
            CREATE TABLE user_requests (
                request_id TEXT PRIMARY KEY,
                request_type TEXT NOT NULL
            );
            CREATE TABLE branch_tasks_v2 (
                branch_task_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL,
                status TEXT NOT NULL
            );
            """
        )
        connection.executemany(
            "INSERT INTO user_requests VALUES (?, ?)",
            [
                ("req-p", "bug_investigation"),
                ("req-r", "bug_investigation"),
                ("req-c", "bug_investigation"),
                ("req-g", "branch_run"),
            ],
        )
        connection.executemany(
            "INSERT INTO branch_tasks_v2 VALUES (?, ?, ?)",
            [
                ("task-p", "req-p", "pending"),
                ("task-r", "req-r", "running"),
                ("task-c", "req-c", "cancel_requested"),
                ("task-g", "req-g", "pending"),
            ],
        )

    risks = inventory_queue_risk(tmp_path)
    assert [(row["id"], row["status"]) for row in risks] == [
        ("task-c", "cancel_requested"),
        ("task-p", "pending"),
        ("task-r", "running"),
    ]
    assert all(row["version"] == "v2" for row in risks)


def test_queue_inventory_fails_closed_on_unreadable_or_partial_store(tmp_path: Path):
    (tmp_path / "branch_tasks.json").write_text("{", encoding="utf-8")
    with pytest.raises(FenceError, match="v1 queue unreadable"):
        inventory_queue_risk(tmp_path)

    (tmp_path / "branch_tasks.json").unlink()
    with sqlite3.connect(tmp_path / ".tinyassets.db") as connection:
        connection.execute("CREATE TABLE branch_tasks_v2 (branch_task_id TEXT)")
    with pytest.raises(FenceError, match="v2 queue schema incomplete"):
        inventory_queue_risk(tmp_path)


def test_receipt_store_requires_one_shared_volume_and_data_relative_override(tmp_path: Path):
    inspections = {
        name: {
            "Id": f"id-{index}",
            "State": {"Running": True, "Pid": 100 + index},
            "Config": {"Env": ["TINYASSETS_TRIGGER_RECEIPTS_DB=/data/receipts.db"]},
            "Mounts": [
                {
                    "Destination": "/data",
                    "Name": "tinyassets-data",
                    "Source": str(tmp_path),
                }
            ],
        }
        for index, name in enumerate(EXPECTED_CONTAINERS)
    }
    selected = resolve_receipt_store(inspections, tmp_path)
    assert selected.container_path == "/data/receipts.db"
    assert selected.host_path == tmp_path / "receipts.db"

    inspections["tinyassets-worker"]["Config"]["Env"] = [
        "TINYASSETS_TRIGGER_RECEIPTS_DB=/tmp/escape.db"
    ]
    with pytest.raises(FenceError, match="outside /data"):
        resolve_receipt_store(inspections, tmp_path)


def test_restart_racer_inventory_includes_all_three_watchdog_families():
    assert set(RESTART_RACER_UNITS) == {
        "daemon-watchdog.timer",
        "daemon-watchdog.service",
        "tinyassets-watchdog.timer",
        "tinyassets-watchdog.service",
        "tinyassets-autoheal.timer",
        "tinyassets-autoheal.service",
    }
    assert DAEMON_SERVICE == "tinyassets-daemon.service"


def test_safe_fleet_requires_exact_five_exact_digest_revision_and_no_old_ids():
    image_ref = "ghcr.io/jonnyton/tinyassets-daemon@sha256:" + "a" * 64
    revision = "b" * 40
    observation = {
        "containers": {
            name: {
                "id": f"new-{index}",
                "running": True,
                "image_ref": image_ref,
                "revision": revision,
            }
            for index, name in enumerate(EXPECTED_CONTAINERS)
        },
        "volume_container_names": list(EXPECTED_CONTAINERS),
        "stray_writer_processes": [],
        "queue_risk": [],
    }
    old_ids = {name: f"old-{index}" for index, name in enumerate(EXPECTED_CONTAINERS)}
    assert safe_fleet_matches(observation, image_ref, revision, old_ids)

    observation["containers"]["tinyassets-worker"]["revision"] = "c" * 40
    assert not safe_fleet_matches(observation, image_ref, revision, old_ids)

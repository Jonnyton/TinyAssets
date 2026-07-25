"""Operator-only, exact-founder-home scoped reset safety contract."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

_HOME_A = "u-01aaaaaaaaaaaaaaaaaaaaaaaa"
_HOME_B = "u-01bbbbbbbbbbbbbbbbbbbbbbbb"
_SUBJECT_A = "workos|test-a"
_SUBJECT_B = "workos|test-b"


def _seed(base: Path) -> None:
    from tinyassets.daemon_server import (
        ensure_universe_registered,
        grant_universe_access,
        initialize_author_server,
        set_founder_home,
    )

    initialize_author_server(base)
    for universe_id, subject in (
        (_HOME_A, _SUBJECT_A),
        (_HOME_B, _SUBJECT_B),
    ):
        home = base / universe_id
        home.mkdir()
        (home / "soul.md").write_text(f"# {universe_id}\n", encoding="utf-8")
        ensure_universe_registered(
            base,
            universe_id=universe_id,
            universe_path=home,
        )
        grant_universe_access(
            base,
            universe_id=universe_id,
            actor_id=subject,
            permission="admin",
            granted_by=subject,
        )
        set_founder_home(
            base,
            founder_sub=subject,
            universe_id=universe_id,
            platform_generated=True,
        )


@pytest.fixture
def seeded(tmp_path: Path) -> Path:
    base = tmp_path / "data"
    base.mkdir()
    _seed(base)
    return base


def _connect(base: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(base / ".tinyassets.db"))
    conn.row_factory = sqlite3.Row
    return conn


def test_inventory_classifies_current_schema_and_epoch2_stores(
    seeded: Path,
) -> None:
    from tinyassets.scoped_reset import (
        MAIN_DB_TABLE_CLASSIFICATIONS,
        inspect_reset_scope,
    )

    scope = inspect_reset_scope(seeded, principal=_SUBJECT_A)

    assert scope.home_id == _HOME_A
    assert scope.blockers == ()
    assert scope.schema_tables <= MAIN_DB_TABLE_CLASSIFICATIONS.keys()
    assert MAIN_DB_TABLE_CLASSIFICATIONS["request_admissions"] == "preserve"
    assert MAIN_DB_TABLE_CLASSIFICATIONS["request_admission_events"] == "preserve"
    assert MAIN_DB_TABLE_CLASSIFICATIONS["branch_tasks_v2"] == "preserve_or_block"
    assert (
        MAIN_DB_TABLE_CLASSIFICATIONS["branch_tasks_v2_quarantine"]
        == "block_matching"
    )
    assert (
        MAIN_DB_TABLE_CLASSIFICATIONS["branch_tasks_v2_maintenance_state"]
        == "preserve"
    )
    assert (
        MAIN_DB_TABLE_CLASSIFICATIONS["request_admission_rollouts"]
        == "preserve_or_block"
    )


def test_unclassified_schema_growth_fails_loudly(seeded: Path) -> None:
    from tinyassets.scoped_reset import ScopedResetSchemaError, inspect_reset_scope

    with _connect(seeded) as conn:
        conn.execute(
            "CREATE TABLE future_store "
            "(row_id TEXT PRIMARY KEY, universe_id TEXT NOT NULL)"
        )

    with pytest.raises(ScopedResetSchemaError, match="future_store"):
        inspect_reset_scope(seeded, principal=_SUBJECT_A)


@pytest.mark.parametrize("foreign_state", ["binding", "grant"])
def test_foreign_binding_or_grant_blocks_exact_home(
    seeded: Path,
    foreign_state: str,
) -> None:
    from tinyassets.scoped_reset import inspect_reset_scope

    with _connect(seeded) as conn:
        if foreign_state == "binding":
            conn.execute(
                "UPDATE founder_home SET universe_id = ? WHERE founder_sub = ?",
                (_HOME_A, _SUBJECT_B),
            )
        else:
            conn.execute(
                """
                INSERT INTO universe_acl (
                    universe_id, actor_id, permission, granted_at, granted_by
                ) VALUES (?, ?, 'read', 1.0, ?)
                """,
                (_HOME_A, _SUBJECT_B, _SUBJECT_A),
            )

    scope = inspect_reset_scope(seeded, principal=_SUBJECT_A)
    assert any(foreign_state in blocker for blocker in scope.blockers)


@pytest.mark.parametrize("active_store", ["daemon", "request", "epoch2"])
def test_active_daemon_request_or_epoch2_task_blocks(
    seeded: Path,
    active_store: str,
) -> None:
    from tinyassets.scoped_reset import inspect_reset_scope

    with _connect(seeded) as conn:
        if active_store == "daemon":
            conn.execute(
                """
                INSERT INTO author_runtime_instances (
                    instance_id, universe_id, author_id, provider_name,
                    model_name, status, created_by, created_at, updated_at
                ) VALUES (
                    'runtime-a', ?, 'author-a', 'test', 'test', 'running',
                    ?, 1.0, 1.0
                )
                """,
                (_HOME_A, _SUBJECT_A),
            )
        elif active_store == "request":
            conn.execute(
                """
                INSERT INTO user_requests (
                    request_id, universe_id, user_id, request_type, text,
                    status, created_at, updated_at
                ) VALUES ('request-a', ?, ?, 'test', 'test', 'open', 1.0, 1.0)
                """,
                (_HOME_A, _SUBJECT_A),
            )
        else:
            conn.execute(
                """
                INSERT INTO branch_tasks_v2 (
                    branch_task_id, admission_id, request_id, universe_id,
                    branch_def_id, trigger_source, priority_weight, status,
                    queued_at
                ) VALUES (
                    'task-a', 'admission-a', 'request-a', ?, 'branch-a',
                    'user_request', 1.0, 'pending', '2026-07-25T00:00:00Z'
                )
                """,
                (_HOME_A,),
            )

    scope = inspect_reset_scope(seeded, principal=_SUBJECT_A)
    assert any(active_store in blocker for blocker in scope.blockers)


def test_credentials_and_reparse_points_block_without_following(
    seeded: Path,
) -> None:
    from tinyassets.scoped_reset import inspect_reset_scope

    credentials = seeded / _HOME_A / ".credential-vault.json"
    credentials.write_text('{"sentinel":"do-not-read"}', encoding="utf-8")
    link = seeded / _HOME_A / "outside-link"
    if sys.platform == "win32":
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "New-Item",
                "-ItemType",
                "Junction",
                "-Path",
                str(link),
                "-Target",
                str(seeded / _HOME_B),
            ],
            check=True,
            capture_output=True,
        )
    else:
        link.symlink_to(seeded / _HOME_B, target_is_directory=True)

    scope = inspect_reset_scope(seeded, principal=_SUBJECT_A)
    assert any("credential" in blocker for blocker in scope.blockers)
    assert any("link or reparse point" in blocker for blocker in scope.blockers)
    assert credentials.read_text(encoding="utf-8") == '{"sentinel":"do-not-read"}'


def test_process_shared_barrier_excludes_reset_while_writer_is_active(
    seeded: Path,
) -> None:
    from tinyassets.scoped_reset import (
        ScopedResetLeaseBusy,
        acquire_maintenance_barrier,
    )

    writer = acquire_maintenance_barrier(seeded, exclusive=False, timeout=0.2)
    try:
        with pytest.raises(ScopedResetLeaseBusy):
            acquire_maintenance_barrier(seeded, exclusive=True, timeout=0.05)
    finally:
        writer.release()

    resetter = acquire_maintenance_barrier(seeded, exclusive=True, timeout=0.2)
    resetter.release()


def test_fault_contract_names_every_recovery_boundary() -> None:
    from tinyassets.scoped_reset import FAULT_POINTS

    assert FAULT_POINTS == (
        "before_rename",
        "after_rename",
        "before_commit",
        "after_commit",
        "before_cleanup",
        "after_cleanup",
    )


def test_scoped_reset_is_not_registered_as_public_surface() -> None:
    package_root = Path(__file__).resolve().parents[1] / "tinyassets"
    public_sources = (
        package_root / "universe_server.py",
        package_root / "mcp_server.py",
        package_root / "api" / "universe.py",
    )
    for source in public_sources:
        text = source.read_text(encoding="utf-8")
        assert "plan_test_identity_reset" not in text
        assert "apply_test_identity_reset" not in text
        assert "recover_scoped_resets" not in text

    assert "TINYASSETS_TEST_IDENTITIES" not in os.environ


def _roster(*, include_subject: bool = True):
    from tinyassets.scoped_reset import TestIdentityRoster

    aliases = {"alice": _SUBJECT_A}
    allowlisted = frozenset({_SUBJECT_A}) if include_subject else frozenset()
    return TestIdentityRoster(
        revision="roster-rev-1",
        aliases=aliases,
        allowlisted_subjects=allowlisted,
    )


def _state_snapshot(base: Path) -> tuple[bytes, tuple[tuple[object, ...], ...]]:
    db_bytes = (base / ".tinyassets.db").read_bytes()
    with _connect(base) as conn:
        rows = tuple(
            tuple(row)
            for row in conn.execute(
                "SELECT founder_sub, universe_id, created_at, platform_generated "
                "FROM founder_home ORDER BY founder_sub"
            )
        )
    return db_bytes, rows


def test_plan_is_read_only_stable_and_never_emits_raw_subject(
    seeded: Path,
) -> None:
    from tinyassets.scoped_reset import plan_test_identity_reset

    before = _state_snapshot(seeded)
    first = plan_test_identity_reset(seeded, alias="alice", roster=_roster())
    second = plan_test_identity_reset(seeded, alias="alice", roster=_roster())

    assert first == second
    assert first["plan_id"].startswith("sha256:")
    assert first["inventory_revision"]
    assert first["roster_revision"] == "roster-rev-1"
    assert first["identity_alias"] == "alice"
    assert first["home_id"] == _HOME_A
    assert first["noop"] is False
    assert first["blockers"] == []
    assert any(
        action["table"] == "founder_home"
        for action in first["database_actions"]
    )
    assert _SUBJECT_A not in json.dumps(first, sort_keys=True)
    assert _state_snapshot(seeded) == before


def test_unknown_alias_and_nonallowlisted_subject_fail_closed(
    seeded: Path,
) -> None:
    from tinyassets.scoped_reset import plan_test_identity_reset

    with pytest.raises(PermissionError, match="unknown test identity alias"):
        plan_test_identity_reset(seeded, alias="missing", roster=_roster())
    with pytest.raises(PermissionError, match="not allowlisted"):
        plan_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(include_subject=False),
        )


def test_allowlisted_subject_without_state_has_stable_noop_plan(
    seeded: Path,
) -> None:
    from tinyassets.scoped_reset import TestIdentityRoster, plan_test_identity_reset

    roster = TestIdentityRoster(
        revision="roster-rev-1",
        aliases={"empty": "workos|empty"},
        allowlisted_subjects=frozenset({"workos|empty"}),
    )
    plan = plan_test_identity_reset(seeded, alias="empty", roster=roster)

    assert plan["noop"] is True
    assert plan["home_id"] is None
    assert plan["database_actions"] == []
    assert plan["filesystem_actions"] == []


def test_plan_digest_changes_when_exact_binding_version_changes(
    seeded: Path,
) -> None:
    from tinyassets.scoped_reset import plan_test_identity_reset

    before = plan_test_identity_reset(seeded, alias="alice", roster=_roster())
    with _connect(seeded) as conn:
        conn.execute(
            "UPDATE founder_home SET created_at = created_at + 1 "
            "WHERE founder_sub = ?",
            (_SUBJECT_A,),
        )
    after = plan_test_identity_reset(seeded, alias="alice", roster=_roster())

    assert before["plan_id"] != after["plan_id"]
    assert before["state_digest"] != after["state_digest"]


def test_operator_cli_loads_private_roster_and_emits_redacted_plan(
    seeded: Path,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from tinyassets.scoped_reset import main

    roster_path = tmp_path / "test-identities.json"
    roster_path.write_text(
        json.dumps({
            "revision": "roster-rev-1",
            "aliases": {"alice": _SUBJECT_A},
            "allowlisted_subjects": [_SUBJECT_A],
        }),
        encoding="utf-8",
    )

    assert main([
        "plan",
        "--data-dir",
        str(seeded),
        "--roster",
        str(roster_path),
        "--identity",
        "alice",
    ]) == 0
    output = capsys.readouterr().out
    plan = json.loads(output)
    assert plan["identity_alias"] == "alice"
    assert plan["home_id"] == _HOME_A
    assert _SUBJECT_A not in output


def test_roster_rejects_credentials_and_unexpected_fields(
    tmp_path: Path,
) -> None:
    from tinyassets.scoped_reset import load_test_identity_roster

    roster_path = tmp_path / "bad-roster.json"
    roster_path.write_text(
        json.dumps({
            "revision": "roster-rev-1",
            "aliases": {"alice": _SUBJECT_A},
            "allowlisted_subjects": [_SUBJECT_A],
            "cookies": "must-not-be-accepted",
        }),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="unexpected roster fields"):
        load_test_identity_roster(roster_path)


def test_completed_plan_replay_is_read_only_and_returns_receipt(
    seeded: Path,
) -> None:
    from tinyassets.scoped_reset import read_completed_plan_receipt

    receipt = {
        "plan_id": "sha256:completed",
        "status": "completed",
        "home_id": _HOME_A,
        "fence": 7,
    }
    with _connect(seeded) as conn:
        conn.execute(
            """
            CREATE TABLE scoped_reset_operations (
                plan_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                commit_witness INTEGER NOT NULL,
                receipt_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            INSERT INTO scoped_reset_operations (
                plan_id, state, commit_witness, receipt_json
            ) VALUES (?, 'completed', 1, ?)
            """,
            ("sha256:completed", json.dumps(receipt)),
        )
    replacement = seeded / _HOME_A / "new-home-sentinel"
    replacement.write_text("new state\n", encoding="utf-8")
    before = _state_snapshot(seeded)

    assert read_completed_plan_receipt(
        seeded,
        plan_id="sha256:completed",
    ) == receipt
    assert read_completed_plan_receipt(
        seeded,
        plan_id="sha256:unknown",
    ) is None
    assert replacement.read_text(encoding="utf-8") == "new state\n"
    assert _state_snapshot(seeded) == before

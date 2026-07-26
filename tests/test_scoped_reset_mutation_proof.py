"""Mutation proof for scoped principal filtering and crash recovery."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

import tinyassets.scoped_reset as scoped_reset
from tinyassets.scoped_reset import (
    ScopedResetBlocked,
    ScopedResetPlanChanged,
    ScopedResetRecoveryError,
    apply_test_identity_reset,
    plan_test_identity_reset,
    recover_scoped_resets,
)
from tinyassets.scoped_reset import (
    TestIdentityRoster as IdentityRoster,
)

_HOME_A = "u-01aaaaaaaaaaaaaaaaaaaaaaaa"
_HOME_B = "u-01bbbbbbbbbbbbbbbbbbbbbbbb"
_SUBJECT_A = "workos|test-a"
_SUBJECT_B = "workos|test-b"


def _connect(base: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(base / ".tinyassets.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _seed(base: Path) -> None:
    from tinyassets.daemon_server import (
        ensure_universe_registered,
        grant_universe_access,
        initialize_author_server,
        set_founder_home,
    )

    initialize_author_server(base)
    for home_id, subject in (
        (_HOME_A, _SUBJECT_A),
        (_HOME_B, _SUBJECT_B),
    ):
        home = base / home_id
        home.mkdir()
        (home / "soul.md").write_text(f"# {home_id}\n", encoding="utf-8")
        ensure_universe_registered(
            base,
            universe_id=home_id,
            universe_path=home,
        )
        grant_universe_access(
            base,
            universe_id=home_id,
            actor_id=subject,
            permission="admin",
            granted_by=subject,
        )
        set_founder_home(
            base,
            founder_sub=subject,
            universe_id=home_id,
            platform_generated=True,
        )


@pytest.fixture
def seeded(tmp_path: Path) -> Path:
    base = tmp_path / "data"
    base.mkdir()
    _seed(base)
    return base


def _roster() -> IdentityRoster:
    return IdentityRoster(
        revision="mutation-proof-v1",
        aliases={"alice": _SUBJECT_A},
        allowlisted_subjects=frozenset({_SUBJECT_A}),
    )


def _plan(base: Path) -> dict[str, object]:
    return plan_test_identity_reset(base, alias="alice", roster=_roster())


def _fault_after(point_to_fail: str):
    def inject(point: str) -> None:
        if point == point_to_fail:
            raise RuntimeError(f"injected:{point}")

    return inject


def test_widened_principal_filter_is_rejected_before_delete(
    seeded: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from tinyassets.daemon_server import grant_universe_access

    grant_universe_access(
        seeded,
        universe_id=_HOME_B,
        actor_id=_SUBJECT_A,
        permission="read",
        granted_by=_SUBJECT_B,
    )
    plan = _plan(seeded)
    original = scoped_reset._action_key_values

    def widen_filter(
        action: dict[str, object],
        *,
        principal: str,
    ) -> dict[str, object]:
        keys = original(action, principal=principal)
        if action["table"] == "universe_acl":
            keys.pop("actor_id")
        return keys

    monkeypatch.setattr(scoped_reset, "_action_key_values", widen_filter)

    with pytest.raises(ScopedResetPlanChanged, match="exact primary key"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
        )
    with _connect(seeded) as conn:
        foreign = conn.execute(
            "SELECT permission FROM universe_acl "
            "WHERE universe_id = ? AND actor_id = ?",
            (_HOME_B, _SUBJECT_B),
        ).fetchone()
    assert foreign is not None
    monkeypatch.undo()
    recover_scoped_resets(seeded)
    assert (seeded / _HOME_A / "soul.md").is_file()


def test_real_planner_predicate_widening_changes_the_reviewed_plan(
    seeded: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(seeded)
    original = scoped_reset._select_rows

    def widen_real_selection(
        conn: sqlite3.Connection,
        *,
        table: str,
        where: str,
        params: tuple[object, ...],
    ) -> list[sqlite3.Row]:
        if table == "universe_acl" and where == "actor_id = ?":
            return list(conn.execute('SELECT * FROM "universe_acl" ORDER BY rowid'))
        return original(conn, table=table, where=where, params=params)

    monkeypatch.setattr(scoped_reset, "_select_rows", widen_real_selection)

    with pytest.raises(ScopedResetPlanChanged, match="reviewed plan"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
        )
    assert (seeded / _HOME_A / "soul.md").is_file()
    assert (seeded / _HOME_B / "soul.md").is_file()


def test_founder_home_predicate_widening_is_rejected(
    seeded: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with _connect(seeded) as conn:
        conn.execute(
            "UPDATE founder_home SET universe_id = ? WHERE founder_sub = ?",
            (_HOME_A, _SUBJECT_B),
        )

    original = scoped_reset._select_rows

    def widen_founder_home_selection(
        conn: sqlite3.Connection,
        *,
        table: str,
        where: str,
        params: tuple[object, ...],
    ) -> list[sqlite3.Row]:
        if table == "founder_home":
            return list(
                conn.execute(
                    'SELECT * FROM "founder_home" WHERE universe_id = ? '
                    "ORDER BY rowid",
                    (_HOME_A,),
                )
            )
        return original(conn, table=table, where=where, params=params)

    monkeypatch.setattr(
        scoped_reset,
        "_select_rows",
        widen_founder_home_selection,
    )

    with _connect(seeded) as conn:
        with pytest.raises(
            scoped_reset.ScopedResetPlanChanged,
            match="founder-home selection escaped",
        ):
            scoped_reset._database_actions(
                conn,
                principal=_SUBJECT_A,
                alias="alice",
                home_id=_HOME_A,
            )


@pytest.mark.parametrize(
    "fault_point",
    ["after_journal", "after_prepare", "after_complete"],
)
def test_journal_ordering_windows_recover_without_stranding_state(
    seeded: Path,
    fault_point: str,
) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match=f"injected:{fault_point}"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after(fault_point),
        )

    recover_scoped_resets(seeded)

    journals = list((seeded / ".scoped-reset-journal").glob("*.json"))
    assert journals == []
    if fault_point in {"after_journal", "after_prepare"}:
        assert (seeded / _HOME_A / "soul.md").is_file()
    else:
        assert not (seeded / _HOME_A).exists()


def test_partial_temporary_journal_is_swept_before_retry(
    seeded: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(seeded)
    real_replace = os.replace

    def fail_journal_publish(source: str | Path, target: str | Path) -> None:
        if Path(source).suffix == ".tmp" and Path(target).suffix == ".json":
            raise OSError("injected journal publish failure")
        real_replace(source, target)

    monkeypatch.setattr(scoped_reset.os, "replace", fail_journal_publish)
    with pytest.raises(OSError, match="journal publish"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
        )
    monkeypatch.undo()

    recover_scoped_resets(seeded)

    assert list((seeded / ".scoped-reset-journal").glob("*.tmp")) == []
    assert (seeded / _HOME_A / "soul.md").is_file()


def test_recovery_rederives_paths_and_validates_journal(
    seeded: Path,
) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match="injected:after_rename"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_rename"),
        )
    with _connect(seeded) as conn:
        conn.execute(
            "UPDATE scoped_reset_operations SET source_path = ? "
            "WHERE plan_id = ?",
            (str(seeded.parent / "outside"), plan["plan_id"]),
        )

    with pytest.raises(ScopedResetRecoveryError, match="path evidence"):
        recover_scoped_resets(seeded)
    assert not (seeded / _HOME_A).exists()


def test_recovery_rejects_journal_content_tampering(seeded: Path) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match="injected:after_rename"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_rename"),
        )
    operation_id = str(plan["plan_id"]).removeprefix("sha256:")
    journal = seeded / ".scoped-reset-journal" / f"{operation_id}.json"
    payload = json.loads(journal.read_text(encoding="utf-8"))
    payload["source_path"] = str(seeded.parent / "outside")
    journal.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ScopedResetRecoveryError, match="journal evidence"):
        recover_scoped_resets(seeded)
    assert not (seeded / _HOME_A).exists()


def test_journal_persists_reviewed_filesystem_identity(seeded: Path) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match="injected:after_prepare"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_prepare"),
        )

    operation_id = str(plan["plan_id"]).removeprefix("sha256:")
    journal = seeded / ".scoped-reset-journal" / f"{operation_id}.json"
    payload = json.loads(journal.read_text(encoding="utf-8"))
    planned_identity = plan["filesystem_actions"][0]["home_filesystem_identity"]

    assert payload.get("home_filesystem_identity") == planned_identity


def test_recovery_rejects_linked_staging_operation_ancestor(
    seeded: Path,
) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match="injected:after_rename"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_rename"),
        )
    operation_id = str(plan["plan_id"]).removeprefix("sha256:")
    staging_root = seeded / ".scoped-reset-staging"
    operation_dir = staging_root / operation_id
    relocated = staging_root / "relocated-operation"
    operation_dir.replace(relocated)
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
                str(operation_dir),
                "-Target",
                str(relocated),
            ],
            check=True,
            capture_output=True,
        )
    else:
        operation_dir.symlink_to(relocated, target_is_directory=True)

    with pytest.raises(ScopedResetRecoveryError, match="path evidence"):
        recover_scoped_resets(seeded)
    assert not (seeded / _HOME_A).exists()


@pytest.mark.parametrize(
    "boundary",
    [
        "reviewed_source",
        "pre_rename",
        "precommit_recovery",
        "postcommit_cleanup",
    ],
)
def test_foreign_directory_is_refused_at_every_filesystem_boundary(
    seeded: Path,
    boundary: str,
) -> None:
    plan = _plan(seeded)
    bob_file = seeded / _HOME_B / "bobs_novel.md"
    bob_file.write_text("belongs to bob\n", encoding="utf-8")
    parked_alice = seeded.parent / f"parked-alice-{boundary}"

    if boundary == "reviewed_source":
        (seeded / _HOME_A).replace(parked_alice)
        (seeded / _HOME_B).replace(seeded / _HOME_A)
        with pytest.raises((ScopedResetBlocked, ScopedResetPlanChanged)):
            apply_test_identity_reset(
                seeded,
                alias="alice",
                roster=_roster(),
                plan_id=plan["plan_id"],
            )
        foreign_location = seeded / _HOME_A
    elif boundary == "pre_rename":
        def replace_before_rename(point: str) -> None:
            if point == "before_rename":
                (seeded / _HOME_A).replace(parked_alice)
                (seeded / _HOME_B).replace(seeded / _HOME_A)

        with pytest.raises(ScopedResetPlanChanged, match="filesystem identity"):
            apply_test_identity_reset(
                seeded,
                alias="alice",
                roster=_roster(),
                plan_id=plan["plan_id"],
                fault_injector=replace_before_rename,
            )
        foreign_location = seeded / _HOME_A
    else:
        fault_point = (
            "after_rename"
            if boundary == "precommit_recovery"
            else "after_commit"
        )
        with pytest.raises(RuntimeError, match=f"injected:{fault_point}"):
            apply_test_identity_reset(
                seeded,
                alias="alice",
                roster=_roster(),
                plan_id=plan["plan_id"],
                fault_injector=_fault_after(fault_point),
            )
        operation_id = str(plan["plan_id"]).removeprefix("sha256:")
        staging = seeded / ".scoped-reset-staging" / operation_id / "home"
        staging.replace(parked_alice)
        (seeded / _HOME_B).replace(staging)
        with pytest.raises(ScopedResetRecoveryError, match="filesystem identity"):
            recover_scoped_resets(seeded)
        foreign_location = staging

    assert (foreign_location / "bobs_novel.md").read_text(
        encoding="utf-8"
    ) == "belongs to bob\n"
    assert (parked_alice / "soul.md").is_file()


@pytest.mark.parametrize("replacement_state", ["neither", "foreign_source"])
def test_precommit_recovery_refuses_unaccounted_home_state(
    seeded: Path,
    replacement_state: str,
) -> None:
    plan = _plan(seeded)
    bob_file = seeded / _HOME_B / "bobs_novel.md"
    bob_file.write_text("belongs to bob\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="injected:after_rename"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_rename"),
        )

    operation_id = str(plan["plan_id"]).removeprefix("sha256:")
    staging = seeded / ".scoped-reset-staging" / operation_id / "home"
    parked_alice = seeded.parent / f"parked-alice-{replacement_state}"
    staging.replace(parked_alice)
    if replacement_state == "foreign_source":
        (seeded / _HOME_B).replace(seeded / _HOME_A)

    with pytest.raises(ScopedResetRecoveryError):
        recover_scoped_resets(seeded)

    with _connect(seeded) as conn:
        state = conn.execute(
            "SELECT state FROM scoped_reset_operations WHERE plan_id = ?",
            (plan["plan_id"],),
        ).fetchone()
    assert state is not None and state[0] == "staged"
    assert (parked_alice / "soul.md").is_file()
    if replacement_state == "foreign_source":
        assert (seeded / _HOME_A / "bobs_novel.md").read_text(
            encoding="utf-8"
        ) == "belongs to bob\n"
    else:
        assert bob_file.read_text(encoding="utf-8") == "belongs to bob\n"


def test_precommit_recovery_accepts_already_restored_owned_home(
    seeded: Path,
) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match="injected:after_rename"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_rename"),
        )

    operation_id = str(plan["plan_id"]).removeprefix("sha256:")
    staging = seeded / ".scoped-reset-staging" / operation_id / "home"
    staging.replace(seeded / _HOME_A)

    recover_scoped_resets(seeded)

    with _connect(seeded) as conn:
        state = conn.execute(
            "SELECT state FROM scoped_reset_operations WHERE plan_id = ?",
            (plan["plan_id"],),
        ).fetchone()
    assert state is not None and state[0] == "rolled_back"
    assert (seeded / _HOME_A / "soul.md").is_file()


def test_missing_commit_witness_never_restores_files_over_deleted_rows(
    seeded: Path,
) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match="injected:after_commit"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_commit"),
        )
    with _connect(seeded) as conn:
        conn.execute(
            "UPDATE scoped_reset_operations SET commit_witness = 0 "
            "WHERE plan_id = ?",
            (plan["plan_id"],),
        )

    with pytest.raises(
        ScopedResetRecoveryError,
        match="pre-commit database state changed",
    ):
        recover_scoped_resets(seeded)
    assert not (seeded / _HOME_A).exists()

    with _connect(seeded) as conn:
        conn.execute(
            "UPDATE scoped_reset_operations SET commit_witness = 1 "
            "WHERE plan_id = ?",
            (plan["plan_id"],),
        )
    recover_scoped_resets(seeded)
    assert not (seeded / _HOME_A).exists()


def test_filesystem_rollback_failure_stays_recoverable_and_loud(
    seeded: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match="injected:after_rename"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_rename"),
        )
    real_replace = os.replace

    def fail_restore(source: str | Path, target: str | Path) -> None:
        if Path(target).name == _HOME_A:
            raise OSError("injected rollback rename failure")
        real_replace(source, target)

    monkeypatch.setattr(scoped_reset.os, "replace", fail_restore)
    with pytest.raises(ScopedResetRecoveryError, match="rollback rename failed"):
        recover_scoped_resets(seeded)
    assert not (seeded / _HOME_A).exists()

    monkeypatch.undo()
    recover_scoped_resets(seeded)
    assert (seeded / _HOME_A / "soul.md").is_file()


def test_rollback_flushes_both_rename_parents_and_staging_root(
    seeded: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(seeded)
    with pytest.raises(RuntimeError, match="injected:after_rename"):
        apply_test_identity_reset(
            seeded,
            alias="alice",
            roster=_roster(),
            plan_id=plan["plan_id"],
            fault_injector=_fault_after("after_rename"),
        )
    operation_id = str(plan["plan_id"]).removeprefix("sha256:")
    operation_dir = seeded / ".scoped-reset-staging" / operation_id
    seen: list[Path] = []
    real_fsync = scoped_reset._fsync_directory

    def record_fsync(path: Path) -> None:
        seen.append(path)
        real_fsync(path)

    monkeypatch.setattr(scoped_reset, "_fsync_directory", record_fsync)
    recover_scoped_resets(seeded)

    assert {
        seeded,
        operation_dir,
        seeded / ".scoped-reset-staging",
    } <= set(seen)

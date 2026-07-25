"""Mutation proof for scoped principal filtering and crash recovery."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

import tinyassets.scoped_reset as scoped_reset
from tinyassets.scoped_reset import (
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

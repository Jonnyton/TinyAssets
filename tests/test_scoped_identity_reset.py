"""Security contract for reversible, test-identity-scoped reset."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

_A1 = "u-01aaaaaaaaaaaaaaaaaaaaaaaa"
_A2 = "u-01aaaaaaaaaaaaaaaaaaaaaaab"
_B1 = "u-01bbbbbbbbbbbbbbbbbbbbbbbb"
_ALLOWED = frozenset({"founder-a", "founder-b", "unknown-test-user"})


def _rows(base: Path, table: str) -> list[tuple]:
    with sqlite3.connect(str(base / ".tinyassets.db")) as conn:
        return conn.execute(f'SELECT * FROM "{table}" ORDER BY 1').fetchall()


def _snapshot(base: Path) -> dict[str, object]:
    tables = (
        "universes",
        "universe_rules",
        "universe_acl",
        "founder_home",
        "branches",
        "branch_heads",
        "branch_definitions",
        "goals",
        "gate_claims",
        "canonical_bindings",
    )
    return {
        "tables": {table: _rows(base, table) for table in tables},
        "dirs": {
            uid: (base / uid / "soul.md").read_bytes()
            for uid in (_A1, _A2, _B1)
            if (base / uid / "soul.md").is_file()
        },
        "runs": (base / ".runs.db").read_bytes(),
        "wiki": (base / "wiki" / "commons.md").read_bytes(),
    }


def _seed(base: Path) -> None:
    from tinyassets.daemon_server import (
        ensure_universe_registered,
        grant_universe_access,
        initialize_author_server,
        save_branch_definition,
        save_goal,
        set_founder_home,
    )

    initialize_author_server(base)
    for uid in (_A1, _A2, _B1):
        udir = base / uid
        udir.mkdir()
        (udir / "soul.md").write_text(f"# {uid}\n", encoding="utf-8")
        ensure_universe_registered(base, universe_id=uid, universe_path=udir)

    for uid in (_A1, _A2):
        grant_universe_access(
            base,
            universe_id=uid,
            actor_id="founder-a",
            permission="admin",
            granted_by="founder-a",
        )
    grant_universe_access(
        base,
        universe_id=_B1,
        actor_id="founder-b",
        permission="admin",
        granted_by="founder-b",
    )
    # Delegated admin is access, not ownership. Reset A revokes this grant but
    # must never turn it into authority to delete B's universe.
    grant_universe_access(
        base,
        universe_id=_B1,
        actor_id="founder-a",
        permission="admin",
        granted_by="founder-b",
    )
    set_founder_home(base, founder_sub="founder-a", universe_id=_A1)
    set_founder_home(base, founder_sub="founder-b", universe_id=_B1)

    save_branch_definition(
        base,
        branch_def={"branch_def_id": "b-commons", "name": "commons"},
    )
    save_goal(base, goal={"goal_id": "g-commons", "name": "commons goal"})
    with sqlite3.connect(str(base / ".tinyassets.db")) as conn:
        conn.execute(
            "INSERT INTO gate_claims "
            "(claim_id, branch_def_id, goal_id, rung_key, evidence_url, "
            " evidence_note, claimed_by, claimed_at) "
            "VALUES ('c-commons', 'b-commons', 'g-commons', 'r1', '', '', "
            "        'founder-b', '2026-07-21T00:00:00Z')"
        )
        conn.execute(
            "INSERT INTO canonical_bindings "
            "(goal_id, scope_token, branch_version_id, bound_by_actor_id, "
            " bound_at, visibility) "
            "VALUES ('g-commons', '', 'bv-commons', 'founder-b', 1.0, 'public')"
        )
        for branch_id, uid, actor in (
            ("bi-a1", _A1, "founder-a"),
            ("bi-a2", _A2, "founder-a"),
            ("bi-b", _B1, "founder-b"),
        ):
            conn.execute(
                "INSERT INTO branches "
                "(branch_id, universe_id, name, created_by, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 1.0, 1.0)",
                (branch_id, uid, branch_id, actor),
            )
            conn.execute(
                "INSERT INTO branch_heads (branch_id, updated_at) VALUES (?, 1.0)",
                (branch_id,),
            )

    (base / ".runs.db").write_bytes(b"runs-sentinel")
    wiki = base / "wiki"
    wiki.mkdir()
    (wiki / "commons.md").write_text("wiki sentinel\n", encoding="utf-8")


@pytest.fixture
def seeded(tmp_path: Path) -> Path:
    base = tmp_path / "data"
    base.mkdir()
    _seed(base)
    return base


def test_plan_enumerates_exact_scope_without_mutating(seeded: Path) -> None:
    from tinyassets.reset import plan_test_identity_reset

    before = _snapshot(seeded)
    plan = plan_test_identity_reset(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
    )

    assert plan["principal"] == "founder-a"
    assert plan["universe_dirs"] == [_A1, _A2]
    assert plan["rows"]["founder_home"] == [
        {"founder_sub": "founder-a"},
    ]
    assert plan["rows"]["universe_acl"] == [
        {"universe_id": _A1, "actor_id": "founder-a"},
        {"universe_id": _A2, "actor_id": "founder-a"},
        {"universe_id": _B1, "actor_id": "founder-a"},
    ]
    owned_branch_ids = {
        row[0] for row in _rows(seeded, "branches") if row[1] in {_A1, _A2}
    }
    assert {row["branch_id"] for row in plan["rows"]["branch_heads"]} == owned_branch_ids
    assert plan["plan_id"].startswith("sha256:")
    assert plan["reversible"] is True
    assert _snapshot(seeded) == before


def test_apply_requires_allowlist_and_the_exact_reviewed_plan(seeded: Path) -> None:
    from tinyassets.reset import ResetPlanChangedError, reset_test_identity

    before = _snapshot(seeded)
    with pytest.raises(PermissionError, match="not an allowlisted test identity"):
        reset_test_identity(
            seeded,
            principal="production-founder",
            allowed_principals=_ALLOWED,
            confirm=False,
        )
    with pytest.raises(ResetPlanChangedError):
        reset_test_identity(
            seeded,
            principal="founder-a",
            allowed_principals=_ALLOWED,
            confirm=True,
            plan_id="sha256:not-the-reviewed-plan",
        )
    assert _snapshot(seeded) == before


def test_apply_is_scoped_repeatable_and_reversible(seeded: Path) -> None:
    from tinyassets.reset import reset_test_identity, restore_test_identity

    before = _snapshot(seeded)
    plan = reset_test_identity(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
        confirm=False,
    )
    result = reset_test_identity(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
        confirm=True,
        plan_id=plan["plan_id"],
    )

    assert result["done"] is True
    assert result["reset_id"]
    assert not (seeded / _A1).exists()
    assert not (seeded / _A2).exists()
    assert (seeded / _B1 / "soul.md").read_bytes() == before["dirs"][_B1]
    assert [row[0] for row in _rows(seeded, "universes")] == [_B1]
    assert [(row[0], row[1]) for row in _rows(seeded, "founder_home")] == [
        ("founder-b", _B1),
    ]
    assert [(row[0], row[1], row[2]) for row in _rows(seeded, "universe_acl")] == [
        (_B1, "founder-b", "admin"),
    ]
    assert _rows(seeded, "branch_definitions") == before["tables"]["branch_definitions"]
    assert _rows(seeded, "goals") == before["tables"]["goals"]
    assert _rows(seeded, "gate_claims") == before["tables"]["gate_claims"]
    assert _rows(seeded, "canonical_bindings") == before["tables"]["canonical_bindings"]
    assert (seeded / ".runs.db").read_bytes() == before["runs"]
    assert (seeded / "wiki" / "commons.md").read_bytes() == before["wiki"]

    restore_plan = restore_test_identity(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
        reset_id=result["reset_id"],
        confirm=False,
    )
    assert restore_plan["universe_dirs"] == [_A1, _A2]
    assert restore_plan["confirmed"] is False
    assert _snapshot(seeded) != before
    restored = restore_test_identity(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
        reset_id=result["reset_id"],
        confirm=True,
    )
    assert restored["restored"] is True
    assert _snapshot(seeded) == before

    # A fresh plan/apply cycle after the first reset sees no state and is a
    # no-op. Running the operation twice therefore equals running it once.
    empty_plan = reset_test_identity(
        seeded,
        principal="unknown-test-user",
        allowed_principals=_ALLOWED,
        confirm=False,
    )
    empty_result = reset_test_identity(
        seeded,
        principal="unknown-test-user",
        allowed_principals=_ALLOWED,
        confirm=True,
        plan_id=empty_plan["plan_id"],
    )
    assert empty_result["done"] is True
    assert empty_result["reset_id"] == ""
    assert _snapshot(seeded) == before


def test_restore_refuses_to_overwrite_new_state(seeded: Path) -> None:
    from tinyassets.reset import (
        ResetRestoreConflictError,
        reset_test_identity,
        restore_test_identity,
    )

    plan = reset_test_identity(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
        confirm=False,
    )
    result = reset_test_identity(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
        confirm=True,
        plan_id=plan["plan_id"],
    )
    (seeded / _A1).mkdir()
    (seeded / _A1 / "new.md").write_text("new state\n", encoding="utf-8")
    before = (seeded / _A1 / "new.md").read_bytes()

    with pytest.raises(ResetRestoreConflictError, match="already exists"):
        restore_test_identity(
            seeded,
            principal="founder-a",
            allowed_principals=_ALLOWED,
            reset_id=result["reset_id"],
            confirm=True,
        )
    assert (seeded / _A1 / "new.md").read_bytes() == before
    assert [row[0] for row in _rows(seeded, "universes")] == [_B1]


def test_hostile_index_value_cannot_delete_operational_directories(seeded: Path) -> None:
    from tinyassets.reset import reset_test_identity

    wiki_before = (seeded / "wiki" / "commons.md").read_bytes()
    with sqlite3.connect(str(seeded / ".tinyassets.db")) as conn:
        conn.execute(
            "INSERT INTO universe_acl "
            "(universe_id, actor_id, permission, granted_at, granted_by) "
            "VALUES ('wiki', 'hostile-test-user', 'admin', 1.0, 'hostile-test-user')"
        )
    allowed = _ALLOWED | {"hostile-test-user"}
    plan = reset_test_identity(
        seeded,
        principal="hostile-test-user",
        allowed_principals=allowed,
        confirm=False,
    )
    result = reset_test_identity(
        seeded,
        principal="hostile-test-user",
        allowed_principals=allowed,
        confirm=True,
        plan_id=plan["plan_id"],
    )

    assert result["done"] is True
    assert result["universe_dirs"] == []
    assert (seeded / "wiki" / "commons.md").read_bytes() == wiki_before


def test_manifest_never_contains_bearer_or_host_credentials(seeded: Path, monkeypatch) -> None:
    from tinyassets.reset import reset_test_identity

    monkeypatch.setenv("OPENAI_API_KEY", "host-api-key-sentinel")
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "host-oauth-sentinel")
    plan = reset_test_identity(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
        confirm=False,
    )
    result = reset_test_identity(
        seeded,
        principal="founder-a",
        allowed_principals=_ALLOWED,
        confirm=True,
        plan_id=plan["plan_id"],
    )
    manifest = (
        seeded
        / ".resets"
        / result["reset_id"]
        / "manifest.json"
    ).read_text(encoding="utf-8")

    assert "host-api-key-sentinel" not in manifest
    assert "host-oauth-sentinel" not in manifest
    assert "bearer" not in manifest.lower()
    assert json.loads(manifest)["principal"] == "founder-a"


def test_operator_roster_supports_multiple_real_subjects_without_tokens() -> None:
    from tinyassets.reset import load_test_identity_roster

    roster = load_test_identity_roster(
        '{"alice":"workos-user-01","bob":"workos-user-02"}'
    )

    assert roster == {
        "alice": "workos-user-01",
        "bob": "workos-user-02",
    }
    with pytest.raises(ValueError, match="JSON object"):
        load_test_identity_roster('["workos-user-01"]')
    with pytest.raises(ValueError, match="anonymous"):
        load_test_identity_roster('{"guest":"anonymous"}')
    with pytest.raises(ValueError, match="unique"):
        load_test_identity_roster('{"alice":"same-user","bob":"same-user"}')


def test_operator_cli_resolves_alias_and_requires_reviewed_plan(
    seeded: Path,
    monkeypatch,
    capsys,
) -> None:
    from tinyassets.reset import main

    monkeypatch.setenv(
        "TINYASSETS_TEST_IDENTITIES",
        '{"alice":"founder-a","bob":"founder-b"}',
    )
    assert main(["plan", "--data-dir", str(seeded), "--identity", "alice"]) == 0
    plan = json.loads(capsys.readouterr().out)
    assert plan["principal"] == "founder-a"
    assert plan["universe_dirs"] == [_A1, _A2]

    with pytest.raises(SystemExit):
        main([
            "apply",
            "--data-dir",
            str(seeded),
            "--identity",
            "alice",
            "--plan-id",
            "sha256:not-reviewed",
        ])
    assert (seeded / _A1).is_dir()

    assert main([
        "apply",
        "--data-dir",
        str(seeded),
        "--identity",
        "alice",
        "--plan-id",
        plan["plan_id"],
    ]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["done"] is True
    assert result["reset_id"]
    assert (seeded / _B1).is_dir()

    assert main([
        "restore",
        "--data-dir",
        str(seeded),
        "--identity",
        "alice",
        "--reset-id",
        result["reset_id"],
    ]) == 0
    restore_plan = json.loads(capsys.readouterr().out)
    assert restore_plan["confirmed"] is False
    assert not (seeded / _A1).exists()

    assert main([
        "restore",
        "--data-dir",
        str(seeded),
        "--identity",
        "alice",
        "--reset-id",
        result["reset_id"],
        "--confirm",
    ]) == 0
    restored = json.loads(capsys.readouterr().out)
    assert restored["restored"] is True
    assert (seeded / _A1).is_dir()

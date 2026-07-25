"""Actor-scoped Goal canonical storage and transition behavior."""

from __future__ import annotations

import json

from tinyassets import daemon_server
from tinyassets.branch_versions import publish_branch_version
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.daemon_server import (
    _connect,
    _initialize_author_server_locked,
    get_goal,
    initialize_author_server,
    save_branch_definition,
    save_goal,
    set_canonical_branch,
)


def _seed_goal(base_path, goal_id: str = "g1", author: str = "alice") -> None:
    save_goal(
        base_path,
        goal={"goal_id": goal_id, "name": "Scoped Goal", "author": author},
    )


def _seed_version(base_path, branch_id: str) -> str:
    node = NodeDefinition(
        node_id="n1",
        display_name="N1",
        prompt_template="echo",
    )
    branch = BranchDefinition(
        branch_def_id=branch_id,
        name=branch_id,
        graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
        edges=[EdgeDefinition(from_node="n1", to_node="END")],
        entry_point="n1",
        node_defs=[node],
        state_schema=[],
    )
    save_branch_definition(base_path, branch_def=branch.to_dict())
    return publish_branch_version(
        base_path,
        branch.to_dict(),
        publisher="alice",
    ).branch_version_id


def _set_personal(base_path, **kwargs):
    assert hasattr(daemon_server, "set_goal_canonical")
    return daemon_server.set_goal_canonical(base_path, **kwargs)


def _resolve(base_path, **kwargs):
    assert hasattr(daemon_server, "resolve_goal_canonical")
    return daemon_server.resolve_goal_canonical(base_path, **kwargs)


def _get_personal(base_path, **kwargs):
    assert hasattr(daemon_server, "get_goal_canonical")
    return daemon_server.get_goal_canonical(base_path, **kwargs)


def test_goal_canonicals_schema_has_exact_columns_and_composite_key(tmp_path):
    initialize_author_server(tmp_path)

    with _connect(tmp_path) as conn:
        columns = list(conn.execute("PRAGMA table_info(goal_canonicals)"))

    assert [column["name"] for column in columns] == [
        "goal_id",
        "scope_actor",
        "branch_version_id",
        "set_at",
        "set_by",
    ]
    assert {
        column["name"] for column in columns if column["pk"]
    } == {"goal_id", "scope_actor"}


def test_default_write_updates_new_table_and_legacy_column(tmp_path):
    _seed_goal(tmp_path)
    branch_version_id = _seed_version(tmp_path, "default")

    set_canonical_branch(
        tmp_path,
        goal_id="g1",
        branch_version_id=branch_version_id,
        set_by="alice",
    )

    with _connect(tmp_path) as conn:
        row = conn.execute(
            "SELECT branch_version_id, set_by FROM goal_canonicals "
            "WHERE goal_id = ? AND scope_actor = ''",
            ("g1",),
        ).fetchone()
    assert row["branch_version_id"] == branch_version_id
    assert row["set_by"] == "alice"
    assert get_goal(
        tmp_path,
        goal_id="g1",
    )["canonical_branch_version_id"] == branch_version_id


def test_personal_canonicals_coexist_and_resolve_without_changing_default(tmp_path):
    _seed_goal(tmp_path)
    default_version = _seed_version(tmp_path, "default")
    alice_version = _seed_version(tmp_path, "alice")
    bob_version = _seed_version(tmp_path, "bob")
    set_canonical_branch(
        tmp_path,
        goal_id="g1",
        branch_version_id=default_version,
        set_by="alice",
    )

    _set_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="alice",
        branch_version_id=alice_version,
        set_by="alice",
    )
    _set_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
        branch_version_id=bob_version,
        set_by="bob",
    )

    assert _resolve(
        tmp_path,
        goal_id="g1",
        scope_actor="alice",
    ) == alice_version
    assert _resolve(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
    ) == bob_version
    assert _get_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
    )["branch_version_id"] == bob_version
    assert _resolve(
        tmp_path,
        goal_id="g1",
        scope_actor="carol",
    ) == default_version
    assert get_goal(
        tmp_path,
        goal_id="g1",
    )["canonical_branch_version_id"] == default_version


def test_personal_overwrite_and_unset_falls_back_to_default(tmp_path):
    _seed_goal(tmp_path)
    default_version = _seed_version(tmp_path, "default")
    first_personal = _seed_version(tmp_path, "personal-1")
    second_personal = _seed_version(tmp_path, "personal-2")
    set_canonical_branch(
        tmp_path,
        goal_id="g1",
        branch_version_id=default_version,
        set_by="alice",
    )

    _set_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
        branch_version_id=first_personal,
        set_by="bob",
    )
    _set_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
        branch_version_id=second_personal,
        set_by="bob",
    )
    assert _resolve(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
    ) == second_personal

    _set_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
        branch_version_id=None,
        set_by="bob",
    )
    assert _resolve(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
    ) == default_version


def test_resolution_falls_back_to_legacy_when_new_table_has_no_rows(tmp_path):
    _seed_goal(tmp_path)
    legacy_version = _seed_version(tmp_path, "legacy")
    with _connect(tmp_path) as conn:
        conn.execute(
            "UPDATE goals SET canonical_branch_version_id = ? WHERE goal_id = ?",
            (legacy_version, "g1"),
        )
        conn.execute("DELETE FROM goal_canonicals WHERE goal_id = ?", ("g1",))

    assert _resolve(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
    ) == legacy_version


def test_migration_backfills_legacy_default_idempotently(tmp_path):
    _seed_goal(tmp_path)
    legacy_version = _seed_version(tmp_path, "legacy")
    with _connect(tmp_path) as conn:
        conn.execute(
            "UPDATE goals SET canonical_branch_version_id = ? WHERE goal_id = ?",
            (legacy_version, "g1"),
        )
        conn.execute("DELETE FROM goal_canonicals WHERE goal_id = ?", ("g1",))

    _initialize_author_server_locked(tmp_path)
    _initialize_author_server_locked(tmp_path)

    with _connect(tmp_path) as conn:
        rows = list(
            conn.execute(
                "SELECT scope_actor, branch_version_id FROM goal_canonicals "
                "WHERE goal_id = ?",
                ("g1",),
            )
        )
    assert [(row["scope_actor"], row["branch_version_id"]) for row in rows] == [
        ("", legacy_version),
    ]


def test_action_allows_actor_to_set_only_their_personal_scope(
    tmp_path,
    monkeypatch,
):
    from tinyassets.api import engine_helpers, market

    _seed_goal(tmp_path, author="alice")
    default_version = _seed_version(tmp_path, "default")
    bob_version = _seed_version(tmp_path, "bob")
    set_canonical_branch(
        tmp_path,
        goal_id="g1",
        branch_version_id=default_version,
        set_by="alice",
    )
    monkeypatch.setattr(market, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(engine_helpers, "_current_actor", lambda: "bob")

    result = json.loads(
        market._action_goal_set_canonical(
            {
                "goal_id": "g1",
                "branch_version_id": bob_version,
                "scope": "bob",
            }
        )
    )

    assert result["status"] == "ok"
    assert result["scope_actor"] == "bob"
    assert result["canonical_branch_version_id"] == bob_version
    assert _resolve(tmp_path, goal_id="g1", scope_actor="bob") == bob_version
    assert get_goal(
        tmp_path,
        goal_id="g1",
    )["canonical_branch_version_id"] == default_version


def test_action_rejects_cross_actor_scope_even_for_goal_author(
    tmp_path,
    monkeypatch,
):
    from tinyassets.api import engine_helpers, market

    _seed_goal(tmp_path, author="alice")
    bob_version = _seed_version(tmp_path, "bob")
    monkeypatch.setattr(market, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(engine_helpers, "_current_actor", lambda: "alice")

    result = json.loads(
        market._action_goal_set_canonical(
            {
                "goal_id": "g1",
                "branch_version_id": bob_version,
                "scope": "bob",
            }
        )
    )

    assert result["status"] == "rejected"
    assert "another actor" in result["error"]
    assert _get_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
    ) is None


def test_action_keeps_default_authority_restricted(tmp_path, monkeypatch):
    from tinyassets.api import engine_helpers, market

    _seed_goal(tmp_path, author="alice")
    bob_version = _seed_version(tmp_path, "bob")
    monkeypatch.setattr(market, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(engine_helpers, "_current_actor", lambda: "bob")
    monkeypatch.delenv("UNIVERSE_SERVER_CAPABILITIES", raising=False)

    result = json.loads(
        market._action_goal_set_canonical(
            {
                "goal_id": "g1",
                "branch_version_id": bob_version,
                "scope": "",
            }
        )
    )

    assert result["status"] == "rejected"
    assert get_goal(
        tmp_path,
        goal_id="g1",
    )["canonical_branch_version_id"] is None


def test_goal_get_returns_current_actors_resolved_canonical(tmp_path, monkeypatch):
    from tinyassets.api import branches, engine_helpers, market

    _seed_goal(tmp_path, author="alice")
    default_version = _seed_version(tmp_path, "default")
    bob_version = _seed_version(tmp_path, "bob")
    set_canonical_branch(
        tmp_path,
        goal_id="g1",
        branch_version_id=default_version,
        set_by="alice",
    )
    _set_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
        branch_version_id=bob_version,
        set_by="bob",
    )
    monkeypatch.setattr(market, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(engine_helpers, "_current_actor", lambda: "bob")
    monkeypatch.setattr(branches, "_ensure_workflow_db", lambda: None)

    result = json.loads(market._action_goal_get({"goal_id": "g1"}))

    assert result["scope_actor"] == "bob"
    assert result["actor_canonical_branch_version_id"] == bob_version
    assert result["goal"]["canonical_branch_version_id"] == default_version


def test_run_canonical_routes_personal_binding_to_immutable_runner(
    tmp_path,
    monkeypatch,
):
    from tinyassets.api import engine_helpers, market, runs

    _seed_goal(tmp_path, author="alice")
    default_version = _seed_version(tmp_path, "default")
    bob_version = _seed_version(tmp_path, "bob")
    set_canonical_branch(
        tmp_path,
        goal_id="g1",
        branch_version_id=default_version,
        set_by="alice",
    )
    _set_personal(
        tmp_path,
        goal_id="g1",
        scope_actor="bob",
        branch_version_id=bob_version,
        set_by="bob",
    )
    seen: dict[str, str] = {}

    def _run_version(kwargs):
        seen.update(kwargs)
        return json.dumps({"status": "queued", "run_id": "run-personal"})

    monkeypatch.setattr(market, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(engine_helpers, "_current_actor", lambda: "bob")
    monkeypatch.setattr(runs, "_action_run_branch_version", _run_version)

    result = json.loads(
        market._action_goal_run_canonical(
            {"goal_id": "g1", "inputs_json": '{"patch_notes":"fix it"}'}
        )
    )

    assert seen["branch_version_id"] == bob_version
    assert result["branch_version_id_used"] == bob_version
    assert result["scope_actor"] == "bob"
    assert result["source"] == "actor_canonical"


def test_run_resolution_uses_new_table_default_before_legacy(tmp_path):
    from tinyassets.api.canonical_dispatch import resolve_canonical_for_run

    _seed_goal(tmp_path, author="alice")
    new_default = _seed_version(tmp_path, "new-default")
    with _connect(tmp_path) as conn:
        conn.execute(
            "INSERT INTO goal_canonicals "
            "(goal_id, scope_actor, branch_version_id, set_at, set_by) "
            "VALUES (?, '', ?, 1.0, 'alice')",
            ("g1", new_default),
        )
        conn.execute(
            "UPDATE goals SET canonical_branch_version_id = NULL "
            "WHERE goal_id = ?",
            ("g1",),
        )
        conn.execute(
            "DELETE FROM canonical_bindings WHERE goal_id = ?",
            ("g1",),
        )

    resolution = resolve_canonical_for_run(
        tmp_path,
        goal_id="g1",
        viewer="carol",
    )

    assert resolution["ok"] is True
    assert resolution["branch_version_id"] == new_default
    assert resolution["source"] == "canonical_stored"

"""A fresh account can hold a UI bundle before it has published anything.

Installing a bundle needs somewhere private to put it, and that used to mean an
`app_experience` binding, which used to mean a published agent definition. So the
person most likely to ask for a custom UI — someone who has just signed up — was
the one person who could not have one, and the only way out was to adopt a
stranger's published layout first.

A binding may now carry no definition at all. These tests are about what that must
NOT cost: it must not publish anything, must not be reusable by another account,
must not mint a second place on a retry, and must never be picked up by the paths
that need a real design behind them.
"""

from __future__ import annotations

import pytest

from tinyassets.custom_agents import (
    AgentValidationError,
    create_binding,
    get_binding,
    list_bindings,
    publish_definition,
    update_binding,
)


@pytest.fixture()
def base(tmp_path):
    return tmp_path


def _experience(name: str = "App experience") -> dict:
    return {"schema_version": 1, "name": name, "role": "app_experience"}


def _bootstrap(base, *, universe: str = "u-alice", actor: str = "alice", payload=None):
    return create_binding(
        base,
        universe_id=universe,
        definition_id="",
        created_by=actor,
        payload=payload if payload is not None else _experience(),
    )


def test_a_new_account_gets_a_private_place_with_nothing_published(base) -> None:
    binding = _bootstrap(base)

    assert binding["agent_definition_id"] is None
    assert binding["status"] == "configured"
    assert binding["revision"] == 1
    assert binding["created_by"] == "alice"
    assert binding["configuration"]["role"] == "app_experience"

    # The point of the whole thing: nothing about this account became public.
    from tinyassets.custom_agents import list_definitions

    assert list_definitions(base) == []

    # And it is reachable as its own row, so a UI can be stored in it.
    assert get_binding(
        base, universe_id="u-alice", binding_id=binding["agent_binding_id"]
    )["agent_binding_id"] == binding["agent_binding_id"]


def test_bootstrapping_twice_returns_the_same_place_untouched(base) -> None:
    first = _bootstrap(base)

    # A real install writes a library into it. A second bootstrap must not be a
    # way to wipe that: the caller of a bootstrap is not passing the fields it is
    # not trying to change.
    stored = dict(first["configuration"])
    stored["ui_library"] = [{"kind": "tinyassets.app-ui.v1", "ui_id": "office"}]
    update_binding(
        base,
        universe_id="u-alice",
        binding_id=first["agent_binding_id"],
        expected_revision=first["revision"],
        updated_by="alice",
        payload=stored,
    )

    second = _bootstrap(base)

    assert second["agent_binding_id"] == first["agent_binding_id"]
    assert second["revision"] == 2, "the update landed and the retry did not bump it"
    assert second["configuration"]["ui_library"] == stored["ui_library"]
    assert len(list_bindings(base, universe_id="u-alice")) == 1

    # Idempotent under a differing payload too — that is the retry-after-an
    # -unconfirmed-reply case, where the client may resend a default document.
    third = _bootstrap(base, payload=_experience("Renamed by a retry"))
    assert third["agent_binding_id"] == first["agent_binding_id"]
    assert third["configuration"]["name"] == "App experience"
    assert third["configuration"]["ui_library"] == stored["ui_library"]


def test_another_account_never_reuses_someone_elses_place(base) -> None:
    mine = _bootstrap(base, actor="alice")
    theirs = _bootstrap(base, actor="bob")

    assert theirs["agent_binding_id"] != mine["agent_binding_id"]
    assert theirs["created_by"] == "bob"

    # Same universe, two owners, two private places. Returning Alice's row to Bob
    # would hand him her configuration.
    rows = list_bindings(base, universe_id="u-alice")
    assert {row["created_by"] for row in rows} == {"alice", "bob"}


def test_a_different_role_gets_its_own_place(base) -> None:
    experience = _bootstrap(base)
    other = _bootstrap(
        base, payload={"schema_version": 1, "name": "Other", "role": "something_else"}
    )
    assert other["agent_binding_id"] != experience["agent_binding_id"]

    # A role is what makes the lookup specific, so it is required when there is no
    # definition to identify the binding by.
    with pytest.raises(AgentValidationError, match="must name a role"):
        _bootstrap(base, payload={"schema_version": 1, "name": "No role"})


def test_configuration_updates_work_without_ever_adopting_a_definition(base) -> None:
    binding = _bootstrap(base)
    stored = dict(binding["configuration"])
    stored["ui_selection"] = {"version": 1, "state": "active", "ui_id": "office"}

    updated = update_binding(
        base,
        universe_id="u-alice",
        binding_id=binding["agent_binding_id"],
        expected_revision=binding["revision"],
        updated_by="alice",
        payload=stored,
    )

    # The regression this pins: the definition stayed None instead of becoming the
    # literal string "None" and failing its own existence check.
    assert updated["agent_definition_id"] is None
    assert updated["configuration"]["ui_selection"]["ui_id"] == "office"
    assert updated["revision"] == 2


def test_adopting_a_published_design_later_still_works(base) -> None:
    binding = _bootstrap(base)
    definition = publish_definition(
        base,
        author_id="alice",
        payload={
            "schema_version": 1,
            "name": "A layout",
            "components": {
                "layout": {
                    "kind": "tinyassets.app-layout.v1",
                    "version": 1,
                    "surfaces": ["conversation"],
                    "density": "compact",
                }
            },
        },
    )

    adopted = update_binding(
        base,
        universe_id="u-alice",
        binding_id=binding["agent_binding_id"],
        expected_revision=binding["revision"],
        updated_by="alice",
        payload=binding["configuration"],
        definition_id=definition["agent_definition_id"],
    )
    assert adopted["agent_definition_id"] == definition["agent_definition_id"]

    # A nonexistent one is still refused — relaxing NULL must not relax that.
    with pytest.raises(LookupError):
        update_binding(
            base,
            universe_id="u-alice",
            binding_id=binding["agent_binding_id"],
            expected_revision=adopted["revision"],
            updated_by="alice",
            payload=binding["configuration"],
            definition_id="agent_definition_does_not_exist",
        )


def test_a_definitionless_binding_is_invisible_to_definition_lookups(base) -> None:
    """The safety half of making the column nullable.

    A binding with no design behind it must never be chosen to answer a
    conversation or be activated for serving. That is not a separate guard: SQLite
    does not match NULL with `= ?`, so every reader that resolves a binding BY
    definition simply cannot see it. This asserts the property those readers rely
    on, at the storage layer where it actually holds.
    """
    import sqlite3

    from tinyassets.custom_agents import _agent_connect

    experience = _bootstrap(base)
    definition = publish_definition(
        base,
        author_id="alice",
        payload={
            "schema_version": 1,
            "name": "Real",
            "components": {"c": {"kind": "k", "version": 1}},
        },
    )
    adopted = create_binding(
        base,
        universe_id="u-alice",
        definition_id=definition["agent_definition_id"],
        created_by="alice",
        payload=_experience("Adopted"),
    )

    with _agent_connect(base) as conn:
        conn.row_factory = sqlite3.Row
        for probe in (definition["agent_definition_id"], "", "None", "null"):
            found = conn.execute(
                "SELECT agent_binding_id FROM agent_bindings WHERE agent_definition_id = ?",
                (probe,),
            ).fetchall()
            ids = {str(row["agent_binding_id"]) for row in found}
            assert experience["agent_binding_id"] not in ids, probe

        # The adopted one IS found, so the query itself works and the absence
        # above is about NULL rather than about a broken probe.
        found = conn.execute(
            "SELECT agent_binding_id FROM agent_bindings WHERE agent_definition_id = ?",
            (definition["agent_definition_id"],),
        ).fetchall()
        assert {str(r["agent_binding_id"]) for r in found} == {
            adopted["agent_binding_id"]
        }


def test_existing_databases_migrate_without_touching_a_row(base) -> None:
    """The migration rebuilds the table, so it has to preserve ids and revisions.

    A live client holds a revision as a CAS precondition. Renumbering during a
    migration would turn its next write into a phantom conflict.
    """
    import sqlite3

    from tinyassets.custom_agents import _agent_connect, _migrate_nullable_binding_definition

    definition = publish_definition(
        base,
        author_id="alice",
        payload={
            "schema_version": 1,
            "name": "Pre-migration",
            "components": {"c": {"kind": "k", "version": 1}},
        },
    )
    binding = create_binding(
        base,
        universe_id="u-alice",
        definition_id=definition["agent_definition_id"],
        created_by="alice",
        payload=_experience(),
    )
    bumped = update_binding(
        base,
        universe_id="u-alice",
        binding_id=binding["agent_binding_id"],
        expected_revision=1,
        updated_by="alice",
        payload=_experience("Bumped"),
    )
    assert bumped["revision"] == 2

    # Put the OLD shape back, then migrate forward again.
    with _agent_connect(base) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("DROP INDEX IF EXISTS idx_agent_binding_universe")
        conn.execute("DROP INDEX IF EXISTS idx_agent_binding_definition")
        conn.execute("ALTER TABLE agent_bindings RENAME TO agent_bindings_old")
        conn.execute(
            """
            CREATE TABLE agent_bindings (
                agent_binding_id TEXT PRIMARY KEY,
                universe_id TEXT NOT NULL,
                agent_definition_id TEXT NOT NULL,
                configuration_json TEXT NOT NULL,
                revision INTEGER NOT NULL DEFAULT 1 CHECK (revision >= 1),
                status TEXT NOT NULL DEFAULT 'configured'
                    CHECK (status IN ('configured', 'serving')),
                created_by TEXT NOT NULL,
                updated_by TEXT NOT NULL,
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY(agent_definition_id)
                    REFERENCES agent_definitions(agent_definition_id) ON DELETE RESTRICT
            )
            """
        )
        conn.execute(
            "INSERT INTO agent_bindings SELECT * FROM agent_bindings_old"
        )
        conn.execute("DROP TABLE agent_bindings_old")
        assert "NOT NULL" in str(
            conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'agent_bindings'"
            ).fetchone()[0]
        )

        _migrate_nullable_binding_definition(conn)

        sql = str(
            conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'agent_bindings'"
            ).fetchone()[0]
        )
        assert "agent_definition_id TEXT NOT NULL" not in sql
        rows = conn.execute("SELECT * FROM agent_bindings").fetchall()
        assert len(rows) == 1
        assert str(rows[0]["agent_binding_id"]) == binding["agent_binding_id"]
        assert int(rows[0]["revision"]) == 2, "a renumbered revision is a phantom conflict"
        assert str(rows[0]["agent_definition_id"]) == definition["agent_definition_id"]

        # Idempotent: running it again on the new shape changes nothing.
        _migrate_nullable_binding_definition(conn)
        assert len(conn.execute("SELECT * FROM agent_bindings").fetchall()) == 1

    # And the bootstrap works on the migrated database.
    assert _bootstrap(base)["agent_definition_id"] is None

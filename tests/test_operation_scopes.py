"""Users define what their own operations may spend — within a ceiling.

The ceiling is the whole safety argument: a self-declaration that can confer
anything is privilege escalation with extra steps.
"""

from __future__ import annotations

import pytest

from tinyassets.storage.operation_scopes import (
    DELEGABLE_SCOPES,
    OperationScopeError,
    OperationScopeStore,
)


@pytest.fixture
def store(tmp_path):
    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(str(tmp_path))
    return OperationScopeStore(tmp_path)


def test_a_user_can_define_their_own_operation(store):
    defined = store.define(
        universe_id="u-a", operation="nightly_digest",
        scopes=["tinyassets.knowledge"], defined_by="user_1",
    )
    assert defined.scopes == ("tinyassets.knowledge",)
    assert store.scopes_for(universe_id="u-a", operation="nightly_digest") == (
        "tinyassets.knowledge",
    )


def test_definitions_do_not_leak_across_universes(store):
    store.define(universe_id="u-a", operation="nightly_digest",
                 scopes=["tinyassets.knowledge"], defined_by="user_1")
    assert store.scopes_for(universe_id="u-b", operation="nightly_digest") == ()


def test_a_non_delegable_scope_is_refused_loudly(store):
    """Silently dropping it would run, fail later, and look like our fault."""
    with pytest.raises(OperationScopeError, match="cannot be delegated"):
        store.define(universe_id="u-a", operation="sneaky",
                     scopes=["tinyassets.cloud_worker"], defined_by="user_1")
    assert store.scopes_for(universe_id="u-a", operation="sneaky") == ()


def test_a_partly_invalid_definition_is_refused_entirely(store):
    with pytest.raises(OperationScopeError):
        store.define(universe_id="u-a", operation="mixed",
                     scopes=["tinyassets.memory", "tinyassets.desktop"],
                     defined_by="user_1")
    assert store.scopes_for(universe_id="u-a", operation="mixed") == ()


def test_operator_scopes_are_outside_the_ceiling():
    for scope in ("tinyassets.cloud_worker", "tinyassets.desktop",
                  "tinyassets.cloud_worker_healthcheck"):
        assert scope not in DELEGABLE_SCOPES, scope


def test_a_revoked_scope_stops_working_on_read(store, monkeypatch):
    """Re-filtered on read: removing a scope from the ceiling disarms old rows."""
    store.define(universe_id="u-a", operation="digest",
                 scopes=["tinyassets.knowledge"], defined_by="user_1")
    monkeypatch.setattr(
        "tinyassets.storage.operation_scopes.DELEGABLE_SCOPES", frozenset()
    )
    assert store.scopes_for(universe_id="u-a", operation="digest") == ()


def test_a_definition_overrides_the_shipped_default(store):
    assert store.scopes_for(
        universe_id="u-a", operation="repository_spec_delivery"
    ) == ("tinyassets.extensions.costly",)
    store.define(universe_id="u-a", operation="repository_spec_delivery",
                 scopes=["tinyassets.memory"], defined_by="user_1")
    assert store.scopes_for(
        universe_id="u-a", operation="repository_spec_delivery"
    ) == ("tinyassets.memory",)


def test_redefining_replaces_rather_than_accumulates(store):
    store.define(universe_id="u-a", operation="digest",
                 scopes=["tinyassets.knowledge", "tinyassets.memory"],
                 defined_by="user_1")
    store.define(universe_id="u-a", operation="digest",
                 scopes=["tinyassets.memory"], defined_by="user_1")
    assert store.scopes_for(universe_id="u-a", operation="digest") == (
        "tinyassets.memory",
    )


@pytest.mark.parametrize("bad", ["", "  ", "has space", "x", "a" * 80, "9lead"])
def test_malformed_operation_names_are_refused(store, bad):
    with pytest.raises(OperationScopeError):
        store.define(universe_id="u-a", operation=bad,
                     scopes=["tinyassets.memory"], defined_by="user_1")


def test_operation_names_are_case_normalised(store):
    """Deliberate: `Nightly_Digest` and `nightly_digest` are one operation.

    Otherwise a user could define two operations that read identically and
    differ only in case, and a binding declaring one would silently miss the
    other's scopes.
    """
    store.define(universe_id="u-a", operation="Nightly_Digest",
                 scopes=["tinyassets.memory"], defined_by="user_1")
    assert store.scopes_for(universe_id="u-a", operation="nightly_digest") == (
        "tinyassets.memory",
    )


def test_an_empty_scope_list_is_refused(store):
    with pytest.raises(OperationScopeError, match="at least one"):
        store.define(universe_id="u-a", operation="empty", scopes=[],
                     defined_by="user_1")


def test_listing_includes_builtins_and_definitions(store):
    store.define(universe_id="u-a", operation="nightly_digest",
                 scopes=["tinyassets.knowledge"], defined_by="user_1")
    names = {item.operation for item in store.list_for(universe_id="u-a")}
    assert "nightly_digest" in names
    assert "repository_spec_delivery" in names

"""Automations of any kind: schedule + branch + inputs + declared operations."""

from __future__ import annotations

import json

import pytest

from tinyassets.storage.scheduled_work import (
    ScheduledWorkError,
    ScheduledWorkStore,
)


@pytest.fixture
def store(tmp_path):
    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(str(tmp_path))
    return ScheduledWorkStore(tmp_path)


def _make(store, **over):
    kwargs = dict(
        universe_id="u-a", name="niche_watch", kind="niche_watch",
        branch_def_id="abc123", inputs_json='{"sites": ["example.com"]}',
        cadence_seconds=3600, declared_operations=["fetch_web"], owner_id="user_1",
    )
    kwargs.update(over)
    return store.create(**kwargs)


def test_any_kind_can_be_built(store):
    """The point: kinds are free labels, not a platform enum."""
    for kind in ("niche_watch", "crm_sync", "wallet_trade", "repository_spec"):
        item = _make(store, name=kind, kind=kind)
        assert item.kind == kind
    assert len(store.list_for(universe_id="u-a")) == 4


def test_it_starts_paused(store):
    """Nothing spends the founder's compute the moment it is described."""
    assert _make(store).state == "paused"


def test_a_branch_is_required(store):
    """An automation runs a branch; without one there is no work to do."""
    with pytest.raises(ScheduledWorkError, match="branch_def_id is required"):
        _make(store, branch_def_id="")


def test_declared_operations_are_carried(store):
    item = _make(store, declared_operations=["fetch_web", "draft_post"])
    assert item.declared_operations == ("draft_post", "fetch_web")


def test_start_and_stop_round_trip(store):
    item = _make(store)
    started = store.set_state(universe_id="u-a", work_id=item.work_id,
                              state="active", expected_revision=item.revision)
    assert started.state == "active" and started.revision == 2
    stopped = store.set_state(universe_id="u-a", work_id=item.work_id,
                              state="paused", expected_revision=started.revision)
    assert stopped.state == "paused" and stopped.revision == 3


def test_a_stale_revision_is_refused(store):
    """Without this a control call silently no-ops while reporting success."""
    item = _make(store)
    store.set_state(universe_id="u-a", work_id=item.work_id, state="active",
                    expected_revision=item.revision)
    with pytest.raises(ScheduledWorkError, match="revision conflict"):
        store.set_state(universe_id="u-a", work_id=item.work_id, state="paused",
                        expected_revision=item.revision)


def test_it_cannot_be_controlled_from_another_universe(store):
    item = _make(store)
    with pytest.raises(ScheduledWorkError, match="no such automation"):
        store.set_state(universe_id="u-other", work_id=item.work_id,
                        state="active", expected_revision=item.revision)
    assert store.get(universe_id="u-other", work_id=item.work_id) is None


def test_names_are_unique_per_universe_but_not_globally(store):
    _make(store)
    with pytest.raises(ScheduledWorkError, match="already exists"):
        _make(store)
    other = _make(store, universe_id="u-b")
    assert other.name == "niche_watch"


def test_a_busy_loop_cadence_is_refused(store):
    with pytest.raises(ScheduledWorkError, match="at least 60"):
        _make(store, cadence_seconds=5)


@pytest.mark.parametrize("bad", ["not json", "[1,2]", '"text"'])
def test_malformed_inputs_are_refused(store, bad):
    with pytest.raises(ScheduledWorkError, match="inputs_json"):
        _make(store, inputs_json=bad)


def test_inputs_round_trip_as_an_object(store):
    item = _make(store, inputs_json='{"topic": "prediction markets"}')
    assert json.loads(item.inputs_json) == {"topic": "prediction markets"}


def test_listing_is_scoped_to_the_universe(store):
    _make(store)
    _make(store, universe_id="u-b", name="other_thing")
    names = [i.name for i in store.list_for(universe_id="u-a")]
    assert names == ["niche_watch"]


def test_inputs_can_be_repaired_without_rebuilding(store):
    """A branch declaring an input the automation lacks must be FIXABLE.

    Found live 2026-08-07: the agent looped correctly, ran the automation twice,
    and could not repair it because create was the only verb. An automation you
    can only replace is not one a founder can iterate on.
    """
    item = _make(store, inputs_json="{}")
    fixed = store.update_inputs(
        universe_id="u-a", work_id=item.work_id,
        inputs_json='{"topic": "prediction markets"}',
        expected_revision=item.revision,
    )
    assert json.loads(fixed.inputs_json) == {"topic": "prediction markets"}
    assert fixed.revision == 2


def test_updating_inputs_honours_the_revision(store):
    item = _make(store)
    store.update_inputs(universe_id="u-a", work_id=item.work_id,
                        inputs_json='{"a": 1}', expected_revision=item.revision)
    with pytest.raises(ScheduledWorkError, match="revision conflict"):
        store.update_inputs(universe_id="u-a", work_id=item.work_id,
                            inputs_json='{"b": 2}',
                            expected_revision=item.revision)


def test_inputs_cannot_be_edited_from_another_universe(store):
    item = _make(store)
    with pytest.raises(ScheduledWorkError, match="no such automation"):
        store.update_inputs(universe_id="u-other", work_id=item.work_id,
                            inputs_json='{"a": 1}',
                            expected_revision=item.revision)


@pytest.mark.parametrize("bad", ["not json", "[1,2]"])
def test_malformed_replacement_inputs_are_refused(store, bad):
    item = _make(store)
    with pytest.raises(ScheduledWorkError, match="inputs_json"):
        store.update_inputs(universe_id="u-a", work_id=item.work_id,
                            inputs_json=bad, expected_revision=item.revision)
    assert json.loads(store.get(universe_id="u-a", work_id=item.work_id).inputs_json)


def test_a_table_created_before_deliver_to_is_migrated(tmp_path):
    """CREATE TABLE IF NOT EXISTS does not alter an existing table.

    Adding a column to _SCHEMA passes fresh installs and every test while
    breaking production on INSERT with "no column named X". That is exactly what
    silently killed six build_automation attempts on 2026-08-07.
    """
    import sqlite3

    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.storage import db_path

    initialize_author_server(str(tmp_path))
    # Build the OLD shape by hand: everything except deliver_to.
    conn = sqlite3.connect(db_path(tmp_path))
    conn.executescript(
        "CREATE TABLE scheduled_work (work_id TEXT PRIMARY KEY,"
        " universe_id TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,"
        " branch_def_id TEXT NOT NULL, inputs_json TEXT NOT NULL,"
        " cadence_seconds INTEGER NOT NULL, declared_operations_json TEXT NOT NULL,"
        " state TEXT NOT NULL, revision INTEGER NOT NULL, owner_id TEXT NOT NULL,"
        " created_at REAL NOT NULL, updated_at REAL NOT NULL,"
        " last_run_at REAL, last_run_id TEXT, UNIQUE (universe_id, name))"
    )
    conn.commit()
    conn.close()

    store = ScheduledWorkStore(tmp_path)  # must migrate, not explode
    created = store.create(
        universe_id="u-a", name="after_migration", kind="probe",
        branch_def_id="abc", owner_id="user_1", deliver_to="D123",
    )
    assert created.deliver_to == "D123"

"""The shared catalog, and the floor it must never cross.

This is the first store in the repo that is deliberately shared BETWEEN users, so
the tests that matter most are the ones about what it cannot contain. The platform
floor is "do not affect other users"; a shared store passes it only if reading it
reveals nothing about any user.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from tinyassets.storage import db_path
from tinyassets.storage.learned_models import (
    COLUMNS,
    FORBIDDEN_COLUMNS,
    LearnedModelCatalog,
    record_verified_model,
)


def _at(minutes):
    return datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc) + timedelta(minutes=minutes)


@pytest.fixture
def catalog(tmp_path):
    return LearnedModelCatalog(tmp_path)


# ---------------------------------------------------------------------------
# The cross-user floor.
# ---------------------------------------------------------------------------


def test_the_table_has_exactly_three_columns_and_none_is_about_a_user(catalog, tmp_path):
    catalog.record(source_kind="subscription_cli", model_id="vendor-line-4-7", now=_at(0))
    with sqlite3.connect(db_path(tmp_path)) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(learned_models)")]
    assert tuple(columns) == COLUMNS, (
        "a fourth column in a store shared between users has to be argued for, not "
        "added: see FORBIDDEN_COLUMNS")
    assert not FORBIDDEN_COLUMNS.intersection(columns)


def test_no_caller_supplied_identity_can_reach_the_table(catalog, tmp_path):
    """The API has no parameter for it, and the stored bytes prove nothing leaked."""
    catalog.record(source_kind="subscription_cli", model_id="vendor-line-4-7", now=_at(0))
    catalog.record(source_kind="api_key_http", model_id="other-line-2-1", now=_at(1))
    with sqlite3.connect(db_path(tmp_path)) as conn:
        # The STORED DATA, not the DDL: the schema's own comments explain why the
        # columns are safe to share, so they legitimately contain the word "user".
        rows = conn.execute("SELECT * FROM learned_models").fetchall()
        stored = " ".join(str(value) for row in rows for value in row).lower()
    for secret in ("owner", "universe", "user", "principal", "actor", "prompt",
                   "credential", "token", "home-a", "u-1"):
        assert secret not in stored, f"{secret!r} reached a store shared between users"
    # What IS there is only the three facts, twice.
    assert len(rows) == 2 and all(len(row) == 3 for row in rows)
    assert "subscription_cli" in stored and "vendor-line-4-7" in stored


def test_a_second_verification_accumulates_nothing(catalog, tmp_path):
    """No count of verifications: "3 universes use this" is a fact about users."""
    assert catalog.record(source_kind="subscription_cli", model_id="x-4-7", now=_at(0)) is True
    # A different user, later, verifying the same id.
    assert catalog.record(source_kind="subscription_cli", model_id="x-4-7", now=_at(99)) is False
    rows = catalog.for_source_kind("subscription_cli")
    assert len(rows) == 1
    assert rows[0].first_verified_at.startswith("2026-09-26T12:00"), (
        "the first verification time stands; a later one must not overwrite it")


def test_one_source_kind_never_sees_another_kinds_ids(catalog):
    catalog.record(source_kind="subscription_cli", model_id="cli-line-4-7", now=_at(0))
    catalog.record(source_kind="api_key_http", model_id="http-line-2-1", now=_at(1))
    assert [row.model_id for row in catalog.for_source_kind("subscription_cli")] == ["cli-line-4-7"]
    assert [row.model_id for row in catalog.for_source_kind("api_key_http")] == ["http-line-2-1"]


# ---------------------------------------------------------------------------
# Reading, and what it does not do.
# ---------------------------------------------------------------------------


def test_an_absent_database_reads_as_empty_without_creating_one(tmp_path):
    missing = tmp_path / "nothing-here"
    assert LearnedModelCatalog(missing).for_source_kind("subscription_cli") == []
    assert not missing.exists(), "an observational read must not bring a database into being"


def test_a_database_without_the_table_reads_as_empty_and_gains_nothing(tmp_path):
    path = db_path(tmp_path)
    with sqlite3.connect(path) as seed:
        seed.execute("CREATE TABLE sentinel (only_this TEXT)")
    before = {row[0] for row in sqlite3.connect(path).execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert LearnedModelCatalog(tmp_path).for_source_kind("subscription_cli") == []
    after = {row[0] for row in sqlite3.connect(path).execute(
        "SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert after == before, f"the read created {sorted(after - before)}"


@pytest.mark.parametrize("bad", ["", "   ", None, 5, "x" * 201, "has\u0000null"])
def test_a_malformed_id_or_kind_is_refused_not_stored(catalog, bad):
    with pytest.raises(ValueError):
        catalog.record(source_kind="subscription_cli", model_id=bad, now=_at(0))
    with pytest.raises(ValueError):
        catalog.record(source_kind=bad, model_id="x-4-7", now=_at(0))
    assert catalog.for_source_kind("subscription_cli") == []


# ---------------------------------------------------------------------------
# Newest per class, through the store.
# ---------------------------------------------------------------------------


def test_only_the_newest_of_each_class_is_offered(catalog):
    for minute, model in enumerate(
        ["vendor-line-4-6", "vendor-line-4-7", "vendor-other-5-1", "plain-model"]
    ):
        catalog.record(source_kind="subscription_cli", model_id=model, now=_at(minute))
    assert sorted(row.model_id for row in catalog.newest_for_source_kind("subscription_cli")) == [
        "plain-model", "vendor-line-4-7", "vendor-other-5-1"]


def test_learning_a_newer_sibling_does_not_delete_the_older_row(catalog):
    """The catalog keeps both; only the OFFER is reduced.

    This is what lets a user who is happily using the older one keep it: their own
    id is unioned back on top of the offer, and it is still here to be unioned.
    """
    catalog.record(source_kind="subscription_cli", model_id="vendor-line-4-6", now=_at(0))
    catalog.record(source_kind="subscription_cli", model_id="vendor-line-4-7", now=_at(1))
    assert len(catalog.for_source_kind("subscription_cli")) == 2
    assert [row.model_id for row in catalog.newest_for_source_kind("subscription_cli")] == [
        "vendor-line-4-7"]


# ---------------------------------------------------------------------------
# Best-effort recording.
# ---------------------------------------------------------------------------


def test_a_failed_learn_never_raises_at_the_call_site(tmp_path, monkeypatch):
    """The caller is always a turn that already produced a result."""
    import tinyassets.storage.learned_models as module

    def explode(self, **_kwargs):
        raise sqlite3.DatabaseError("disk went away")

    monkeypatch.setattr(module.LearnedModelCatalog, "record", explode)
    assert record_verified_model(tmp_path, source_kind="subscription_cli",
                                 model_id="vendor-line-4-7") is False


def test_the_best_effort_path_still_records_when_it_can(tmp_path):
    assert record_verified_model(tmp_path, source_kind="subscription_cli",
                                 model_id="vendor-line-4-7") is True
    assert [row.model_id for row in LearnedModelCatalog(tmp_path)
            .for_source_kind("subscription_cli")] == ["vendor-line-4-7"]


# ---------------------------------------------------------------------------
# End to end: the union actually reaches a universe's model list.
# ---------------------------------------------------------------------------


def _native_models(tmp_path, monkeypatch, declared):
    """Drive the REAL _native_models, the function that builds a CLI source's list."""
    from types import SimpleNamespace

    from tinyassets.provider_assignment_manifest import ModelAccess
    from tinyassets.providers import served_model_plan

    monkeypatch.setattr(served_model_plan, "_resolve_serving_source", lambda *args: None)
    monkeypatch.setattr("tinyassets.providers.call.get_provider_router", lambda: SimpleNamespace(
        _providers={"a-cli": SimpleNamespace(is_available=lambda: True)},
    ))
    return served_model_plan._native_models(
        tmp_path, tmp_path / "universe", "owner",
        SimpleNamespace(provider="a-cli", access=ModelAccess("explicit", declared)),
    )


def test_a_learned_id_reaches_a_universe_that_never_declared_it(tmp_path, monkeypatch):
    """The founder's bug: a newly released model was invisible until someone patched.

    The owner declared only an older id. Another user's verified call taught the
    platform a newer one, and it now appears here - as a candidate needing access,
    which is honest: the platform knows it exists, this universe has not granted it.
    """
    LearnedModelCatalog(tmp_path).record(
        source_kind="subscription", model_id="vendor-newline-5-1", now=_at(0))
    models = _native_models(tmp_path, monkeypatch, ("", "vendor-line-4-6"))
    listed = {model.model_id: model.availability_basis for model in models.models}
    assert "vendor-newline-5-1" in listed, (
        "a model the platform has verified elsewhere must be offerable here")
    assert listed["vendor-newline-5-1"] == "platform_verified_elsewhere", (
        "and must say where the evidence came from, not claim this connection "
        "verified it")
    # The owner's own declaration keeps its own honest basis.
    assert listed["vendor-line-4-6"] == "owner_declared"


def test_a_users_own_id_is_never_removed_by_a_newer_catalog_sibling(tmp_path, monkeypatch):
    """Founder: "if someone wants to use opus 4.6 that would only be on their list"."""
    catalog = LearnedModelCatalog(tmp_path)
    catalog.record(source_kind="subscription", model_id="vendor-line-4-6", now=_at(0))
    catalog.record(source_kind="subscription", model_id="vendor-line-4-7", now=_at(1))
    # This universe declared the OLDER one and is happily using it.
    models = _native_models(tmp_path, monkeypatch, ("", "vendor-line-4-6"))
    ids = [model.model_id for model in models.models]
    assert "vendor-line-4-6" in ids, (
        "the catalog offers only the newest of a class, but a union must never "
        "remove the id this user already had")
    assert "vendor-line-4-7" in ids, "and the newer one is added alongside it"
    # The user's own row is NOT relabelled as platform-verified.
    basis = {model.model_id: model.availability_basis for model in models.models}
    assert basis["vendor-line-4-6"] == "owner_declared"


def test_the_catalog_never_duplicates_an_id_the_universe_already_has(tmp_path, monkeypatch):
    LearnedModelCatalog(tmp_path).record(
        source_kind="subscription", model_id="vendor-line-4-7", now=_at(0))
    models = _native_models(tmp_path, monkeypatch, ("", "vendor-line-4-7"))
    ids = [model.model_id for model in models.models]
    assert ids.count("vendor-line-4-7") == 1
    # ...and the one that survives is the universe's own declaration.
    basis = {model.model_id: model.availability_basis for model in models.models}
    assert basis["vendor-line-4-7"] == "owner_declared"


def test_an_empty_catalog_leaves_the_list_exactly_as_it_was(tmp_path, monkeypatch):
    models = _native_models(tmp_path, monkeypatch, ("", "vendor-line-4-6"))
    assert [model.model_id for model in models.models] == ["", "vendor-line-4-6"]
    assert [model.availability_basis for model in models.models] == [
        "executor_default", "owner_declared"]


def test_another_source_kinds_learning_does_not_leak_into_this_one(tmp_path, monkeypatch):
    LearnedModelCatalog(tmp_path).record(
        source_kind="http", model_id="http-only-3-1", now=_at(0))
    models = _native_models(tmp_path, monkeypatch, ("", "vendor-line-4-6"))
    assert "http-only-3-1" not in [model.model_id for model in models.models]


def test_the_saved_model_survives_the_union_even_when_it_is_unusable(tmp_path, monkeypatch):
    """The half of the #4027 tick property that lives HERE (lead asked to pin it).

    The dropdown ticks the saved default from the SAVED POLICY, not from the offer
    list, so the union cannot untick it -- that half is pinned in #4027 by
    test_saved_unavailable_choice_remains_visible_but_not_applicable, against the
    page's own renderMenu. What this PR could break is the other half: the union
    quietly dropping the saved id from the list. It must not, whatever the catalog
    knows.
    """
    catalog = LearnedModelCatalog(tmp_path)
    # The catalog knows a newer sibling AND an unrelated newer line.
    catalog.record(source_kind="subscription", model_id="vendor-line-4-7", now=_at(0))
    catalog.record(source_kind="subscription", model_id="vendor-other-9-9", now=_at(1))
    # The universe's saved choice is the OLDER sibling.
    models = _native_models(tmp_path, monkeypatch, ("", "vendor-line-4-6"))
    ids = [model.model_id for model in models.models]
    assert "vendor-line-4-6" in ids, (
        "the saved model must still be in the list for the dropdown to tick it")
    # Its position is the owner-declared block, ahead of anything contributed, so
    # the current choice is not buried under learned candidates.
    assert ids.index("vendor-line-4-6") < ids.index("vendor-line-4-7")
    bases = {model.model_id: model.availability_basis for model in models.models}
    assert bases["vendor-line-4-6"] == "owner_declared"
    assert bases["vendor-other-9-9"] == "platform_verified_elsewhere"


def test_the_table_is_classified_for_both_user_deletion_paths(tmp_path):
    """A new table the reset gate has never heard of BLOCKS a scoped reset.

    The table is created lazily, on the first thing learned, so no existing test
    would have met it and the gate would have fired in production instead. Both
    sweeps classify it as preserved, for the same reason: it is shared between
    users by design and holds nothing of any one of them, so one subject's reset or
    deletion must not remove a row every other user of that source kind relies on.
    """
    from tinyassets.account_deletion import PRESERVED_TABLES
    from tinyassets.scoped_reset import MAIN_DB_TABLE_CLASSIFICATIONS

    assert MAIN_DB_TABLE_CLASSIFICATIONS.get("learned_models") == "preserve"
    assert "learned_models" in PRESERVED_TABLES

    # And it really does lack every column either sweep would scope on, which is
    # WHY preserving it is correct rather than merely convenient.
    LearnedModelCatalog(tmp_path).record(
        source_kind="subscription", model_id="vendor-line-4-7", now=_at(0))
    with sqlite3.connect(db_path(tmp_path)) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(learned_models)")}
    assert not columns & {"owner_user_id", "universe_id", "actor_id", "principal_id"}

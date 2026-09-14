"""Canonical database preference persistence: isolation, CAS and legacy absence."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest

from tinyassets.account_deletion import deletion_plan
from tinyassets.providers.model_policy import ModelRef
from tinyassets.providers.model_preferences import MAX_GENERATION, ModelPreferences
from tinyassets.storage.model_preferences import (
    ModelPreferenceStore,
    PreferenceConflict,
    PreferenceStoreUnavailable,
)
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore

AUTO = ModelPreferences("automatic", None, ())
PIN = ModelPreferences("explicit", ModelRef("owned:future", "arbitrary/new-model"), ())


def test_absence_is_legacy_and_get_does_not_create_policy(tmp_path):
    store = ModelPreferenceStore(tmp_path)
    snapshot = store.get("owner", "universe")
    assert snapshot.document() == {"generation": 0, "policy": None, "updated_at": None}
    with SQLiteProviderWorkAuthorityStore(tmp_path).connection() as conn:
        assert conn.execute("SELECT count(*) FROM universe_model_preferences").fetchone()[0] == 0
        assert conn.execute("SELECT count(*) FROM provider_work_bindings").fetchone()[0] == 0


def test_save_order_reset_to_auto_and_reload_never_reset_generation(tmp_path):
    store = ModelPreferenceStore(tmp_path)
    ordered = ModelPreferences(
        "explicit",
        PIN.saved_default,
        (
            ModelRef("local:host", ""),
            ModelRef("owned:future", "another-model"),
        ),
    )
    first = store.save("owner", "universe", expected_generation=0, policy=ordered)
    assert first.generation == 1 and first.policy == ordered and first.updated_at.endswith("Z")
    assert ModelPreferenceStore(tmp_path).get("owner", "universe") == first
    second = store.save("owner", "universe", expected_generation=1, policy=AUTO)
    assert second.generation == 2 and second.policy == AUTO
    with pytest.raises(PreferenceConflict) as error:
        store.save("owner", "universe", expected_generation=0, policy=PIN)
    assert error.value.current == second
    assert store.get("owner", "universe") == second


def test_owner_and_universe_are_both_in_key(tmp_path):
    store = ModelPreferenceStore(tmp_path)
    first = store.save("owner-a", "u-a", expected_generation=0, policy=PIN)
    second = store.save("owner-b", "u-a", expected_generation=0, policy=AUTO)
    third = store.save("owner-a", "u-b", expected_generation=0, policy=AUTO)
    assert store.get("owner-a", "u-a") == first
    assert store.get("owner-b", "u-a") == second
    assert store.get("owner-a", "u-b") == third
    assert store.get("owner-b", "u-b").policy is None


@pytest.mark.parametrize("initial", [False, True])
def test_two_writers_one_wins_same_generation(tmp_path, initial):
    store = ModelPreferenceStore(tmp_path)
    store.get("o", "u")  # initialize shared database before the race
    generation = 0
    if initial:
        generation = store.save("o", "u", expected_generation=0, policy=AUTO).generation
    barrier = Barrier(2)

    def write(prefs):
        barrier.wait(timeout=10)
        try:
            return "saved", ModelPreferenceStore(tmp_path).save(
                "o",
                "u",
                expected_generation=generation,
                policy=prefs,
            )
        except PreferenceConflict as exc:
            return "conflict", exc.current

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(write, [PIN, AUTO]))
    assert sorted(result[0] for result in results) == ["conflict", "saved"]
    assert results[0][1] == results[1][1] == store.get("o", "u")
    assert results[0][1].generation == generation + 1


@pytest.mark.parametrize("raw", ["{}", '{"version":2}', '{"version":1,"version":1}', "null"])
def test_corrupt_row_cannot_be_read_as_absent_or_overwritten(tmp_path, raw):
    store = ModelPreferenceStore(tmp_path)
    store.save("owner", "universe", expected_generation=0, policy=PIN)
    with SQLiteProviderWorkAuthorityStore(tmp_path).connection() as conn:
        conn.execute("UPDATE universe_model_preferences SET policy_json = ?", (raw,))
    with pytest.raises(PreferenceStoreUnavailable):
        store.get("owner", "universe")
    with pytest.raises(PreferenceStoreUnavailable):
        store.save("owner", "universe", expected_generation=1, policy=AUTO)
    with SQLiteProviderWorkAuthorityStore(tmp_path).connection() as conn:
        row = conn.execute(
            "SELECT generation, policy_json FROM universe_model_preferences"
        ).fetchone()
        assert tuple(row) == (1, raw)


def test_generation_exhaustion_is_held_not_wraparound(tmp_path):
    store = ModelPreferenceStore(tmp_path)
    store.save("o", "u", expected_generation=0, policy=PIN)
    with SQLiteProviderWorkAuthorityStore(tmp_path).connection() as conn:
        conn.execute("UPDATE universe_model_preferences SET generation = ?", (MAX_GENERATION,))
    with pytest.raises(PreferenceStoreUnavailable):
        store.save("o", "u", expected_generation=MAX_GENERATION, policy=AUTO)
    assert store.get("o", "u").generation == MAX_GENERATION


def test_preferences_participate_in_existing_account_deletion_sweep(tmp_path):
    store = ModelPreferenceStore(tmp_path)
    store.save("owner-a", "u-a", expected_generation=0, policy=PIN)
    other = store.save("owner-b", "u-b", expected_generation=0, policy=AUTO)
    with SQLiteProviderWorkAuthorityStore(tmp_path).connection() as conn:
        plan = deletion_plan(conn, principal="owner-a", home="u-a")
        assert plan["universe_model_preferences"] == [
            ("universe_id", "universe"), ("owner_user_id", "principal"),
        ]
        conn.execute("DELETE FROM universe_model_preferences WHERE universe_id = ?", ("u-a",))
    assert store.get("owner-a", "u-a").policy is None
    assert store.get("owner-b", "u-b") == other


def test_invalid_generation_or_scope_never_writes(tmp_path):
    store = ModelPreferenceStore(tmp_path)
    for owner, universe, generation in [("", "u", 0), ("o", "", 0), ("o", "u", True)]:
        with pytest.raises(ValueError):
            store.save(owner, universe, expected_generation=generation, policy=PIN)
    assert store.get("o", "u").policy is None

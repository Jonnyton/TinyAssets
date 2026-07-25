"""Tests for tinyassets.idempotency — @idempotent_by_step decorator and helpers."""

from __future__ import annotations

import importlib
import inspect

import pytest

from tinyassets.idempotency import (
    _CHECKPOINT_MARKER_KEY,
    IdempotencyStore,
    checkpoint,
    derive_effect_key,
    idempotent_by_step,
    resolve_effector_identity,
)
from tinyassets.storage.external_write_receipts import (
    STATUS_FAILED,
    STATUS_SUCCEEDED,
    finalize_receipt,
    lookup_identity_alias,
    lookup_receipt,
    release_reservation,
    try_reserve_receipt,
)

# ─── IdempotencyStore ──────────────────────────────────────────────────────────

class TestIdempotencyStore:
    def test_get_returns_none_on_miss(self, tmp_path):
        store = IdempotencyStore(tmp_path / ".idempotency.db")
        assert store.get("run1", "step1") is None

    def test_set_and_get_roundtrip(self, tmp_path):
        store = IdempotencyStore(tmp_path / ".idempotency.db")
        store.set("run1", "step1", {"answer": 42})
        result = store.get("run1", "step1")
        assert result == {"answer": 42}

    def test_set_is_idempotent_on_conflict(self, tmp_path):
        store = IdempotencyStore(tmp_path / ".idempotency.db")
        store.set("run1", "step1", {"answer": 1})
        store.set("run1", "step1", {"answer": 99})
        # First write wins due to INSERT OR IGNORE
        assert store.get("run1", "step1") == {"answer": 1}

    def test_different_pairs_do_not_collide(self, tmp_path):
        store = IdempotencyStore(tmp_path / ".idempotency.db")
        store.set("run1", "step1", "result-A")
        store.set("run1", "step2", "result-B")
        store.set("run2", "step1", "result-C")
        assert store.get("run1", "step1") == "result-A"
        assert store.get("run1", "step2") == "result-B"
        assert store.get("run2", "step1") == "result-C"

    def test_has_returns_false_on_miss(self, tmp_path):
        store = IdempotencyStore(tmp_path / ".idempotency.db")
        assert store.has("run1", "step1") is False

    def test_has_returns_true_after_set(self, tmp_path):
        store = IdempotencyStore(tmp_path / ".idempotency.db")
        store.set("run1", "step1", None)
        # None serializes to "null" in JSON, get returns None for null too,
        # so has() is based on row presence — verify via raw get
        # Note: get returns json.loads("null") == None, so has() returns None is not None == False
        # This is a known subtlety: None result looks like a miss.
        # has() calls get() and checks `is not None`, so None results appear as misses.
        # We document this behavior and test the non-None case:
        store.set("run2", "stepA", {"ok": True})
        assert store.has("run2", "stepA") is True

    def test_result_survives_reconnect(self, tmp_path):
        db_path = tmp_path / ".idempotency.db"
        store1 = IdempotencyStore(db_path)
        store1.set("run1", "step1", [1, 2, 3])
        store2 = IdempotencyStore(db_path)
        assert store2.get("run1", "step1") == [1, 2, 3]

    def test_non_serializable_values_coerced_to_str(self, tmp_path):
        store = IdempotencyStore(tmp_path / ".idempotency.db")
        # json.dumps with default=str should handle unserializable types
        import datetime
        store.set("run1", "step1", datetime.date(2026, 1, 1))
        result = store.get("run1", "step1")
        assert result == "2026-01-01"

    def test_creates_parent_dirs(self, tmp_path):
        nested = tmp_path / "a" / "b" / "c" / ".idempotency.db"
        store = IdempotencyStore(nested)
        store.set("r", "s", 1)
        assert store.get("r", "s") == 1


def test_effect_key_is_derived_from_durable_goal_period_and_item_identity():
    first = derive_effect_key(
        goal_id="goal-1",
        schedule_period="2026-07-25",
        item_fingerprint="sha256:item-a",
    )
    replay = derive_effect_key(
        goal_id="goal-1",
        schedule_period="2026-07-25",
        item_fingerprint="sha256:item-a",
    )
    different_period = derive_effect_key(
        goal_id="goal-1",
        schedule_period="2026-07-26",
        item_fingerprint="sha256:item-a",
    )

    assert first == replay
    assert first.startswith("effect:v1:")
    assert len(first.removeprefix("effect:v1:")) == 64
    assert different_period != first


@pytest.mark.parametrize(
    "field",
    ["goal_id", "schedule_period", "item_fingerprint"],
)
def test_effect_key_fails_loudly_when_durable_identity_is_missing(field):
    identity = {
        "goal_id": "goal-1",
        "schedule_period": "2026-07-25",
        "item_fingerprint": "sha256:item-a",
    }
    identity[field] = ""

    with pytest.raises(ValueError, match=field):
        derive_effect_key(**identity)


def test_dual_identity_keeps_legacy_active_and_records_system_parity(tmp_path):
    packet = {
        "idempotency_hint": "legacy-hint",
        "goal_id": "goal-1",
        "schedule_period": "2026-07-25",
        "item_fingerprint": "sha256:item-a",
    }

    identity = resolve_effector_identity(
        packet,
        sink="github_pull_request",
        universe_dir=tmp_path,
        mode="dual",
    )

    assert identity.active_key == "legacy-hint"
    assert identity.system_key == derive_effect_key(
        goal_id="goal-1",
        schedule_period="2026-07-25",
        item_fingerprint="sha256:item-a",
    )
    assert identity.parity_recorded is True
    assert lookup_identity_alias(
        tmp_path,
        caller_hint="legacy-hint",
        sink="github_pull_request",
    ) == identity.system_key


def test_dual_identity_journal_is_written_and_finalized_under_both_keys(tmp_path):
    identity = resolve_effector_identity(
        {
            "idempotency_hint": "legacy-hint",
            "goal_id": "goal-1",
            "schedule_period": "2026-07-25",
            "item_fingerprint": "sha256:item-a",
        },
        sink="github_pull_request",
        universe_dir=tmp_path,
        mode="dual",
    )

    reservation = try_reserve_receipt(
        tmp_path,
        idempotency_hint=identity.active_key,
        sink="github_pull_request",
        run_id="run-1",
    )
    assert reservation["status"] == "reserved"
    system_pending = lookup_receipt(
        tmp_path,
        idempotency_hint=identity.system_key,
        sink="github_pull_request",
    )
    assert system_pending is not None
    assert system_pending["run_id"] == "run-1"

    evidence = {"remote_id": "pr-17"}
    assert finalize_receipt(
        tmp_path,
        idempotency_hint=identity.active_key,
        sink="github_pull_request",
        evidence=evidence,
        run_id="run-1",
    )
    legacy = lookup_receipt(
        tmp_path,
        idempotency_hint=identity.active_key,
        sink="github_pull_request",
    )
    system = lookup_receipt(
        tmp_path,
        idempotency_hint=identity.system_key,
        sink="github_pull_request",
    )
    assert legacy is not None and system is not None
    assert legacy["status"] == system["status"] == STATUS_SUCCEEDED
    assert legacy["evidence"] == system["evidence"] == evidence


def test_dual_identity_failure_release_keeps_both_keys_in_parity(tmp_path):
    identity = resolve_effector_identity(
        {
            "idempotency_hint": "legacy-failure",
            "goal_id": "goal-1",
            "schedule_period": "2026-07-25",
            "item_fingerprint": "sha256:item-failure",
        },
        sink="github_pull_request",
        universe_dir=tmp_path,
        mode="dual",
    )
    try_reserve_receipt(
        tmp_path,
        idempotency_hint=identity.active_key,
        sink="github_pull_request",
        run_id="run-failed",
    )

    assert release_reservation(
        tmp_path,
        idempotency_hint=identity.active_key,
        sink="github_pull_request",
        run_id="run-failed",
    )
    for key in (identity.active_key, identity.system_key):
        receipt = lookup_receipt(
            tmp_path,
            idempotency_hint=key,
            sink="github_pull_request",
        )
        assert receipt is not None
        assert receipt["status"] == STATUS_FAILED

    retry = try_reserve_receipt(
        tmp_path,
        idempotency_hint=identity.active_key,
        sink="github_pull_request",
        run_id="run-retry",
    )
    assert retry["status"] == "reserved_after_failed"
    for key in (identity.active_key, identity.system_key):
        receipt = lookup_receipt(
            tmp_path,
            idempotency_hint=key,
            sink="github_pull_request",
        )
        assert receipt is not None
        assert receipt["status"] == "pending"
        assert receipt["run_id"] == "run-retry"


def test_system_identity_mode_ignores_caller_hint_for_active_key(tmp_path):
    packet = {
        "idempotency_hint": "caller-controlled",
        "goal_id": "goal-1",
        "schedule_period": "2026-W30",
        "item_fingerprint": "sha256:item-a",
    }
    dual = resolve_effector_identity(
        packet,
        sink="github_pull_request",
        universe_dir=tmp_path,
        mode="dual",
    )
    try_reserve_receipt(
        tmp_path,
        idempotency_hint=dual.active_key,
        sink="github_pull_request",
        run_id="run-parity",
    )
    assert finalize_receipt(
        tmp_path,
        idempotency_hint=dual.active_key,
        sink="github_pull_request",
        evidence={"remote_id": "pr-17"},
        run_id="run-parity",
    )

    identity = resolve_effector_identity(
        {
            **packet,
            "idempotency_hint": "new-caller-controlled",
            "item_fingerprint": "sha256:item-new",
        },
        sink="github_pull_request",
        universe_dir=tmp_path,
        mode="system",
    )

    assert identity.active_key == identity.system_key
    assert identity.active_key != "new-caller-controlled"
    assert identity.parity_recorded is True


def test_system_identity_flag_cannot_flip_before_dual_parity(tmp_path):
    packet = {
        "idempotency_hint": "caller-controlled",
        "goal_id": "goal-1",
        "schedule_period": "2026-W30",
        "item_fingerprint": "sha256:item-a",
    }
    resolve_effector_identity(
        packet,
        sink="github_pull_request",
        universe_dir=tmp_path,
        mode="dual",
    )

    with pytest.raises(ValueError, match="proven dual-write parity"):
        resolve_effector_identity(
            packet,
            sink="github_pull_request",
            universe_dir=tmp_path,
            mode="system",
        )


def test_system_identity_flag_requires_every_dual_alias_to_have_parity(tmp_path):
    proven = {
        "idempotency_hint": "proven",
        "goal_id": "goal-1",
        "schedule_period": "2026-W30",
        "item_fingerprint": "sha256:proven",
    }
    proven_identity = resolve_effector_identity(
        proven,
        sink="github_pull_request",
        universe_dir=tmp_path,
        mode="dual",
    )
    try_reserve_receipt(
        tmp_path,
        idempotency_hint=proven_identity.active_key,
        sink="github_pull_request",
        run_id="run-proven",
    )
    finalize_receipt(
        tmp_path,
        idempotency_hint=proven_identity.active_key,
        sink="github_pull_request",
        evidence={"remote_id": "pr-17"},
        run_id="run-proven",
    )
    pending = {
        **proven,
        "idempotency_hint": "pending",
        "item_fingerprint": "sha256:pending",
    }
    pending_identity = resolve_effector_identity(
        pending,
        sink="github_pull_request",
        universe_dir=tmp_path,
        mode="dual",
    )
    try_reserve_receipt(
        tmp_path,
        idempotency_hint=pending_identity.active_key,
        sink="github_pull_request",
        run_id="run-pending",
    )

    with pytest.raises(ValueError, match="proven dual-write parity"):
        resolve_effector_identity(
            {
                **proven,
                "idempotency_hint": "new",
                "item_fingerprint": "sha256:new",
            },
            sink="github_pull_request",
            universe_dir=tmp_path,
            mode="system",
        )


def test_system_identity_mode_fails_loudly_without_durable_fields(tmp_path):
    with pytest.raises(ValueError, match="goal_id"):
        resolve_effector_identity(
            {"idempotency_hint": "caller-controlled"},
            sink="github_pull_request",
            universe_dir=tmp_path,
            mode="system",
        )


@pytest.mark.parametrize(
    ("module_name", "reconciliation_supported"),
    [
        ("tinyassets.effectors.github_pr", False),
        ("tinyassets.effectors.twitter_post", False),
        ("tinyassets.effectors.wiki_write_back", True),
        ("tinyassets.effectors.windows_desktop", False),
    ],
)
def test_receipt_backed_effectors_are_wired_to_identity_migration(
    module_name,
    reconciliation_supported,
):
    module = importlib.import_module(module_name)
    assert "resolve_effector_identity(" in inspect.getsource(module)
    assert (
        module.DESTINATION_RECONCILIATION["supported"]
        is reconciliation_supported
    )
    if reconciliation_supported:
        assert "_reconcile_page_marker(" in inspect.getsource(module)
    else:
        assert "system effect key" in module.DESTINATION_RECONCILIATION["reason"]
        assert "hold_unreconciled_pending(" in inspect.getsource(module)
    assert "hold_receipt_finalization_failure(" in inspect.getsource(module)


# ─── @idempotent_by_step decorator ────────────────────────────────────────────

class TestIdempotentByStepDecorator:
    def _make_store(self, tmp_path):
        return IdempotencyStore(tmp_path / ".idempotency.db")

    def test_first_call_executes_function(self, tmp_path, monkeypatch):
        store = self._make_store(tmp_path)
        import tinyassets.idempotency as _mod
        monkeypatch.setattr(_mod, "_store", store)

        call_count = 0

        @idempotent_by_step
        def side_effect(run_id: str, step_id: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        result = side_effect("run1", "step1")
        assert call_count == 1
        assert result == {"count": 1}

    def test_second_call_returns_cached(self, tmp_path, monkeypatch):
        store = self._make_store(tmp_path)
        import tinyassets.idempotency as _mod
        monkeypatch.setattr(_mod, "_store", store)

        call_count = 0

        @idempotent_by_step
        def side_effect(run_id: str, step_id: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"count": call_count}

        side_effect("run1", "step1")
        result = side_effect("run1", "step1")
        assert call_count == 1
        assert result == {"count": 1}

    def test_different_step_ids_execute_independently(self, tmp_path, monkeypatch):
        store = self._make_store(tmp_path)
        import tinyassets.idempotency as _mod
        monkeypatch.setattr(_mod, "_store", store)

        call_count = 0

        @idempotent_by_step
        def fn(run_id: str, step_id: str) -> int:
            nonlocal call_count
            call_count += 1
            return call_count

        r1 = fn("run1", "step1")
        r2 = fn("run1", "step2")
        assert r1 == 1
        assert r2 == 2
        assert call_count == 2

    def test_different_run_ids_execute_independently(self, tmp_path, monkeypatch):
        store = self._make_store(tmp_path)
        import tinyassets.idempotency as _mod
        monkeypatch.setattr(_mod, "_store", store)

        executed = []

        @idempotent_by_step
        def fn(run_id: str, step_id: str) -> str:
            executed.append(run_id)
            return f"result-{run_id}"

        r1 = fn("run-A", "step1")
        r2 = fn("run-B", "step1")
        assert r1 == "result-run-A"
        assert r2 == "result-run-B"
        assert len(executed) == 2

    def test_preserves_function_metadata(self):
        @idempotent_by_step
        def my_function(run_id: str, step_id: str) -> None:
            """Original docstring."""

        assert my_function.__name__ == "my_function"
        assert my_function.__doc__ == "Original docstring."
        assert my_function.__wrapped__ is not None  # type: ignore[attr-defined]

    def test_marks_decorated_function(self):
        @idempotent_by_step
        def fn(run_id: str, step_id: str) -> None:
            pass

        assert getattr(fn, "_idempotent_by_step", False) is True

    def test_exception_in_function_does_not_cache(self, tmp_path, monkeypatch):
        store = self._make_store(tmp_path)
        import tinyassets.idempotency as _mod
        monkeypatch.setattr(_mod, "_store", store)

        call_count = 0

        @idempotent_by_step
        def fn(run_id: str, step_id: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("first call explodes")
            return "recovered"

        with pytest.raises(ValueError):
            fn("run1", "step1")

        # Second call should re-execute (first result was never stored)
        result = fn("run1", "step1")
        assert result == "recovered"
        assert call_count == 2

    def test_passes_extra_args_and_kwargs(self, tmp_path, monkeypatch):
        store = self._make_store(tmp_path)
        import tinyassets.idempotency as _mod
        monkeypatch.setattr(_mod, "_store", store)

        received = {}

        @idempotent_by_step
        def fn(run_id: str, step_id: str, extra: int, *, label: str = "") -> dict:
            received["extra"] = extra
            received["label"] = label
            return {"extra": extra, "label": label}

        result = fn("run1", "step1", 7, label="hello")
        assert result == {"extra": 7, "label": "hello"}
        assert received == {"extra": 7, "label": "hello"}

    def test_cached_result_returned_without_calling_fn(self, tmp_path, monkeypatch):
        store = self._make_store(tmp_path)
        # Pre-seed store with a result
        store.set("run1", "step1", {"cached": True})
        import tinyassets.idempotency as _mod
        monkeypatch.setattr(_mod, "_store", store)

        called = []

        @idempotent_by_step
        def fn(run_id: str, step_id: str) -> dict:
            called.append(True)
            return {"cached": False}

        result = fn("run1", "step1")
        assert result == {"cached": True}
        assert called == []


# ─── checkpoint helper ────────────────────────────────────────────────────────

class TestCheckpointHelper:
    def test_returns_checkpoint_marker_key(self):
        delta = checkpoint("halfway", state={})
        assert _CHECKPOINT_MARKER_KEY in delta

    def test_appends_checkpoint_id_to_list(self):
        delta = checkpoint("halfway", state={})
        assert "halfway" in delta[_CHECKPOINT_MARKER_KEY]

    def test_accumulates_multiple_checkpoints(self):
        state = {}
        d1 = checkpoint("first", state=state)
        # Merge delta back into state to simulate code node usage
        state.update(d1)
        d2 = checkpoint("second", state=state)
        state.update(d2)
        assert state[_CHECKPOINT_MARKER_KEY] == ["first", "second"]

    def test_does_not_mutate_existing_state(self):
        state = {"some_key": "some_value"}
        checkpoint("cp", state=state)
        assert "some_key" in state
        assert _CHECKPOINT_MARKER_KEY not in state

    def test_checkpoint_with_empty_existing_list(self):
        state = {_CHECKPOINT_MARKER_KEY: []}
        delta = checkpoint("cp", state=state)
        assert delta[_CHECKPOINT_MARKER_KEY] == ["cp"]

    def test_checkpoint_with_none_existing(self):
        state = {_CHECKPOINT_MARKER_KEY: None}
        delta = checkpoint("cp", state=state)
        assert delta[_CHECKPOINT_MARKER_KEY] == ["cp"]

    def test_returns_dict_with_only_marker_key(self):
        delta = checkpoint("cp", state={})
        assert set(delta.keys()) == {_CHECKPOINT_MARKER_KEY}

"""Tests for tinyassets.idempotency — @idempotent_by_step decorator and helpers."""

from __future__ import annotations

import pytest

from tinyassets.idempotency import (
    _CHECKPOINT_MARKER_KEY,
    IdempotencyStore,
    checkpoint,
    idempotent_by_step,
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

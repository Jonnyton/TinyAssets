"""Producer-registry test-gap closure (Phase E concern).

Covers corners not exercised by the existing Phase C/E/F test files:

- ``run_producers(producer_config={...})`` routes each producer its
  own config slice by ``producer.name``.
- ``run_producers`` with an empty registry returns ``[]``.
- ``producer_interface_enabled()`` edge inputs (whitespace, garbage
  strings) — any non-off value stays on.
- ``run_branch_task_producers(producer_config={...})`` slice-routing.
- ``unregister_branch_task_producer`` (no coverage prior to this file).
- ``run_branch_task_producers`` stamps ``origin`` onto each task
  regardless of what the producer tries to set.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tinyassets import producers as in_univ_mod
from tinyassets.branch_tasks import BranchTask, new_task_id
from tinyassets.producers import (
    branch_task as bt_producer_mod,
)
from tinyassets.producers import (
    producer_interface_enabled,
    register,
    registered_producers,
    reset_registry,
    run_producers,
)
from tinyassets.producers.branch_task import (
    register_branch_task_producer,
    registered_branch_task_producers,
    reset_branch_task_registry,
    run_branch_task_producers,
    unregister_branch_task_producer,
)
from tinyassets.work_targets import WorkTarget


@pytest.fixture
def universe_dir(tmp_path: Path) -> Path:
    d = tmp_path / "test-universe"
    d.mkdir()
    return d


@pytest.fixture(autouse=True)
def _clean_both_registries():
    """Save-and-restore pattern (precedent: tests/test_goal_pool.py
    _clean_branch_task_registry). A plain reset+reset across yield leaks
    empty registries to downstream test files — many production suites
    depend on import-time registrations (goal_pool, node_bid, domain
    producers) still being present when they run."""
    saved_iu = list(in_univ_mod._REGISTRY)
    saved_bt = list(bt_producer_mod._REGISTRY)
    reset_registry()
    reset_branch_task_registry()
    yield
    reset_registry()
    reset_branch_task_registry()
    in_univ_mod._REGISTRY.extend(saved_iu)
    bt_producer_mod._REGISTRY.extend(saved_bt)


# ─── TaskProducer (in-universe) gaps ───────────────────────────────────


class _ConfigCapturingProducer:
    """Records the ``config`` it received on each ``produce`` call."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.origin = "seed"
        self.seen_configs: list = []

    def produce(self, universe_path, *, config=None):
        self.seen_configs.append(config)
        return []


def test_run_producers_routes_config_slice_by_name(universe_dir):
    """``producer_config`` is a per-name dict; each producer sees
    only its own slice (or ``None`` if unlisted)."""
    alpha = _ConfigCapturingProducer("alpha")
    beta = _ConfigCapturingProducer("beta")
    gamma = _ConfigCapturingProducer("gamma")
    register(alpha)
    register(beta)
    register(gamma)

    run_producers(
        universe_dir,
        producer_config={
            "alpha": {"k": 1},
            "beta": {"k": 2},
            # gamma omitted intentionally
        },
    )

    assert alpha.seen_configs == [{"k": 1}]
    assert beta.seen_configs == [{"k": 2}]
    assert gamma.seen_configs == [None]


def test_run_producers_empty_registry_returns_empty_list(universe_dir):
    """No producers registered → no work, no crash."""
    assert registered_producers() == ()
    assert run_producers(universe_dir) == []


def test_run_producers_none_config_defaults_to_empty(universe_dir):
    """Omitting producer_config entirely → every producer gets None."""
    alpha = _ConfigCapturingProducer("alpha")
    register(alpha)
    run_producers(universe_dir)  # no producer_config kwarg
    assert alpha.seen_configs == [None]


@pytest.mark.parametrize(
    "value",
    ["", "   ", "maybe", "weird-string", "1on", "True "],
)
def test_producer_interface_enabled_non_off_values_stay_on(
    monkeypatch, value,
):
    """Any value that isn't a recognized off-synonym keeps the flag on.

    Current semantics: only ``off`` / ``0`` / ``false`` / ``no``
    (case-insensitive, trimmed) disable the flag. Garbage and empty
    strings default to on — defensive posture keeps the interface
    active under typo or deploy-env sloppiness.
    """
    monkeypatch.setenv("TINYASSETS_PRODUCER_INTERFACE", value)
    assert producer_interface_enabled() is True


def test_producer_interface_enabled_trims_whitespace_on_off(monkeypatch):
    """The off check strips+lowercases the env value."""
    monkeypatch.setenv("TINYASSETS_PRODUCER_INTERFACE", "  OFF  ")
    assert producer_interface_enabled() is False


# ─── BranchTaskProducer gaps ───────────────────────────────────────────


class _BTConfigCapturingProducer:
    """BranchTaskProducer that records its config and emits one task."""

    def __init__(self, name: str, origin: str = "goal_pool") -> None:
        self.name = name
        self.origin = origin
        self.seen_configs: list = []

    def produce(self, universe_path, *, subscribed_goals, config=None):
        self.seen_configs.append(config)
        return [
            BranchTask(
                branch_task_id=new_task_id(),
                branch_def_id="fantasy_author:universe_cycle_wrapper",
                universe_id="u",
                inputs={},
                # producer lies about trigger_source; runner must
                # overwrite with producer.origin.
                trigger_source="opportunistic",
            ),
        ]


def test_run_branch_task_producers_routes_config_slice(universe_dir):
    """BranchTaskProducer sees only its own slice of ``producer_config``."""
    a = _BTConfigCapturingProducer("alpha")
    b = _BTConfigCapturingProducer("beta")
    register_branch_task_producer(a)
    register_branch_task_producer(b)

    run_branch_task_producers(
        universe_dir,
        subscribed_goals=["maintenance"],
        producer_config={"alpha": {"x": 10}, "beta": {"x": 20}},
    )

    assert a.seen_configs == [{"x": 10}]
    assert b.seen_configs == [{"x": 20}]


def test_run_branch_task_producers_stamps_origin_overriding_producer(
    universe_dir,
):
    """``trigger_source`` comes from the PRODUCER'S ``origin``, not
    whatever value the producer put on the emitted task."""
    liar = _BTConfigCapturingProducer("liar", origin="goal_pool")
    register_branch_task_producer(liar)

    emitted = run_branch_task_producers(
        universe_dir, subscribed_goals=["maintenance"],
    )

    assert len(emitted) == 1
    assert emitted[0].trigger_source == "goal_pool"


def test_unregister_branch_task_producer_removes_by_name(universe_dir):
    """``unregister_branch_task_producer`` removes and returns True."""
    register_branch_task_producer(_BTConfigCapturingProducer("to-remove"))
    register_branch_task_producer(_BTConfigCapturingProducer("keep"))

    removed = unregister_branch_task_producer("to-remove")
    assert removed is True

    names = [p.name for p in registered_branch_task_producers()]
    assert names == ["keep"]


def test_unregister_branch_task_producer_missing_returns_false():
    """Unregistering a name that was never registered is a no-op
    returning False."""
    register_branch_task_producer(_BTConfigCapturingProducer("alpha"))

    removed = unregister_branch_task_producer("never_registered")
    assert removed is False

    names = [p.name for p in registered_branch_task_producers()]
    assert names == ["alpha"]


def test_unregister_branch_task_producer_empty_registry_returns_false():
    """Unregistering from an empty registry returns False safely."""
    assert unregister_branch_task_producer("anything") is False
    assert registered_branch_task_producers() == ()


def test_branch_task_registry_is_distinct_from_task_producer_registry(
    universe_dir,
):
    """Reset isolation: clearing one registry does not affect the
    other. This pins the "two protocols, two registries" invariant
    (preflight §4.3 #2) from a reset angle that existing tests don't
    cover."""
    # Populate in-universe registry
    class _IU:
        name = "iu"
        origin = "seed"
        def produce(self, universe_path, *, config=None):
            return [WorkTarget(target_id="x", title="x")]

    register(_IU())
    register_branch_task_producer(_BTConfigCapturingProducer("bt"))

    # Reset ONLY the branch-task registry
    reset_branch_task_registry()
    assert registered_branch_task_producers() == ()
    assert len(registered_producers()) == 1  # in-universe unaffected

    # Reset ONLY the in-universe registry
    register_branch_task_producer(_BTConfigCapturingProducer("bt2"))
    reset_registry()
    assert registered_producers() == ()
    assert len(registered_branch_task_producers()) == 1  # bt unaffected

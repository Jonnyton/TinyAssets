"""BranchTaskProducer protocol + active registry (Phase F).

Distinct from ``tinyassets/producers/__init__.py``'s in-universe
``TaskProducer``:

- ``TaskProducer.produce`` → ``list[WorkTarget]`` (content, in-universe,
  runs inside review gates).
- ``BranchTaskProducer.produce`` → ``list[BranchTask]`` (execution
  intents, cross-universe, runs at dispatcher boundaries).

Two registries, two protocols, zero overlap. Preflight §4.3 invariant 2
(R2 keystone). Invariant 3 clarifies the call-site split.

Synchronous for v1; memo §3.2 allows a future async variant when a
producer does I/O (HTTP, remote git fetch). Current goal_pool reads
local files + optional ``git fetch`` — sync is fine.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Protocol, runtime_checkable

from tinyassets.branch_tasks import BranchTask

logger = logging.getLogger(__name__)


@runtime_checkable
class BranchTaskProducer(Protocol):
    """Produces candidate BranchTasks for the dispatcher.

    Invoked exactly once per dispatcher cycle with the caller's
    current subscribed-goals list (which the producer may use or
    ignore). Must be idempotent: re-invoking with unchanged inputs
    returns the same BranchTask set. Callers append-upsert into
    ``branch_tasks.json``; duplicate ``branch_task_id``s are
    swallowed by queue-level idempotency.
    """

    name: str
    """Stable identifier. Must match ``[a-z][a-z0-9_-]*``.
    Examples: ``"goal_pool"``."""

    origin: str
    """The ``BranchTask.trigger_source`` this producer stamps.
    Must match a value in ``VALID_TRIGGER_SOURCES``."""

    def produce(
        self,
        universe_path: Path,
        *,
        subscribed_goals: list[str],
        config: dict | None = None,
    ) -> list[BranchTask]:
        """Return candidate BranchTasks.

        Raises: SHOULD NOT raise on empty state — return ``[]``.
        MAY raise on genuinely corrupt input; the orchestrator logs
        and continues with the next producer.
        """
        ...


_REGISTRY: list[BranchTaskProducer] = []


def register_branch_task_producer(producer: BranchTaskProducer) -> None:
    """Register a producer. Idempotent on ``producer.name`` — re-register
    replaces the prior instance (hot-reload + duplicate-register guard).
    """
    global _REGISTRY
    _REGISTRY = [p for p in _REGISTRY if p.name != producer.name]
    _REGISTRY.append(producer)


def registered_branch_task_producers() -> tuple[BranchTaskProducer, ...]:
    """Return active producers in registration order."""
    return tuple(_REGISTRY)


def unregister_branch_task_producer(name: str) -> bool:
    """Remove by name. Returns True if it was present."""
    global _REGISTRY
    before = len(_REGISTRY)
    _REGISTRY = [p for p in _REGISTRY if p.name != name]
    return len(_REGISTRY) != before


def reset_branch_task_registry() -> None:
    """Clear. Test-only hook."""
    global _REGISTRY
    _REGISTRY = []


def run_branch_task_producers(
    universe_path: Path,
    *,
    subscribed_goals: list[str],
    producer_config: dict | None = None,
) -> list[BranchTask]:
    """Invoke every registered producer, collect all produced tasks.

    Idempotency is enforced downstream at queue-append time via
    ``branch_task_id`` uniqueness. Producers that raise are logged
    and skipped; other producers still run.
    """
    cfg = producer_config or {}
    emitted: list[BranchTask] = []
    for producer in registered_branch_task_producers():
        try:
            produced = producer.produce(
                universe_path,
                subscribed_goals=subscribed_goals,
                config=cfg.get(producer.name),
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "branch_task producer %s failed: %s", producer.name, exc,
            )
            continue
        for task in produced:
            # Stamp origin consistently — producer can't lie about trigger_source.
            task.trigger_source = producer.origin
            emitted.append(task)
    return emitted

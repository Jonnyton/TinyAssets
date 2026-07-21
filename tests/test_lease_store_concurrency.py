from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from tinyassets.branch_tasks import BranchTask
from tinyassets.runtime.lease_store import AlreadyClaimedError, LeaseStore, RecordReference


def test_two_service_instances_have_exactly_one_atomic_claim_winner(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "leases.sqlite3"
    stores = (LeaseStore(db_path), LeaseStore(db_path))
    task = BranchTask(
        branch_task_id=str(uuid4()),
        branch_def_id="branch-loop",
        universe_id="universe-a",
        queued_at="2026-07-19T12:00:00Z",
    )
    stores[0].add_task(task)
    barrier = Barrier(2)

    def compete(index: int):
        barrier.wait(timeout=5)
        try:
            return stores[index].claim(
                task.branch_task_id,
                daemon_id=f"daemon-{index}",
                bind_capsule=lambda _lease: RecordReference(
                    record_id=str(uuid4()),
                    content_sha256=str(index) * 64,
                ),
            )
        except AlreadyClaimedError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(compete, range(2)))

    winners = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    losers = [outcome for outcome in outcomes if isinstance(outcome, AlreadyClaimedError)]
    persisted = stores[0].read_task(task.branch_task_id)

    assert len(winners) == 1
    assert len(losers) == 1
    assert losers[0].code == "already_claimed"
    assert winners[0].fence == 1
    assert persisted.lease_id == winners[0].lease_id
    assert persisted.lease_fence == 1
    claim_events = [
        event
        for event in stores[0].events(task.branch_task_id)
        if event.kind == "claimed"
    ]
    assert len(claim_events) == 1


def test_only_atomic_claim_winner_persists_a_capsule(tmp_path: Path) -> None:
    contender_count = 8
    db_path = tmp_path / "leases.sqlite3"
    stores = tuple(LeaseStore(db_path) for _ in range(contender_count))
    task = BranchTask(
        branch_task_id=str(uuid4()),
        branch_def_id="branch-loop",
        universe_id="universe-a",
        queued_at="2026-07-19T12:00:00Z",
    )
    stores[0].add_task(task)
    barrier = Barrier(contender_count)
    persisted_capsules: list[tuple[object, RecordReference]] = []

    def compete(index: int):
        def persist_capsule(identity):
            capsule = RecordReference(
                record_id=str(uuid4()),
                content_sha256=f"{index:x}" * 64,
            )
            persisted_capsules.append((identity, capsule))
            return capsule

        barrier.wait(timeout=5)
        try:
            return stores[index].claim(
                task.branch_task_id,
                daemon_id=f"daemon-{index}",
                bind_capsule=persist_capsule,
            )
        except AlreadyClaimedError as exc:
            return exc

    with ThreadPoolExecutor(max_workers=contender_count) as pool:
        outcomes = list(pool.map(compete, range(contender_count)))

    winners = [outcome for outcome in outcomes if not isinstance(outcome, Exception)]
    losers = [outcome for outcome in outcomes if isinstance(outcome, AlreadyClaimedError)]
    persisted = stores[0].read_task(task.branch_task_id)

    assert len(winners) == 1
    assert len(losers) == contender_count - 1
    assert len(persisted_capsules) == 1
    capsule_identity, capsule = persisted_capsules[0]
    assert capsule_identity.lease_id == winners[0].lease_id
    assert capsule_identity.fence == winners[0].fence == persisted.lease_fence == 1
    assert capsule.record_id == winners[0].capsule.record_id == persisted.capsule_id
    assert capsule.content_sha256 == persisted.capsule_sha256


def test_lease_store_claim_has_no_production_dispatch_caller() -> None:
    """Dormant-authority guard (S2 fix-2).

    ``LeaseStore`` is the DESIGNATED sole claim authority, but it is DORMANT
    in production: the daemon's live execution route is the legacy JSON
    ``claim_task`` until S4/S10 supplies the signed capsule/Order binder and
    migrates the daemon to ``LeaseStore.claim`` (exec plan §17 [S10]). Both
    stores can technically grant ownership of the same task today, so
    production safety against dual-claim rests on exactly one invariant: NO
    production dispatch module wires ``LeaseStore`` into the daemon execution
    path. This static guard fails the moment anyone does — and inverts at
    S4/S10, when the JSON route must be gone instead.
    """
    repo = Path(__file__).resolve().parent.parent
    dispatch_sources = [
        repo / "fantasy_daemon" / "__main__.py",
        repo / "tinyassets" / "dispatcher.py",
        repo / "tinyassets" / "idle_cycle.py",
        repo / "tinyassets" / "producers" / "goal_pool.py",
        repo / "tinyassets" / "bug_investigation.py",
        repo / "tinyassets" / "branch_tasks.py",
    ]
    # Fail closed: a renamed/moved listed module must FAIL the guard, never
    # silently hollow it (mutation-test-fail-closed-default).
    missing = [path.name for path in dispatch_sources if not path.exists()]
    assert not missing, f"guard source(s) missing — update the list: {missing}"
    wiring_patterns = (
        re.compile(r"^\s*(from|import)\s+\S*lease_store", re.MULTILINE),
        re.compile(r"\bLeaseStore\s*\("),
    )
    offenders = []
    for source_path in dispatch_sources:
        text = source_path.read_text(encoding="utf-8")
        if any(pattern.search(text) for pattern in wiring_patterns):
            offenders.append(source_path.name)
    assert not offenders, (
        "LeaseStore wired into a production dispatch module before S4/S10 "
        "retires the JSON claim route: " + ", ".join(offenders)
    )

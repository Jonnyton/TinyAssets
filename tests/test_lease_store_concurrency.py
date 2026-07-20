from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

from tinyassets.branch_tasks import BranchTask, append_task, claim_task, read_queue
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


def test_json_and_sqlite_claim_paths_cannot_both_grant_ownership(
    tmp_path: Path,
) -> None:
    universe_dir = tmp_path / "universe"
    task = BranchTask(
        branch_task_id=str(uuid4()),
        branch_def_id="branch-loop",
        universe_id="universe-a",
        queued_at="2026-07-19T12:00:00Z",
    )
    append_task(universe_dir, task)
    store = LeaseStore(tmp_path / "leases.sqlite3")
    store.add_task(task)
    barrier = Barrier(2)

    def json_claim():
        barrier.wait(timeout=5)
        try:
            return claim_task(universe_dir, task.branch_task_id, "json-daemon")
        except RuntimeError as exc:
            return exc

    def sqlite_claim():
        barrier.wait(timeout=5)
        return store.claim(
            task.branch_task_id,
            daemon_id="sqlite-daemon",
            bind_capsule=lambda _identity: RecordReference(str(uuid4()), "f" * 64),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        json_future = pool.submit(json_claim)
        sqlite_future = pool.submit(sqlite_claim)
        json_outcome = json_future.result()
        sqlite_lease = sqlite_future.result()

    assert isinstance(json_outcome, RuntimeError)
    assert "SQLite lease store" in str(json_outcome)
    assert sqlite_lease.task_id == task.branch_task_id
    assert store.read_task(task.branch_task_id).status == "leased"
    json_projection = read_queue(universe_dir)[0]
    assert json_projection.status == "pending"
    assert not json_projection.claimed_by

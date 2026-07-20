from __future__ import annotations

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

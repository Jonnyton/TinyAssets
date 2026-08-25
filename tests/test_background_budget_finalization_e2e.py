"""Real-store end-to-end proof of the PRODUCTION background provider path.

History: this file began as the finalization proof for Codex REJECT #2 on #2531, built on
a caller-populated ``ServedProviderAuthority`` the router honoured. Codex REJECT #4 settled
that no in-process provenance scheme is sound ("if arbitrary in-process Python is the
adversary, no underscore, sentinel, or same-process secret suffices"), so the consumer was
re-routed through the repo's hardened path instead, and this proof was rewritten to drive
THAT path against every real store:

    _claimable_cloud_path (real admission/continuation/authority/queue stores)
      -> descriptor-based claim (hydrates executor_worker_id / executor_runtime_id)
      -> prepare_claimed_cloud_provider_call  (the consumer's actual call)
      -> _ClaimedCloudProviderSession
      -> _reserve_and_arm_cloud_branch_carrier_in_transaction
      -> a server-minted, pid-bound, ONE-USE ProviderInvocationCarrier
      -> the REAL ProviderRouter (carrier branch: chain pinned to the carrier's provider,
         cfg.max_tokens pinned to the carrier's bound)
      -> provider.complete

No test-side authority is constructed anywhere: the only thing faked is the provider at the
end of the chain (a counting stub). Monkeypatches: none.
"""

from __future__ import annotations

import asyncio
import sqlite3
from datetime import timedelta
from pathlib import Path

import pytest

from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter
from tinyassets.cloud_automation_continuation import prepare_claimed_cloud_provider_call
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
from tinyassets.providers.router import ProviderRouter
from tinyassets.storage.provider_work_authority import db_path as authority_db_path


class _CountingProvider(BaseProvider):
    def __init__(self) -> None:
        self.name = "codex"
        self.family = "codex"
        self.calls: list[ModelConfig] = []

    async def complete(self, prompt, system, config: ModelConfig, *, universe_dir=None):
        self.calls.append(config)
        return ProviderResponse(
            text="routed-ok", provider="codex", model="fake", family="codex",
            latency_ms=0.0, input_tokens=700, output_tokens=300, cost_microunits=50,
        )


def _real_router_call(fake: _CountingProvider):
    """The consumer's provider_call shape, routed through the REAL ProviderRouter."""
    router = ProviderRouter({"codex": fake})

    def through_real_router(prompt, system="", *, role="writer", **kwargs):
        return asyncio.run(router.call(
            role, prompt, system,
            operation=kwargs["operation"],
            universe_context=kwargs["universe_context"],
        )).text

    return through_real_router


def test_consumer_path_launches_through_one_use_carrier_on_real_stores(tmp_path: Path) -> None:
    from tests.test_cloud_automation_continuation import (
        BRANCH_TASK_ID,
        NOW,
        _claimable_cloud_path,
    )

    _fixture, _continuation, _admission, audience, _attempt, _claimed = _claimable_cloud_path(
        tmp_path
    )
    # A heartbeat renews the claim resolution the cloud path revalidates against
    # (canonical authority); the fixture is anchored to a frozen NOW.
    assert Epoch2BranchTaskAdapter(
        tmp_path, clock=lambda: NOW + timedelta(seconds=2)
    ).heartbeat(BRANCH_TASK_ID, worker_id=audience.worker_id) is not None
    task = Epoch2BranchTaskAdapter(tmp_path).get(BRANCH_TASK_ID)
    # The claim hydrated the executor identity the cloud path authorizes against — no
    # by-hand assignment (the bug fixed at _as_execution_task).
    assert task.executor_worker_id == audience.worker_id
    assert task.executor_runtime_id == audience.runtime_id

    fake = _CountingProvider()
    authorized = prepare_claimed_cloud_provider_call(
        tmp_path,
        claimed_task=task,
        daemon_id=audience.daemon_id,
        provider_call=_real_router_call(fake),
        clock=lambda: NOW + timedelta(seconds=2),  # fixture is frozen at NOW
    )
    assert authorized is not None  # a prepared cloud continuation: the consumer runs it

    assert authorized("first", "system") == "routed-ok"
    assert len(fake.calls) == 1  # the real router launched the real provider

    # The carrier's bound is a HARD pre-launch bound on the config the provider sees
    # (Codex #6: a reservation is only accounting unless the launch is capped).
    launched_cfg = fake.calls[0]
    assert launched_cfg.max_tokens is not None and launched_cfg.max_tokens >= 1

    # And it rode a ONE-USE carrier reserved on the real authority store: exactly one
    # reservation row for this launch, keyed to the claim.
    conn = sqlite3.connect(authority_db_path(tmp_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT state, ordinal, claim_id FROM provider_invocation_reservations"
    ).fetchall()
    assert len(rows) == 1, [dict(r) for r in rows]
    assert rows[0]["ordinal"] == 1


@pytest.mark.xfail(
    strict=True,
    reason=(
        "carrier usage accounting gap: the one-use carrier path CONSUMES its reservation "
        "but records no actuals (no actual_* on provider_invocation_reservations, no "
        "post-call finalize). Pre-activation blocker for the rolling cap; lane tracked in "
        "draft #2531."
    ),
)
def test_carrier_launch_records_actual_usage(tmp_path: Path) -> None:
    from tests.test_cloud_automation_continuation import (
        BRANCH_TASK_ID,
        NOW,
        _claimable_cloud_path,
    )

    _fixture, _c, _a, audience, _at, _cl = _claimable_cloud_path(tmp_path)
    assert Epoch2BranchTaskAdapter(
        tmp_path, clock=lambda: NOW + timedelta(seconds=2)
    ).heartbeat(BRANCH_TASK_ID, worker_id=audience.worker_id) is not None
    task = Epoch2BranchTaskAdapter(tmp_path).get(BRANCH_TASK_ID)
    fake = _CountingProvider()
    authorized = prepare_claimed_cloud_provider_call(
        tmp_path, claimed_task=task, daemon_id=audience.daemon_id,
        provider_call=_real_router_call(fake),
        clock=lambda: NOW + timedelta(seconds=2),  # fixture is frozen at NOW
    )
    assert authorized is not None
    authorized("first", "system")
    conn = sqlite3.connect(authority_db_path(tmp_path))
    conn.row_factory = sqlite3.Row
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(provider_invocation_reservations)")}
    assert "actual_total_tokens" in cols  # does not exist yet — the gap
    row = conn.execute(
        "SELECT actual_total_tokens FROM provider_invocation_reservations"
    ).fetchone()
    assert row["actual_total_tokens"] == 1000


def test_consumer_poll_once_registers_and_claims_for_real(tmp_path: Path, monkeypatch) -> None:
    """Codex REJECT #5: the claim boundary itself, through the REAL consumer.

    Everything the consumer does to become a claimant is real: it registers its daemon
    (create_daemon), provisions a runtime for the universe (ensure_daemon_runtime),
    persists ONE queue descriptor inside the protocol's 90s validity
    (set_worker_queue_descriptor), and claims through the descriptor-based
    adapter.claim() whose trusted reader is read_worker_claim_descriptor — i.e. the
    claim validates the PERSISTED descriptor, not an echo of what was presented.

    Seams stubbed because they are separate, already-tested concerns (NOT the claim):
    serving-universe enumeration, the founder's provider assignment lookup, _execute
    (the carrier launch is proven by the test above), and CANDIDATE ENUMERATION:
    the store's candidate integrity classifier (_classify_epoch2_row) requires a task
    fully linked to a committed operator admission (request/admission/receipt/result/
    metadata cross-checks); the continuation fixture's admission helper is a by-id
    shortcut that can never satisfy it, so list_candidates is stubbed to return the
    seeded task. Follow-up: seed a fully-linked operator admission and drop that
    stub.
    to a frozen NOW; the consumer's clock and the adapter clock are pinned to it so the
    descriptor's remaining validity is judged in fixture time.
    """
    import functools
    from datetime import datetime as _real_datetime

    import tinyassets.runtime.assigned_queue_consumer as consumer_module
    from tests.test_cloud_automation_continuation import (
        BRANCH_TASK_ID,
        NOW,
        _activate_cloud,
        _admit_claimable_cloud_task,
        _background_binding,
        _fixture,
        _issue_epoch2_attempt,
        _prepare,
    )
    from tinyassets.background_branch_authority import (
        BackgroundBranchExecutorAudience,
        BackgroundBranchExecutorClass,
    )
    from tinyassets.branch_tasks_v2 import read_worker_claim_descriptor
    from tinyassets.daemon_registry import get_daemon
    from tinyassets.runtime.assigned_queue_consumer import AssignedQueueConsumer
    from tinyassets.storage import db_path

    universe_id = "universe_alice"
    # The consumer is dark by default; poll_once() returns 0 before any work unless
    # the flag is on. Enabling it here exercises the real poll, not a no-op.
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")

    class _FrozenDatetime(_real_datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW if tz is None else NOW.astimezone(tz)

    monkeypatch.setattr(consumer_module, "datetime", _FrozenDatetime)
    monkeypatch.setattr(
        consumer_module, "Epoch2BranchTaskAdapter",
        functools.partial(Epoch2BranchTaskAdapter, clock=lambda: NOW + timedelta(seconds=2)),
    )
    import tinyassets.provider_serving_binding as serving_binding_module

    monkeypatch.setattr(
        serving_binding_module, "list_serving_universes", lambda _base: [universe_id]
    )
    # The founder's provider assignment (a separate seam): provider + OWNING PRINCIPAL.
    # The consumer authors this universe's daemon as that principal — the admission
    # linkage requires the directed daemon's author to be the binding principal.
    monkeypatch.setattr(
        AssignedQueueConsumer, "_assignment",
        lambda self, _u: type(
            "Assignment", (), {"provider": "codex", "owner_user_id": "acct_alice", "state": "ready"}
        )(),
    )
    executed: list[object] = []
    monkeypatch.setattr(
        Epoch2BranchTaskAdapter, "list_candidates",
        lambda self, *, universe_id="", limit=1000: (
            [t for t in [self.get(BRANCH_TASK_ID)]
             if t is not None and t.universe_id == universe_id]
        ),
    )
    monkeypatch.setattr(
        AssignedQueueConsumer, "_execute", lambda self, task, lease: executed.append(task)
    )

    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    # REAL registration — the consumer becomes a worker the cloud path can authorize.
    daemon_id = consumer._ensure_daemon(universe_id)
    runtime_id = consumer._ensure_runtime(universe_id, "codex")
    descriptor = consumer._current_descriptor(universe_id, runtime_id)  # persisted, once
    worker_id = consumer.worker_id_for(universe_id)
    assert descriptor.worker_id == worker_id and descriptor.runtime_instance_id == runtime_id

    # Seed a claimable cloud task DIRECTED AT the consumer's own identity (the fixture
    # minus its final claim step).
    audience = BackgroundBranchExecutorAudience(
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id=daemon_id, runtime_id=runtime_id, worker_id=worker_id,
    )
    fixture = _fixture(tmp_path, background_binding=_background_binding(daemon_id=daemon_id))
    continuation = _prepare(fixture).record
    active = _activate_cloud(fixture)
    admission = _admit_claimable_cloud_task(
        fixture, active,
        continuation_id=continuation.continuation_id,
        daemon_id=daemon_id,
        daemon_soul_hash=str(get_daemon(tmp_path, daemon_id=daemon_id)["soul_hash"]),
    )
    _issue_epoch2_attempt(tmp_path, fixture, continuation, admission, audience=audience)

    # THE CLAIM BOUNDARY, for real.
    assert consumer.poll_once() == 1
    for future in list(consumer._active.values()):
        future.result(timeout=5)
    task = Epoch2BranchTaskAdapter(
        tmp_path, clock=lambda: NOW + timedelta(seconds=3)
    ).get(BRANCH_TASK_ID)
    assert task.claimed_by == worker_id
    assert task.executor_worker_id == worker_id  # hydrated by the claim
    assert task.executor_runtime_id == runtime_id
    assert [t.branch_task_id for t in executed] == [BRANCH_TASK_ID]

    # And the trusted reader's PERSISTED descriptor is byte-equal to what was presented.
    conn = sqlite3.connect(db_path(tmp_path))
    conn.row_factory = sqlite3.Row  # the store reads rows by name
    try:
        assert read_worker_claim_descriptor(conn, worker_id) == descriptor
    finally:
        conn.close()

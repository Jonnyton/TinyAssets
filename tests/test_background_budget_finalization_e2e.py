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

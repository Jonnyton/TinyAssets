"""Queue lease telemetry and provider call metadata tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tinyassets.branch_tasks import (
    BranchTask,
    append_task,
    claim_task,
    new_task_id,
    read_queue,
    reclaim_expired_leases,
)


def _utc(offset_s: float = 0.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(seconds=offset_s)


def _make_task(universe: Path) -> BranchTask:
    task = BranchTask(
        branch_task_id=new_task_id(),
        branch_def_id="def-telemetry-test",
        universe_id="u-telemetry-test",
        trigger_source="owner_queued",
    )
    append_task(universe, task)
    return task


def test_reclaim_resets_expired_lease(tmp_path):
    task = _make_task(tmp_path)
    claimed = claim_task(tmp_path, task.branch_task_id, "daemon::test::1")
    assert claimed is not None

    count = reclaim_expired_leases(tmp_path, now=_utc(offset_s=10_000))
    assert count == 1
    row = {task.branch_task_id: task for task in read_queue(tmp_path)}[
        task.branch_task_id
    ]
    assert row.status == "pending"
    assert row.claimed_by == ""
    assert row.lease_expires_at == ""


def test_reclaim_leaves_fresh_lease_alone(tmp_path):
    task = _make_task(tmp_path)
    assert claim_task(tmp_path, task.branch_task_id, "daemon::test::1") is not None

    assert reclaim_expired_leases(tmp_path) == 0
    rows = {task.branch_task_id: task for task in read_queue(tmp_path)}
    assert rows[task.branch_task_id].status == "running"


def test_reclaim_skips_leaseless_running_rows(tmp_path):
    task = _make_task(tmp_path)
    assert claim_task(tmp_path, task.branch_task_id, "daemon::test::1") is not None
    from tinyassets.branch_tasks import _read_raw, _write_raw, queue_path

    queue = queue_path(tmp_path)
    raw = _read_raw(queue)
    for row in raw:
        row["lease_expires_at"] = ""
    _write_raw(queue, raw)

    assert reclaim_expired_leases(tmp_path, now=_utc(offset_s=10_000)) == 0


def test_reclaim_ignores_pending_rows(tmp_path):
    _make_task(tmp_path)
    assert reclaim_expired_leases(tmp_path, now=_utc(offset_s=10_000)) == 0


def test_call_meta_shape():
    from tinyassets.providers.base import ProviderResponse
    from tinyassets.providers.router import ProviderRouter

    response = ProviderResponse(
        text="hi",
        provider="codex",
        model="gpt-5.1-codex",
        family="openai",
        latency_ms=812,
    )
    assert ProviderRouter._call_meta(response, attempts=2) == {
        "model": "gpt-5.1-codex",
        "family": "openai",
        "latency_ms": 812,
        "degraded": False,
        "attempts": 2,
    }


@pytest.mark.asyncio
async def test_call_with_policy_returns_meta_triple():
    from tinyassets.providers.base import ProviderResponse
    from tinyassets.providers.router import ProviderRouter

    class _Provider:
        name = "fake"

        async def complete(self, prompt, system, cfg, *, universe_dir=None):
            return ProviderResponse(
                text="out",
                provider="fake",
                model="fake-1",
                family="test",
                latency_ms=5,
            )

    router = ProviderRouter()
    router._providers = {"fake": _Provider()}
    router._role_chains = {"writer": ["fake"]}

    text, name, meta = await router.call_with_policy(
        "writer", "p", "s", {"preferred": {"provider": "fake"}}
    )
    assert text == "out"
    assert name == "fake"
    assert meta["model"] == "fake-1"

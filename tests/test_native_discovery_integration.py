"""Real owned custody/member/serving/work boundaries, synthetic provider only."""

import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from tests import test_native_model_authority as authority_tests
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_native_model_authority import _call
from tests.test_run_provider_session import _branch, _CountingProvider, _run_branch
from tinyassets.credential_vault import write_credential_vault
from tinyassets.exceptions import ProviderAuthorityHeldError, ProviderError
from tinyassets.provider_assignment import provider_assignment_admission
from tinyassets.provider_assignment_manifest import ModelAccess
from tinyassets.providers.model_policy import ModelRef
from tinyassets.providers.native_catalogue import NativeCatalogue, NativeModel
from tinyassets.providers.served_model_plan import prepare_owned_model_plan
from tinyassets.storage.provider_work_authority import db_path

native = authority_tests.native


pytestmark = pytest.mark.usefixtures("cloud_runtime")


def catalogue(ids, *, age=0):
    return NativeCatalogue(
        tuple(NativeModel(name, frozenset({"text"})) for name in ids),
        ids[0] if ids else None, datetime.now(timezone.utc) - timedelta(seconds=age),
    )


def install_discovery(native, monkeypatch, discover=None):
    from tinyassets.daemon_server import set_founder_home

    set_founder_home(native.base, founder_sub="owner-1", universe_id=native.universe.name,
                     platform_generated=True)
    seen, configs = [], []
    monkeypatch.setattr("tinyassets.providers.call.get_provider_router", lambda: native.router)
    monkeypatch.setattr(native.provider, "native_credential_service", "codex")

    async def enumerate_models(*, universe_dir, credential_snapshot_dir):
        assert universe_dir == native.universe
        assert credential_snapshot_dir.is_dir()
        seen.append(credential_snapshot_dir)
        # A separate thread must acquire both fences while metadata IO runs.
        def unlocked():
            with provider_assignment_admission().exclusive(universe_dir):
                with sqlite3.connect(db_path(native.base), timeout=0.1) as conn:
                    conn.execute("BEGIN IMMEDIATE")
        with ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(unlocked).result(timeout=2)
        return catalogue(["new-account-model"]) if discover is None else await discover()

    monkeypatch.setattr(native.provider, "enumerate_models", enumerate_models)
    complete = native.provider.complete

    async def record(prompt, system, config, **kwargs):
        configs.append(config)
        return await complete(prompt, system, config, **kwargs)
    monkeypatch.setattr(native.provider, "complete", record)
    return seen, configs


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
def test_new_account_model_reaches_real_serving_authority_without_locks(native, monkeypatch):
    seen, configs = install_discovery(native, monkeypatch)
    context = replace(native.context, model_selection=ModelRef("codex", "new-account-model"))
    assert _call(native, context).provider == "codex"
    assert configs[0].native_model_id == "new-account-model"
    assert configs[0].selected_model is None
    assert seen and all(not path.exists() for path in seen)


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
@pytest.mark.parametrize("failure", ["absent", "rotated", "stale", "unknown"])
def test_discovered_selection_refuses_before_inference(native, monkeypatch, failure):
    async def discover():
        if failure == "rotated":
            write_credential_vault(native.universe, [], owner_user_id="owner-1",
                                   universe_id=native.universe.name)
        if failure == "unknown":
            return None
        return catalogue(["not-selected" if failure == "absent" else "new-account-model"],
                         age=600 if failure == "stale" else 0)
    seen, configs = install_discovery(native, monkeypatch, discover)
    context = replace(native.context, model_selection=ModelRef("codex", "new-account-model"))
    with pytest.raises(ProviderAuthorityHeldError):
        _call(native, context)
    assert not configs and native.provider.calls == 0
    assert seen and all(not path.exists() for path in seen)


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
def test_cancelled_selection_releases_real_owned_snapshot(native, monkeypatch):
    async def exercise():
        started = asyncio.Event()

        async def discover():
            started.set()
            await asyncio.Event().wait()
        seen, configs = install_discovery(native, monkeypatch, discover)
        context = replace(native.context, model_selection=ModelRef("codex", "new-account-model"))
        task = asyncio.create_task(native.router.call(
            "writer", "hello", "system", operation="converse", universe_context=context,
        ))
        await asyncio.wait_for(started.wait(), 3)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert not configs and seen and all(not path.exists() for path in seen)
    asyncio.run(exercise())


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
def test_picker_refresh_adds_new_model_without_static_release_table(native, monkeypatch):
    ids = ["initial-model"]

    async def discover():
        return catalogue(ids)
    install_discovery(native, monkeypatch, discover)

    def options():
        return prepare_owned_model_plan(
            base=native.base, universe=native.universe, owner="owner-1", agent=native.agent,
            allow_empty=True,
        )
    before = options()
    ids.append("brand-new-account-release")
    after = options()
    assert [m.model_id for m in before.catalog.connections[0].models] == ["", "initial-model"]
    assert [m.model_id for m in after.catalog.connections[0].models] == ["", *ids]
    assert after.catalog.connections[0].models[-1].availability_basis == "executor_enumerated"
    assert after.catalog.connections[0].default_model_id == ""


@pytest.mark.parametrize("native", ["discovered"], indirect=True)
@pytest.mark.parametrize("unsupported", [False, True])
def test_unavailable_enumeration_keeps_provider_default_usable(native, monkeypatch, unsupported):
    from tinyassets.providers.model_options import model_options_document

    async def discover():
        if unsupported:
            return None
        raise ProviderError("metadata temporarily unavailable")
    seen, configs = install_discovery(native, monkeypatch, discover)
    plan = prepare_owned_model_plan(
        base=native.base, universe=native.universe, owner="owner-1", agent=native.agent,
    )
    assert plan.plan.next_candidate("owner-1", native.universe.name) == ModelRef("codex", "")
    reason = "native_enumeration_unsupported" if unsupported else "native_catalogue_unavailable"
    assert any(item.reason == reason for item in plan.ineligible)
    document = model_options_document(plan.catalog, plan.plan, plan.ineligible)
    default = next(row for row in document["options"] if row["reference"]["model_id"] == "")
    assert default["in_candidate_catalog"] and default["reasons"] == []
    assert document["source_failures"][0]["reasons"][0]["reason"] == reason
    assert _call(native).provider == "codex"
    assert configs[0].native_model_id == "" and all(not path.exists() for path in seen)


def test_workflow_discovered_model_has_sealed_versioned_evidence(
    tmp_path, monkeypatch, authenticate_request,
):
    snapshots = []

    async def enumerate_models(self, *, universe_dir, credential_snapshot_dir):
        snapshots.append(credential_snapshot_dir)
        assert credential_snapshot_dir.is_dir()
        return catalogue(["new-work-model"])
    monkeypatch.setattr(_CountingProvider, "native_credential_service", "codex")
    monkeypatch.setattr(_CountingProvider, "enumerate_models", enumerate_models)
    branch = _branch(node_count=1)
    branch.node_defs[0].llm_policy["preferred"]["model_id"] = "new-work-model"
    before = branch.to_dict()
    result, provider, _ = _run_branch(
        tmp_path, monkeypatch, authenticate_request, branch,
        model_access={"codex": ModelAccess("discovered")},
    )
    assert result["terminal_status"] == "completed", result["terminal_error"]
    assert branch.to_dict() == before
    assert provider.calls[0].native_model_id == "new-work-model"
    with sqlite3.connect(db_path(tmp_path)) as conn:
        records = conn.execute(
            "SELECT record_json FROM provider_invocation_reservations",
        ).fetchall()
    evidence = json.loads(records[0][0])["selection"]["model_evidence"]
    assert evidence["kind"] == "native" and evidence["version"] == 2
    assert evidence["basis"] == "executor_enumerated" and evidence["source_digest"]
    assert snapshots and all(not path.exists() for path in snapshots)


def test_background_discovered_model_keeps_workflow_authority_and_settles_once(
    tmp_path, monkeypatch,
):
    from tests.test_background_budget_finalization_e2e import (
        _CountingProvider as BackgroundProvider,
    )
    from tests.test_background_budget_finalization_e2e import _run_consumer_once
    from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter
    from tinyassets.daemon_server import set_founder_home
    from tinyassets.runs import get_run_by_branch_task_id

    seen = []

    async def enumerate_models(self, *, universe_dir, credential_snapshot_dir):
        seen.append(credential_snapshot_dir)
        return catalogue(["background-new-model"])
    monkeypatch.setattr(BackgroundProvider, "native_credential_service", "codex")
    monkeypatch.setattr(BackgroundProvider, "enumerate_models", enumerate_models)
    set_founder_home(tmp_path, founder_sub="acct_alice", universe_id="universe_alice",
                     platform_generated=True)
    task_id, _, _, _, _ = _run_consumer_once(
        tmp_path, monkeypatch, model_access={"codex": ModelAccess("discovered")},
        policy={"preferred": {"provider": "codex", "model_id": "background-new-model"}},
    )
    task = Epoch2BranchTaskAdapter(tmp_path).get(task_id)
    run = get_run_by_branch_task_id(tmp_path, branch_task_id=task_id)
    assert task.status == "succeeded", None if run is None else run.get("error")
    with sqlite3.connect(db_path(tmp_path)) as conn:
        records = [json.loads(row[0]) for row in conn.execute(
            "SELECT record_json FROM provider_invocation_reservations",
        )]
    assert len(records) == 1 and records[0]["state"] == "succeeded"
    assert records[0]["selection"]["model_id"] == "background-new-model"
    assert records[0]["selection"]["model_evidence"]["version"] == 2
    assert seen and all(not path.exists() for path in seen)


@pytest.mark.parametrize("correction", [
    {"version": 1}, {"version": True}, {"basis": "owner_declared"},
    {"observed_at": "yesterday"}, {"completed_at": "2026-09-01T00:00:00"},
    {"source_digest": ""}, {"extra": "field"},
])
def test_enumerated_native_evidence_is_strict_and_separately_versioned(correction):
    from tinyassets.providers.native_model_selection import NativeSelection

    now = datetime.now(timezone.utc).isoformat()
    original = NativeSelection("provider", "new", "new", "executor_enumerated", now, now, "digest")
    assert NativeSelection.from_dict(original.to_dict()) == original
    document = {**original.to_dict(), **correction}
    with pytest.raises(ValueError):
        NativeSelection.from_dict(document)

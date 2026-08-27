"""Real-store proof for the assigned consumer's background-binding carrier path.

The consumer claims with its boot-scoped process lease, reuses the executor identity
authorized by the background binding, and launches through a server-minted one-use
``ProviderInvocationCarrier``.  Only the terminal provider is a counting test double;
queue enumeration, admission, activation, background authority, assignment, custody,
provider binding/receipt/claim/reservation, and routing all use their real stores.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path

from tinyassets.background_branch_authority import (
    BackgroundBranchExecutorAudience,
    BackgroundBranchExecutorClass,
)
from tinyassets.background_branch_authority_service import (
    BackgroundBranchAuthorityOwnerKind,
    BackgroundBranchAuthorityOwnerState,
)
from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
from tinyassets.providers.router import ProviderRouter
from tinyassets.storage.background_branch_authority import (
    SQLiteBackgroundBranchAuthorityStore,
)
from tinyassets.storage.provider_work_authority import db_path as authority_db_path


class _CountingProvider(BaseProvider):
    def __init__(self, on_call=None) -> None:
        self.name = "codex"
        self.family = "codex"
        self.calls: list[ModelConfig] = []
        self.on_call = on_call

    async def complete(self, prompt, system, config: ModelConfig, *, universe_dir=None):
        if self.on_call is not None:
            self.on_call()
        self.calls.append(config)
        return ProviderResponse(
            text="routed-ok",
            provider="codex",
            model="fake",
            family="codex",
            latency_ms=0.0,
            input_tokens=700,
            output_tokens=300,
            cost_microunits=50,
        )


def _seed_branch_version(tmp_path: Path):
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    node = NodeDefinition(
        node_id="n1",
        display_name="Background writer",
        prompt_template="Complete the assigned background task.",
    )
    branch = BranchDefinition(
        branch_def_id="branch_repo_spec_loop",
        name="Repository spec loop",
        author="acct_alice",
        visibility="private",
        graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
        edges=[EdgeDefinition(from_node="n1", to_node="END")],
        entry_point="n1",
        node_defs=[node],
        state_schema=[],
    )
    initialize_author_server(tmp_path)
    save_branch_definition(tmp_path, branch_def=branch.to_dict())
    return publish_branch_version(tmp_path, branch.to_dict(), publisher="acct_alice")


def _seed_serving_assignment(tmp_path: Path) -> None:
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import create_binding, publish_definition
    from tinyassets.provider_serving_binding import (
        bind_serving_provider,
        list_serving_universes,
        set_serving,
    )

    universe_dir = tmp_path / "universe_alice"
    universe_dir.mkdir(exist_ok=True)
    write_credential_vault(
        universe_dir,
        [
            {
                "credential_type": "llm_subscription",
                "service": "codex",
                "auth_json_b64": "e30=",
            }
        ],
        owner_user_id="acct_alice",
        universe_id="universe_alice",
    )
    definition = publish_definition(
        tmp_path,
        author_id="acct_alice",
        payload={
            "schema_version": 1,
            "name": "Background agent",
            "description": "Runs one assigned background Branch.",
            "tags": ["test"],
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    agent = create_binding(
        tmp_path,
        universe_id="universe_alice",
        definition_id=definition["agent_definition_id"],
        created_by="acct_alice",
        payload={"schema_version": 1, "name": "Background agent", "role": "writer"},
    )
    connected = bind_serving_provider(
        base_path=tmp_path,
        universe_dir=universe_dir,
        owner_user_id="acct_alice",
        universe_id="universe_alice",
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=1,
        provider="codex",
    )
    set_serving(
        base_path=tmp_path,
        universe_dir=universe_dir,
        owner_user_id="acct_alice",
        universe_id="universe_alice",
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"],
        enabled=True,
    )
    assert list_serving_universes(tmp_path) == ["universe_alice"]


def _seed_claimable_background_path(tmp_path: Path):
    from tests.test_cloud_automation_continuation import (
        BRANCH_TASK_ID,
        _activate_cloud,
        _admit_claimable_cloud_task,
        _background_binding,
        _fixture,
        _issue_epoch2_attempt,
        _prepare,
    )
    from tinyassets.daemon_registry import create_daemon, ensure_daemon_runtime

    version = _seed_branch_version(tmp_path)
    daemon = create_daemon(
        tmp_path,
        display_name="Owner-authorized background daemon",
        created_by="acct_alice",
        soul_mode="soul",
        soul_text="Run this universe's accepted background Branch.",
    )
    runtime = ensure_daemon_runtime(
        tmp_path,
        daemon_id=str(daemon["daemon_id"]),
        universe_id="universe_alice",
        provider_name="codex",
        model_name="gpt-5",
        created_by="acct_alice",
        worker_id="worker_binding_1",
        metadata={"automation_executor_class": "cloud"},
    )
    binding = replace(
        _background_binding(
            daemon_id=str(daemon["daemon_id"]),
            branch_version_id=version.branch_version_id,
        ),
        runtime_id=str(runtime["runtime_instance_id"]),
    )
    fixture = _fixture(
        tmp_path,
        background_binding=binding,
        branch_version_id=version.branch_version_id,
        branch_content_digest=f"sha256:{version.content_hash}",
    )
    continuation = _prepare(fixture).record
    assert continuation is not None
    active = _activate_cloud(fixture)
    admission = _admit_claimable_cloud_task(
        fixture,
        active,
        continuation_id=continuation.continuation_id,
        daemon_id=str(daemon["daemon_id"]),
        daemon_soul_hash=str(daemon["soul_hash"]),
    )
    audience = BackgroundBranchExecutorAudience(
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id=str(daemon["daemon_id"]),
        runtime_id=str(runtime["runtime_instance_id"]),
        worker_id="worker_binding_1",
    )
    _issue_epoch2_attempt(
        tmp_path,
        fixture,
        continuation,
        admission,
        audience=audience,
    )
    _seed_serving_assignment(tmp_path)

    candidates = Epoch2BranchTaskAdapter(tmp_path).list_candidates(
        universe_id="universe_alice",
        limit=20,
    )
    assert [task.branch_task_id for task in candidates] == [BRANCH_TASK_ID]
    return BRANCH_TASK_ID, audience


def _run_consumer_once(tmp_path: Path, monkeypatch):
    import tinyassets.providers.call as provider_call_module
    from tinyassets.runtime.assigned_queue_consumer import AssignedQueueConsumer

    branch_task_id, audience = _seed_claimable_background_path(tmp_path)
    observed_owner_states: list[BackgroundBranchAuthorityOwnerState] = []

    def observe_running_owner() -> None:
        owner = SQLiteBackgroundBranchAuthorityStore(tmp_path).get_owner(
            owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
            owner_id=branch_task_id,
        )
        assert owner is not None
        observed_owner_states.append(owner.state)

    fake = _CountingProvider(observe_running_owner)
    previous_router = provider_call_module.get_provider_router()
    previous_force_mock = provider_call_module.is_force_mock()
    provider_call_module.set_provider_router(ProviderRouter({"codex": fake}))
    provider_call_module.set_force_mock(False)
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)

    class _DeferredExecutor:
        def __init__(self) -> None:
            self.future: Future[None] | None = None
            self.job = None

        def submit(self, fn, *args):
            self.future = Future()
            self.job = (fn, args)
            return self.future

        def run(self) -> None:
            assert self.future is not None and self.job is not None
            fn, args = self.job
            try:
                fn(*args)
            except BaseException as exc:
                self.future.set_exception(exc)
                raise
            else:
                self.future.set_result(None)

        def shutdown(self, **_kwargs) -> None:
            pass

    deferred = _DeferredExecutor()
    consumer._executor.shutdown(wait=False, cancel_futures=True)
    consumer._executor = deferred
    try:
        assert not hasattr(consumer, "worker_id_for")
        assert consumer.poll_once() == 1
        pending_owner = SQLiteBackgroundBranchAuthorityStore(tmp_path).get_owner(
            owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
            owner_id=branch_task_id,
        )
        assert pending_owner is not None
        assert pending_owner.state is BackgroundBranchAuthorityOwnerState.PENDING
        deferred.run()
        for future in list(consumer._active.values()):
            future.result(timeout=10)
    finally:
        consumer.stop()
        provider_call_module.set_provider_router(previous_router)
        provider_call_module.set_force_mock(previous_force_mock)
    return branch_task_id, audience, consumer, fake, observed_owner_states


def test_consumer_poll_once_claims_with_process_lease_and_launches_carrier(
    tmp_path: Path,
    monkeypatch,
) -> None:
    branch_task_id, audience, consumer, fake, owner_states = _run_consumer_once(
        tmp_path, monkeypatch
    )

    task = Epoch2BranchTaskAdapter(tmp_path).get(branch_task_id)
    assert task is not None
    assert task.status == "succeeded", task.error
    assert task.claimed_by == consumer.consumer_id
    assert len(fake.calls) == 1
    assert owner_states == [BackgroundBranchAuthorityOwnerState.RUNNING]
    launched_config = fake.calls[0]
    assert launched_config.max_tokens is not None and launched_config.max_tokens >= 1
    assert launched_config.credential_snapshot_dir is not None
    assert not launched_config.credential_snapshot_dir.exists()

    from tinyassets.runs import get_run_by_branch_task_id

    run = get_run_by_branch_task_id(tmp_path, branch_task_id=branch_task_id)
    assert run is not None
    assert run["daemon_id"] == audience.daemon_id
    assert run["runtime_instance_id"] == audience.runtime_id
    assert run["worker_id"] == consumer.consumer_id

    terminal_owner = SQLiteBackgroundBranchAuthorityStore(tmp_path).get_owner(
        owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
        owner_id=branch_task_id,
    )
    assert terminal_owner is not None
    assert terminal_owner.state is BackgroundBranchAuthorityOwnerState.SUCCEEDED

    conn = sqlite3.connect(authority_db_path(tmp_path))
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT state, ordinal, claim_id, actual_total_tokens, "
        "actual_cost_microunits FROM provider_invocation_reservations"
    ).fetchall()
    assert len(rows) == 1, [dict(row) for row in rows]
    assert rows[0]["state"] == "succeeded"
    assert rows[0]["ordinal"] == 1
    assert rows[0]["actual_total_tokens"] == 1000
    assert rows[0]["actual_cost_microunits"] == 50

    receipt = conn.execute(
        "SELECT json_extract(record_json, '$.principal_id') AS principal_id, "
        "json_extract(record_json, '$.actor_id') AS actor_id "
        "FROM provider_work_receipts"
    ).fetchone()
    claim = conn.execute(
        "SELECT json_extract(record_json, '$.worker_id') AS worker_id, "
        "json_extract(record_json, '$.runtime_id') AS runtime_id "
        "FROM provider_work_execution_claims"
    ).fetchone()
    assert receipt["principal_id"] == "acct_alice"
    assert receipt["actor_id"] == audience.daemon_id
    assert claim["worker_id"] == audience.daemon_id
    assert claim["runtime_id"] == audience.runtime_id


def test_carrier_launch_records_actual_usage(tmp_path: Path, monkeypatch) -> None:
    _run_consumer_once(tmp_path, monkeypatch)
    conn = sqlite3.connect(authority_db_path(tmp_path))
    conn.row_factory = sqlite3.Row
    cols = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(provider_invocation_reservations)")
    }
    assert "actual_total_tokens" in cols
    row = conn.execute(
        "SELECT actual_total_tokens FROM provider_invocation_reservations"
    ).fetchone()
    assert row["actual_total_tokens"] == 1000

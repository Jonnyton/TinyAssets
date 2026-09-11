"""Real-store proof for the assigned consumer's background-binding carrier path.

The consumer claims with its boot-scoped process lease, reuses the executor identity
authorized by the background binding, and launches through a server-minted one-use
``ProviderInvocationCarrier``.  Only the terminal provider is a counting test double;
queue enumeration, admission, activation, background authority, assignment, custody,
provider binding/receipt/claim/reservation, and routing all use their real stores.
"""

from __future__ import annotations

import json
import sqlite3
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path

import pytest

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
    def __init__(self, on_call=None, *, name="codex") -> None:
        self.name = name
        self.family = name
        self.calls: list[ModelConfig] = []
        self.on_call = on_call

    async def complete(self, prompt, system, config: ModelConfig, *, universe_dir=None):
        if self.on_call is not None:
            self.on_call()
        self.calls.append(config)
        return ProviderResponse(
            text="routed-ok",
            provider=self.name,
            model="fake",
            family=self.family,
            latency_ms=0.0,
            input_tokens=700,
            output_tokens=300,
            cost_microunits=50,
        )


def _seed_branch_version(tmp_path: Path, *, policy=None):
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    nodes = [NodeDefinition(
        node_id=f"n{index + 1}",
        display_name="Background writer",
        prompt_template="Complete the assigned background task.",
        llm_policy=node_policy,
    ) for index, node_policy in enumerate(policy if isinstance(policy, list) else [policy])]
    branch = BranchDefinition(
        branch_def_id="branch_repo_spec_loop",
        name="Repository spec loop",
        author="acct_alice",
        visibility="private",
        graph_nodes=[GraphNodeRef(id=n.node_id, node_def_id=n.node_id) for n in nodes],
        edges=[EdgeDefinition(from_node=n.node_id, to_node=(
            nodes[index + 1].node_id if index + 1 < len(nodes) else "END"
        )) for index, n in enumerate(nodes)],
        entry_point="n1",
        node_defs=nodes,
        state_schema=[],
    )
    initialize_author_server(tmp_path)
    save_branch_definition(tmp_path, branch_def=branch.to_dict())
    return publish_branch_version(tmp_path, branch.to_dict(), publisher="acct_alice")


def _seed_serving_assignment(tmp_path: Path, *, model_access=None, services=("codex",)) -> None:
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
                "service": service,
                **({"auth_json_b64": "e30="} if service == "codex"
                   else {"oauth_token": "synthetic-claude-test-only"}),
            }
            for service in services
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
        model_access=model_access,
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


def _seed_claimable_background_path(tmp_path: Path, *, model_access=None,
                                    services=("codex",), policy=None):
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

    version = _seed_branch_version(tmp_path, policy=policy)
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
    if model_access is not None:
        from tinyassets.daemon_server import set_founder_home

        set_founder_home(
            tmp_path,
            founder_sub="acct_alice",
            universe_id="universe_alice",
            platform_generated=True,
        )
    _seed_serving_assignment(tmp_path, model_access=model_access, services=services)

    candidates = Epoch2BranchTaskAdapter(tmp_path).list_candidates(
        universe_id="universe_alice",
        limit=20,
    )
    assert [task.branch_task_id for task in candidates] == [BRANCH_TASK_ID]
    return BRANCH_TASK_ID, audience


def _run_consumer_once(tmp_path: Path, monkeypatch, *, model_access=None,
                       services=("codex",), policy=None, before_execution=None):
    import tinyassets.providers.call as provider_call_module
    from tinyassets.runtime.assigned_queue_consumer import AssignedQueueConsumer

    observed_owner_states: list[BackgroundBranchAuthorityOwnerState] = []

    def observe_running_owner() -> None:
        owner = SQLiteBackgroundBranchAuthorityStore(tmp_path).get_owner(
            owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
            owner_id=branch_task_id,
        )
        assert owner is not None
        observed_owner_states.append(owner.state)

    fake = _CountingProvider(observe_running_owner)
    fake.peers = {"codex": fake}
    if "claude" in services:
        fake.peers["claude-code"] = _CountingProvider(observe_running_owner, name="claude-code")
    previous_router = provider_call_module.get_provider_router()
    previous_force_mock = provider_call_module.is_force_mock()
    provider_call_module.set_provider_router(ProviderRouter(fake.peers))
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
        branch_task_id, audience = _seed_claimable_background_path(
            tmp_path,
            model_access=model_access,
            services=services,
            policy=policy,
        )
        assert not hasattr(consumer, "worker_id_for")
        assert consumer.poll_once() == 1
        pending_owner = SQLiteBackgroundBranchAuthorityStore(tmp_path).get_owner(
            owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
            owner_id=branch_task_id,
        )
        assert pending_owner is not None
        assert pending_owner.state is BackgroundBranchAuthorityOwnerState.PENDING
        if before_execution is not None:
            before_execution()
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
        row["name"] for row in conn.execute("PRAGMA table_info(provider_invocation_reservations)")
    }
    assert "actual_total_tokens" in cols
    row = conn.execute(
        "SELECT actual_total_tokens FROM provider_invocation_reservations"
    ).fetchone()
    assert row["actual_total_tokens"] == 1000


def test_model_selection_preserves_background_execution(tmp_path: Path, monkeypatch) -> None:
    """Real owner opt-in must not remove the consumer's ability to launch work."""
    from tinyassets.provider_assignment_manifest import ModelAccess

    task_id, audience, consumer, fake, states = _run_consumer_once(
        tmp_path,
        monkeypatch,
        model_access={"codex": ModelAccess("discovered")},
    )
    task = Epoch2BranchTaskAdapter(tmp_path).get(task_id)
    assert task.status == "succeeded", task.error
    assert task.claimed_by == consumer.consumer_id
    assert len(fake.calls) == 1
    assert states == [BackgroundBranchAuthorityOwnerState.RUNNING]
    with sqlite3.connect(authority_db_path(tmp_path)) as conn:
        receipts = [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT record_json FROM provider_work_receipts",
            )
        ]
        reservations = [
            json.loads(row[0])
            for row in conn.execute(
                "SELECT record_json FROM provider_invocation_reservations",
            )
        ]
    assert len(receipts) == len(reservations) == 1
    assert receipts[0]["schema_version"] == 4
    assert receipts[0]["authority_scope"] == "manifest"
    assert receipts[0]["provider"] is None
    assert receipts[0]["binding_id"] is None
    assert receipts[0]["actor_id"] == audience.daemon_id
    assert reservations[0]["schema_version"] == 3
    assert reservations[0]["selection"]["provider"] == "codex"
    assert reservations[0]["state"] == "succeeded"
    assert reservations[0]["actual_total_tokens"] == 1000
    assert reservations[0]["actual_cost_microunits"] == 50


@pytest.mark.parametrize("rotated", [None, "codex", "claude-code"])
def test_background_selection_uses_independent_current_member(tmp_path, monkeypatch, rotated):
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.provider_assignment import load_provider_assignment
    from tinyassets.provider_assignment_manifest import ModelAccess

    monkeypatch.setenv("TINYASSETS_ALLOW_CLAUDE_SERVING", "1")

    def rotate():
        if rotated is not None:
            write_credential_vault(
                tmp_path / "universe_alice",
                [
                    {"credential_type": "llm_subscription", "service": "codex",
                     "auth_json_b64": "eyJyb3RhdGVkIjp0cnVlfQ==" if rotated == "codex" else "e30="},
                    {"credential_type": "llm_subscription", "service": "claude",
                     "oauth_token": "rotated-test-only" if rotated == "claude-code"
                     else "synthetic-claude-test-only"},
                ], owner_user_id="acct_alice", universe_id="universe_alice",
            )

    task_id, _, _, fake, _ = _run_consumer_once(
        tmp_path, monkeypatch,
        services=("codex", "claude"),
        model_access={name: ModelAccess("discovered") for name in ("codex", "claude-code")},
        policy={"preferred": {"provider": "claude-code"}, "fallback_chain": []},
        before_execution=rotate,
    )
    assert len(fake.calls) == 0
    assert len(fake.peers["claude-code"].calls) == int(rotated != "claude-code")
    task = Epoch2BranchTaskAdapter(tmp_path).get(task_id)
    assert (task.status == "succeeded") == (rotated != "claude-code"), task.error
    assignment = load_provider_assignment(tmp_path, universe_id="universe_alice")
    assert assignment.provider == "codex"
    with sqlite3.connect(authority_db_path(tmp_path)) as conn:
        rows = [json.loads(row[0]) for row in conn.execute(
            "SELECT record_json FROM provider_invocation_reservations",
        )]
    assert len(rows) == int(rotated != "claude-code")
    if rows:
        assert rows[0]["selection"]["provider"] == "claude-code"
        assert rows[0]["state"] == "succeeded"


def test_background_explicit_unknown_model_cannot_silently_default(tmp_path, monkeypatch):
    from tinyassets.provider_assignment_manifest import ModelAccess

    task_id, _, _, fake, _ = _run_consumer_once(
        tmp_path, monkeypatch,
        model_access={"codex": ModelAccess("discovered")},
        policy={"preferred": {"provider": "codex", "model": "unavailable-model"}},
    )
    assert fake.calls == []
    assert Epoch2BranchTaskAdapter(tmp_path).get(task_id).status != "succeeded"
    with sqlite3.connect(authority_db_path(tmp_path)) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM provider_invocation_reservations",
        ).fetchone() == (0,)


@pytest.mark.parametrize("allowance", [1, 2])
def test_background_members_share_one_attempt_budget(tmp_path, monkeypatch, allowance):
    from tinyassets.provider_assignment_manifest import ModelAccess

    monkeypatch.setenv("TINYASSETS_ALLOW_CLAUDE_SERVING", "1")
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_UNIVERSE_MAX_INVOCATIONS", str(allowance))
    task_id, _, _, fake, _ = _run_consumer_once(
        tmp_path, monkeypatch, services=("codex", "claude"),
        model_access={name: ModelAccess("discovered") for name in ("codex", "claude-code")},
        policy=[{"preferred": {"provider": provider}, "fallback_chain": []}
                for provider in ("codex", "claude-code")],
    )
    task = Epoch2BranchTaskAdapter(tmp_path).get(task_id)
    assert (task.status == "succeeded") == (allowance == 2), task.error
    assert len(fake.calls) == 1
    assert len(fake.peers["claude-code"].calls) == allowance - 1
    with sqlite3.connect(authority_db_path(tmp_path)) as conn:
        receipts = [json.loads(row[0]) for row in conn.execute(
            "SELECT record_json FROM provider_work_receipts",
        )]
        reservations = [json.loads(row[0]) for row in conn.execute(
            "SELECT record_json FROM provider_invocation_reservations ORDER BY ordinal",
        )]
        assert conn.execute(
            "SELECT COUNT(*) FROM provider_work_execution_claims",
        ).fetchone() == (1,)
    assert len(receipts) == 1
    assert receipts[0]["max_invocations"] == allowance
    assert len(reservations) == allowance
    assert {r["receipt_id"] for r in reservations} == {receipts[0]["receipt_id"]}
    assert [r["state"] for r in reservations] == ["succeeded"] * allowance
    assert sum(r["actual_total_tokens"] for r in reservations) == 1000 * allowance

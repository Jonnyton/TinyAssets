from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from tinyassets.evaluation.scenario_runner import AcceptanceScenario
from tinyassets.execution_subject import ExecutionSubject, ExecutionSubjectKind
from tinyassets.provider_work_authority import ProviderWorkBindingSeed
from tinyassets.storage.automation_activations import (
    AutomationActivationExecutor,
    AutomationActivationStore,
)
from tinyassets.storage.cloud_automation_control import CloudAutomationControlStore
from tinyassets.storage.outbound_connections import ActionCap, ConnectionLedger
from tinyassets.storage.provider_work_authority import SQLiteProviderWorkAuthorityStore
from tinyassets.user_owned_cloud_automation import RepositorySpecWorkDefinition

NOW = datetime(2026, 8, 3, 23, 0, tzinfo=timezone.utc)
ACCEPTED_SPEC_CONTENT = "# Accepted repository specification\n"


def _baseline_scenario() -> AcceptanceScenario:
    return AcceptanceScenario(
        scenario_id="scenario:repo-spec-baseline-v1",
        target_surface="session_trace_summary",
        user_story=(
            "A repository owner needs a deterministic preflight that checks "
            "immutable repository and OpenSpec evidence before any provider "
            "or GitHub effect is authorized. The preflight must be safe for "
            "multi-tenant cloud execution and preserve exact evidence."
        ),
        allowed_tools=[],
        evaluator_chain=["evaluator:coding-trajectory-v1"],
        artifact_requirements=[{"kind": "content_digest", "required": True}],
        pass_threshold={"min_score": 1.0},
        cost_budget={"max_tokens": 0, "max_wall_time_seconds": 10},
        privacy_scope="universe_only",
        idempotency_key_constructor="scenario+candidate+artifact-digests",
        setup=[],
    )


def _definition() -> RepositorySpecWorkDefinition:
    from tinyassets.user_owned_cloud_automation import acceptance_scenario_digest

    return RepositorySpecWorkDefinition.from_dict(
        {
            "schema_version": 1,
            "principal_id": "acct_alice",
            "universe_id": "universe_alice",
            "repository": "example/project",
            "accepted_spec_ref": "openspec/specs/example/spec.md",
            "accepted_spec_digest": f"sha256:{'a' * 64}",
            "branch_def_id": "branch_repo_spec_loop",
            "branch_version_id": "branch_repo_spec_loop@abc12345",
            "branch_content_digest": f"sha256:{'b' * 64}",
            "acceptance_scenario_id": "scenario:repo-spec-baseline-v1",
            "acceptance_scenario_digest": acceptance_scenario_digest(
                _baseline_scenario()
            ),
            "input_artifact_digests": [
                f"sha256:{'a' * 64}",
                f"sha256:{'b' * 64}",
            ],
            "provider_binding_id": "pwb_11111111111111111111111111111111",
            "destination_grant_id": "destination_grant_project",
            "destination_purpose": "pull_request",
            "max_attempts": 2,
            "max_provider_invocations": 4,
            "max_wall_time_seconds": 3600,
            "max_tokens": 100_000,
            "max_cost_microunits": 5_000_000,
        }
    )


def _seed(tmp_path) -> None:
    definition = _definition()
    activations = AutomationActivationStore(tmp_path, clock=lambda: NOW)
    stopped = activations.create_stopped(
        universe_id=definition.universe_id,
        automation_id="automation_spec_drain",
    )
    active = activations.activate(
        expected=stopped,
        executor_class=AutomationActivationExecutor.CLOUD,
        subject=ExecutionSubject(
            kind=ExecutionSubjectKind.BRANCH_VERSION,
            ref=definition.branch_version_id,
            digest=definition.branch_content_digest,
        ),
        lease_id="lease_cloud_spec_drain",
    )
    assert active is not None
    CloudAutomationControlStore(tmp_path, clock=lambda: NOW).schedule_initial(
        definition,
        automation_id="automation_spec_drain",
        activation=active,
        cadence_seconds=300,
        due_at=NOW,
    )


def _seed_setup_authority(
    tmp_path,
    *,
    stage_spec: bool = True,
) -> RepositorySpecWorkDefinition:
    from tinyassets.branch_versions import publish_branch_version
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition
    from tinyassets.storage.cloud_automation_inputs import stage_accepted_spec

    node = NodeDefinition(
        node_id="n1",
        display_name="Repository spec worker",
        prompt_template="Apply the next accepted spec slice.",
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
    version = publish_branch_version(
        tmp_path,
        branch.to_dict(),
        publisher="acct_alice",
    )
    installed = SQLiteProviderWorkAuthorityStore(
        tmp_path,
        clock=lambda: NOW,
        allow_test_fixtures=True,
    ).install_test_binding(
        ProviderWorkBindingSeed(
            owner_user_id="acct_alice",
            universe_id="universe_alice",
            provider="codex",
            credential_reference_digest=f"sha256:{'9' * 64}",
            allowed_operations=("repository_spec_delivery",),
            allowed_roles=("writer",),
            assignment_generation=1,
            assignment_digest=f"sha256:{'8' * 64}",
            max_invocations=4,
            max_tokens=100_000,
            max_cost_microunits=5_000_000,
            expires_at="2026-08-30T00:00:00Z",
        )
    )
    assert installed.record is not None
    raw = _definition().to_dict()
    raw["accepted_spec_digest"] = (
        f"sha256:{hashlib.sha256(ACCEPTED_SPEC_CONTENT.encode('utf-8')).hexdigest()}"
    )
    raw["provider_binding_id"] = installed.record.binding_id
    raw["branch_version_id"] = version.branch_version_id
    raw["branch_content_digest"] = f"sha256:{version.content_hash}"
    raw["input_artifact_digests"] = [
        raw["accepted_spec_digest"],
        raw["branch_content_digest"],
    ]
    definition = RepositorySpecWorkDefinition.from_dict(raw)
    if stage_spec:
        stage_accepted_spec(
            tmp_path,
            accepted_spec_ref=definition.accepted_spec_ref,
            content=ACCEPTED_SPEC_CONTENT,
            expected_digest=definition.accepted_spec_digest,
        )
    ledger = ConnectionLedger(
        tmp_path / "outbound.db",
        verify_authenticated_principal=lambda: "acct_alice",
    )
    ledger.create_connection(
        connection_id="conn_tinyassets",
        owner_user_id="acct_alice",
        connection_class="pull-request-writer",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        provider="github",
        destination="github.com/example/project",
        credential_ref="vault://github/example-project",
    )
    ledger.grant_connection(
        grant_id=definition.destination_grant_id,
        connection_id="conn_tinyassets",
        owner_user_id="acct_alice",
        universe_id="universe_alice",
        granted_at=1.0,
        unprompted_action_cap=ActionCap("one_pull_request", 1, "pull_requests"),
    )
    return definition


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    from tinyassets.api import cloud_automations, permissions

    _seed(tmp_path)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)
    actor = {"id": "acct_alice"}
    monkeypatch.setattr(permissions, "current_actor_id", lambda: actor["id"])
    return cloud_automations, actor


def test_owner_can_inspect_private_automation_without_secret_material(api_env) -> None:
    api, _actor = api_env

    result = api.cloud_automations(
        action="get",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
    )

    assert result["automation"]["desired_state"] == "active"
    assert result["automation"]["revision"] == 1
    assert result["definition"]["repository"] == "example/project"
    assert result["current_trigger"]["status"] == "pending"
    encoded = json.dumps(result, sort_keys=True)
    assert "lease_cloud_spec_drain" not in encoded


def test_non_owner_reads_and_writes_are_non_oracular(api_env) -> None:
    api, actor = api_env
    actor["id"] = "acct_mallory"

    read = api.cloud_automations(
        action="get",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
    )
    write = api.cloud_automations(
        action="pause",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=1,
    )

    assert read == {"error": "not_found", "resource": "cloud_automation"}
    assert write == read


def test_owner_pause_resume_and_stop_use_revision_fences(api_env) -> None:
    api, _actor = api_env

    paused = api.cloud_automations(
        action="pause",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=1,
    )
    stale = api.cloud_automations(
        action="resume",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=1,
    )
    resumed = api.cloud_automations(
        action="resume",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=2,
    )
    stopped = api.cloud_automations(
        action="stop",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=3,
    )

    assert paused["automation"]["desired_state"] == "paused"
    assert stale["error"] == "automation_revision_conflict"
    assert resumed["automation"]["desired_state"] == "active"
    assert stopped["automation"]["desired_state"] == "stopped"
    assert stopped["activation"]["state"] == "stopped"


def test_existing_canonical_handles_route_automation_controls(api_env, monkeypatch) -> None:
    from tinyassets import universe_server as server

    calls: list[dict[str, object]] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(server, "_cloud_automations_impl", fake)

    read = json.loads(
        server.read_graph(
            target="automation",
            graph_id="universe_alice",
            automation_id="automation_spec_drain",
        )
    )
    write = json.loads(
        server.write_graph(
            target="automation",
            operation="pause",
            graph_id="universe_alice",
            automation_id="automation_spec_drain",
            expected_revision=7,
            payload_json='{"owner_actor":"acct_mallory"}',
        )
    )

    assert read == {"ok": True}
    assert write == {"ok": True}
    assert calls == [
        {
            "action": "get",
            "universe_id": "universe_alice",
            "automation_id": "automation_spec_drain",
            "limit": 30,
        },
        {
            "action": "pause",
            "universe_id": "universe_alice",
            "automation_id": "automation_spec_drain",
            "expected_revision": 7,
            "payload": '{"owner_actor":"acct_mallory"}',
        },
    ]


def test_existing_write_handle_builds_and_publishes_user_branch(
    api_env,
    monkeypatch,
) -> None:
    from tinyassets import universe_server as server

    calls: list[dict[str, object]] = []

    def fake(**kwargs):
        calls.append(kwargs)
        return json.dumps({"ok": True})

    monkeypatch.setattr(server, "_extensions_impl", fake)
    spec = '{"name":"Repo loop","node_defs":[{"node_id":"n1"}]}'

    built = json.loads(
        server.write_graph(
            target="branch",
            operation="create",
            payload_json=spec,
            idempotency_key="request_1234567890abcdef",
        )
    )
    published = json.loads(
        server.write_graph(
            target="branch",
            operation="publish",
            branch_id="branch_repo_loop",
            description="Ready for cloud activation",
        )
    )

    assert built == {"ok": True}
    assert published == {"ok": True}
    assert json.loads(calls[0]["spec_json"])["visibility"] == "private"
    assert calls == [
        {
            "action": "build_branch",
            "spec_json": calls[0]["spec_json"],
            "request_id": "request_1234567890abcdef",
        },
        {
            "action": "publish_version",
            "branch_def_id": "branch_repo_loop",
            "notes": "Ready for cloud activation",
        },
    ]


def test_branch_staging_preserves_explicit_private_visibility() -> None:
    from tinyassets.api.branches import _staged_branch_from_spec

    branch, errors = _staged_branch_from_spec(
        {"name": "Private repository loop", "visibility": "private"}
    )

    assert errors == []
    assert branch.visibility == "private"


def test_non_owner_cannot_publish_private_branch(tmp_path, monkeypatch) -> None:
    from tinyassets import universe_server as server
    from tinyassets.api import permissions
    from tinyassets.branches import BranchDefinition
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    initialize_author_server(tmp_path)
    save_branch_definition(
        tmp_path,
        branch_def=BranchDefinition(
            branch_def_id="branch_alice_private",
            name="Alice private workflow",
            author="acct_alice",
            visibility="private",
        ).to_dict(),
    )
    actor = {"id": "acct_mallory"}
    monkeypatch.setattr(
        permissions,
        "current_request_actor_id",
        lambda: actor["id"],
    )

    denied = json.loads(
        server.write_graph(
            target="branch",
            operation="publish",
            branch_id="branch_alice_private",
        )
    )
    actor["id"] = "acct_alice"
    published = json.loads(
        server.write_graph(
            target="branch",
            operation="publish",
            branch_id="branch_alice_private",
        )
    )

    assert denied == {"error": "Branch 'branch_alice_private' not found."}
    assert published["branch_version_id"].startswith("branch_alice_private@")
    assert published["publisher"] == "acct_alice"


def test_phone_branch_create_replays_one_idempotent_definition(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets import universe_server as server
    from tinyassets.api import permissions
    from tinyassets.daemon_server import initialize_author_server

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        permissions,
        "current_request_actor_id",
        lambda: "acct_alice",
    )
    initialize_author_server(tmp_path)
    spec = {
        "name": "Repository loop",
        "entry_point": "ready",
        "node_defs": [
            {
                "node_id": "ready",
                "display_name": "Ready",
                "prompt_template": "Apply one accepted specification slice.",
            }
        ],
        "edges": [
            {"from": "START", "to": "ready"},
            {"from": "ready", "to": "END"},
        ],
        "state_schema": [{"name": "result", "type": "str"}],
    }

    first = json.loads(
        server.write_graph(
            target="branch",
            operation="create",
            payload_json=json.dumps(spec),
            idempotency_key="request_phone_branch_0001",
        )
    )
    replay = json.loads(
        server.write_graph(
            target="branch",
            operation="create",
            payload_json=json.dumps(spec),
            idempotency_key="request_phone_branch_0001",
        )
    )
    changed = dict(spec)
    changed["description"] = "Different definition under the same request key."
    conflict = json.loads(
        server.write_graph(
            target="branch",
            operation="create",
            payload_json=json.dumps(changed),
            idempotency_key="request_phone_branch_0001",
        )
    )

    assert "branch_def_id" in replay, replay
    assert replay["branch_def_id"] == first["branch_def_id"]
    assert replay["batch_receipt"]["idempotent_replay"] is True
    assert conflict["error"] == "branch_idempotency_conflict"


def test_concurrent_phone_branch_create_has_one_definition_winner(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets import universe_server as server
    from tinyassets.api import permissions
    from tinyassets.daemon_server import initialize_author_server

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(
        permissions,
        "current_request_actor_id",
        lambda: "acct_alice",
    )
    initialize_author_server(tmp_path)
    base = {
        "name": "Repository loop",
        "entry_point": "ready",
        "node_defs": [
            {
                "node_id": "ready",
                "display_name": "Ready",
                "prompt_template": "Apply one accepted specification slice.",
            }
        ],
        "edges": [
            {"from": "START", "to": "ready"},
            {"from": "ready", "to": "END"},
        ],
        "state_schema": [{"name": "result", "type": "str"}],
    }
    candidates = [
        {**base, "description": description}
        for description in ("definition-a", "definition-b")
        for _index in range(4)
    ]

    def create(spec: dict[str, object]) -> dict[str, object]:
        return json.loads(
            server.write_graph(
                target="branch",
                operation="create",
                payload_json=json.dumps(spec),
                idempotency_key="request_phone_branch_concurrent_0001",
            )
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(create, candidates))

    built = [result for result in results if result.get("status") == "built"]
    conflicts = [
        result
        for result in results
        if result.get("error") == "branch_idempotency_conflict"
    ]
    assert len(built) == 4
    assert len(conflicts) == 4
    assert sum(
        not bool(result["batch_receipt"]["idempotent_replay"])
        for result in built
    ) == 1
    assert len({str(result["branch_def_id"]) for result in built}) == 1


def test_owner_can_prepare_cloud_activation_from_chatbot_payload(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions
    from tinyassets.background_branch_authority import (
        BackgroundBranchExecutorAudience,
        BackgroundBranchExecutorClass,
    )
    from tinyassets.cloud_automation_runtime import (
        activate_one_requested_cloud_automation,
    )
    from tinyassets.daemon_registry import ensure_daemon_runtime, select_project_loop_daemon
    from tinyassets.storage.automation_activations import AutomationActivationStore

    definition = _seed_setup_authority(tmp_path)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)
    raw_definition = definition.to_dict()
    raw_definition["principal_id"] = "acct_mallory"
    raw_definition["universe_id"] = "universe_mallory"

    result = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        payload={
            "definition": raw_definition,
            "accepted_spec_content": ACCEPTED_SPEC_CONTENT,
            "cadence_seconds": 300,
            "operator": {
                "display_name": "Alice Cloud Builder",
                "soul_text": "Execute Alice's versioned user-authored Branches.",
            },
        },
    )

    assert result["status"] == "activation_requested"
    assert result["automation"]["principal_id"] == "acct_alice"
    assert result["automation"]["universe_id"] == "universe_alice"
    assert result["baseline_evaluation"]["status"] == "admitted"
    assert result["baseline_evaluation"]["scenario_id"] == (
        "scenario:repo-spec-baseline-v1"
    )
    assert result["baseline_evaluation"]["input_artifact_digests"] == list(
        definition.input_artifact_digests
    )
    assert result["baseline_evaluation"]["receipt_digest"].startswith("sha256:")
    server_automation_id = result["automation"]["automation_id"]
    replay = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        payload={
            "definition": raw_definition,
            "accepted_spec_content": ACCEPTED_SPEC_CONTENT,
            "cadence_seconds": 300,
            "operator": {
                "display_name": "Alice Cloud Builder",
                "soul_text": "Execute Alice's versioned user-authored Branches.",
            },
        },
    )
    assert replay["daemon_id"] == result["daemon_id"]
    activation = AutomationActivationStore(tmp_path).get(
        "universe_alice", server_automation_id
    )
    assert activation is not None and activation.state.value == "stopped"
    daemon = select_project_loop_daemon(
        tmp_path,
        universe_id="universe_alice",
        owner_user_id="acct_alice",
    )
    assert daemon is not None and daemon["has_soul"] is True
    runtime = ensure_daemon_runtime(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id="universe_alice",
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-worker",
        worker_id="worker_cloud_1",
    )

    activated = activate_one_requested_cloud_automation(
        tmp_path,
        universe_id="universe_alice",
        audience=BackgroundBranchExecutorAudience(
            executor_class=BackgroundBranchExecutorClass.CLOUD,
            daemon_id=daemon["daemon_id"],
            runtime_id=runtime["runtime_instance_id"],
            worker_id="worker_cloud_1",
        ),
        clock=lambda: NOW,
    )

    assert activated is not None
    assert activated.trigger.status.value == "admitted"
    replacement_replay = activate_one_requested_cloud_automation(
        tmp_path,
        universe_id="universe_alice",
        audience=BackgroundBranchExecutorAudience(
            executor_class=BackgroundBranchExecutorClass.CLOUD,
            daemon_id=daemon["daemon_id"],
            runtime_id=runtime["runtime_instance_id"],
            worker_id="worker_cloud_1",
        ),
        clock=lambda: NOW,
    )
    assert replacement_replay is not None
    assert replacement_replay.branch_task_id == activated.branch_task_id
    active = AutomationActivationStore(tmp_path).get(
        "universe_alice", server_automation_id
    )
    assert active is not None and active.state.value == "active"


def test_phone_rebinds_and_rolls_back_to_published_branch_versions(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions
    from tinyassets.branch_versions import get_branch_version, publish_branch_version
    from tinyassets.cloud_automation_control import CloudAutomationDesiredState
    from tinyassets.cloud_automation_setup import prepare_cloud_automation
    from tinyassets.daemon_server import save_branch_definition
    from tinyassets.storage.cloud_automation_continuation import (
        SQLiteCloudAutomationContinuationStore,
    )
    from tinyassets.storage.cloud_automation_control import CloudAutomationControlStore

    original = _seed_setup_authority(tmp_path)
    setup = prepare_cloud_automation(
        tmp_path,
        original,
        automation_id="automation_spec_drain",
        cadence_seconds=300,
        operator_display_name="Alice Cloud Builder",
        operator_soul_text="Run Alice's published repository workflow.",
        clock=lambda: NOW,
    )
    controls = CloudAutomationControlStore(tmp_path, clock=lambda: NOW)
    stopped = controls.set_desired_state(
        expected=setup.control,
        desired_state=CloudAutomationDesiredState.STOPPED,
    )
    original_version = get_branch_version(tmp_path, original.branch_version_id)
    assert original_version is not None
    edited_snapshot = json.loads(json.dumps(original_version.snapshot))
    edited_snapshot["node_defs"][0]["prompt_template"] = (
        "Apply the evolved accepted specification safely."
    )
    save_branch_definition(tmp_path, branch_def=edited_snapshot)
    evolved_version = publish_branch_version(
        tmp_path,
        edited_snapshot,
        publisher="acct_alice",
    )
    evolved_raw = original.to_dict()
    evolved_raw["branch_version_id"] = evolved_version.branch_version_id
    evolved_raw["branch_content_digest"] = f"sha256:{evolved_version.content_hash}"
    evolved_raw["input_artifact_digests"] = [
        evolved_raw["accepted_spec_digest"],
        evolved_raw["branch_content_digest"],
    ]
    evolved = RepositorySpecWorkDefinition.from_dict(evolved_raw)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    rebound = cloud_automations.cloud_automations(
        action="rebind",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=stopped.revision,
        payload={"definition": evolved.to_dict()},
    )

    assert rebound["status"] == "activation_requested"
    assert rebound["automation"]["revision"] == stopped.revision + 1
    assert rebound["definition"]["branch_version_id"] == evolved.branch_version_id
    continuation = SQLiteCloudAutomationContinuationStore(tmp_path).get(
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
    )
    assert continuation is not None
    assert continuation.generation == 2
    assert continuation.branch_version_id == evolved.branch_version_id

    rebound_control = controls.get_control(
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
    )
    assert rebound_control is not None
    restopped = controls.set_desired_state(
        expected=rebound_control,
        desired_state=CloudAutomationDesiredState.STOPPED,
    )
    rolled_back = cloud_automations.cloud_automations(
        action="rebind",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=restopped.revision,
        payload={"definition": original.to_dict()},
    )
    assert rolled_back["status"] == "activation_requested"
    assert rolled_back["definition"]["branch_version_id"] == original.branch_version_id
    rolled_back_continuation = SQLiteCloudAutomationContinuationStore(tmp_path).get(
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
    )
    assert rolled_back_continuation is not None
    assert rolled_back_continuation.generation == 3


def test_phone_rebind_requires_current_stopped_owner_control(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions
    from tinyassets.cloud_automation_setup import prepare_cloud_automation

    definition = _seed_setup_authority(tmp_path)
    setup = prepare_cloud_automation(
        tmp_path,
        definition,
        automation_id="automation_spec_drain",
        cadence_seconds=300,
        operator_display_name="Alice Cloud Builder",
        operator_soul_text="Run Alice's published repository workflow.",
        clock=lambda: NOW,
    )
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    active = cloud_automations.cloud_automations(
        action="rebind",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=setup.control.revision,
        payload={"definition": definition.to_dict()},
    )
    stale = cloud_automations.cloud_automations(
        action="rebind",
        universe_id="universe_alice",
        automation_id="automation_spec_drain",
        expected_revision=setup.control.revision + 1,
        payload={"definition": definition.to_dict()},
    )

    assert active["error"] == "automation_rebind_invalid"
    assert "must be stopped" in active["detail"]
    assert stale == {
        "error": "automation_revision_conflict",
        "expected_revision": setup.control.revision + 1,
        "current_revision": setup.control.revision,
    }


def test_phone_create_rejects_accepted_spec_content_with_wrong_digest(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions

    definition = _seed_setup_authority(tmp_path)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    result = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="automation_bad_spec_digest",
        payload={
            "definition": definition.to_dict(),
            "accepted_spec_content": "content that does not match the frozen digest",
            "cadence_seconds": 300,
            "operator": {"soul_text": "Run my user-authored repository workflow."},
        },
    )

    assert result["error"] == "automation_setup_invalid"
    assert "accepted spec digest" in result["detail"]


def test_phone_create_stages_and_rehashes_accepted_spec_content(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions

    definition = _seed_setup_authority(tmp_path, stage_spec=False)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    result = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="automation_staged_spec",
        payload={
            "definition": definition.to_dict(),
            "accepted_spec_content": ACCEPTED_SPEC_CONTENT,
            "cadence_seconds": 300,
            "operator": {"soul_text": "Run my user-authored repository workflow."},
        },
    )

    assert result["status"] == "activation_requested"


def test_prepare_rejects_unavailable_accepted_spec_artifact(tmp_path) -> None:
    from tinyassets.cloud_automation_setup import prepare_cloud_automation

    definition = _seed_setup_authority(tmp_path, stage_spec=False)

    with pytest.raises(ValueError, match="accepted spec artifact is unavailable"):
        prepare_cloud_automation(
            tmp_path,
            definition,
            automation_id="automation_missing_spec",
            cadence_seconds=300,
            operator_display_name="Alice Cloud Builder",
            operator_soul_text="Run my user-authored repository workflow.",
            clock=lambda: NOW,
        )


def test_prepare_rejects_fabricated_acceptance_scenario_digest(tmp_path) -> None:
    from tinyassets.cloud_automation_setup import prepare_cloud_automation
    from tinyassets.user_owned_cloud_automation import AutomationAdmissionError

    valid = _seed_setup_authority(tmp_path)
    raw = valid.to_dict()
    raw["acceptance_scenario_digest"] = f"sha256:{'f' * 64}"
    forged = RepositorySpecWorkDefinition.from_dict(raw)

    with pytest.raises(AutomationAdmissionError, match="scenario_mismatch"):
        prepare_cloud_automation(
            tmp_path,
            forged,
            automation_id="automation_forged_scenario",
            cadence_seconds=300,
            operator_display_name="Alice Cloud Builder",
            operator_soul_text="Execute Alice's versioned user-authored Branches.",
            clock=lambda: NOW,
        )


def test_prepare_rejects_missing_required_baseline_artifacts(tmp_path) -> None:
    from tinyassets.cloud_automation_setup import prepare_cloud_automation
    from tinyassets.user_owned_cloud_automation import AutomationAdmissionError

    valid = _seed_setup_authority(tmp_path)
    raw = valid.to_dict()
    raw["input_artifact_digests"] = [f"sha256:{'d' * 64}"]
    incomplete = RepositorySpecWorkDefinition.from_dict(raw)

    with pytest.raises(AutomationAdmissionError, match="artifact_mismatch"):
        prepare_cloud_automation(
            tmp_path,
            incomplete,
            automation_id="automation_missing_baseline_artifacts",
            cadence_seconds=300,
            operator_display_name="Alice Cloud Builder",
            operator_soul_text="Execute Alice's versioned user-authored Branches.",
            clock=lambda: NOW,
        )


def test_non_owner_cannot_activate_private_branch_version(tmp_path) -> None:
    from tinyassets.cloud_automation_setup import prepare_cloud_automation

    alice = _seed_setup_authority(tmp_path)
    provider_store = SQLiteProviderWorkAuthorityStore(
        tmp_path,
        clock=lambda: NOW,
        allow_test_fixtures=True,
    )
    installed = provider_store.install_test_binding(
        ProviderWorkBindingSeed(
            owner_user_id="acct_mallory",
            universe_id="universe_mallory",
            provider="codex",
            credential_reference_digest=f"sha256:{'7' * 64}",
            allowed_operations=("repository_spec_delivery",),
            allowed_roles=("writer",),
            assignment_generation=1,
            assignment_digest=f"sha256:{'6' * 64}",
            max_invocations=4,
            max_tokens=100_000,
            max_cost_microunits=5_000_000,
            expires_at="2026-08-30T00:00:00Z",
        )
    )
    assert installed.record is not None
    ledger = ConnectionLedger(
        tmp_path / "outbound.db",
        verify_authenticated_principal=lambda: "acct_mallory",
    )
    ledger.create_connection(
        connection_id="conn_mallory",
        owner_user_id="acct_mallory",
        connection_class="pull-request-writer",
        scopes=("pull_requests:write", "pull_requests:read_for_commit"),
        provider="github",
        destination="github.com/example/project",
        credential_ref="vault://github/mallory-project",
    )
    ledger.grant_connection(
        grant_id="destination_grant_mallory",
        connection_id="conn_mallory",
        owner_user_id="acct_mallory",
        universe_id="universe_mallory",
        granted_at=1.0,
        unprompted_action_cap=ActionCap(
            "one_pull_request",
            1,
            "pull_requests",
        ),
    )
    raw = alice.to_dict()
    raw.update(
        {
            "principal_id": "acct_mallory",
            "universe_id": "universe_mallory",
            "provider_binding_id": installed.record.binding_id,
            "destination_grant_id": "destination_grant_mallory",
        }
    )
    foreign_private = RepositorySpecWorkDefinition.from_dict(raw)

    with pytest.raises(ValueError, match="immutable Branch version does not exist"):
        prepare_cloud_automation(
            tmp_path,
            foreign_private,
            automation_id="automation_foreign_private",
            cadence_seconds=300,
            operator_display_name="Mallory Cloud Builder",
            operator_soul_text="Execute only Mallory's authorized workflows.",
            clock=lambda: NOW,
        )


def test_phone_list_discovers_safe_requester_owned_prerequisites(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions
    from tinyassets.cloud_automation_setup import prepare_cloud_automation

    definition = _seed_setup_authority(tmp_path)
    prepare_cloud_automation(
        tmp_path,
        definition,
        automation_id="automation_spec_drain",
        cadence_seconds=300,
        operator_display_name="Alice Cloud Builder",
        operator_soul_text="Execute Alice's versioned user-authored Branches.",
        clock=lambda: NOW,
    )
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    result = cloud_automations.cloud_automations(
        action="list",
        universe_id="universe_alice",
    )
    encoded = json.dumps(result, sort_keys=True)

    assert result["prerequisites"]["provider_bindings"] == [
        {
            "binding_id": definition.provider_binding_id,
            "provider": "codex",
            "allowed_operations": ["repository_spec_delivery"],
            "allowed_roles": ["writer"],
            "max_invocations": 4,
            "max_tokens": 100_000,
            "max_cost_microunits": 5_000_000,
            "expires_at": "2026-08-30T00:00:00Z",
        }
    ]
    assert result["prerequisites"]["destination_grants"] == [
        {
            "grant_id": definition.destination_grant_id,
            "connection_class": "pull-request-writer",
            "provider": "github",
            "destination": "github.com/example/project",
            "scopes": ["pull_requests:write", "pull_requests:read_for_commit"],
            "action_cap": {
                "name": "one_pull_request",
                "maximum": 1,
                "unit": "pull_requests",
            },
        }
    ]
    assert "credential" not in encoded
    assert "assignment_digest" not in encoded


def test_phone_create_auto_selects_single_safe_prerequisites(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions

    definition = _seed_setup_authority(tmp_path)
    raw = definition.to_dict()
    for field in (
        "provider_binding_id",
        "destination_grant_id",
        "acceptance_scenario_id",
        "acceptance_scenario_digest",
    ):
        del raw[field]
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    result = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="automation_phone_setup",
        payload={
            "definition": raw,
            "accepted_spec_content": ACCEPTED_SPEC_CONTENT,
            "cadence_seconds": 300,
            "operator": {
                "display_name": "Alice Cloud Builder",
                "soul_text": "Execute Alice's versioned user-authored Branches.",
            },
        },
    )

    assert result["status"] == "activation_requested"
    assert result["definition"]["provider_binding_id"] == definition.provider_binding_id
    assert result["definition"]["destination_grant_id"] == (
        definition.destination_grant_id
    )
    assert result["definition"]["acceptance_scenario_id"] == (
        "scenario:repo-spec-baseline-v1"
    )
    assert result["definition"]["acceptance_scenario_digest"] == (
        definition.acceptance_scenario_digest
    )


def test_phone_create_returns_actionable_setup_when_connections_are_missing(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions

    raw = _definition().to_dict()
    raw.pop("provider_binding_id")
    raw.pop("destination_grant_id")
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    result = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="automation_phone_setup",
        payload={"definition": raw, "cadence_seconds": 300},
    )

    assert result == {
        "error": "automation_setup_required",
        "detail": (
            "connect requester-owned compute, then retry "
            "read_graph target=automations"
        ),
        "prerequisites": {
            "provider_bindings": [],
            "destination_grants": [],
            "ready": False,
        },
    }


def test_stale_worker_cannot_reactivate_after_owner_stop(tmp_path, monkeypatch) -> None:
    from tinyassets.background_branch_authority import (
        BackgroundBranchExecutorAudience,
        BackgroundBranchExecutorClass,
    )
    from tinyassets.cloud_automation_control import CloudAutomationDesiredState
    from tinyassets.cloud_automation_runtime import activate_one_requested_cloud_automation
    from tinyassets.cloud_automation_setup import prepare_cloud_automation
    from tinyassets.daemon_registry import ensure_daemon_runtime, select_project_loop_daemon
    from tinyassets.storage.automation_activations import AutomationActivationStore
    from tinyassets.storage.cloud_automation_control import CloudAutomationControlStore

    definition = _seed_setup_authority(tmp_path)
    setup = prepare_cloud_automation(
        tmp_path,
        definition,
        automation_id="automation_spec_drain",
        cadence_seconds=300,
        operator_display_name="Alice Cloud Builder",
        operator_soul_text="Execute Alice's versioned user-authored Branches.",
        clock=lambda: NOW,
    )
    controls = CloudAutomationControlStore(tmp_path, clock=lambda: NOW)
    controls.set_desired_state(
        expected=setup.control,
        desired_state=CloudAutomationDesiredState.STOPPED,
    )
    daemon = select_project_loop_daemon(
        tmp_path,
        universe_id=definition.universe_id,
        owner_user_id=definition.principal_id,
    )
    assert daemon is not None
    runtime = ensure_daemon_runtime(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id=definition.universe_id,
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-worker",
        worker_id="worker_cloud_1",
    )

    # Model a worker that selected the active record just before stop committed.
    monkeypatch.setattr(
        CloudAutomationControlStore,
        "list_controls",
        lambda self, *, universe_id, limit=100: [setup.control],
    )
    activated = activate_one_requested_cloud_automation(
        tmp_path,
        universe_id=definition.universe_id,
        audience=BackgroundBranchExecutorAudience(
            executor_class=BackgroundBranchExecutorClass.CLOUD,
            daemon_id=daemon["daemon_id"],
            runtime_id=runtime["runtime_instance_id"],
            worker_id="worker_cloud_1",
        ),
        clock=lambda: NOW,
    )

    assert activated is None
    activation = AutomationActivationStore(tmp_path).get(
        definition.universe_id,
        "automation_spec_drain",
    )
    assert activation is not None and activation.state.value == "stopped"


def test_phone_create_aliases_converge_on_one_server_automation_identity(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions

    definition = _seed_setup_authority(tmp_path)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)
    payload = {
        "definition": definition.to_dict(),
        "accepted_spec_content": ACCEPTED_SPEC_CONTENT,
        "cadence_seconds": 300,
        "operator": {"soul_text": "Run my accepted repository workflow."},
    }

    first = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="my-first-label",
        payload=payload,
    )
    second = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="a-different-label-for-the-same-work",
        payload=payload,
    )
    listed = cloud_automations.cloud_automations(
        action="list",
        universe_id="universe_alice",
    )

    assert first["status"] == "activation_requested"
    assert second["status"] == "activation_requested"
    assert first["automation"]["automation_id"] == second["automation"]["automation_id"]
    assert listed["count"] == 1


def test_phone_cloud_create_fails_while_canonical_tray_lease_is_active(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions
    from tinyassets.storage.automation_activations import (
        AutomationActivationExecutor,
        AutomationActivationStore,
    )
    from tinyassets.user_owned_cloud_automation import repository_spec_automation_id

    definition = _seed_setup_authority(tmp_path)
    automation_id = repository_spec_automation_id(definition)
    activations = AutomationActivationStore(tmp_path, clock=lambda: NOW)
    stopped = activations.create_stopped(
        universe_id=definition.universe_id,
        automation_id=automation_id,
    )
    tray = activations.activate(
        expected=stopped,
        executor_class=AutomationActivationExecutor.TRAY,
        subject=ExecutionSubject(
            kind=ExecutionSubjectKind.BRANCH_VERSION,
            ref=definition.branch_version_id,
            digest=definition.branch_content_digest,
        ),
        lease_id="tray-local-drain-live",
    )
    assert tray is not None
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    result = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="caller-alias-cannot-bypass-tray",
        payload={
            "definition": definition.to_dict(),
            "accepted_spec_content": ACCEPTED_SPEC_CONTENT,
            "cadence_seconds": 300,
            "operator": {"soul_text": "Run my accepted repository workflow."},
        },
    )

    assert result["error"] == "automation_setup_invalid"
    assert result["detail"] == "automation is already active"
    assert activations.get(definition.universe_id, automation_id) == tray


def test_wrong_provider_worker_cannot_activate_requester_bound_automation(
    tmp_path,
) -> None:
    from tinyassets.background_branch_authority import (
        BackgroundBranchExecutorAudience,
        BackgroundBranchExecutorClass,
    )
    from tinyassets.cloud_automation_continuation import CloudContinuationActivationError
    from tinyassets.cloud_automation_runtime import (
        activate_one_requested_cloud_automation,
    )
    from tinyassets.cloud_automation_setup import prepare_cloud_automation
    from tinyassets.daemon_registry import (
        ensure_daemon_runtime,
        select_project_loop_daemon,
    )
    from tinyassets.storage.automation_activations import AutomationActivationStore

    definition = _seed_setup_authority(tmp_path)
    prepare_cloud_automation(
        tmp_path,
        definition,
        automation_id="automation_spec_drain",
        cadence_seconds=300,
        operator_display_name="Alice Cloud Builder",
        operator_soul_text="Run Alice's accepted repository workflow.",
        clock=lambda: NOW,
    )
    daemon = select_project_loop_daemon(
        tmp_path,
        universe_id=definition.universe_id,
        owner_user_id=definition.principal_id,
    )
    assert daemon is not None
    runtime = ensure_daemon_runtime(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id=definition.universe_id,
        provider_name="claude",
        model_name="claude-fable-5",
        created_by="cloud-worker",
        worker_id="worker_claude_1",
    )

    with pytest.raises(
        CloudContinuationActivationError,
        match="executor_audience_unavailable",
    ):
        activate_one_requested_cloud_automation(
            tmp_path,
            universe_id=definition.universe_id,
            principal_id=definition.principal_id,
            audience=BackgroundBranchExecutorAudience(
                executor_class=BackgroundBranchExecutorClass.CLOUD,
                daemon_id=daemon["daemon_id"],
                runtime_id=runtime["runtime_instance_id"],
                worker_id="worker_claude_1",
            ),
            clock=lambda: NOW,
        )
    activation = AutomationActivationStore(tmp_path).get(
        definition.universe_id,
        "automation_spec_drain",
    )
    assert activation is not None and activation.state.value == "stopped"


def test_provider_drift_between_precheck_and_activation_leaves_no_orphan(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.background_branch_authority import (
        BackgroundBranchExecutorAudience,
        BackgroundBranchExecutorClass,
    )
    from tinyassets.cloud_automation_continuation import CloudContinuationActivationError
    from tinyassets.cloud_automation_runtime import (
        activate_one_requested_cloud_automation,
    )
    from tinyassets.cloud_automation_setup import prepare_cloud_automation
    from tinyassets.daemon_registry import (
        ensure_daemon_runtime,
        select_project_loop_daemon,
    )
    from tinyassets.storage.automation_activations import AutomationActivationStore
    from tinyassets.storage.request_admissions import RequestAdmissionStore

    definition = _seed_setup_authority(tmp_path)
    prepare_cloud_automation(
        tmp_path,
        definition,
        automation_id="automation_spec_drain",
        cadence_seconds=300,
        operator_display_name="Alice Cloud Builder",
        operator_soul_text="Run Alice's accepted repository workflow.",
        clock=lambda: NOW,
    )
    daemon = select_project_loop_daemon(
        tmp_path,
        universe_id=definition.universe_id,
        owner_user_id=definition.principal_id,
    )
    assert daemon is not None
    runtime = ensure_daemon_runtime(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id=definition.universe_id,
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-worker",
        worker_id="worker_codex_1",
    )
    audience = BackgroundBranchExecutorAudience(
        executor_class=BackgroundBranchExecutorClass.CLOUD,
        daemon_id=daemon["daemon_id"],
        runtime_id=runtime["runtime_instance_id"],
        worker_id="worker_codex_1",
    )

    from tinyassets import cloud_automation_runtime

    original_resolve = cloud_automation_runtime._ExactAudienceResolver.resolve
    drifted = False

    def drift_after_precheck(resolver, *, continuation, branch_task_id):
        nonlocal drifted
        resolved = original_resolve(
            resolver,
            continuation=continuation,
            branch_task_id=branch_task_id,
        )
        if resolved is not None and branch_task_id == "pre_activation_provider_fence":
            with RequestAdmissionStore(tmp_path).connection() as conn:
                conn.execute(
                    "UPDATE author_runtime_instances SET provider_name = 'claude' "
                    "WHERE instance_id = ?",
                    (audience.runtime_id,),
                )
                conn.commit()
            drifted = True
        return resolved

    monkeypatch.setattr(
        cloud_automation_runtime._ExactAudienceResolver,
        "resolve",
        drift_after_precheck,
    )
    with pytest.raises(
        CloudContinuationActivationError,
        match="executor_audience_unavailable",
    ):
        activate_one_requested_cloud_automation(
            tmp_path,
            universe_id=definition.universe_id,
            principal_id=definition.principal_id,
            audience=audience,
            clock=lambda: NOW,
        )
    assert drifted is True
    activation = AutomationActivationStore(tmp_path).get(
        definition.universe_id,
        "automation_spec_drain",
    )
    assert activation is not None and activation.state.value == "stopped"
    with RequestAdmissionStore(tmp_path).connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM request_admissions").fetchone()[0] == 0
        assert conn.execute("SELECT COUNT(*) FROM branch_tasks_v2").fetchone()[0] == 0


def test_phone_create_derives_internal_definition_from_human_inputs(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions

    seeded = _seed_setup_authority(tmp_path)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    result = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="my-repository-loop",
        payload={
            "definition": {
                "repository": seeded.repository,
                "accepted_spec_ref": seeded.accepted_spec_ref,
                "branch_version_id": seeded.branch_version_id,
            },
            "accepted_spec_content": ACCEPTED_SPEC_CONTENT,
            "cadence_seconds": 300,
            "operator": {"soul_text": "Run my accepted repository workflow."},
        },
    )

    assert result["status"] == "activation_requested"
    assert result["definition"]["branch_def_id"] == seeded.branch_def_id
    assert result["definition"]["branch_content_digest"] == (
        seeded.branch_content_digest
    )
    assert result["definition"]["accepted_spec_digest"] == (
        seeded.accepted_spec_digest
    )
    assert result["definition"]["input_artifact_digests"] == list(
        seeded.input_artifact_digests
    )
    assert result["definition"]["acceptance_scenario_id"] == (
        "scenario:repo-spec-baseline-v1"
    )


def test_phone_create_rejects_missing_content_and_internal_authority_inputs(
    tmp_path,
    monkeypatch,
) -> None:
    from tinyassets.api import cloud_automations, permissions

    seeded = _seed_setup_authority(tmp_path)
    monkeypatch.setattr(cloud_automations, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(permissions, "is_authenticated_request", lambda: True)
    monkeypatch.setattr(permissions, "current_actor_id", lambda: "acct_alice")
    monkeypatch.setattr(permissions, "universe_access_allows", lambda _uid, write: True)

    missing_content = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="missing-content",
        payload={
            "definition": {
                "repository": seeded.repository,
                "accepted_spec_ref": seeded.accepted_spec_ref,
                "accepted_spec_digest": seeded.accepted_spec_digest,
                "branch_version_id": seeded.branch_version_id,
            },
            "cadence_seconds": 300,
            "operator": {"soul_text": "Run my accepted repository workflow."},
        },
    )
    asserted_authority = cloud_automations.cloud_automations(
        action="create",
        universe_id="universe_alice",
        automation_id="asserted-authority",
        payload={
            "definition": {
                "repository": seeded.repository,
                "accepted_spec_ref": seeded.accepted_spec_ref,
                "branch_version_id": seeded.branch_version_id,
                "provider_binding_id": "pwb_00000000000000000000000000000000",
                "destination_grant_id": "destination_grant_not_selected",
            },
            "accepted_spec_content": ACCEPTED_SPEC_CONTENT,
            "cadence_seconds": 300,
            "operator": {"soul_text": "Run my accepted repository workflow."},
        },
    )

    assert missing_content["error"] == "automation_setup_invalid"
    assert "accepted_spec_content is required" in missing_content["detail"]
    assert asserted_authority["error"] == "automation_setup_invalid"
    assert "provider binding id assertion" in asserted_authority["detail"]

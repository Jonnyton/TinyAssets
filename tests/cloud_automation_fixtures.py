"""Fixtures for the fleet-era cloud-automation layer, kept from the deleted
``test_cloud_automation_api.py`` (its API is gone) while the legacy consumer
pump it seeds still runs. They go with that pump (plan Tier C1).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
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

#: Anchored to the real clock, deliberately NOT a fixed literal.
#:
#: `prepare_cloud_automation` derives the background Branch binding's
#: `expires_at` from the injected clock as `now + max(86_400, ...)`, but the
#: `cloud_automations` rebind path validates that expiry against the REAL clock
#: — it accepts no clock parameter, so there is nothing to inject. A hardcoded
#: NOW therefore arms a 24-hour fuse: `expires_at` is the only one of the
#: binding guard's eleven conditions that depends on wall-clock time, and it
#: flips to False exactly one day after the literal. The suite then goes red
#: with no commit touching it, which is how `main` broke on 2026-08-04 23:00Z.
#:
#: Nothing here asserts a literal date; NOW is only ever a relative anchor.
NOW = datetime.now(timezone.utc).replace(microsecond=0)

#: Provider-grant expiry, expressed RELATIVE to NOW instead of as a literal.
#:
#: A literal here is a SECOND fuse, distinct from the binding one above and not
#: fixed by anchoring NOW: `resolve_inactive_cloud_authority` refuses a provider
#: grant whose `expires_at` has passed, also measured against the real clock. So
#: the hardcoded 2026-08-30 would have gone red on 2026-08-30 with
#: `provider_binding_unavailable` — trading a fuse that had already blown for
#: one 25 days out. Found by cross-family review of the first fix, which
#: reproduced it by running the test with NOW moved to 2026-09-01.
#:
#: The offset preserves the original literals' relationship: the old grant
#: expiry sat ~26 days after the old NOW.
GRANT_EXPIRES_AT = (NOW + timedelta(days=26)).strftime("%Y-%m-%dT%H:%M:%SZ")
ACCEPTED_SPEC_CONTENT = "# Accepted repository specification\n"


pytestmark = pytest.mark.usefixtures("cloud_runtime")


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
            expires_at=GRANT_EXPIRES_AT,
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

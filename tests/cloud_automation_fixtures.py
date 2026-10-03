"""Fixtures for the fleet-era cloud-automation layer, kept from the deleted
``test_cloud_automation_api.py`` (its API is gone) while the legacy consumer
pump it seeds still runs. They go with that pump (plan Tier C1).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tinyassets.evaluation.scenario_runner import AcceptanceScenario
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

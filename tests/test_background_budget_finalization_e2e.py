"""END-TO-END finalization proof for the background budget path (Codex REJECT #2, #2528).

This is the test the consumer's budget keystone has been missing: it seeds EVERY store
the background path reads through its REAL public API (no SimpleNamespace stubs, no
in-memory hand-DDL), drives one background call through the REAL ProviderRouter, and
asserts the router reserved-before-launch and FINALIZED the call's actual usage into
``served_provider_budget_reservations`` for the background attempt — so the consumer's
rolling cap charges what was truly spent.

Why every store must be real: ``reserve_served_provider_budget`` validates the served
assignment + provider-work binding + credential custody, and the consumer's
``_authorize_launch`` validates the admitted task + activation + background
binding/attempt/owner fences with matching digests and generations. A stub for ANY
of them either short-circuits the gate (false assurance) or dies before reservation
(what happened to the previous integration test: ``_ProviderStore has no connection``).

Seeding recipe (each step is the same public call a real universe makes):

  served side   — tests/test_provider_served_router.py::_served_context:
                  write_credential_vault(codex llm_subscription) -> publish_definition
                  -> create_binding -> bind_serving_provider(provider="codex")
                  -> set_serving(enabled=True)      ==> assignment.state == "ready",
                  one status=="serving" agent binding, custody row.
  task side     — tinyassets/storage/request_admissions.py DDL: one request_admissions
                  row (grant_generation, body_digest), one branch_tasks_v2 row claimed
                  by the consumer (claimed_by == lease.consumer_id, live
                  lease_expires_at), one automation_activations row (active, epoch,
                  subject digest, immutable branch version) — all under db_path(base).
  background    — tests/test_background_branch_authority_store.py::_binding/_attempt/
  authority       _owner shapes: SQLiteBackgroundBranchAuthorityStore(base)
                  .transaction(): insert_binding + insert_attempt; store.insert_owner
                  (QUEUE_TASK owner, owner_id == branch_task_id, ACTIVE, fenced to the
                  exact binding + attempt). attempt.logical_attempt_key MUST equal
                  build_request_task_attempt_key(tenant_id=owner, request_id,
                  admission_id, task_id, body_digest, admission_generation).
  provider-work — issued by the consumer itself (_current_background_binding ->
  binding         ProviderWorkBindingService.issue) on first launch; needs no seed.
  roles         — _branch_roles reads branch_versions; it is a pure roles lookup
                  unrelated to budget, so it is the ONE thing legitimately stubbed.

Kept as a strict xfail until the seeding below is wired: it must fail at the seam
named in `reason`, never pass vacuously. Flip strict xfail -> real pass only when
the final assertions hold against the real router.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.xfail(
    strict=True,
    reason=(
        "SEEDING NOT YET WIRED: the real-store recipe in this module's docstring is "
        "encoded step by step below but the task/background-authority seeding still "
        "raises before reserve_served_provider_budget is reached. When wired, the "
        "assertions prove REJECT #2 (router finalizes actual usage for a "
        "budget_owner='background_attempt' call). strict=True: an accidental pass "
        "is a bug in the test, not a proof."
    ),
)


def _seed_served_side(base: Path, universe_id: str, owner: str) -> dict:
    """Real served assignment + custody, via the exact public calls a universe makes."""
    from tinyassets.credential_vault import write_credential_vault
    from tinyassets.custom_agents import create_binding, publish_definition
    from tinyassets.provider_serving_binding import bind_serving_provider, set_serving

    universe_dir = base / universe_id
    universe_dir.mkdir(parents=True, exist_ok=True)
    write_credential_vault(
        universe_dir,
        [{"credential_type": "llm_subscription", "service": "codex", "auth_json_b64": "e30="}],
        owner_user_id=owner,
        universe_id=universe_id,
    )
    definition = publish_definition(
        base,
        author_id=owner,
        payload={
            "schema_version": 1,
            "name": "Served",
            "description": "budget e2e fixture",
            "tags": ["test"],
            "components": {"identity": {"kind": "soul", "config": {}}},
        },
    )
    agent = create_binding(
        base,
        universe_id=universe_id,
        definition_id=definition["agent_definition_id"],
        created_by=owner,
        payload={
            "schema_version": 1,
            "name": "served binding",
            "role": "operator",
            "goals": [],
            "components": {},
        },
    )
    connected = bind_serving_provider(
        base_path=base,
        universe_dir=universe_dir,
        owner_user_id=owner,
        universe_id=universe_id,
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=1,
        provider="codex",
    )
    serving = set_serving(
        base_path=base,
        universe_dir=universe_dir,
        owner_user_id=owner,
        universe_id=universe_id,
        agent_binding_id=agent["agent_binding_id"],
        expected_revision=connected["agent_binding"]["revision"],
        enabled=True,
    )["agent_binding"]
    return {"universe_dir": universe_dir, "serving": serving}


def _seed_task_side(base: Path, universe_id: str, owner: str, consumer_id: str) -> dict:
    """One admitted, claimed, activated Epoch-2 task under the REAL request-admission
    schema (db_path(base)) — the rows the consumer's _authorize_launch re-reads."""
    from tinyassets.storage.request_admissions import RequestAdmissionStore

    task_id = "bt2_" + "a" * 32
    admission_id = "adm_" + "b" * 32
    request_id = "req_" + "c" * 32
    body_digest = "sha256:" + "e" * 64
    subject_digest = "sha256:" + "d" * 64
    store = RequestAdmissionStore(base)
    with store.connection() as conn:
        # TODO(lane): insert via the store's own writer methods once identified
        # (RequestAdmissionStore.admit / branch_tasks_v2 claim path) rather than raw
        # SQL, so column semantics (queue_epoch, protocol_version, trigger_source,
        # priority_policy_version, state) are set exactly as production sets them.
        conn.execute(
            "INSERT INTO request_admissions (admission_id, request_id, branch_task_id, "
            "tenant_id, actor_id, universe_id, idempotency_key_hash, body_digest, "
            "body_digest_version, trigger_source, accepted_priority_weight, "
            "priority_policy_version, grant_generation, state, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (admission_id, request_id, task_id, owner, owner, universe_id, "k" * 64,
             body_digest, 1, "user_request", 50, 1, 3, "admitted",
             "2099-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO branch_tasks_v2 (branch_task_id, admission_id, request_id, "
            "universe_id, branch_def_id, inputs_json, trigger_source, priority_weight, "
            "automation_id, automation_activation_epoch, automation_executor_class, "
            "automation_subject_kind, automation_subject_ref, automation_subject_digest, "
            "automation_branch_version, automation_lease_id, status, queue_epoch, "
            "protocol_version, claimed_by, queued_at, claimed_at, heartbeat_at, "
            "lease_expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (task_id, admission_id, request_id, universe_id, "branch-a", "{}",
             "user_request", 50, "automation-a", 7, "cloud", "branch_version",
             "branch-version-a", subject_digest, "branch-version-a", "activation-lease-a",
             "running", 2, 1, consumer_id, "2099-01-01T00:00:00+00:00",
             "2099-01-01T00:00:00+00:00", "2099-01-01T00:00:00+00:00",
             "2099-01-01T01:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO automation_activations (universe_id, automation_id, epoch, "
            "executor_class, subject_kind, subject_ref, subject_digest, "
            "immutable_branch_version, lease_id, state, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (universe_id, "automation-a", 7, "cloud", "branch_version",
             "branch-version-a", subject_digest, "branch-version-a", "activation-lease-a",
             "active", "2099-01-01T00:00:00+00:00"),
        )
        conn.commit()
    return {
        "task_id": task_id, "admission_id": admission_id, "request_id": request_id,
        "body_digest": body_digest, "subject_digest": subject_digest,
        "admission_generation": 3,
    }


def _seed_background_authority(base: Path, universe_id: str, owner: str, task: dict) -> None:
    """Background binding + attempt + QUEUE_TASK owner, fenced to each other, keyed by the
    SAME logical attempt key the consumer computes."""
    from tinyassets.background_branch_authority import (
        BackgroundBranchAttempt,
        BackgroundBranchBinding,
        build_request_task_attempt_key,
    )
    from tinyassets.background_branch_authority_service import (
        BackgroundBranchAttemptFence,
        BackgroundBranchAuthorityOwnerKind,
        BackgroundBranchAuthorityOwnerRecord,
        BackgroundBranchAuthorityOwnerState,
        BackgroundBranchBindingFence,
    )
    from tinyassets.storage.background_branch_authority import (
        SQLiteBackgroundBranchAuthorityStore,
    )

    logical_key = build_request_task_attempt_key(
        tenant_id=owner,
        request_id=task["request_id"],
        admission_id=task["admission_id"],
        task_id=task["task_id"],
        body_digest=task["body_digest"],
        admission_generation=task["admission_generation"],
    )
    binding = BackgroundBranchBinding.from_dict({
        "schema_version": 1, "binding_id": "background-binding-a", "status": "active",
        "generation": 5, "binding_digest": "sha256:" + "2" * 64,
        "authorizing_principal_id": owner, "universe_id": universe_id,
        "branch_def_id": "branch-a", "operation": "invoke_branch_version",
        "source_kind": "request_admission", "source_id": task["request_id"],
        "source_revision": "3", "source_digest": task["body_digest"],
        "revocation_generation": 0, "target_mode": "pinned_version",
        "pinned_branch_version_id": "branch-version-a",
        "permitted_executor_classes": ["cloud"], "daemon_id": None, "runtime_id": None,
        "expires_at": "2099-01-01T02:00:00Z", "max_attempts": 2, "remaining_depth": 0,
        "remaining_count": 2, "remaining_cost_microunits": 10_000,
        "child_delegation": {"allowed_branch_def_ids": [], "allowed_operations": [],
                             "max_depth": 0, "max_count": 0, "max_cost_microunits": 0},
    })
    attempt = BackgroundBranchAttempt.from_dict({
        "schema_version": 1, "attempt_id": "attempt-a", "logical_attempt_key": logical_key,
        "binding_id": binding.binding_id, "binding_digest": binding.binding_digest,
        "binding_generation": binding.generation, "authorizing_principal_id": owner,
        "universe_id": universe_id, "branch_def_id": "branch-a",
        "branch_version_id": "branch-version-a",
        "branch_content_digest": task["subject_digest"],
        "operation": "invoke_branch_version", "source_kind": "request_admission",
        "source_id": task["request_id"], "source_generation": 3,
        "executor_audience": {"executor_class": "cloud", "daemon_id": None,
                              "runtime_id": "runtime-a", "worker_id": "worker-a"},
        "claim_generation": 1, "lease_generation": 1,
        "lease_expires_at": "2099-01-01T02:00:00Z", "remaining_depth": 0,
        "remaining_count": 2, "remaining_cost_microunits": 10_000,
        "lifecycle": "claimed", "hold_reason": None, "terminal_reason": None,
        "created_at": "2099-01-01T00:00:00Z", "updated_at": "2099-01-01T00:00:00Z",
        "provenance": {"authorizing_principal_id": owner,
                       "source_kind": "request_admission", "source_id": task["request_id"],
                       "executor_class": "cloud", "daemon_id": None,
                       "runtime_id": "runtime-a", "worker_id": "worker-a",
                       "parent_attempt_id": None, "origin_attempt_id": "attempt-a",
                       "audit_correlation_ids": [], "receipt_refs": {
                           "b2_execution_grant_id": None, "provider_work_receipt_id": None,
                           "provider_attempt_receipt_id": None, "payment_receipt_id": None,
                           "effect_receipt_id": None}},
    })
    store = SQLiteBackgroundBranchAuthorityStore(base)
    with store.transaction() as tx:
        tx.insert_binding(binding)
        tx.insert_attempt(attempt)
    store.insert_owner(BackgroundBranchAuthorityOwnerRecord(
        owner_kind=BackgroundBranchAuthorityOwnerKind.QUEUE_TASK,
        owner_id=task["task_id"], universe_id=universe_id,
        authorizing_principal_id=owner, source_generation=3, transition_generation=1,
        state=BackgroundBranchAuthorityOwnerState.ACTIVE,
        binding=BackgroundBranchBindingFence(binding),
        attempt=BackgroundBranchAttemptFence(attempt),
        hold_reason=None, updated_at="2099-01-01T00:00:00Z",
    ))


def test_background_call_reserves_and_finalizes_actual_usage_end_to_end(
    tmp_path: Path, monkeypatch
) -> None:
    import asyncio
    import sqlite3

    import tinyassets.background_served_provider as background_provider
    from tinyassets.branch_tasks_v2 import AssignedConsumerLease, Epoch2BranchTask
    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
    from tinyassets.providers.router import ProviderRouter
    from tinyassets.storage import db_path

    base, universe_id, owner = tmp_path, "u-e2e", "owner-e2e"
    # The REAL boot-time bring-up: creates every table + runs migrations once,
    # exactly as the daemon does at start — no table-by-table hand DDL.
    initialize_author_server(base)
    lease = AssignedConsumerLease(
        consumer_id="assigned-consumer:e2e", lease_id="assigned-lease:e2e",
        expires_at="2099-01-01T01:00:00+00:00",
    )
    _seed_served_side(base, universe_id, owner)
    task = _seed_task_side(base, universe_id, owner, lease.consumer_id)
    _seed_background_authority(base, universe_id, owner, task)
    # The ONE legitimate stub: roles come from branch_versions (unrelated to budget).
    monkeypatch.setattr(background_provider, "_branch_roles", lambda *_a: ("writer",))

    claimed = Epoch2BranchTask(
        branch_task_id=task["task_id"], admission_id=task["admission_id"],
        request_id=task["request_id"], branch_def_id="branch-a", universe_id=universe_id,
        actor_id=owner, automation_id="automation-a", automation_activation_epoch=7,
        automation_executor_class="cloud", automation_subject_ref="branch-version-a",
        automation_subject_digest=task["subject_digest"],
        automation_branch_version="branch-version-a",
        automation_lease_id="activation-lease-a", status="running",
        claimed_by=lease.consumer_id, claimed_at="2099-01-01T00:00:00+00:00",
        lease_expires_at="2099-01-01T01:00:00+00:00",
    )

    class _CountingProvider(BaseProvider):
        def __init__(self) -> None:
            self.name = "codex"
            self.family = "codex"
            self.calls = 0

        async def complete(self, prompt, system, config: ModelConfig, *, universe_dir=None):
            self.calls += 1
            return ProviderResponse(
                text="routed-ok", provider="codex", model="fake", family="codex",
                latency_ms=0.0, input_tokens=700, output_tokens=300, cost_microunits=50,
            )

    fake = _CountingProvider()
    router = ProviderRouter({"codex": fake})

    def through_real_router(prompt, system, *, role, config, **kwargs):
        return asyncio.run(router.call(
            role, prompt, system, operation=kwargs["operation"],
            universe_context=kwargs["universe_context"],
        )).text

    session = background_provider._BackgroundAssignedProviderSession(
        base, claimed, lease, through_real_router
    )
    assert session("first") == "routed-ok"
    assert fake.calls == 1  # REJECT #1: the real background path launched.

    conn = sqlite3.connect(db_path(base))
    conn.row_factory = sqlite3.Row
    served_rows = conn.execute(
        "SELECT state, actual_total_tokens, actual_cost_microunits "
        "FROM served_provider_budget_reservations"
    ).fetchall()
    # REJECT #2: the router reserved AND finalized REAL usage for the background attempt.
    assert len(served_rows) == 1, [dict(r) for r in served_rows]
    assert served_rows[0]["actual_total_tokens"] == 1000
    assert served_rows[0]["actual_cost_microunits"] == 50
    assert served_rows[0]["state"] != "reserved"
    own = [r["state"] for r in conn.execute(
        "SELECT state FROM assigned_queue_provider_reservations"
    )]
    assert own == ["settled"]

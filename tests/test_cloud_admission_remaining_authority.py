"""Negatives for the three authority sites task 8/9 left ungated.

Each test drives the real caller under an **injected** process observation —
never an environment variable, never a network read — and asserts the guarded
path refuses. The provider negative spies the provider invocation itself rather
than the returned text, because a refusal that still called the model is not a
refusal.

Admission is never inherited here. Every test installs its own observation
through the module-local `admitted_runtime` fixture or `_install_observation`,
so no suite-wide admitted default can make a negative vacuous. Nothing in
this module is autouse.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tinyassets import daemon_registry
from tinyassets import platform_runtime_provenance as provenance
from tinyassets.branch_tasks_v2 import Epoch2BranchTaskAdapter, WorkerClaimDescriptor
from tinyassets.daemon_registry import (
    create_daemon,
    ensure_daemon_runtime,
    set_worker_queue_descriptor,
)
from tinyassets.daemon_server import initialize_author_server
from tinyassets.storage.automation_activations import AutomationActivationExecutor


def _install_observation(monkeypatch, verdict: str | None) -> None:
    """Inject the process-owned observation. `None` = never observed."""
    observation = provenance.ProcessProvenanceObservation(
        resolver=lambda: provenance.RuntimeProvenance(
            verdict or provenance.NOT_CLOUD, "instance_mismatch", True, True
        )
    )
    if verdict is not None:
        observation.observe()
    monkeypatch.setattr(provenance, "_PROCESS_OBSERVATION", observation)


@pytest.fixture
def admitted_runtime(monkeypatch):
    """An admitted cloud process, injected — the baseline every control needs."""
    _install_observation(monkeypatch, provenance.CLOUD)


@pytest.fixture
def refused_runtime(monkeypatch):
    """A process that looked and is NOT cloud."""
    _install_observation(monkeypatch, provenance.NOT_CLOUD)


@pytest.fixture
def unobserved_runtime(monkeypatch):
    """A process that never looked. `peek()` is None; that is not cloud."""
    _install_observation(monkeypatch, None)


# --- Site 1 (the agent runtime's provider execution) was retired with that
# runtime; its admission gate had no other caller.


# --- Site 2: worker queue descriptor publication/refresh -------------------


def _seed_admitted_worker(base_path: Path) -> dict:
    daemon = create_daemon(
        base_path,
        display_name="Descriptor Runner",
        created_by="owner-a",
        soul_text="Run the owner's versioned Branch composition.",
    )
    return ensure_daemon_runtime(
        base_path,
        daemon_id=daemon["daemon_id"],
        universe_id="universe-a",
        provider_name="codex",
        model_name="gpt-5",
        created_by="cloud-worker",
        worker_id="worker-a",
        metadata={"automation_executor_class": "cloud"},
    )


def _descriptor(runtime: dict, *, seconds: int = 75, boot_id: str = "boot-a") -> dict:
    return {
        "queue_protocol_version": 2,
        "capabilities": ["operator_request_v1"],
        "worker_id": "worker-a",
        "runtime_instance_id": runtime["runtime_instance_id"],
        "boot_id": boot_id,
        "build_sha": "a" * 40,
        "config_hash": "sha256:" + ("b" * 64),
        "universe_id": "universe-a",
        "expires_at": (
            datetime.now(timezone.utc) + timedelta(seconds=seconds)
        ).isoformat(),
    }


@pytest.mark.parametrize("observation", ["refused", "unobserved"])
def test_unadmitted_process_cannot_renew_a_cloud_descriptor(
    tmp_path, monkeypatch, admitted_runtime, observation
) -> None:
    """Row-mint is admitted; row-REFRESH must be too, or the window is renewable."""
    initialize_author_server(tmp_path)
    runtime = _seed_admitted_worker(tmp_path)
    runtime_id = runtime["runtime_instance_id"]
    set_worker_queue_descriptor(
        tmp_path,
        runtime_instance_id=runtime_id,
        descriptor=_descriptor(runtime),
        expected_worker_id="worker-a",
    )
    before = daemon_registry.daemon_server.get_runtime_instance(
        tmp_path, instance_id=runtime_id
    )
    before_descriptor = dict(
        before["metadata"]["queue_protocol_descriptor"]
    )

    _install_observation(
        monkeypatch, provenance.NOT_CLOUD if observation == "refused" else None
    )

    with pytest.raises(PermissionError) as refusal:
        set_worker_queue_descriptor(
            tmp_path,
            runtime_instance_id=runtime_id,
            descriptor=_descriptor(runtime, seconds=900, boot_id="boot-hijack"),
            expected_worker_id="worker-a",
        )
    assert provenance.PLATFORM_NOT_CLOUD_REASON in str(refusal.value)

    after = daemon_registry.daemon_server.get_runtime_instance(
        tmp_path, instance_id=runtime_id
    )
    # The expiry window is exactly what an unadmitted renewal would extend.
    assert after["metadata"]["queue_protocol_descriptor"] == before_descriptor


@pytest.mark.parametrize("observation", ["refused", "unobserved"])
def test_unchanged_descriptor_fast_return_is_also_gated(
    tmp_path, monkeypatch, admitted_runtime, observation
) -> None:
    """The no-op equality return is still an authority-bearing refresh path.

    Left ungated it would report success to an unadmitted caller, which is a
    liveness assertion about a runtime that process has no authority over.
    """
    initialize_author_server(tmp_path)
    runtime = _seed_admitted_worker(tmp_path)
    runtime_id = runtime["runtime_instance_id"]
    descriptor = _descriptor(runtime)
    set_worker_queue_descriptor(
        tmp_path,
        runtime_instance_id=runtime_id,
        descriptor=descriptor,
        expected_worker_id="worker-a",
    )

    _install_observation(
        monkeypatch, provenance.NOT_CLOUD if observation == "refused" else None
    )

    with pytest.raises(PermissionError):
        set_worker_queue_descriptor(
            tmp_path,
            runtime_instance_id=runtime_id,
            descriptor=dict(descriptor),
            expected_worker_id="worker-a",
        )


def test_clearing_a_descriptor_stays_allowed_for_shutdown_cleanup(
    tmp_path, monkeypatch, admitted_runtime
) -> None:
    """Revocation direction-check: clearing REMOVES authority, so it is not gated.

    A process that has lost admission must still be able to withdraw its own
    claim; refusing the clear would strand a live-looking descriptor for the
    remainder of its validity window — the opposite of the invariant.
    """
    initialize_author_server(tmp_path)
    runtime = _seed_admitted_worker(tmp_path)
    runtime_id = runtime["runtime_instance_id"]
    set_worker_queue_descriptor(
        tmp_path,
        runtime_instance_id=runtime_id,
        descriptor=_descriptor(runtime),
        expected_worker_id="worker-a",
    )

    _install_observation(monkeypatch, provenance.NOT_CLOUD)

    cleared = set_worker_queue_descriptor(
        tmp_path,
        runtime_instance_id=runtime_id,
        descriptor=None,
        expected_worker_id="worker-a",
    )
    assert cleared["metadata"]["queue_protocol_descriptor"] is None


# --- Site 3: Epoch2 cloud-activation claim ---------------------------------


def _activation_descriptor(
    executor_class: AutomationActivationExecutor,
    *,
    worker_id: str = "worker-a",
) -> WorkerClaimDescriptor:
    return WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id=worker_id,
        runtime_instance_id=f"runtime::{worker_id}",
        boot_id=f"boot::{worker_id}",
        build_sha="a" * 40,
        config_hash="sha256:" + ("b" * 64),
        universe_id="universe-a",
        expires_at=(
            datetime.now(timezone.utc) + timedelta(seconds=75)
        ).isoformat(),
        executor_class=executor_class,
    )


def _active_tray_automation(base_path: Path, *, automation_id: str):
    """A TRAY-class activation. The non-cloud arm this change must not touch."""
    from tests.test_fantasy_daemon_epoch2_dispatch import _activation_subject
    from tinyassets.storage.automation_activations import AutomationActivationStore

    activations = AutomationActivationStore(base_path)
    stopped = activations.create_stopped(
        universe_id="universe-a",
        automation_id=automation_id,
    )
    active = activations.activate(
        expected=stopped,
        executor_class=AutomationActivationExecutor.TRAY,
        subject=_activation_subject(f"branch-version-{automation_id}"),
        lease_id=f"tray-lease-{automation_id}",
    )
    assert active is not None
    return active


@pytest.mark.parametrize("observation", ["refused", "unobserved"])
def test_cloud_class_claim_refuses_under_unadmitted_process(
    tmp_path, monkeypatch, admitted_runtime, observation
) -> None:
    """A live persisted cloud descriptor is a record, never permission.

    Deliberately passes **no** optional callback — the only escape hatch — so
    the refusal has to come from the non-optional cloud-activation predicate.
    """
    from tests.test_fantasy_daemon_epoch2_dispatch import (
        _active_cloud_automation,
        _commit_epoch2,
    )

    initialize_author_server(tmp_path)
    active = _active_cloud_automation(tmp_path)
    committed = _commit_epoch2(
        tmp_path,
        key="unadmitted-cloud-claim",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )
    live = WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id="worker-a",
        runtime_instance_id="runtime::worker-a",
        boot_id="boot::worker-a",
        build_sha="a" * 40,
        config_hash="sha256:" + ("b" * 64),
        universe_id="universe-a",
        expires_at=(
            datetime.now(timezone.utc) + timedelta(seconds=75)
        ).isoformat(),
        executor_class=AutomationActivationExecutor.CLOUD,
    )
    adapter = Epoch2BranchTaskAdapter(tmp_path)

    _install_observation(
        monkeypatch, provenance.NOT_CLOUD if observation == "refused" else None
    )

    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=live,
        descriptor_reader=lambda _conn, _worker: live,
    )

    assert claimed is None
    assert adapter.get(committed["branch_task_id"]).status == "pending"


def test_admitted_cloud_class_claim_is_preserved(tmp_path, admitted_runtime) -> None:
    """Positive control: the same request succeeds on an admitted process."""
    from tests.test_fantasy_daemon_epoch2_dispatch import (
        _active_cloud_automation,
        _commit_epoch2,
    )

    initialize_author_server(tmp_path)
    active = _active_cloud_automation(tmp_path)
    committed = _commit_epoch2(
        tmp_path,
        key="admitted-cloud-claim",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )
    live = WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id="worker-a",
        runtime_instance_id="runtime::worker-a",
        boot_id="boot::worker-a",
        build_sha="a" * 40,
        config_hash="sha256:" + ("b" * 64),
        universe_id="universe-a",
        expires_at=(
            datetime.now(timezone.utc) + timedelta(seconds=75)
        ).isoformat(),
        executor_class=AutomationActivationExecutor.CLOUD,
    )
    adapter = Epoch2BranchTaskAdapter(tmp_path)

    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=live,
        descriptor_reader=lambda _conn, _worker: live,
    )

    assert claimed is not None
    assert adapter.get(committed["branch_task_id"]).status == "running"


def test_non_cloud_generic_claim_is_unaffected_by_admission(
    tmp_path, monkeypatch, admitted_runtime
) -> None:
    """Preserved semantics: a task with no activation fields is not cloud-class.

    The guard belongs to the cloud-activation arm only; widening it to every
    claim would change generic queue behaviour, which this change does not own.
    """
    import rfc8785

    from tinyassets.storage.request_admissions import (
        IDEMPOTENCY_HMAC_ENV,
        RequestAdmissionStore,
        mint_idempotency_key_hash,
    )

    initialize_author_server(tmp_path)
    monkeypatch.setenv(IDEMPOTENCY_HMAC_ENV, "k" * 48)
    body = rfc8785.dumps(
        {
            "branch_id": "",
            "directed_daemon_id": "",
            "directed_daemon_instruction": "",
            "pickup_incentive": "",
            "priority_weight": 50.0,
            "request_type": "general",
            "schema_version": "request-admission-v2",
            "text": "execute one bounded branch slice",
            "universe_id": "universe-a",
        }
    )
    committed = RequestAdmissionStore(tmp_path).commit_admission(
        tenant_id="tenant-a",
        actor_id="actor-a",
        universe_id="universe-a",
        idempotency_key_hash=mint_idempotency_key_hash("generic-claim"),
        body_digest="sha256:" + hashlib.sha256(body).hexdigest(),
        body_digest_version="rfc8785-v1",
        request_type="general",
        text="execute one bounded branch slice",
        branch_id="",
        branch_def_id="ordinary-user-branch",
        trigger_source="operator_request",
        accepted_priority_weight=50.0,
        policy_version="operator-priority-v1",
        grant_generation=3,
        receipt={
            "authority": "request-local",
            "grant_generation": 3,
            "priority_policy_version": "operator-priority-v1",
            "directed_assignment": {},
        },
        directed_daemon_id="",
        created_at=datetime.now(timezone.utc).isoformat(),
        automation_activation=None,
    )
    live = WorkerClaimDescriptor(
        queue_protocol_version=2,
        capabilities=frozenset({"operator_request_v1"}),
        worker_id="worker-a",
        runtime_instance_id="runtime::worker-a",
        boot_id="boot::worker-a",
        build_sha="a" * 40,
        config_hash="sha256:" + ("b" * 64),
        universe_id="universe-a",
        expires_at=(
            datetime.now(timezone.utc) + timedelta(seconds=75)
        ).isoformat(),
        executor_class=None,
    )
    adapter = Epoch2BranchTaskAdapter(tmp_path)

    _install_observation(monkeypatch, provenance.NOT_CLOUD)

    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=live,
        descriptor_reader=lambda _conn, _worker: live,
    )

    assert claimed is not None


@pytest.mark.parametrize("observation", ["refused", "unobserved"])
def test_tray_activation_claim_is_unaffected_by_cloud_admission(
    tmp_path, monkeypatch, admitted_runtime, observation
) -> None:
    """Scope control: the gate is the cloud arm, so TRAY must behave as at base.

    Measured on the read-only base checkout at e389505b (same runtime as
    16e6f0bf): a tray-class task with a matching tray descriptor claims
    successfully on a `not_cloud` process AND on an unobserved one. That is
    otherwise-valid non-cloud activation behaviour, and refusing it would be a
    policy expansion beyond this change. A generic no-activation task exercises
    the earlier `not any(activation_fields)` return, so it cannot stand in for
    this: only a populated non-cloud activation reaches the new predicate.
    """
    from tests.test_fantasy_daemon_epoch2_dispatch import _commit_epoch2

    initialize_author_server(tmp_path)
    active = _active_tray_automation(tmp_path, automation_id="automation-tray")
    committed = _commit_epoch2(
        tmp_path,
        key=f"tray-activation-{observation}",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )
    live = _activation_descriptor(AutomationActivationExecutor.TRAY)
    adapter = Epoch2BranchTaskAdapter(tmp_path)

    _install_observation(
        monkeypatch, provenance.NOT_CLOUD if observation == "refused" else None
    )

    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=live,
        descriptor_reader=lambda _conn, _worker: live,
    )

    assert claimed is not None
    assert adapter.get(committed["branch_task_id"]).status == "running"


def test_cloud_lifecycle_resolves_admission_before_the_write_transaction(
    tmp_path, monkeypatch, admitted_runtime
) -> None:
    """Ordering invariant as an event SEQUENCE, not a call count.

    Two facts have to hold and a count proves neither: the bounded metadata
    read must have *completed* before the store method that opens
    `BEGIN IMMEDIATE` is entered, and the read performed *inside* that
    transaction must be the peek-only cached one. Both the resolver and the
    real store methods are wrapped and delegated to, so the sequence is
    observed on operations that actually reach -- and pass -- the transaction.

    `resume` carries the identical gate (same `_transaction_allows_epoch2_lifecycle`
    predicate, same resolve-before-open ordering), so it is asserted here too.
    """
    from tests.test_fantasy_daemon_epoch2_dispatch import (
        _active_cloud_automation,
        _commit_epoch2,
    )
    from tinyassets import branch_tasks_v2

    initialize_author_server(tmp_path)
    active = _active_cloud_automation(tmp_path)
    committed = _commit_epoch2(
        tmp_path,
        key="ordering-cloud-lifecycle",
        created_at=datetime.now(timezone.utc).isoformat(),
        activation=active,
    )
    live = _activation_descriptor(AutomationActivationExecutor.CLOUD)
    adapter = Epoch2BranchTaskAdapter(tmp_path)

    events: list[str] = []
    real_resolve = branch_tasks_v2.resolve_process_cloud_admission
    real_cached = branch_tasks_v2.cached_process_is_cloud_admitted
    real_claim = adapter._store.claim_v2_task
    real_resume = adapter._store.read_live_v2_task_for_resume

    def tracked_resolve():
        result = real_resolve()
        # Recorded AFTER the real resolver returns. "Before the transaction"
        # has to mean completion, not entry -- an entry marker would still be
        # satisfied by a resolver that blocked until inside the lock.
        events.append("resolve:complete")
        return result

    def tracked_cached():
        events.append("cached_peek")
        return real_cached()

    def _wrap(label, real):
        def tracked(*args, **kwargs):
            events.append(f"{label}:enter")
            try:
                return real(*args, **kwargs)
            finally:
                events.append(f"{label}:exit")

        return tracked

    monkeypatch.setattr(
        branch_tasks_v2, "resolve_process_cloud_admission", tracked_resolve
    )
    monkeypatch.setattr(
        branch_tasks_v2, "cached_process_is_cloud_admitted", tracked_cached
    )
    monkeypatch.setattr(
        adapter._store, "claim_v2_task", _wrap("claim_v2_task", real_claim)
    )
    monkeypatch.setattr(
        adapter._store,
        "read_live_v2_task_for_resume",
        _wrap("read_live_v2_task_for_resume", real_resume),
    )

    claimed = adapter.claim(
        committed["branch_task_id"],
        descriptor=live,
        descriptor_reader=lambda _conn, _worker: live,
    )

    # A refused claim would make the sequence assertion vacuous.
    assert claimed is not None
    assert events == [
        "resolve:complete",
        "claim_v2_task:enter",
        "cached_peek",
        "claim_v2_task:exit",
    ]

    events.clear()
    resumed = adapter.resume(
        committed["branch_task_id"],
        descriptor=live,
        descriptor_reader=lambda _conn, _worker: live,
    )

    assert resumed is not None
    assert events == [
        "resolve:complete",
        "read_live_v2_task_for_resume:enter",
        "cached_peek",
        "read_live_v2_task_for_resume:exit",
    ]

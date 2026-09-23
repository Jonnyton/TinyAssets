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


# --- Site 1: provider-authority executor_class derivation ------------------


class _NeverCalledProvider:
    """Spy standing in for the model: invocation itself is the assertion."""

    name = "codex"
    family = "gpt"

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def complete(self, prompt, system, config, *, universe_dir=None):
        self.calls.append((prompt, system))
        raise AssertionError("provider was invoked under an unadmitted runtime")


def _provider_service(tmp_path, authenticate_request):
    from tests.test_agent_runtime_provider_call import _execution_service

    return _execution_service(tmp_path, authenticate_request)


def _authority_row_counts(service) -> dict[str, int]:
    """Read the provider-authority ledger directly.

    "Nothing was minted" is a claim about rows, so it is answered by counting
    rows rather than by reasoning from where the refusal was raised.
    """
    with service.provider_store.connection() as conn:
        return {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in (
                "provider_work_receipts",
                "provider_work_execution_claims",
                "provider_invocation_reservations",
            )
        }


@pytest.mark.parametrize("observation", ["refused", "unobserved"])
def test_provider_execution_refuses_and_never_invokes_provider(
    tmp_path, authenticate_request, monkeypatch, admitted_runtime, observation
) -> None:
    """Otherwise-ready invocation + unadmitted process => no provider call."""
    from tests.test_agent_runtime_invocation import _request
    from tinyassets.providers.router import ProviderRouter

    # Build the admitted invocation under the admitted observation, so the only
    # difference in the negative is the process verdict at execution time.
    service, admitted, _universe_dir, _manifest = _provider_service(
        tmp_path, authenticate_request
    )
    provider = _NeverCalledProvider()

    _install_observation(
        monkeypatch, provenance.NOT_CLOUD if observation == "refused" else None
    )
    baseline_rows = _authority_row_counts(service)

    refusal: BaseException | None = None
    try:
        service.execute_provider_call(
            admitted.invocation.invocation_id,
            typed_input=_request().typed_input,
            router=ProviderRouter({"codex": provider}),
        )
    except BaseException as exc:  # noqa: BLE001 - the spy raises too; both matter
        refusal = exc

    # The primary assertion is the SPY, not the return value or the text: the
    # service swallows a provider exception into an indeterminate outcome, so
    # "did not raise" alone would under-report an invocation that happened.
    assert provider.calls == []
    # The single stable sanitized token, not a paraphrase.
    #
    # Where the refusal comes from, traced rather than assumed: the authority
    # boundary is NOT reached while resolving call material --
    # `_resolve_provider_call_material` never calls `_validated_authority`. It
    # is reached INSIDE the launch-ownership try block, through
    # `issue_receipt -> _transition -> _validated_authority ->
    # admitted_cloud_executor_class()`, which raises a plain `PermissionError`.
    # That lands in `except PermissionError`, whose handler calls
    # `_current_provider_outcome_after_transition`; that revalidates authority,
    # reaches the same site again and rethrows -- which is why the sanitized
    # token survives instead of being rewritten into the handler's
    # "owned by a concurrent launch" message. The assertion is on the token,
    # not on that path, so an earlier refusal would still satisfy it; the catch
    # is not widened, so a swallowed refusal cannot pass.
    assert isinstance(refusal, PermissionError)
    assert provenance.PLATFORM_NOT_CLOUD_REASON in str(refusal)
    assert not isinstance(refusal, AssertionError)
    # Checked against the ledger, not inferred from where the raise happened:
    # no receipt, execution claim or reservation row was written.
    assert _authority_row_counts(service) == baseline_rows
    assert service.get_provider_outcome(admitted.invocation.invocation_id) is None
    assert service.get_continuation(admitted.invocation.invocation_id) is None


def test_admitted_provider_execution_still_runs(
    tmp_path, authenticate_request, admitted_runtime
) -> None:
    """Preserved behaviour: an admitted process still reaches the provider."""
    from tests.test_agent_runtime_invocation import _request
    from tests.test_agent_runtime_provider_call import _RecordingProvider
    from tinyassets.agent_runtime_provider_execution import AgentProviderOutcomeState
    from tinyassets.providers.router import ProviderRouter

    service, admitted, _universe_dir, _manifest = _provider_service(
        tmp_path, authenticate_request
    )
    provider = _RecordingProvider()

    result = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=ProviderRouter({"codex": provider}),
    )

    assert result.state is AgentProviderOutcomeState.SUCCEEDED
    assert len(provider.calls) == 1


def test_receipt_reuse_path_cannot_launder_an_unadmitted_call(
    tmp_path, authenticate_request, monkeypatch, admitted_runtime
) -> None:
    """The replay short-circuit returns a settled outcome, never a fresh call.

    `execute_provider_call` returns an existing outcome before the authority
    check. That is replay of work already spent under an admitted process — it
    must not invoke the provider a second time under a refused one.
    """
    from tests.test_agent_runtime_invocation import _request
    from tests.test_agent_runtime_provider_call import _RecordingProvider
    from tinyassets.providers.router import ProviderRouter

    service, admitted, _universe_dir, _manifest = _provider_service(
        tmp_path, authenticate_request
    )
    first = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=ProviderRouter({"codex": _RecordingProvider()}),
    )

    _install_observation(monkeypatch, provenance.NOT_CLOUD)
    spy = _NeverCalledProvider()
    replay = service.execute_provider_call(
        admitted.invocation.invocation_id,
        typed_input=_request().typed_input,
        router=ProviderRouter({"codex": spy}),
    )

    assert spy.calls == []
    assert replay.typed_output == first.typed_output


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

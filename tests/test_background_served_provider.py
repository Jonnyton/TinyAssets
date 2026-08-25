from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import tinyassets.background_served_provider as background_provider
from tinyassets.background_branch_authority import BackgroundBranchBindingStatus
from tinyassets.branch_tasks_v2 import AssignedConsumerLease, Epoch2BranchTask
from tinyassets.exceptions import ProviderAuthorityHeldError
from tinyassets.providers.base import UniverseContext


@contextmanager
def _connection(conn: sqlite3.Connection):
    yield conn


class _AdmissionStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def connection(self):
        return _connection(self._conn)


class _AdmissionFence:
    @contextmanager
    def shared(self, _universe_dir: Path):
        yield


def _task() -> Epoch2BranchTask:
    return Epoch2BranchTask(
        branch_task_id="bt2_" + "a" * 32,
        admission_id="adm_" + "b" * 32,
        request_id="req_" + "c" * 32,
        branch_def_id="branch-a",
        universe_id="universe-a",
        actor_id="acct_owner_a",
        automation_id="automation-a",
        automation_activation_epoch=7,
        automation_executor_class="cloud",
        automation_subject_ref="branch-version-a",
        automation_subject_digest="sha256:" + "d" * 64,
        automation_branch_version="branch-version-a",
        automation_lease_id="activation-lease-a",
        status="running",
        claimed_by="assigned-consumer:boot-a",
        claimed_at="2099-01-01T00:00:00+00:00",
        lease_expires_at="2099-01-01T01:00:00+00:00",
    )


def _lease() -> AssignedConsumerLease:
    return AssignedConsumerLease(
        consumer_id="assigned-consumer:boot-a",
        lease_id="assigned-lease:boot-a",
        expires_at="2099-01-01T01:00:00+00:00",
    )


def _authority_fixture(tmp_path: Path, monkeypatch):
    universe_dir = tmp_path / "universe-a"
    universe_dir.mkdir()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE branch_tasks_v2 (
            branch_task_id TEXT PRIMARY KEY, admission_id TEXT, request_id TEXT,
            status TEXT, claimed_by TEXT, claimed_at TEXT, lease_expires_at TEXT,
            universe_id TEXT, automation_id TEXT,
            automation_activation_epoch INTEGER, automation_subject_ref TEXT,
            automation_subject_digest TEXT, automation_branch_version TEXT,
            automation_lease_id TEXT
        );
        CREATE TABLE request_admissions (
            admission_id TEXT, request_id TEXT, branch_task_id TEXT,
            actor_id TEXT, body_digest TEXT, grant_generation INTEGER
        );
        CREATE TABLE automation_activations (
            universe_id TEXT, automation_id TEXT, state TEXT, epoch INTEGER,
            subject_ref TEXT, subject_digest TEXT,
            immutable_branch_version TEXT, lease_id TEXT
        );
        """
    )
    task = _task()
    conn.execute(
        "INSERT INTO branch_tasks_v2 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            task.branch_task_id,
            task.admission_id,
            task.request_id,
            task.status,
            task.claimed_by,
            task.claimed_at,
            task.lease_expires_at,
            task.universe_id,
            task.automation_id,
            task.automation_activation_epoch,
            task.automation_subject_ref,
            task.automation_subject_digest,
            task.automation_branch_version,
            task.automation_lease_id,
        ),
    )
    conn.execute(
        "INSERT INTO request_admissions VALUES (?,?,?,?,?,?)",
        (
            task.admission_id,
            task.request_id,
            task.branch_task_id,
            task.actor_id,
            "sha256:" + "e" * 64,
            3,
        ),
    )
    conn.execute(
        "INSERT INTO automation_activations VALUES (?,?,?,?,?,?,?,?)",
        (
            task.universe_id,
            task.automation_id,
            "active",
            task.automation_activation_epoch,
            task.automation_subject_ref,
            task.automation_subject_digest,
            task.automation_branch_version,
            task.automation_lease_id,
        ),
    )
    conn.commit()

    assignment = SimpleNamespace(
        state="ready",
        owner_user_id="acct_owner_a",
        provider="codex",
        generation=4,
        assignment_digest="sha256:" + "f" * 64,
    )
    serving_binding = SimpleNamespace(expires_at="2099-01-01T02:00:00+00:00")
    custody = SimpleNamespace(
        reference_id="credential-a",
        reference_digest="sha256:" + "1" * 64,
        generation=2,
    )
    attempt = SimpleNamespace(
        attempt_id="attempt-a",
        binding_id="background-binding-a",
        binding_generation=5,
        binding_digest="sha256:" + "2" * 64,
        authorizing_principal_id="acct_owner_a",
        universe_id="universe-a",
        branch_def_id="branch-a",
        branch_version_id="branch-version-a",
        branch_content_digest=task.automation_subject_digest,
        lifecycle=SimpleNamespace(value="claimed"),
        lease_expires_at="2099-01-01T02:00:00+00:00",
        remaining_count=2,
        remaining_cost_microunits=10_000,
    )
    background_binding = SimpleNamespace(
        binding_id=attempt.binding_id,
        generation=attempt.binding_generation,
        binding_digest=attempt.binding_digest,
        status=BackgroundBranchBindingStatus.ACTIVE,
    )
    authority_owner = SimpleNamespace(
        state=SimpleNamespace(value="active"),
        binding=SimpleNamespace(expected_record=background_binding),
        attempt=SimpleNamespace(expected_record=attempt),
    )
    provider_binding = SimpleNamespace(
        binding_id="provider-background-a",
        generation=6,
        binding_digest="sha256:" + "3" * 64,
    )

    class _BackgroundStore:
        def __init__(self, _base_path):
            pass

        @staticmethod
        def read_authority_in_transaction(_conn, *, logical_attempt_key):
            assert logical_attempt_key
            return background_binding, attempt

        @staticmethod
        def read_queue_owner_in_transaction(_conn, *, owner_id):
            assert owner_id == task.branch_task_id
            return authority_owner

    class _ProviderStore:
        def __init__(self, _base_path):
            pass

        def validate_in_transaction(self, _conn, **_kwargs):
            return True

    monkeypatch.setattr(background_provider, "_branch_roles", lambda *_a: ("writer",))
    monkeypatch.setattr(
        background_provider, "provider_assignment_admission", lambda: _AdmissionFence()
    )
    monkeypatch.setattr(
        background_provider,
        "load_provider_assignment_in_transaction",
        lambda *_a, **_k: assignment,
    )
    monkeypatch.setattr(
        background_provider,
        "_current_background_binding",
        lambda *_a, **_k: provider_binding,
    )

    import tinyassets.config as config_module
    import tinyassets.credential_vault as vault_module
    import tinyassets.provider_assignment as assignment_module
    import tinyassets.provider_serving_binding as serving_module
    import tinyassets.storage.background_branch_authority as background_store_module
    import tinyassets.storage.provider_work_authority as provider_store_module
    import tinyassets.storage.request_admissions as admission_store_module

    monkeypatch.setattr(config_module, "load_universe_config", lambda _path: {})
    monkeypatch.setattr(
        assignment_module,
        "load_provider_assignment_in_transaction",
        lambda *_a, **_k: assignment,
    )
    monkeypatch.setattr(
        admission_store_module,
        "RequestAdmissionStore",
        lambda _base_path: _AdmissionStore(conn),
    )
    monkeypatch.setattr(
        provider_store_module,
        "SQLiteProviderWorkAuthorityStore",
        _ProviderStore,
    )
    monkeypatch.setattr(
        background_store_module,
        "SQLiteBackgroundBranchAuthorityStore",
        _BackgroundStore,
    )
    monkeypatch.setattr(
        serving_module,
        "resolve_serving_agent_binding",
        # REAL shape (agent_bindings row): the key is "agent_binding_id". The old
        # stub said "binding_id" and hid a KeyError on every real launch.
        lambda *_a, **_k: {"agent_binding_id": "agent-a", "revision": 2},
    )
    current_assignment = {"value": assignment}
    monkeypatch.setattr(
        serving_module,
        "_current_serving_authority",
        lambda *_a, **_k: (
            current_assignment["value"],
            serving_binding,
            custody,
        ),
    )
    monkeypatch.setattr(serving_module, "_is_open_provider", lambda _provider: False)

    events: list[str] = []
    snapshot = SimpleNamespace(
        generation=custody.generation,
        reference_digest=custody.reference_digest,
        directory=tmp_path / "snapshot-a",
    )
    monkeypatch.setattr(
        vault_module,
        "snapshot_llm_subscription_credential",
        lambda **_kwargs: events.append("snapshot") or snapshot,
    )
    monkeypatch.setattr(
        vault_module,
        "cleanup_llm_credential_snapshot",
        lambda value: events.append("cleanup") if value is snapshot else None,
    )
    monkeypatch.setattr(
        background_provider,
        "_hold_background_authority",
        lambda _base_path, _task: events.append("hold"),
    )
    return task, conn, assignment, current_assignment, events


def _reservation_count(conn: sqlite3.Connection) -> int:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master "
        "WHERE type='table' AND name='assigned_queue_provider_reservations'"
    ).fetchone()
    if row[0] == 0:
        return 0
    return int(
        conn.execute("SELECT COUNT(*) FROM assigned_queue_provider_reservations").fetchone()[0]
    )


def test_cross_universe_and_provider_substitution_never_reaches_ambient_call(
    tmp_path: Path, monkeypatch
) -> None:
    task, conn, _assignment, _current, _events = _authority_fixture(tmp_path, monkeypatch)
    raw_calls: list[str] = []
    session = background_provider._BackgroundAssignedProviderSession(
        tmp_path,
        task,
        _lease(),
        lambda *_a, **_k: raw_calls.append("raw") or "unexpected",
    )

    with pytest.raises(PermissionError, match="universe cannot be substituted"):
        session(
            "prompt",
            universe_context=UniverseContext(universe_dir=tmp_path / "universe-b", config={}),
        )
    with pytest.raises((PermissionError, ProviderAuthorityHeldError)):
        session.call_with_policy_sync(
            "writer",
            "prompt",
            "",
            {"writer": {"provider": "claude-code"}},
        )

    assert raw_calls == []
    assert _reservation_count(conn) == 0


def test_assignment_rotation_before_launch_fails_closed(tmp_path: Path, monkeypatch) -> None:
    task, conn, assignment, current, events = _authority_fixture(tmp_path, monkeypatch)
    current["value"] = SimpleNamespace(**{**assignment.__dict__, "generation": 5})
    raw_calls: list[str] = []
    session = background_provider._BackgroundAssignedProviderSession(
        tmp_path,
        task,
        _lease(),
        lambda *_a, **_k: raw_calls.append("raw") or "unexpected",
    )

    with pytest.raises(ProviderAuthorityHeldError):
        session("prompt")

    assert raw_calls == []
    assert _reservation_count(conn) == 0
    assert events == ["hold"]


def test_budget_is_reserved_before_launch_snapshot_is_cleaned_and_retry_does_not_remint(
    tmp_path: Path, monkeypatch
) -> None:
    task, conn, _assignment, _current, events = _authority_fixture(tmp_path, monkeypatch)
    launches: list[int] = []

    def raw_provider(*_args, **_kwargs):
        _kwargs["universe_context"].served_provider.before_provider_launch()
        row = conn.execute("SELECT state FROM assigned_queue_provider_reservations").fetchone()
        assert row["state"] == "launch_started"
        launches.append(1)
        events.append("launch")
        return "ok"

    session = background_provider._BackgroundAssignedProviderSession(
        tmp_path, task, _lease(), raw_provider
    )
    assert session("prompt") == "ok"
    assert events == ["snapshot", "launch", "cleanup"]

    restarted = background_provider._BackgroundAssignedProviderSession(
        tmp_path, task, _lease(), raw_provider
    )
    with pytest.raises(ProviderAuthorityHeldError):
        restarted("prompt")

    assert launches == [1]
    assert _reservation_count(conn) == 1


def test_per_universe_spend_ceiling_counts_other_attempts(tmp_path: Path, monkeypatch) -> None:
    task, conn, _assignment, _current, _events = _authority_fixture(tmp_path, monkeypatch)
    background_provider._ensure_reservation_schema(conn)
    conn.execute(
        "INSERT INTO assigned_queue_provider_reservations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "reservation-other",
            "bt2_" + "9" * 32,
            "attempt-other",
            "universe:universe-a:background_branch_run",
            "provider-background-a",
            6,
            "sha256:" + "3" * 64,
            "background_branch_run",
            "writer",
            125_000,
            5_000,
            "launch_started",
            "2099-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    launches: list[str] = []

    def raw_provider(*_args, **kwargs):
        kwargs["universe_context"].served_provider.before_provider_launch()
        launches.append("launch")
        return "ok"

    session = background_provider._BackgroundAssignedProviderSession(
        tmp_path, task, _lease(), raw_provider
    )

    assert session("first") == "ok"
    with pytest.raises(ProviderAuthorityHeldError):
        session("second")

    assert launches == ["launch"]
    assert _reservation_count(conn) == 2


def test_rolling_cap_charges_finalized_actuals_not_estimates(tmp_path: Path, monkeypatch) -> None:
    """Codex findings #1/#5 (#2516): the rolling cap must charge REAL spend.

    A prior attempt reserved a 125,000-token ESTIMATE (half the 250,000 default
    ceiling) but its call actually used only 1,000 tokens, which the router
    finalized into served_provider_budget_reservations. Under the old
    SUM(max_tokens) logic that attempt still counted as 125,000 and a second
    125,000 share would exhaust the cap. Now the settled attempt is charged at its
    finalized ACTUAL (1,000), so the next call is admitted — the cap has learned
    true spend. (test_per_universe_spend_ceiling_counts_other_attempts keeps the
    complementary guarantee: an IN-FLIGHT 'launch_started' attempt with unknown
    usage is still charged conservatively at its estimate and DOES exhaust.)
    """
    task, conn, _assignment, _current, _events = _authority_fixture(tmp_path, monkeypatch)
    background_provider._ensure_reservation_schema(conn)
    background_provider._ensure_served_budget_schema(conn)
    # The prior attempt: SETTLED (its call returned), estimate 125,000.
    conn.execute(
        "INSERT INTO assigned_queue_provider_reservations VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "reservation-prior",
            "bt2_" + "9" * 32,
            "attempt-prior",
            "universe:universe-a:background_branch_run",
            "provider-background-a",
            6,
            "sha256:" + "3" * 64,
            "background_branch_run",
            "writer",
            125_000,
            5_000,
            "settled",
            "2099-01-01T00:00:00+00:00",
        ),
    )
    # ...and what it REALLY used, as the router finalized it (keyed by the binding).
    conn.execute(
        """
        INSERT INTO served_provider_budget_reservations
          (reservation_id, binding_id, binding_generation, state,
           reserved_total_tokens, reserved_cost_microunits,
           actual_total_tokens, actual_cost_microunits, created_at, lease_deadline)
        VALUES (?, ?, ?, 'succeeded', ?, ?, ?, ?, 0, NULL)
        """,
        ("served_budget_prior", "provider-background-a", 6, 125_000, 5_000, 1_000, 40),
    )
    conn.commit()
    launches: list[str] = []

    def raw_provider(*_args, **kwargs):
        kwargs["universe_context"].served_provider.before_provider_launch()
        launches.append("launch")
        return "ok"

    session = background_provider._BackgroundAssignedProviderSession(
        tmp_path, task, _lease(), raw_provider
    )
    # Admitted: 1,000 actual + this call's 125,000 share < 250,000 ceiling.
    assert session("next") == "ok"
    assert launches == ["launch"]
    # And this call's own row was settled once it returned.
    states = {
        r["reservation_id"]: r["state"]
        for r in conn.execute(
            "SELECT reservation_id, state FROM assigned_queue_provider_reservations"
        )
    }
    assert states["reservation-prior"] == "settled"
    own = [s for rid, s in states.items() if rid != "reservation-prior"]
    assert own == ["settled"], states


@pytest.mark.xfail(
    strict=True,
    reason=(
        "HONEST GAP: this test drives the REAL router (it launches — REJECT #1 is fixed) "
        "and reaches reserve_served_provider_budget, but the shared _authority_fixture "
        "stubs the provider-authority store/assignment/custody, so reservation cannot "
        "complete in-fixture (AttributeError: _ProviderStore has no connection). "
        "Finalization (REJECT #2) is NOT yet proven end-to-end; it needs a fixture "
        "seeding the real SQLiteProviderWorkAuthorityStore + assignment + custody. "
        "strict=True so an accidental pass is flagged, not silently accepted."
    ),
)
def test_background_call_goes_through_the_real_router_and_finalizes_actuals(
    tmp_path: Path, monkeypatch
) -> None:
    """THE INTEGRATION PROOF Codex demanded (REJECT #1/#2/#6, PR #2528).

    Every prior spend test drove the session with a callback provider and
    hand-inserted 'actual' rows — false assurance. This routes a background call
    through the REAL ProviderRouter and asserts the two facts the design rests on:

    1. The background path LAUNCHES (the router no longer re-fences a context that
       already carries an authorized ServedProviderAuthority — REJECT #1).
    2. The router RESERVES before launch and FINALIZES the call's real usage into
       served_provider_budget_reservations for the background attempt (the
       reservation gate now admits budget_owner="background_attempt" — REJECT #2),
       so the consumer's rolling cap charges what was actually spent.
    """
    import asyncio

    from tinyassets.providers.base import BaseProvider, ModelConfig, ProviderResponse
    from tinyassets.providers.router import ProviderRouter

    task, conn, _assignment, _current, _events = _authority_fixture(tmp_path, monkeypatch)
    background_provider._ensure_reservation_schema(conn)
    background_provider._ensure_served_budget_schema(conn)
    # The shared fixture stubs load_universe_config to a bare {} (its callers never
    # reach the router). This test DOES enter the real router, which reads
    # config.allowed_providers as the requester ceiling — give it the real
    # UniverseConfig shape production loads, admitting the assigned provider.
    import tinyassets.config as config_module
    from tinyassets.config import UniverseConfig

    monkeypatch.setattr(
        config_module, "load_universe_config",
        lambda _path: UniverseConfig(allowed_providers=["codex"]),
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
        # Exactly what production does: the session's authority-bearing context is
        # handed to the real router, which reserves, launches, and finalizes.
        resp = asyncio.run(
            router.call(role, prompt, system, operation=kwargs["operation"],
                        universe_context=kwargs["universe_context"])
        )
        return resp.text

    session = background_provider._BackgroundAssignedProviderSession(
        tmp_path, task, _lease(), through_real_router
    )
    assert session("first") == "routed-ok"
    assert fake.calls == 1  # REJECT #1: the real background path launched.

    # REJECT #2: the router finalized REAL usage for the background attempt.
    served = conn.execute(
        "SELECT state, reserved_total_tokens, actual_total_tokens, actual_cost_microunits "
        "FROM served_provider_budget_reservations"
    ).fetchall()
    assert len(served) == 1, served
    assert served[0]["actual_total_tokens"] == 1000  # 700 in + 300 out, from the router
    assert served[0]["actual_cost_microunits"] == 50
    assert served[0]["state"] != "reserved"  # finalized, not left open

    # And the consumer's own row was settled once the call returned, so the cap
    # now charges the finalized 1,000 rather than the 125,000 estimate.
    own = conn.execute(
        "SELECT state FROM assigned_queue_provider_reservations"
    ).fetchall()
    assert [r["state"] for r in own] == ["settled"]


def test_branch_roles_normalizes_bare_hex_content_hash(monkeypatch, tmp_path):
    """A real published version's content_hash is bare hex; the task carries
    sha256:<hex>. The authority compare normalizes both, so a genuine version is
    accepted (Codex #2, PR #2516) — and a truly different hash still fails closed."""
    bare = "a" * 64
    version = SimpleNamespace(
        status="active",
        branch_def_id="bdef-1",
        content_hash=bare,
        snapshot={"node_defs": [{"node_type": "prompt", "model_hint": "writer"}]},
    )
    monkeypatch.setattr(
        "tinyassets.branch_versions.get_branch_version",
        lambda *a, **k: version,
    )
    task = SimpleNamespace(
        automation_branch_version="ver-1",
        branch_def_id="bdef-1",
        automation_subject_digest=f"sha256:{bare}",
    )
    assert background_provider._branch_roles(tmp_path, task) == ("writer",)
    task.automation_subject_digest = "sha256:" + "b" * 64
    with pytest.raises(PermissionError):
        background_provider._branch_roles(tmp_path, task)


def test_branch_version_rollback_before_launch_fails_closed(tmp_path: Path, monkeypatch) -> None:
    """A version current at the initial check but rolled_back by the launch fence must
    fail closed — the fence re-validates the immutable Branch version (Codex #3, #2516)."""
    task, conn, _assignment, _current, events = _authority_fixture(tmp_path, monkeypatch)
    state = {"n": 0}

    def _roles(*_a):
        state["n"] += 1
        if state["n"] > 1:  # first call ok (initial), later call (launch fence) rolled back
            raise PermissionError("immutable Branch version is not current authority")
        return ("writer",)

    monkeypatch.setattr(background_provider, "_branch_roles", _roles)
    raw_calls: list[str] = []

    def raw_provider(*_a, **_k):
        # The provider adapter fires the launch fence, which re-validates the version.
        _k["universe_context"].served_provider.before_provider_launch()
        raw_calls.append("raw")
        return "x"

    session = background_provider._BackgroundAssignedProviderSession(
        tmp_path, task, _lease(), raw_provider
    )
    with pytest.raises(ProviderAuthorityHeldError):
        session("prompt")
    assert raw_calls == []  # fence raised before the provider ran
    launched = conn.execute(
        "SELECT 1 FROM assigned_queue_provider_reservations "
        "WHERE state='launch_started'"
    ).fetchone()
    assert launched is None  # the fence blocked the launch (reservation never armed)
    assert state["n"] >= 2  # the launch fence re-validated the version


def test_scavenge_orphaned_launch_credentials(tmp_path: Path) -> None:
    """Startup reclamation removes stale (crash-orphaned) codex-* credential dirs but
    leaves in-flight (recent) ones and non-codex entries (Codex #4, #2516)."""
    import os
    import time as _t

    from tinyassets.credential_vault import scavenge_orphaned_launch_credentials

    root = tmp_path / ".runtime" / "provider-launch-credentials"
    root.mkdir(parents=True)
    old = root / "codex-staleaaaa"
    old.mkdir()
    (old / "cred.json").write_text("secret")
    recent = root / "codex-freshbbbb"
    recent.mkdir()
    (recent / "cred.json").write_text("secret")
    other = root / "notcodex"
    other.mkdir()
    aged = _t.time() - 7200
    os.utime(old, (aged, aged))
    removed = scavenge_orphaned_launch_credentials(tmp_path, max_age_seconds=3600)
    assert removed == 1
    assert not old.exists()      # stale orphan reclaimed
    assert recent.exists()       # too recent — could back an in-flight call
    assert other.exists()        # not a codex- snapshot dir
    # idempotent: a second sweep with nothing stale removes nothing.
    assert scavenge_orphaned_launch_credentials(tmp_path, max_age_seconds=3600) == 0

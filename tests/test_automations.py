"""User-owned automations: the fence, the fail-loud registration, and the pump.

Every assertion here is mutation-checked -- the guarding line is flipped, the
test goes red, the line is restored. The mutation table lives in the commit
message for this slice.
"""

from __future__ import annotations

import sqlite3
from concurrent.futures import Future
from dataclasses import fields, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import tinyassets.automations as automations_module
from tests.test_background_budget_finalization_e2e import _seed_serving_assignment
from tinyassets.automations import (
    MAX_ACTIVE_PER_UNIVERSE,
    Automation,
    AutomationStore,
    AutomationUnavailable,
    due_automations,
    register_automation,
    run_due_automation,
)
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.runtime.assigned_queue_consumer import AssignedQueueConsumer
from tinyassets.storage import db_path

OWNER = "acct_alice"
UNIVERSE = "universe_alice"
BRANCH = "branch_automation_demo"

NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)


# -- Seeds --------------------------------------------------------------------


def _seed_branch(
    tmp_path: Path,
    *,
    branch_def_id: str = BRANCH,
    author: str = OWNER,
    visibility: str = "public",
) -> str:
    from tinyassets.daemon_server import initialize_author_server, save_branch_definition

    node = NodeDefinition(
        node_id="n1",
        display_name="Automation writer",
        prompt_template="Do the owner's recurring work.",
    )
    branch = BranchDefinition(
        branch_def_id=branch_def_id,
        name="Automation demo",
        author=author,
        visibility=visibility,
        graph_nodes=[GraphNodeRef(id="n1", node_def_id="n1")],
        edges=[EdgeDefinition(from_node="n1", to_node="END")],
        entry_point="n1",
        node_defs=[node],
        state_schema=[],
    )
    initialize_author_server(tmp_path)
    save_branch_definition(tmp_path, branch_def=branch.to_dict())
    return branch_def_id


def _seed_owner(
    tmp_path: Path,
    *,
    universe_id: str = UNIVERSE,
    owner: str = OWNER,
    permission: str = "admin",
    home: str | None = None,
) -> None:
    from tinyassets.daemon_server import (
        grant_universe_access,
        initialize_author_server,
        set_founder_home,
    )

    initialize_author_server(tmp_path)
    (tmp_path / universe_id).mkdir(parents=True, exist_ok=True)
    grant_universe_access(
        tmp_path,
        universe_id=universe_id,
        actor_id=owner,
        permission=permission,
        granted_by=owner,
    )
    set_founder_home(
        tmp_path,
        founder_sub=owner,
        universe_id=universe_id if home is None else home,
    )


def _copy_assignment_to(tmp_path: Path, *, universe_id: str, owner: str) -> None:
    """Give a SECOND universe its own ready assignment row.

    The seeded serving path is hard-wired to one universe; the pump-isolation
    tests need a second owner whose automation must keep running while the
    first one's is refused.
    """
    from tinyassets.provider_assignment import (
        load_provider_assignment,
        provider_assignment_digest,
        store_provider_assignment_in_transaction,
    )

    source = load_provider_assignment(tmp_path, universe_id=UNIVERSE)
    assert source is not None
    clone = replace(source, universe_id=universe_id, owner_user_id=owner)
    clone = replace(
        clone,
        assignment_digest=provider_assignment_digest(
            owner_user_id=clone.owner_user_id,
            universe_id=clone.universe_id,
            provider=clone.provider,
            generation=clone.generation,
            binding_id=clone.binding_id,
            credential_reference_id=clone.credential_reference_id,
            credential_reference_generation=clone.credential_reference_generation,
            credential_reference_digest=clone.credential_reference_digest,
        ),
    )
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        store_provider_assignment_in_transaction(conn, clone)
        conn.commit()


def _switch_assignment_provider(tmp_path: Path, *, universe_id: str, provider: str) -> None:
    """Rebind the universe to another provider, the way an owner would."""
    from tinyassets.provider_assignment import (
        load_provider_assignment,
        provider_assignment_digest,
        store_provider_assignment_in_transaction,
    )

    current = load_provider_assignment(tmp_path, universe_id=universe_id)
    assert current is not None
    switched = replace(current, provider=provider, generation=current.generation + 1)
    switched = replace(
        switched,
        assignment_digest=provider_assignment_digest(
            owner_user_id=switched.owner_user_id,
            universe_id=switched.universe_id,
            provider=switched.provider,
            generation=switched.generation,
            binding_id=switched.binding_id,
            credential_reference_id=switched.credential_reference_id,
            credential_reference_generation=switched.credential_reference_generation,
            credential_reference_digest=switched.credential_reference_digest,
        ),
    )
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute("BEGIN IMMEDIATE")
        store_provider_assignment_in_transaction(conn, switched)
        conn.commit()


@pytest.fixture
def registered(tmp_path: Path, monkeypatch) -> Automation:
    """A universe whose owner can register, plus one active automation."""
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)
    return register_automation(
        tmp_path,
        universe_id=UNIVERSE,
        owner_principal_id=OWNER,
        name="Nightly digest",
        branch_def_id=BRANCH,
        interval_seconds=600,
        inputs={"topic": "spec drift"},
        now=NOW,
    )


class _FakeOutcome:
    def __init__(self, run_id: str = "run_fake", status: str = "completed") -> None:
        self.run_id = run_id
        self.status = status
        self.output: dict[str, object] = {}
        self.error = ""


class _SeamRecorder:
    """Stands in for `_execute`, the one substitutable seam."""

    def __init__(self, status: str = "completed") -> None:
        self.calls: list[tuple[str, dict]] = []
        self.status = status

    def __call__(self, base_path, automation, provider_call, branch, inputs):
        self.calls.append((automation.automation_id, dict(inputs)))
        return _FakeOutcome(
            run_id=f"run_{len(self.calls)}",
            status=self.status,
        )


def _refusal_rows(tmp_path: Path) -> dict[str, str]:
    database = db_path(tmp_path)
    if not database.is_file():
        return {}
    with sqlite3.connect(database) as conn:
        try:
            rows = conn.execute(
                "SELECT branch_task_id, reason FROM assigned_queue_refusals"
            ).fetchall()
        except sqlite3.OperationalError:
            return {}
    return {str(key): str(reason) for key, reason in rows}


# -- 1. The (automation_id, due_at) fence -------------------------------------


def test_claim_attempt_admits_exactly_one_caller(tmp_path: Path) -> None:
    store = AutomationStore(tmp_path)
    results = [
        store.claim_attempt("a1", "2026-08-29T12:00:00+00:00", now=NOW),
        store.claim_attempt("a1", "2026-08-29T12:00:00+00:00", now=NOW),
    ]

    assert results == [True, False]
    # A different instant of the SAME automation is a different claim.
    assert store.claim_attempt("a1", "2026-08-29T12:10:00+00:00", now=NOW) is True


def test_second_run_of_the_same_due_instant_does_not_reach_the_seam(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    seam = _SeamRecorder()
    monkeypatch.setattr(automations_module, "_execute", seam)
    due_at = "2026-08-29T12:10:00+00:00"

    first = run_due_automation(tmp_path, registered, due_at, now=NOW)
    second = run_due_automation(tmp_path, registered, due_at, now=NOW)

    assert first == "ok:ran:run_1"
    assert second == "attempt_exists"
    assert len(seam.calls) == 1


# -- 2. Restart survival ------------------------------------------------------


def test_a_fresh_store_recomputes_the_same_due_at_and_skips_the_claimed_one(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    """A daemon that dies mid-run must not re-launch the same instant on boot."""
    later = NOW + timedelta(seconds=900)
    due_before = due_automations(tmp_path, universe_id=UNIVERSE, now=later)
    assert [pair[1] for pair in due_before] == ["2026-08-29T12:10:00+00:00"]

    # In-flight when the process died: claimed, never finished.
    assert AutomationStore(tmp_path).claim_attempt(
        registered.automation_id, due_before[0][1], now=later
    ) is True

    # Reboot: new store, new consumer, same wall-clock -> same due_at.
    reborn_store = AutomationStore(tmp_path)
    reborn_consumer = AssignedQueueConsumer(tmp_path, max_concurrency=1)
    try:
        due_after = due_automations(tmp_path, universe_id=UNIVERSE, now=later)
        assert [pair[1] for pair in due_after] == [pair[1] for pair in due_before]
        assert reborn_store.get(registered.automation_id) is not None

        seam = _SeamRecorder()
        monkeypatch.setattr(automations_module, "_execute", seam)
        reason = run_due_automation(
            tmp_path,
            due_after[0][0],
            due_after[0][1],
            now=later,
            consumer_id=reborn_consumer.consumer_id,
        )
    finally:
        reborn_consumer.stop()

    assert reason == "attempt_exists"
    assert seam.calls == []


def test_interval_due_at_floors_onto_the_period_grid(
    tmp_path: Path,
    registered: Automation,
) -> None:
    """A daemon down for many intervals owes ONE run, not a backlog burst."""
    assert due_automations(tmp_path, universe_id=UNIVERSE, now=NOW) == []
    much_later = NOW + timedelta(seconds=600 * 7 + 90)
    due = due_automations(tmp_path, universe_id=UNIVERSE, now=much_later)

    assert len(due) == 1
    assert due[0][1] == "2026-08-29T13:10:00+00:00"  # created_at + 7 * 600s


# -- 3. Provider switch, nothing pinned ---------------------------------------


def test_no_column_or_field_pins_a_provider_or_an_executor(
    tmp_path: Path,
    registered: Automation,
) -> None:
    forbidden = ("provider", "worker", "daemon", "runtime", "credential", "binding")
    field_names = {f.name for f in fields(Automation)}
    with sqlite3.connect(AutomationStore(tmp_path).db_path) as conn:
        columns = {
            str(row[1]) for row in conn.execute("PRAGMA table_info(automations)")
        }

    for token in forbidden:
        assert not [name for name in field_names if token in name], token
        assert not [name for name in columns if token in name], token


def test_a_provider_switch_between_runs_needs_no_repreparation(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    from tinyassets.provider_assignment import load_provider_assignment

    built: list[dict] = []
    real_factory = automations_module.__dict__  # keep the import site honest

    def recording_factory(base_path, *, universe_id, principal_id, provider_call):
        from tinyassets.foreground_run_provider import (
            _ForegroundRunProviderSession,
        )

        session = _ForegroundRunProviderSession(
            base_path,
            universe_id=universe_id,
            principal_id=principal_id,
            provider_call=provider_call,
        )
        assignment = load_provider_assignment(base_path, universe_id=universe_id)
        built.append(
            {
                "constructor_inputs": session.constructor_inputs(),
                # What the session's own _admit resolves, at the moment it is built.
                "resolves_provider": "" if assignment is None else assignment.provider,
            }
        )
        return session

    monkeypatch.setattr(
        "tinyassets.foreground_run_provider.new_foreground_run_provider_session",
        recording_factory,
    )
    seam = _SeamRecorder()
    monkeypatch.setattr(automations_module, "_execute", seam)
    assert real_factory is automations_module.__dict__

    run_due_automation(tmp_path, registered, "2026-08-29T12:10:00+00:00", now=NOW)
    _switch_assignment_provider(tmp_path, universe_id=UNIVERSE, provider="claude-code")
    run_due_automation(tmp_path, registered, "2026-08-29T12:20:00+00:00", now=NOW)

    assert len(built) == 2
    first, second = built
    # Nothing provider-derived crosses the boundary: the two sessions are built
    # from identical inputs, and only what they RESOLVE differs.
    assert first["constructor_inputs"] == second["constructor_inputs"]
    assert first["constructor_inputs"]["universe_id"] == UNIVERSE
    assert first["constructor_inputs"]["principal_id"] == OWNER
    assert first["resolves_provider"] == "codex"
    assert second["resolves_provider"] == "claude-code"


# -- 4. Registration fails loud -----------------------------------------------


def _registration_kwargs(**overrides):
    kwargs = {
        "universe_id": UNIVERSE,
        "owner_principal_id": OWNER,
        "name": "Nightly digest",
        "branch_def_id": BRANCH,
        "interval_seconds": 600,
        "cron_expr": "",
        "inputs": {},
        "now": NOW,
    }
    kwargs.update(overrides)
    return kwargs


def test_registration_refuses_when_the_consumer_is_dark(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.delenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", raising=False)
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)

    with pytest.raises(AutomationUnavailable) as caught:
        register_automation(tmp_path, **_registration_kwargs())

    assert caught.value.reason == "consumer_disabled"
    assert AutomationStore(tmp_path).list(universe_id=UNIVERSE) == []


@pytest.mark.parametrize("principal", ["", "   ", "anonymous"])
def test_registration_refuses_an_unauthenticated_principal(
    tmp_path: Path, monkeypatch, principal: str
) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)

    with pytest.raises(AutomationUnavailable) as caught:
        register_automation(
            tmp_path, **_registration_kwargs(owner_principal_id=principal)
        )

    assert caught.value.reason == "authentication_required"


def test_registration_refuses_a_writer_who_is_not_an_admin(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path, permission="write")
    _seed_branch(tmp_path)

    with pytest.raises(AutomationUnavailable) as caught:
        register_automation(tmp_path, **_registration_kwargs())

    assert caught.value.reason == "owner_not_admin"


def test_registration_refuses_an_admin_of_someone_elses_universe(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path, home="universe_somewhere_else")
    _seed_branch(tmp_path)

    with pytest.raises(AutomationUnavailable) as caught:
        register_automation(tmp_path, **_registration_kwargs())

    assert caught.value.reason == "not_owner_home"


def test_registration_refuses_a_universe_with_no_ready_assignment(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)

    with pytest.raises(AutomationUnavailable) as caught:
        register_automation(tmp_path, **_registration_kwargs())

    assert caught.value.reason == "no_serving_assignment"


def test_registration_refuses_a_branch_the_owner_cannot_read(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(
        tmp_path,
        branch_def_id="branch_private_other",
        author="acct_bob",
        visibility="private",
    )

    with pytest.raises(AutomationUnavailable) as caught:
        register_automation(
            tmp_path, **_registration_kwargs(branch_def_id="branch_private_other")
        )
    assert caught.value.reason == "branch_not_readable"

    with pytest.raises(AutomationUnavailable) as missing:
        register_automation(
            tmp_path, **_registration_kwargs(branch_def_id="branch_does_not_exist")
        )
    assert missing.value.reason == "branch_not_readable"


@pytest.mark.parametrize(
    "trigger",
    [
        {"interval_seconds": 0, "cron_expr": ""},          # neither
        {"interval_seconds": 600, "cron_expr": "0 * * * *"},  # both
        {"interval_seconds": 60, "cron_expr": ""},          # under the floor
        {"interval_seconds": -600, "cron_expr": ""},        # nonsense
        {"interval_seconds": 0, "cron_expr": "not a cron"},  # unparseable
        {"interval_seconds": 0, "cron_expr": "0 0 * *"},     # four fields
    ],
)
def test_registration_refuses_a_trigger_that_cannot_fire(
    tmp_path: Path, monkeypatch, trigger: dict
) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)

    with pytest.raises(AutomationUnavailable) as caught:
        register_automation(tmp_path, **_registration_kwargs(**trigger))

    assert caught.value.reason == "trigger_invalid"
    assert AutomationStore(tmp_path).list(universe_id=UNIVERSE) == []


def test_registration_refuses_past_the_per_universe_ceiling(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)
    for index in range(MAX_ACTIVE_PER_UNIVERSE):
        register_automation(
            tmp_path, **_registration_kwargs(name=f"automation {index}")
        )

    with pytest.raises(AutomationUnavailable) as caught:
        register_automation(tmp_path, **_registration_kwargs(name="one too many"))

    assert caught.value.reason == "too_many_automations"
    assert len(AutomationStore(tmp_path).list(universe_id=UNIVERSE)) == (
        MAX_ACTIVE_PER_UNIVERSE
    )


def test_a_cron_registration_is_stored_and_comes_due_on_its_minute(
    tmp_path: Path, monkeypatch
) -> None:
    import time as _time

    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path)
    automation = register_automation(
        tmp_path,
        **_registration_kwargs(interval_seconds=0, cron_expr="* * * * *"),
    )
    assert automation.trigger_kind == "cron"

    # `* * * * *` matches every local minute, so the bucket itself is the proof.
    local = _time.localtime(NOW.timestamp())
    assert local is not None
    due = due_automations(tmp_path, universe_id=UNIVERSE, now=NOW + timedelta(seconds=30))

    assert [pair[1] for pair in due] == ["2026-08-29T12:00:00+00:00"]


# -- 5. Authority is re-derived at run time -----------------------------------


def test_an_owner_who_lost_admin_is_refused_and_the_automation_pauses(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    from tinyassets.daemon_server import grant_universe_access

    seam = _SeamRecorder()
    monkeypatch.setattr(automations_module, "_execute", seam)
    grant_universe_access(
        tmp_path,
        universe_id=UNIVERSE,
        actor_id=OWNER,
        permission="read",
        granted_by=OWNER,
    )

    reason = run_due_automation(
        tmp_path,
        registered,
        "2026-08-29T12:10:00+00:00",
        now=NOW,
        consumer_id="worker_assigned_test",
    )

    assert reason == "owner_lost_admin"
    assert seam.calls == []
    paused = AutomationStore(tmp_path).get(registered.automation_id)
    assert paused is not None
    assert paused.desired_state == "paused"
    assert paused.pause_reason == "owner_lost_admin"
    assert paused.revision == registered.revision + 1
    assert _refusal_rows(tmp_path) == {
        f"automation:{registered.automation_id}": "owner_lost_admin"
    }
    # Paused means the next poll stops offering it.
    assert due_automations(
        tmp_path, universe_id=UNIVERSE, now=NOW + timedelta(seconds=3600)
    ) == []


def test_a_home_rebind_between_ticks_is_refused_as_not_owner_home(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    from tinyassets.daemon_server import set_founder_home

    seam = _SeamRecorder()
    monkeypatch.setattr(automations_module, "_execute", seam)
    set_founder_home(tmp_path, founder_sub=OWNER, universe_id="universe_elsewhere")

    reason = run_due_automation(
        tmp_path, registered, "2026-08-29T12:10:00+00:00", now=NOW
    )

    assert reason == "not_owner_home"
    assert seam.calls == []


def test_a_revoked_assignment_between_ticks_is_refused(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    seam = _SeamRecorder()
    monkeypatch.setattr(automations_module, "_execute", seam)
    with sqlite3.connect(db_path(tmp_path)) as conn:
        conn.execute("DELETE FROM provider_assignments WHERE universe_id = ?", (UNIVERSE,))
        conn.commit()

    reason = run_due_automation(
        tmp_path, registered, "2026-08-29T12:10:00+00:00", now=NOW
    )

    assert reason == "no_serving_assignment"
    assert seam.calls == []


def test_one_owners_refusal_leaves_another_owners_run_alone(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    from tinyassets.daemon_server import grant_universe_access

    _seed_owner(tmp_path, universe_id="universe_bob", owner="acct_bob")
    _copy_assignment_to(tmp_path, universe_id="universe_bob", owner="acct_bob")
    _seed_branch(tmp_path, branch_def_id="branch_bob", author="acct_bob")
    bob = register_automation(
        tmp_path,
        universe_id="universe_bob",
        owner_principal_id="acct_bob",
        name="Bob's digest",
        branch_def_id="branch_bob",
        interval_seconds=600,
        now=NOW,
    )
    seam = _SeamRecorder()
    monkeypatch.setattr(automations_module, "_execute", seam)
    grant_universe_access(
        tmp_path,
        universe_id=UNIVERSE,
        actor_id=OWNER,
        permission="read",
        granted_by=OWNER,
    )

    refused = run_due_automation(
        tmp_path, registered, "2026-08-29T12:10:00+00:00", now=NOW
    )
    ran = run_due_automation(tmp_path, bob, "2026-08-29T12:10:00+00:00", now=NOW)

    assert refused == "owner_lost_admin"
    assert ran == "ok:ran:run_1"
    assert [call[0] for call in seam.calls] == [bob.automation_id]


def test_a_raising_run_records_a_bounded_reason_and_does_not_propagate(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    def exploding(*_args, **_kwargs):
        raise RuntimeError(r"boom at C:\Users\secret\path with a token")

    monkeypatch.setattr(automations_module, "_execute", exploding)

    reason = run_due_automation(
        tmp_path, registered, "2026-08-29T12:10:00+00:00", now=NOW
    )

    assert reason.startswith("automation_error:RuntimeError")
    assert "secret" not in reason
    assert _refusal_rows(tmp_path)[f"automation:{registered.automation_id}"] == reason


# -- Owner controls -----------------------------------------------------------


def test_pause_resume_and_retire_move_the_revision_and_gate_the_due_scan(
    tmp_path: Path,
    registered: Automation,
) -> None:
    store = AutomationStore(tmp_path)
    later = NOW + timedelta(seconds=1200)

    paused = store.set_desired_state(
        registered.automation_id,
        "paused",
        expected_revision=registered.revision,
        reason="owner_requested",
        now=NOW,
    )
    assert paused.desired_state == "paused"
    assert due_automations(tmp_path, universe_id=UNIVERSE, now=later) == []

    with pytest.raises(ValueError):
        store.set_desired_state(
            registered.automation_id,
            "active",
            expected_revision=registered.revision,  # stale
            now=NOW,
        )

    resumed = store.set_desired_state(
        registered.automation_id,
        "active",
        expected_revision=paused.revision,
        now=NOW,
    )
    assert resumed.pause_reason == ""
    assert len(due_automations(tmp_path, universe_id=UNIVERSE, now=later)) == 1

    retired = store.retire(
        registered.automation_id, expected_revision=resumed.revision, now=NOW
    )
    assert retired.retired_at
    assert store.list(universe_id=UNIVERSE) == []
    assert len(store.list(universe_id=UNIVERSE, include_retired=True)) == 1
    assert due_automations(tmp_path, universe_id=UNIVERSE, now=later) == []
    with pytest.raises(ValueError):
        store.set_desired_state(
            registered.automation_id,
            "active",
            expected_revision=retired.revision,
            now=NOW,
        )


# -- 6. The consumer pump -----------------------------------------------------


class _InlineExecutor:
    """Runs submissions on the calling thread so a poll is assertable."""

    def __init__(self) -> None:
        self.submissions: list[tuple] = []

    def submit(self, fn, *args):
        self.submissions.append(args)
        future: Future = Future()
        try:
            future.set_result(fn(*args))
        except BaseException as exc:  # pragma: no cover - surfaced by the assertion
            future.set_exception(exc)
        return future

    def shutdown(self, **_kwargs) -> None:
        pass


def _consumer_with_inline_executor(tmp_path: Path, *, max_concurrency: int = 2):
    consumer = AssignedQueueConsumer(tmp_path, max_concurrency=max_concurrency)
    inline = _InlineExecutor()
    consumer._executor.shutdown(wait=False)
    consumer._executor = inline
    return consumer, inline


def test_poll_once_submits_a_universes_due_automations(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE],
    )
    ran: list[str] = []
    monkeypatch.setattr(
        automations_module,
        "run_due_automation",
        lambda base, automation, due_at, **kwargs: ran.append(
            f"{automation.automation_id}@{due_at}"
        )
        or "ok:ran:run_1",
    )
    consumer, inline = _consumer_with_inline_executor(tmp_path)

    try:
        submitted = consumer.poll_once()
    finally:
        consumer.stop()

    # The poll uses the real clock, so the expected due_at is whatever the due
    # scan itself yields at this instant -- the contract is that the pump passes
    # the scan's pair through untouched, not that it invents one.
    expected = due_automations(
        tmp_path, universe_id=UNIVERSE, now=datetime.now(timezone.utc)
    )
    assert submitted == 1
    assert inline.submissions and inline.submissions[0][0] == UNIVERSE
    assert ran == [f"{registered.automation_id}@{expected[0][1]}"]


def test_poll_once_leaves_a_paused_universe_alone(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE],
    )
    scanned: list[str] = []
    monkeypatch.setattr(
        automations_module,
        "due_automations",
        lambda base, *, universe_id, now: scanned.append(universe_id) or [],
    )
    (tmp_path / UNIVERSE / ".pause").write_text("owner paused", encoding="utf-8")
    consumer, inline = _consumer_with_inline_executor(tmp_path)

    try:
        consumer.poll_once()
    finally:
        consumer.stop()

    assert scanned == []
    assert inline.submissions == []


def test_one_universes_scan_failure_does_not_stop_the_poll(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    _seed_owner(tmp_path, universe_id="universe_bob", owner="acct_bob")
    _copy_assignment_to(tmp_path, universe_id="universe_bob", owner="acct_bob")
    _seed_branch(tmp_path, branch_def_id="branch_bob", author="acct_bob")
    bob = register_automation(
        tmp_path,
        universe_id="universe_bob",
        owner_principal_id="acct_bob",
        name="Bob's digest",
        branch_def_id="branch_bob",
        interval_seconds=600,
        now=NOW,
    )
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE, "universe_bob"],
    )
    real_due = automations_module.due_automations

    def flaky(base, *, universe_id, now):
        if universe_id == UNIVERSE:
            raise RuntimeError("scan exploded")
        return real_due(base, universe_id=universe_id, now=now)

    monkeypatch.setattr(automations_module, "due_automations", flaky)
    ran: list[str] = []
    monkeypatch.setattr(
        automations_module,
        "run_due_automation",
        lambda base, automation, due_at, **kwargs: ran.append(automation.automation_id)
        or "ok:ran:run_1",
    )
    consumer, _inline = _consumer_with_inline_executor(tmp_path)

    try:
        submitted = consumer.poll_once()
    finally:
        consumer.stop()

    assert submitted == 1
    assert ran == [bob.automation_id]
    refusals = _refusal_rows(tmp_path)
    assert refusals[f"universe:{UNIVERSE}:automations"].startswith(
        "automation_scan_error:RuntimeError"
    )


def test_a_universe_running_an_automation_skips_the_legacy_pump_that_poll(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE],
    )
    monkeypatch.setattr(
        automations_module,
        "run_due_automation",
        lambda *_args, **_kwargs: "ok:ran:run_1",
    )
    # The legacy pump only runs behind a live audience and an empty pending list.
    # Without this the assertion below would be green no matter what the code did.
    monkeypatch.setattr(
        AssignedQueueConsumer,
        "_publish_heartbeat",
        lambda self, universe_id: object(),
    )
    pumped: list[str] = []
    monkeypatch.setattr(
        AssignedQueueConsumer,
        "_pump_automation",
        lambda self, universe_id, audience: pumped.append(universe_id) or False,
    )
    consumer, _inline = _consumer_with_inline_executor(tmp_path)

    try:
        consumer.poll_once()
    finally:
        consumer.stop()

    assert pumped == []


def test_the_legacy_pump_still_runs_for_a_universe_with_no_due_automation(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    """The positive control for the test above: the skip is conditional, not a
    blanket disable of the fleet-era pump task 3.3 has not deleted yet."""
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE],
    )
    monkeypatch.setattr(
        automations_module,
        "due_automations",
        lambda base, *, universe_id, now: [],
    )
    monkeypatch.setattr(
        AssignedQueueConsumer,
        "_publish_heartbeat",
        lambda self, universe_id: object(),
    )
    pumped: list[str] = []
    monkeypatch.setattr(
        AssignedQueueConsumer,
        "_pump_automation",
        lambda self, universe_id, audience: pumped.append(universe_id) or False,
    )
    consumer, _inline = _consumer_with_inline_executor(tmp_path)

    try:
        consumer.poll_once()
    finally:
        consumer.stop()

    assert pumped == [UNIVERSE]


def test_a_dark_consumer_scans_no_automations_at_all(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    monkeypatch.delenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", raising=False)
    scanned: list[str] = []
    monkeypatch.setattr(
        automations_module,
        "due_automations",
        lambda base, *, universe_id, now: scanned.append(universe_id) or [],
    )
    consumer, inline = _consumer_with_inline_executor(tmp_path)

    try:
        assert consumer.poll_once() == 0
    finally:
        consumer.stop()

    assert scanned == []
    assert inline.submissions == []


# -- 7. The real path ---------------------------------------------------------


def test_the_real_run_path_admits_through_the_live_session_and_records_a_run(
    tmp_path: Path,
    registered: Automation,
    monkeypatch,
) -> None:
    """No seam: the branch runs through the real foreground session.

    This is the whole D1 claim end to end -- the automation row carries no
    provider, and the run still reaches the universe's seeded codex assignment,
    admits on the owner's own authority, and lands a run row actored to the
    universe.
    """
    import tinyassets.providers.call as provider_call_module
    from tests.test_background_budget_finalization_e2e import _CountingProvider
    from tinyassets.providers.router import ProviderRouter
    from tinyassets.runs import get_run

    fake = _CountingProvider()
    previous_router = provider_call_module.get_provider_router()
    previous_force_mock = provider_call_module.is_force_mock()
    provider_call_module.set_provider_router(ProviderRouter({"codex": fake}))
    provider_call_module.set_force_mock(False)
    try:
        reason = run_due_automation(
            tmp_path,
            registered,
            "2026-08-29T12:10:00+00:00",
            now=NOW,
            consumer_id="worker_assigned_real",
        )
    finally:
        provider_call_module.set_provider_router(previous_router)
        provider_call_module.set_force_mock(previous_force_mock)

    assert reason.startswith("ok:ran:"), reason
    run_id = reason.split("ok:ran:", 1)[1]
    record = get_run(tmp_path, run_id)
    assert record is not None
    assert record["status"] == "completed"
    assert record["actor"] == f"universe:{UNIVERSE}"
    assert record["run_name"] == f"automation:{registered.automation_id[:8]}"
    assert len(fake.calls) == 1

    finished = AutomationStore(tmp_path).get(registered.automation_id)
    assert finished is not None
    assert finished.last_run_id == run_id
    assert finished.last_due_at == "2026-08-29T12:10:00+00:00"
    assert finished.desired_state == "active"
    assert _refusal_rows(tmp_path)[f"automation:{registered.automation_id}"] == reason

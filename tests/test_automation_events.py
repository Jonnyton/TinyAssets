"""Engine events wake an owner's subscribed automation through the real pump.

An ``event`` automation is a subscription. The engine emits ``run_completed``
from ``runs.update_run_status`` (and the boot sweep) and
``pending_request_answered`` from ``storage.pending_requests.resolve_request``;
each match stores a ``once`` wake, which the real consumer pump fires.

Driven through the real emitters: a real run row taken terminal by the real
status writer, a real pending request answered through the connector's own
``answer_request``, the real ``register_automation``, the real store and the
real consumer. The only substitute is ``_execute``, the seam
``tinyassets.automations`` names for tests -- it fakes the graph a wake runs,
never the event, the scheduling or the checks.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

import tinyassets.automations as automations_module
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_automations import (
    OWNER,
    UNIVERSE,
    _consumer_with_inline_executor,
    _FakeOutcome,
    _seed_branch,
    _seed_owner,
)
from tests.test_background_budget_finalization_e2e import _seed_serving_assignment
from tinyassets.auth.middleware import identity_context
from tinyassets.auth.provider import Identity
from tinyassets.automations import (
    TRIGGER_EVENT,
    TRIGGER_ONCE,
    Automation,
    AutomationStore,
    AutomationUnavailable,
    due_automations,
    register_automation,
)
from tinyassets.runs import (
    RUN_STATUS_COMPLETED,
    RUN_STATUS_FAILED,
    RUN_STATUS_RUNNING,
    create_run,
    recover_in_flight_runs,
    update_run_status,
)

pytestmark = pytest.mark.usefixtures("cloud_runtime")

FOLLOWED = "branch_followed"
FOLLOWER = "branch_follower"
BOB = "acct_bob"
BOB_UNIVERSE = "universe_bob"
BOB_BRANCH = "branch_bobs_own"


@pytest.fixture(autouse=True)
def _pin_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """Alice's serving home with two PRIVATE branches; Bob has his own home."""
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path, branch_def_id=FOLLOWED, visibility="private")
    _seed_branch(tmp_path, branch_def_id=FOLLOWER, visibility="private")
    _seed_owner(tmp_path, universe_id=BOB_UNIVERSE, owner=BOB)
    _seed_branch(tmp_path, branch_def_id=BOB_BRANCH, author=BOB, visibility="private")
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE],
    )
    return tmp_path


def _as(actor: str | None):
    return identity_context(
        None if actor is None else Identity(user_id=actor, username=actor)
    )


def _subscribe(base: Path, event_type: str, event_filter=None, **kw) -> Automation:
    owner = kw.pop("owner", OWNER)
    with _as(owner):
        return register_automation(
            base,
            universe_id=kw.pop("universe_id", UNIVERSE),
            owner_principal_id=owner,
            name="follow",
            branch_def_id=kw.pop("branch_def_id", FOLLOWER),
            event_type=event_type,
            event_filter=event_filter,
            inputs={"why": "followed"},
            **kw,
        )


def _wakes(base: Path, universe: str = UNIVERSE) -> list[Automation]:
    return [
        row for row in AutomationStore(base).list(universe_id=universe)
        if row.trigger_kind == TRIGGER_ONCE
    ]


def _start(base: Path, *, actor: str, queue_universe_id: str | None = None,
           bound: str | None = None, branch_def_id: str = FOLLOWED) -> str:
    """A running run, created with `bound` as the request identity."""
    with _as(bound):
        run_id = create_run(
            base, branch_def_id=branch_def_id, thread_id="t", inputs={},
            actor=actor, queue_universe_id=queue_universe_id,
        )
    update_run_status(base, run_id, status=RUN_STATUS_RUNNING)
    return run_id


def _finish(base: Path, *, actor: str, status: str = RUN_STATUS_COMPLETED,
            queue_universe_id: str | None = None, bound: str | None = None,
            branch_def_id: str = FOLLOWED, ended_by: str | None = "acct_stranger",
            ) -> str:
    """Create a run as `bound`, then end it with a DIFFERENT ambient identity:
    the event is stamped from the run's creation, never from who is ambient
    when it ends."""
    run_id = _start(base, actor=actor, queue_universe_id=queue_universe_id,
                    bound=bound, branch_def_id=branch_def_id)
    with _as(ended_by):
        update_run_status(base, run_id, status=status, finished_at=1.0)
    return run_id


class _Graph:
    """The `_execute` seam: records what each fired wake ran, with its inputs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, base_path, automation, provider_call, branch, inputs,
                 on_run_started=None):
        self.calls.append((automation.branch_def_id, dict(inputs)))
        run_id = f"graph_run_{len(self.calls)}"
        if callable(on_run_started):
            on_run_started(run_id)
        return _FakeOutcome(run_id=run_id, status="completed")


def _poll(base: Path) -> None:
    consumer, _inline = _consumer_with_inline_executor(base)
    try:
        consumer.poll_once()
    finally:
        consumer.stop()


# -- run_completed ------------------------------------------------------------


def test_a_finished_run_wakes_the_branch_that_follows_it_through_the_pump(
    home: Path, monkeypatch,
) -> None:
    sub = _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    run_id = _finish(home, actor=OWNER)

    [wake] = _wakes(home)
    assert (wake.owner_principal_id, wake.branch_def_id) == (OWNER, FOLLOWER)
    assert wake.inputs == {
        "why": "followed",
        "event": {
            "type": "run_completed", "subscription_id": sub.automation_id,
            "run_id": run_id, "branch_def_id": FOLLOWED, "outcome": "completed",
        },
    }

    graph = _Graph()
    monkeypatch.setattr(automations_module, "_execute", graph)
    _poll(home)
    assert graph.calls == [(FOLLOWER, wake.inputs)]
    assert AutomationStore(home).get(wake.automation_id).retired_at
    # The subscription itself stays, and is never due on a clock.
    assert AutomationStore(home).get(sub.automation_id).retired_at == ""
    assert _wakes(home) == []


def test_the_universes_own_background_run_wakes_the_owner_bound_for_it(
    home: Path,
) -> None:
    """An automation run's actor is `universe:<id>`; the owner is bound for it.
    A universe run nobody was bound for wakes nothing: no principal is not a
    broadcast (Codex refute 2026-09-28, P1)."""
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    _finish(home, actor=f"universe:{UNIVERSE}", bound=OWNER, ended_by=None)
    _finish(home, actor=f"universe:{UNIVERSE}", bound=None, ended_by=OWNER)
    assert len(_wakes(home)) == 1


def test_only_the_transition_announces_a_run(home: Path) -> None:
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    run_id = _finish(home, actor=OWNER)
    # A later terminal write that only re-persists output is not a second end.
    update_run_status(home, run_id, status=RUN_STATUS_COMPLETED, output={"x": 1})
    assert len(_wakes(home)) == 1


def test_the_filter_selects_branch_and_outcome(home: Path) -> None:
    _subscribe(home, "run_completed",
               {"branch_def_id": FOLLOWED, "outcome": RUN_STATUS_FAILED})
    _finish(home, actor=OWNER)  # completed: no match
    _finish(home, actor=OWNER, status=RUN_STATUS_FAILED, branch_def_id=FOLLOWER)
    assert _wakes(home) == []
    _finish(home, actor=OWNER, status=RUN_STATUS_FAILED)
    [wake] = _wakes(home)
    assert wake.inputs["event"]["outcome"] == "failed"


def test_a_deploy_killed_run_is_announced_as_interrupted(home: Path) -> None:
    _subscribe(home, "run_completed",
               {"branch_def_id": FOLLOWED, "outcome": "interrupted"})
    run_id = _start(home, actor=f"universe:{UNIVERSE}", bound=OWNER)
    with _as(None):  # boot: no request is bound
        assert recover_in_flight_runs(home) == 1
    [wake] = _wakes(home)
    assert wake.inputs["event"]["run_id"] == run_id


def test_a_paused_subscription_does_not_wake(home: Path) -> None:
    sub = _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    AutomationStore(home).pause_for_reason(
        sub.automation_id, reason="owner", now=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc),
    )
    _finish(home, actor=OWNER)
    assert _wakes(home) == []


# -- The cross-user floor -------------------------------------------------------


def test_another_users_run_in_the_owners_universe_wakes_nothing(home: Path) -> None:
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    # Bob's own run recorded against Alice's universe.
    _finish(home, actor=BOB, queue_universe_id=UNIVERSE)
    # Alice's universe's run with Bob bound (a visitor-driven turn).
    _finish(home, actor=f"universe:{UNIVERSE}", bound=BOB)
    # Bob's plain run of a same-named branch: his home, not hers.
    _finish(home, actor=BOB)
    assert _wakes(home) == []
    assert _wakes(home, BOB_UNIVERSE) == []


def test_a_co_admin_sharing_the_home_wakes_only_their_own_subscriptions(
    home: Path,
) -> None:
    """Carol is an admin whose home is also Alice's universe. Her run must not
    spend Alice's subscription, and her own subscription is hers to wake."""
    carol = "acct_carol"
    _seed_owner(home, owner=carol)
    _seed_branch(home, branch_def_id="branch_carols", author=carol,
                 visibility="private")
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    _finish(home, actor=carol)
    assert _wakes(home) == []
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED}, owner=carol,
               branch_def_id="branch_carols")
    _finish(home, actor=carol)
    [wake] = _wakes(home)
    assert wake.owner_principal_id == carol


def test_a_recovered_run_wakes_only_its_own_owner_not_a_co_admin(
    home: Path,
) -> None:
    """Codex refute 2026-09-28, P1: Alice and Carol share a home, each following
    A. Alice's background run is recovered at boot with nobody bound; only
    Alice's subscription wakes."""
    carol = "acct_carol"
    _seed_owner(home, owner=carol)
    _seed_branch(home, branch_def_id="branch_carols", author=carol,
                 visibility="private")
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED}, owner=carol,
               branch_def_id="branch_carols")
    _start(home, actor=f"universe:{UNIVERSE}", bound=OWNER)
    with _as(None):
        assert recover_in_flight_runs(home) == 1
    assert [wake.owner_principal_id for wake in _wakes(home)] == [OWNER]


def test_a_cancelled_run_announces_nothing(home: Path) -> None:
    """Codex refute 2026-09-28, P1: a collaborator's cancel of the owner's run
    must not start the owner's follow-up work. Whoever cancels caused the end."""
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    _finish(home, actor=OWNER, bound=OWNER, status="cancelled", ended_by=BOB)
    assert _wakes(home) == []
    with pytest.raises(AutomationUnavailable) as caught:
        _subscribe(home, "run_completed",
                   {"branch_def_id": FOLLOWED, "outcome": "cancelled"})
    assert caught.value.reason == "event_filter_invalid"


def test_the_owners_run_in_another_universe_wakes_nothing(home: Path) -> None:
    _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    _finish(home, actor=OWNER, queue_universe_id=BOB_UNIVERSE)
    _finish(home, actor=f"universe:{BOB_UNIVERSE}", bound=OWNER)
    assert _wakes(home) == []


def test_a_subscription_whose_owner_lost_admin_records_why_and_stores_nothing(
    home: Path,
) -> None:
    from tinyassets.daemon_server import grant_universe_access

    sub = _subscribe(home, "run_completed", {"branch_def_id": FOLLOWED})
    grant_universe_access(home, universe_id=UNIVERSE, actor_id=OWNER,
                          permission="write", granted_by=OWNER)
    _finish(home, actor=f"universe:{UNIVERSE}", bound=OWNER)
    assert _wakes(home) == []
    from tinyassets.storage.assigned_queue_refusals import AssignedQueueRefusalStore

    reasons = AssignedQueueRefusalStore(home).fresh_reasons(
        universe_id=UNIVERSE, max_age_seconds=3600,
    )
    assert reasons[f"automation:{sub.automation_id}"] == (
        "event_wake_refused:owner_not_admin"
    )


# -- pending_request_answered -------------------------------------------------


def _owner_request():
    return identity_context(Identity(
        user_id=OWNER, username=OWNER, capabilities=["tinyassets.universe.write"],
    ))


def _ask(base: Path, title: str = "Which city?") -> str:
    """The agent raises a question in Alice's universe, as the connector does."""
    from tinyassets.api.pending_requests import request_from_user

    with _owner_request():
        out = request_from_user(universe_id=UNIVERSE, payload=json.dumps({
            "kind": "question", "title": title, "body": "Pick one.",
            "action": {"type": "answer"},
            "fields": [{"name": "city", "type": "text", "label": "City"}],
        }))
    assert out.get("request_id"), out
    return out["request_id"]


def test_answering_through_the_connector_wakes_the_subscribed_branch(
    home: Path, monkeypatch,
) -> None:
    from tinyassets.api.pending_requests import answer_request

    _subscribe(home, "pending_request_answered")
    request_id = _ask(home)
    with _owner_request():
        out = answer_request(universe_id=UNIVERSE, payload=json.dumps({
            "request_id": request_id, "values": {"city": "Lisbon"},
        }))
    assert out.get("status") == "answered", out

    [wake] = _wakes(home)
    assert wake.inputs["event"] == {
        "type": "pending_request_answered",
        "subscription_id": wake.inputs["event"]["subscription_id"],
        "request_id": request_id, "kind": "question", "status": "answered",
    }
    graph = _Graph()
    monkeypatch.setattr(automations_module, "_execute", graph)
    _poll(home)
    assert [branch for branch, _inputs in graph.calls] == [FOLLOWER]


def test_a_dismissal_by_the_owner_wakes_and_one_with_nobody_bound_does_not(
    home: Path,
) -> None:
    from tinyassets.storage.pending_requests import resolve_request

    _subscribe(home, "pending_request_answered", {"status": "dismissed"})
    first, second = _ask(home), _ask(home, title="Which country?")
    with _as(None):
        assert resolve_request(home / UNIVERSE, first, status="dismissed")
    assert _wakes(home) == []
    with _as(OWNER):
        assert resolve_request(home / UNIVERSE, second, status="dismissed")
    [wake] = _wakes(home)
    assert wake.owner_principal_id == OWNER


def test_an_answer_by_someone_else_wakes_nothing(home: Path) -> None:
    from tinyassets.storage.pending_requests import resolve_request

    _subscribe(home, "pending_request_answered")
    request_id = _ask(home)
    with _as(BOB):
        assert resolve_request(home / UNIVERSE, request_id, status="answered")
    assert _wakes(home) == []


def test_an_already_resolved_request_does_not_wake_twice(home: Path) -> None:
    from tinyassets.storage.pending_requests import resolve_request

    _subscribe(home, "pending_request_answered")
    request_id = _ask(home)
    with _as(OWNER):
        assert resolve_request(home / UNIVERSE, request_id, status="answered")
        assert not resolve_request(home / UNIVERSE, request_id, status="answered")
    assert len(_wakes(home)) == 1


# -- Registration ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("event_type", "event_filter", "extra", "reason"),
    [
        ("canon_change", None, {}, "event_type_unknown"),
        ("file_changed", None, {}, "event_type_unknown"),
        # A run_completed subscription must name the branch it follows.
        ("run_completed", None, {}, "event_filter_invalid"),
        ("run_completed", {"branch_def_id": FOLLOWED, "error": "x"}, {},
         "event_filter_invalid"),
        ("run_completed", {"branch_def_id": 3}, {}, "event_filter_invalid"),
        ("run_completed", {"branch_def_id": FOLLOWED}, {"interval_seconds": 600},
         "trigger_invalid"),
        ("pending_request_answered", None, {"not_before": "2026-10-01T00:00:00Z"},
         "trigger_invalid"),
    ],
)
def test_a_subscription_that_could_not_fire_is_refused(
    home: Path, event_type, event_filter, extra, reason,
) -> None:
    with pytest.raises(AutomationUnavailable) as caught:
        _subscribe(home, event_type, event_filter, **extra)
    assert caught.value.reason == reason
    assert AutomationStore(home).list(universe_id=UNIVERSE) == []


def test_a_subscription_is_never_due_on_a_clock(home: Path) -> None:
    from datetime import datetime, timedelta, timezone

    sub = _subscribe(home, "pending_request_answered")
    assert sub.trigger_kind == TRIGGER_EVENT
    later = datetime.now(timezone.utc) + timedelta(days=30)
    assert due_automations(home, universe_id=UNIVERSE, now=later) == []


def test_a_database_from_the_previous_build_gains_the_event_kind(
    tmp_path: Path, home: Path,
) -> None:
    """The stored CHECK predates `event`; connecting rebuilds it, keeping rows."""
    db = AutomationStore(home).db_path
    db.unlink(missing_ok=True)
    old_table = automations_module._AUTOMATIONS_TABLE.replace(
        ",'event'", ""
    ).replace("__TABLE__", "automations")
    assert "'event'" not in old_table
    with sqlite3.connect(db) as conn:
        conn.executescript(old_table)
        conn.execute(
            "INSERT INTO automations (automation_id, universe_id, "
            "owner_principal_id, name, branch_def_id, trigger_kind, "
            "desired_state, created_at, updated_at) VALUES "
            "('old', ?, ?, 'n', ?, 'interval', 'active', 't', 't')",
            (UNIVERSE, OWNER, FOLLOWER),
        )
    sub = _subscribe(home, "pending_request_answered")
    ids = {row.automation_id for row in AutomationStore(home).list(universe_id=UNIVERSE)}
    assert ids == {"old", sub.automation_id}


def test_the_connector_surface_creates_and_projects_a_subscription(home: Path) -> None:
    from tinyassets.api.automations import automations

    with identity_context(Identity(
        user_id=OWNER, username=OWNER,
        capabilities=["tinyassets.universe.write", "tinyassets.universe.admin"],
    )):
        out = automations(action="create", universe_id=UNIVERSE, payload=json.dumps({
            "name": "after research", "branch_def_id": FOLLOWER,
            "event_type": "run_completed",
            "event_filter": {"branch_def_id": FOLLOWED},
        }))
        refused = automations(action="create", universe_id=UNIVERSE, payload=json.dumps({
            "name": "x", "branch_def_id": FOLLOWER, "event_type": "run_completed",
        }))
    assert out["status"] == "automation_created", out
    trigger = out["automation"]["trigger"]
    assert (trigger["kind"], trigger["event_type"], trigger["event_filter"]) == (
        "event", "run_completed", {"branch_def_id": FOLLOWED},
    )
    assert out["automation"]["next_due_at"] == ""
    assert refused["reason"] == "event_filter_invalid"
    assert "branch_def_id (required)" in refused["detail"]

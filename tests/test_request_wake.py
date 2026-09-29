"""`write_graph target="request"` asks the owner's own universe to run its loop once.

A request is a one-shot (`once`) automation of the universe's declared loop
branch, due now, registered through the real `register_automation` and fired by
the real consumer pump. The only substitute is `_execute`, the seam
`tinyassets.automations` names for tests: it records the graph a wake would run
and the inputs it would get, and never fakes the scheduling or the checks.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.automations as automations_module
import tinyassets.universe_server as universe_server
from tests.cloud_runtime_fixture import cloud_runtime  # noqa: F401
from tests.test_automations import OWNER, UNIVERSE, _FakeOutcome, _seed_branch, _seed_owner
from tests.test_background_budget_finalization_e2e import _seed_serving_assignment
from tests.test_node_scheduled_wake import _poll, _wakes
from tinyassets.api import universe as universe_api
from tinyassets.auth.middleware import identity_context
from tinyassets.auth.provider import Identity
from tinyassets.automations import AutomationStore

pytestmark = pytest.mark.usefixtures("cloud_runtime")

LOOP = "branch_owners_loop"
BOB = "acct_bob"


@pytest.fixture(autouse=True)
def _pin_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))


@pytest.fixture
def home(tmp_path: Path, monkeypatch) -> Path:
    """Alice's serving home, whose declared loop is a private branch she wrote."""
    monkeypatch.setenv("TINYASSETS_ASSIGNED_QUEUE_CONSUMER", "1")
    _seed_serving_assignment(tmp_path)
    _seed_owner(tmp_path)
    _seed_branch(tmp_path, branch_def_id=LOOP, visibility="private")
    monkeypatch.setattr(
        universe_api, "_universe_loop_dispatch", lambda _udir: (LOOP, {"mode": "v2"}),
    )
    monkeypatch.setattr(
        "tinyassets.provider_serving_binding.list_serving_universes",
        lambda _base: [UNIVERSE],
    )
    return tmp_path


class _Graph:
    """The `_execute` seam: records each fired wake's branch and inputs."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, base_path, automation, provider_call, branch, inputs,
                 on_run_started=None):
        self.calls.append((automation.branch_def_id, dict(inputs)))
        return _FakeOutcome(run_id=f"run_{len(self.calls)}")


def _request(actor: str, *, key: str = "request-key-0001", **fields) -> dict:
    body = {
        "target": "request",
        "idempotency_key": key,
        "graph_id": UNIVERSE,
        "text": "Summarise today's ledger.",
        "request_type": "general",
    }
    body.update(fields)
    with identity_context(Identity(user_id=actor, username=actor)):
        return json.loads(universe_server.write_graph(**body))


def test_the_owners_request_runs_the_loop_once_with_the_text(home: Path, monkeypatch) -> None:
    graph = _Graph()
    monkeypatch.setattr(automations_module, "_execute", graph)

    result = _request(OWNER)

    assert result["status"] == "accepted", result
    assert result["idempotent_replay"] is False
    [wake] = _wakes(home)
    assert wake.automation_id == result["automation_id"]
    assert wake.branch_def_id == LOOP and wake.owner_principal_id == OWNER
    _poll(home)
    _poll(home)
    assert graph.calls == [
        (LOOP, {"request": "Summarise today's ledger.", "request_type": "general"}),
    ]


def test_a_replay_returns_the_first_wake_and_does_not_wake_twice(
    home: Path, monkeypatch,
) -> None:
    graph = _Graph()
    monkeypatch.setattr(automations_module, "_execute", graph)

    first = _request(OWNER)
    replay = _request(OWNER)

    assert replay["automation_id"] == first["automation_id"]
    assert replay["idempotent_replay"] is True
    assert len(_wakes(home)) == 1
    _poll(home)
    # Replayed after it ran: still the one wake, and nothing fires again.
    after = _request(OWNER)
    _poll(home)
    assert after["automation_id"] == first["automation_id"]
    assert len(graph.calls) == 1


def test_the_same_key_with_a_different_body_is_a_conflict(home: Path) -> None:
    _request(OWNER)

    conflict = _request(OWNER, text="Something else entirely.")

    assert conflict == {"error": "idempotency_key_body_conflict", "universe_id": UNIVERSE}
    assert len(_wakes(home)) == 1


def test_another_user_cannot_spend_the_owners_compute(home: Path) -> None:
    from tinyassets.daemon_server import grant_universe_access

    # Even with write on Alice's universe.
    grant_universe_access(home, universe_id=UNIVERSE, actor_id=BOB, permission="write",
                          granted_by=OWNER)

    refused = _request(BOB)

    assert refused == {"error": "request_owner_only", "universe_id": UNIVERSE}
    assert _wakes(home) == []


def test_two_owners_keys_never_name_the_same_wake() -> None:
    """The id is domain-separated and length-prefixed per field: no choice of
    key reaches another owner's or universe's wake."""
    derive = universe_api._request_wake_id
    base = derive(owner="acct_alice", universe_id="u1", idempotency_key="k" * 16)
    assert base != derive(owner="acct_bob", universe_id="u1", idempotency_key="k" * 16)
    assert base != derive(owner="acct_alice", universe_id="u2", idempotency_key="k" * 16)
    # Moving characters between fields changes the id.
    assert derive(owner="ab", universe_id="c", idempotency_key="d" * 16) != derive(
        owner="a", universe_id="bc", idempotency_key="d" * 16)


@pytest.mark.parametrize("field,value", [
    ("priority_weight", 5.0),
    ("directed_daemon_id", "daemon-1"),
    ("directed_daemon_instruction", "do it"),
    ("pickup_incentive", "a coffee"),
])
def test_a_retired_queue_field_is_refused_not_ignored(home: Path, field, value) -> None:
    refused = _request(OWNER, **{field: value})

    assert refused == {"error": f"request_field_retired:{field}"}
    assert _wakes(home) == []


def test_an_invalid_key_stores_nothing(home: Path) -> None:
    assert _request(OWNER, key="short") == {"error": "request_validation_error"}
    assert AutomationStore(home).list(universe_id=UNIVERSE) == []


def test_a_request_task_left_pending_is_cancelled_with_its_reason(tmp_path: Path) -> None:
    """The retired queue's pending rows keep a recorded disposition."""
    import sqlite3
    from contextlib import closing

    from tests.test_branch_tasks_v2 import _commit
    from tinyassets.daemon_server import initialize_author_server
    from tinyassets.storage import db_path
    from tinyassets.storage.request_admissions import (
        REQUEST_RETIRED_REASON,
        RequestAdmissionStore,
    )

    initialize_author_server(tmp_path)
    committed = _commit(tmp_path)
    store = RequestAdmissionStore(tmp_path)

    assert store.retire_pending_request_tasks() == [committed["branch_task_id"]]
    assert store.retire_pending_request_tasks() == []  # idempotent

    with closing(sqlite3.connect(db_path(tmp_path))) as conn:
        status = conn.execute(
            "SELECT status FROM branch_tasks_v2 WHERE branch_task_id = ?",
            (committed["branch_task_id"],),
        ).fetchone()[0]
        details = [json.loads(row[0]) for row in conn.execute(
            "SELECT detail_json FROM request_admission_events WHERE branch_task_id = ?",
            (committed["branch_task_id"],),
        )]
    assert status == "cancelled"
    assert {"reason": REQUEST_RETIRED_REASON} in details


def test_concurrent_identical_requests_charge_once_and_report_one_new(
    home: Path, monkeypatch,
) -> None:
    """Of racing retries, exactly one is new and exactly one is charged."""
    import threading

    import tinyassets.engine_mcp_server as engine

    charges: list[str] = []
    real_admit = engine._engine_run_admit

    def counting_admit(**kwargs):
        charges.append(kwargs.get("universe_id", ""))
        return real_admit(**kwargs)

    monkeypatch.setattr(engine, "_engine_run_admit", counting_admit)
    barrier = threading.Barrier(4)
    results: list[dict] = []

    def send() -> None:
        barrier.wait(timeout=10)
        results.append(_request(OWNER))

    threads = [threading.Thread(target=send) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    assert len(results) == 4 and all(r.get("status") == "accepted" for r in results), results
    assert len({r["automation_id"] for r in results}) == 1
    assert sorted(r["idempotent_replay"] for r in results) == [False, True, True, True]
    assert len(charges) == 1
    assert len(_wakes(home)) == 1


def test_a_replay_is_a_receipt_even_when_the_universe_cannot_run_now(home: Path) -> None:
    """Retrieving the first wake needs owner authority, not a ready assignment."""
    first = _request(OWNER)
    import tinyassets.provider_assignment as assignment_module

    real = assignment_module.load_provider_assignment
    try:
        assignment_module.load_provider_assignment = lambda *_a, **_k: None
        replay = _request(OWNER)
    finally:
        assignment_module.load_provider_assignment = real

    assert replay["automation_id"] == first["automation_id"]
    assert replay["idempotent_replay"] is True


def test_an_unencodable_field_is_a_validation_error(home: Path) -> None:
    assert _request(OWNER, branch_id="\ud800") == {"error": "request_validation_error"}
    assert _wakes(home) == []


def test_the_mutation_ledger_names_the_wake() -> None:
    target, _summary, meta = universe_api._extract_submit_request(
        {"text": "hi", "request_type": "general"},
        {"automation_id": "req_abc", "idempotent_replay": False},
    )
    assert target == "req_abc"
    assert meta["idempotent_replay"] is False


def test_a_retry_that_misses_the_early_lookup_is_neither_charged_nor_new(
    home: Path, monkeypatch,
) -> None:
    """The race window, made deterministic: the retry's early lookup misses the
    row, so only the locked insert can see it."""
    import tinyassets.engine_mcp_server as engine

    first = _request(OWNER)
    charges: list[str] = []
    monkeypatch.setattr(engine, "_engine_run_admit",
                        lambda **kwargs: charges.append("charged") or True)
    monkeypatch.setattr(AutomationStore, "get", lambda self, automation_id: None)

    retry = _request(OWNER)

    assert retry["automation_id"] == first["automation_id"]
    assert retry["idempotent_replay"] is True
    assert charges == []

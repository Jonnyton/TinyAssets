"""The executor that makes an automation more than a stored row.

Live 2026-08-08: an active daily automation existed, its run completed, and
(1) nothing would ever fire the next cadence — no process read
``cadence_seconds`` — and (2) the finished run's output was never posted to
``deliver_to``; the founder's last message from the platform was "It's
running!". These tests pin both halves: due automations FIRE, finished runs
DELIVER, and both are idempotent.
"""
from __future__ import annotations

import json

import pytest

from tinyassets.scheduled_work_executor import (
    ScheduledWorkExecutor,
    _delivery_body,
    _slack_address,
)
from tinyassets.storage.scheduled_work import ScheduledWorkStore


@pytest.fixture
def base(tmp_path):
    from tinyassets.daemon_server import initialize_author_server

    initialize_author_server(str(tmp_path))
    return tmp_path


@pytest.fixture
def store(base):
    return ScheduledWorkStore(base)


def _automation(store, *, name="daily_brief", deliver_to="slack:T1:D1", **over):
    kwargs = dict(
        universe_id="u-a", name=name, kind="briefing",
        branch_def_id="abc123", inputs_json='{"topic": "agents"}',
        cadence_seconds=3600, declared_operations=["llm_inference"],
        owner_id="user_1", deliver_to=deliver_to,
    )
    kwargs.update(over)
    item = store.create(**kwargs)
    return store.set_state(
        universe_id=item.universe_id, work_id=item.work_id,
        state="active", expected_revision=item.revision,
    )


# -- store: due + undelivered ------------------------------------------------

def test_never_run_active_automation_is_due(store):
    item = _automation(store)
    due = store.list_due(now=1000.0)
    assert [d.work_id for d in due] == [item.work_id]


def test_paused_automation_is_never_due(store):
    item = _automation(store)
    store.set_state(universe_id="u-a", work_id=item.work_id,
                    state="paused", expected_revision=item.revision)
    assert store.list_due(now=1e12) == []


def test_recently_run_automation_is_not_due_until_cadence_elapses(store):
    item = _automation(store)
    store.record_run(universe_id="u-a", work_id=item.work_id, run_id="r1")
    ran_at = store.get(universe_id="u-a", work_id=item.work_id).last_run_at
    assert store.list_due(now=ran_at + 10) == []
    assert [d.work_id for d in store.list_due(now=ran_at + 3600)] == [item.work_id]


def test_undelivered_lists_runs_awaiting_delivery_even_when_paused(store):
    """Pausing after a run fired must not swallow a result already paid for."""
    item = _automation(store)
    store.record_run(universe_id="u-a", work_id=item.work_id, run_id="r1")
    store.set_state(universe_id="u-a", work_id=item.work_id,
                    state="paused", expected_revision=item.revision)
    assert [u.last_run_id for u in store.list_undelivered()] == ["r1"]
    store.record_delivery(universe_id="u-a", work_id=item.work_id, run_id="r1")
    assert store.list_undelivered() == []


# -- executor: fire ----------------------------------------------------------

def _executor(base, *, run=None, get_run=None, post=None, now=None):
    return ScheduledWorkExecutor(
        base,
        run=run or (lambda item: json.dumps({"run_id": "r_fired"})),
        get_run=get_run or (lambda b, rid: None),
        post=post or (lambda uid, addr, body: None),
        now=now or (lambda: 5000.0),
    )


def test_sweep_fires_due_automation_and_records_run(base, store):
    item = _automation(store)
    fired = []
    ex = _executor(base, run=lambda it: (fired.append(it.work_id),
                                         json.dumps({"run_id": "r9"}))[1])
    counts = ex.sweep()
    assert counts["fired"] == 1
    assert fired == [item.work_id]
    assert store.get(universe_id="u-a", work_id=item.work_id).last_run_id == "r9"


def test_sweep_does_not_refire_within_cadence(base, store):
    _automation(store)
    calls = []
    ex = _executor(base, run=lambda it: (calls.append(1),
                                         json.dumps({"run_id": "r1"}))[1])
    ex.sweep()
    ex.sweep()
    assert len(calls) == 1


def test_failed_handoff_backs_off_to_next_cadence_not_next_sweep(base, store):
    """A branch that cannot even start must not become a 30s retry loop —
    both failure shapes (a hard raise, and a hand-off that returned no run id)
    record an attempt and wait out the cadence."""
    item = _automation(store)

    def boom(_item):
        raise RuntimeError("provider exploded")

    ex = _executor(base, run=boom)
    assert ex.sweep()["fired"] == 0
    row = store.get(universe_id="u-a", work_id=item.work_id)
    assert row.last_run_id.startswith("unstarted_")
    calls = []
    ex2 = _executor(base, run=lambda it: (calls.append(1), "not json")[1])
    assert ex2.sweep()["fired"] == 0
    assert calls == []  # backed off — not retried within the cadence


# -- executor: deliver -------------------------------------------------------

def _completed_record(run_id="r1", output=None, inputs=None, status="completed",
                      error=""):
    return {
        "run_id": run_id, "status": status, "error": error,
        "inputs": inputs if inputs is not None else {"topic": "agents"},
        "output": output if output is not None else {
            "topic": "agents", "briefing": "• thing one\n• thing two",
        },
    }


def test_finished_run_is_delivered_once_to_deliver_to(base, store):
    item = _automation(store)
    store.record_run(universe_id="u-a", work_id=item.work_id, run_id="r1")
    posts = []
    ex = _executor(
        base,
        get_run=lambda b, rid: _completed_record(rid),
        post=lambda uid, addr, body: posts.append((uid, addr, body)),
    )
    assert ex.sweep()["delivered"] == 1
    assert ex.sweep()["delivered"] == 0  # idempotent: marked delivered
    (uid, addr, body), = posts
    assert uid == "u-a"
    assert addr == "D1"
    assert "thing one" in body
    assert "daily_brief" in body


def test_delivery_excludes_the_runs_inputs(base, store):
    item = _automation(store)
    store.record_run(universe_id="u-a", work_id=item.work_id, run_id="r1")
    posts = []
    ex = _executor(
        base,
        get_run=lambda b, rid: _completed_record(rid),
        post=lambda uid, addr, body: posts.append(body),
    )
    ex.sweep()
    assert "agents" not in posts[0].replace("daily_brief", "")


def test_failed_run_is_delivered_as_a_failure_notice(base, store):
    """Silence is the one output a founder must never receive."""
    item = _automation(store)
    store.record_run(universe_id="u-a", work_id=item.work_id, run_id="r1")
    posts = []
    ex = _executor(
        base,
        get_run=lambda b, rid: _completed_record(
            rid, status="failed", error="node 'gather' timed out"),
        post=lambda uid, addr, body: posts.append(body),
    )
    assert ex.sweep()["delivered"] == 1
    assert "FAILED" in posts[0]
    assert "timed out" in posts[0]


def test_still_running_run_is_not_delivered_and_not_marked(base, store):
    item = _automation(store)
    store.record_run(universe_id="u-a", work_id=item.work_id, run_id="r1")
    ex = _executor(base, get_run=lambda b, rid: _completed_record(
        rid, status="running"))
    assert ex.sweep()["delivered"] == 0
    assert [u.last_run_id for u in store.list_undelivered()] == ["r1"]


def test_failed_post_retries_next_sweep(base, store):
    item = _automation(store)
    store.record_run(universe_id="u-a", work_id=item.work_id, run_id="r1")
    posts = []

    def flaky(uid, addr, body):
        if not posts:
            posts.append("failed")
            raise RuntimeError("slack 500")
        posts.append(body)

    ex = _executor(base, get_run=lambda b, rid: _completed_record(rid),
                   post=flaky)
    assert ex.sweep()["delivered"] == 0
    assert ex.sweep()["delivered"] == 1  # not marked on failure -> retried


def test_undeliverable_destination_is_marked_and_logged_not_looped(base, store):
    item = _automation(store, deliver_to="carrier-pigeon")
    store.record_run(universe_id="u-a", work_id=item.work_id, run_id="r1")
    posts = []
    ex = _executor(base, get_run=lambda b, rid: _completed_record(rid),
                   post=lambda *a: posts.append(a))
    assert ex.sweep()["delivered"] == 0
    assert posts == []
    assert store.list_undelivered() == []  # marked, never retried


# -- body + address ----------------------------------------------------------

def test_delivery_body_single_output_is_clean():
    class Item:
        name = "daily_brief"
        last_run_id = "r1"

    body = _delivery_body(Item(), _completed_record())
    assert body.startswith("*daily_brief*:")
    assert "thing one" in body


def test_delivery_body_empty_output_says_so_loudly():
    class Item:
        name = "daily_brief"
        last_run_id = "r1"

    body = _delivery_body(Item(), _completed_record(output={"topic": "agents"}))
    assert "produced no output" in body


@pytest.mark.parametrize("value,expected", [
    ("slack:T0BN5LK57FT:U0BMXFK83UK", "U0BMXFK83UK"),
    ("slack:T1:D0BMPBUBBSB", "D0BMPBUBBSB"),
    ("D0BMPBUBBSB", "D0BMPBUBBSB"),
    ("", ""),
    ("carrier-pigeon", ""),
    ("mailto:x@y.z", ""),
])
def test_slack_address_parsing(value, expected):
    assert _slack_address(value) == expected

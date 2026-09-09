"""Scheduler integration over real stores; graph execution is substituted."""
import json
import sqlite3
from datetime import timedelta

import tinyassets.automations as scheduler
import tinyassets.runs as runs
from tests.test_automations import (
    NOW,
    UNIVERSE,
    _FakeOutcome,
    _pin_data_dir,  # noqa: F401 - fixture
    registered,  # noqa: F401 - fixture
)


def test_ticks_recover_new_context_and_previous_output(tmp_path, registered, monkeypatch):
    store = scheduler.AutomationStore(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE automations SET inputs_json = ? WHERE automation_id = ?",
            (json.dumps({"context": {"$automation_context": "v1"}}),
             registered.automation_id),
        )
    # Deliberately pass the stale caller object: recovery must read persisted inputs.
    root = tmp_path / UNIVERSE
    (root / "body.md").write_text("first intent")
    seen = []
    records = {}

    def execute(base, automation, provider, branch, inputs, on_run_started=None):
        seen.append(inputs["context"])
        run_id = "context_run_" + str(len(seen))
        records[run_id] = {
            "run_id": run_id, "queue_universe_id": UNIVERSE,
            "branch_def_id": registered.branch_def_id, "status": "completed",
            "output": {"context": inputs["context"], "artifact": "retained result"},
        }
        return _FakeOutcome(run_id)

    monkeypatch.setattr(scheduler, "_execute", execute)
    monkeypatch.setattr(runs, "get_run", lambda base, run_id: records.get(run_id))
    first_due = (NOW + timedelta(seconds=600)).isoformat()
    assert scheduler.run_due_automation(
        tmp_path, registered, first_due, now=NOW
    ) == "ok:ran:context_run_1"
    (root / "body.md").write_text("updated intent")
    second_due = (NOW + timedelta(seconds=1200)).isoformat()
    assert scheduler.run_due_automation(
        tmp_path, registered, second_due, now=NOW + timedelta(seconds=1200)
    ) == "ok:ran:context_run_2"
    assert seen[0]["previous_run"] is None
    assert seen[0]["brain"]["body.md"]["text"] == "first intent"
    assert seen[1]["brain"]["body.md"]["text"] == "updated intent"
    assert seen[1]["previous_run"]["run_id"] == "context_run_1"
    assert seen[1]["previous_run"]["output"] == {"artifact": "retained result"}
    assert scheduler.run_due_automation(
        tmp_path, registered, second_due, now=NOW + timedelta(seconds=1200)
    ) == "attempt_exists"
    assert len(seen) == 2


def test_corrupt_context_never_reaches_execution(tmp_path, registered, monkeypatch):
    store = scheduler.AutomationStore(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE automations SET inputs_json = ? WHERE automation_id = ?",
            (json.dumps({"context": {"$automation_context": "v1"}}),
             registered.automation_id),
        )
    (tmp_path / UNIVERSE / ".conversation_memory.db").write_text("corrupt")
    calls = []
    monkeypatch.setattr(scheduler, "_execute", lambda *a: calls.append(a))
    reason = scheduler.run_due_automation(
        tmp_path, registered, (NOW + timedelta(seconds=600)).isoformat(), now=NOW
    )
    assert reason.startswith("automation_error")
    assert calls == []
    assert store.get(registered.automation_id).consecutive_failures == 1

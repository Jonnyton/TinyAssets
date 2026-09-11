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
    assert reason == "context_unavailable"
    assert calls == []
    assert store.get(registered.automation_id).consecutive_failures == 1

def _repair_context_case(tmp_path, registered, monkeypatch, with_checkpoint):
    import tinyassets.engine_mcp_server as engine
    store = scheduler.AutomationStore(tmp_path)
    with sqlite3.connect(store.db_path) as conn:
        conn.execute(
            "UPDATE automations SET inputs_json = ? WHERE automation_id = ?",
            (json.dumps({"context": {"$automation_context": "v1"}}),
             registered.automation_id),
        )
    seen, records, admissions = [], {}, []
    original_admit = engine._engine_run_admit

    def admit(*args, **kwargs):
        admissions.append(True)
        return original_admit(*args, **kwargs)

    def execute(base, automation, provider, branch, inputs, on_run_started=None):
        seen.append(inputs["context"])
        run_id = "repair_run_" + str(len(seen))
        records[run_id] = {
            "run_id": run_id, "queue_universe_id": UNIVERSE,
            "branch_def_id": registered.branch_def_id, "status": "completed",
            "output": {"progress": {"completed": {"one": "retained"}}},
        }
        return _FakeOutcome(run_id)

    monkeypatch.setattr(engine, "_engine_run_admit", admit)
    monkeypatch.setattr(scheduler, "_execute", execute)
    monkeypatch.setattr(runs, "get_run", lambda base, run_id: records.get(run_id))

    def tick(seconds):
        at = NOW + timedelta(seconds=seconds)
        return scheduler.run_due_automation(
            tmp_path, store.get(registered.automation_id), at.isoformat(), now=at
        )

    if with_checkpoint:
        assert tick(600) == "ok:ran:repair_run_1"
    database = tmp_path / UNIVERSE / ".conversation_memory.db"
    database.write_text("temporarily corrupt")
    admitted_before = len(admissions)
    assert tick(1200) == "context_unavailable"
    assert len(admissions) == admitted_before
    assert len(seen) == int(with_checkpoint)
    database.unlink()
    assert tick(1800) == "ok:ran:repair_run_" + str(1 + int(with_checkpoint))
    assert store.get(registered.automation_id).consecutive_failures == 0
    if with_checkpoint:
        assert seen[-1]["last_completed_run"]["output"]["progress"]["completed"] == {"one": "retained"}
    else:
        assert seen[-1]["last_completed_run"] is None


def test_checkpoint_recovers_after_context_repair(tmp_path, registered, monkeypatch):
    _repair_context_case(tmp_path, registered, monkeypatch, True)


def test_first_wake_recovers_after_context_repair(tmp_path, registered, monkeypatch):
    _repair_context_case(tmp_path, registered, monkeypatch, False)

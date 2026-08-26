"""Tests for the trajectory supervisor.

The load-bearing ones are the NEGATIVE cases. A stagnation detector that cries
wolf gets ignored, and an ignored supervisor is worse than none — it costs
tokens and trains the reader to skip its output.

`test_reset_shaped_session_does_not_trip` is Codex's refutation of the original
design kept as an executable test: it argued a zero-product-churn predicate
would flag legitimate spec, docs, and security work, *including the harness
reset that introduced this file*. That objection is why the predicate measures
repetition without progress instead of which directories a commit touched.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def load():
    path = REPO_ROOT / "scripts" / "supervisor.py"
    spec = importlib.util.spec_from_file_location("supervisor_under_test", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sup(tmp_path, monkeypatch):
    mod = load()
    store = tmp_path / "events.jsonl"
    monkeypatch.setattr(mod, "EVENTS", store)
    mod._STORE = store
    return mod


def write(mod, events):
    lines = [json.dumps(e) for e in events]
    mod.EVENTS.parent.mkdir(parents=True, exist_ok=True)
    mod.EVENTS.write_text("\n".join(lines) + "\n", encoding="utf-8")


def cmd_event(mod, command, code, ts=0.0):
    return {
        "ts": ts, "kind": "command", "target": "",
        "detail": {
            "normalized": mod.normalize_command(command),
            "signature": mod.command_signature(command),
            "exit_code": code,
        },
    }


# ------------------------------------------------------------ normalization


def test_volatile_fragments_collapse_to_one_signature(sup):
    """Two runs of the same failing test must hash the same.

    Without this a stuck loop looks like N distinct commands and the predicate
    never fires -- the failure mode that makes stagnation detection useless.
    """
    a = "pytest tests/test_x.py --basetemp=/tmp/pytest-of-me/pytest-1 2026-08-25 10:00:00"
    b = "pytest tests/test_x.py --basetemp=/tmp/pytest-of-me/pytest-9 2026-08-26 11:30:00"

    assert sup.command_signature(a) == sup.command_signature(b)


def test_different_commands_keep_different_signatures(sup):
    assert sup.command_signature("pytest tests/a.py") != sup.command_signature(
        "pytest tests/b.py"
    )


def test_uninteresting_commands_are_not_tracked(sup):
    assert sup.is_interesting("pytest tests/x.py")
    assert sup.is_interesting("python scripts/invariants_run.py --check-all")
    assert not sup.is_interesting("ls -la")
    assert not sup.is_interesting("cat README.md")


# -------------------------------------------------------------- predicates


def test_repeat_failure_trips_at_three(sup):
    """Matches AGENTS.md's own prose rule: stuck 3+ iterations."""
    write(sup, [cmd_event(sup, "pytest tests/test_x.py", 1, ts=i) for i in range(3)])

    findings = sup.check()

    assert [f.predicate for f in findings] == ["repeat_failure"]
    assert findings[0].evidence["count"] == 3
    assert "peer-agents" in findings[0].redirect


def test_two_failures_do_not_trip(sup):
    write(sup, [cmd_event(sup, "pytest tests/test_x.py", 1, ts=i) for i in range(2)])

    assert sup.check() == []


def test_repeated_success_never_trips(sup):
    """Re-running a passing command is a workflow, not a loop."""
    write(sup, [cmd_event(sup, "pytest tests/test_x.py", 0, ts=i) for i in range(10)])

    assert sup.check() == []


def test_same_command_different_exit_codes_does_not_trip(sup):
    """Changing failure modes means progress, even if it still fails."""
    write(sup, [
        cmd_event(sup, "pytest tests/test_x.py", 1, ts=0),
        cmd_event(sup, "pytest tests/test_x.py", 2, ts=1),
        cmd_event(sup, "pytest tests/test_x.py", 4, ts=2),
    ])

    assert sup.check() == []


def test_a_commit_resets_repeat_failure(sup):
    """Landing work clears the slate -- the predicate is about being stuck."""
    write(sup, [
        cmd_event(sup, "pytest tests/test_x.py", 1, ts=0),
        cmd_event(sup, "pytest tests/test_x.py", 1, ts=1),
        {"ts": 2, "kind": "commit", "target": "", "detail": {}},
        cmd_event(sup, "pytest tests/test_x.py", 1, ts=3),
    ])

    assert sup.check() == []


def test_edit_thrash_trips_on_repeated_edits_without_a_commit(sup):
    write(sup, [
        {"ts": i, "kind": "edit", "target": "tinyassets/api/universe.py", "detail": {}}
        for i in range(5)
    ])

    findings = sup.check()

    assert [f.predicate for f in findings] == ["edit_thrash"]
    assert findings[0].evidence["file"] == "tinyassets/api/universe.py"


def test_edits_spread_across_files_do_not_trip(sup):
    """Broad work is not thrash. Only the SAME file repeating counts."""
    write(sup, [
        {"ts": i, "kind": "edit", "target": f"tinyassets/mod_{i}.py", "detail": {}}
        for i in range(12)
    ])

    assert [f.predicate for f in sup.check()] == []


def test_no_landing_trips_after_many_calls_without_a_commit(sup):
    write(sup, [
        {"ts": i, "kind": "edit", "target": f"f{i}.py", "detail": {}}
        for i in range(sup.NO_LANDING_CALLS)
    ])

    assert "no_landing" in [f.predicate for f in sup.check()]


def test_no_landing_resets_on_commit(sup):
    events = [{"ts": i, "kind": "edit", "target": f"f{i}.py", "detail": {}}
              for i in range(sup.NO_LANDING_CALLS)]
    events.append({"ts": 999, "kind": "commit", "target": "", "detail": {}})
    write(sup, events)

    assert "no_landing" not in [f.predicate for f in sup.check()]


# ----------------------------------------------------- Codex's refutation


def test_reset_shaped_session_does_not_trip(sup):
    """Codex's objection, kept executable.

    A long docs/spec/security lane that commits steadily is WORKING. The
    original predicate (N consecutive commits with zero product-line churn)
    would have flagged exactly this shape -- the harness reset itself, which
    committed docs, audits, and skills for hours. Nothing here may trip.
    """
    events = []
    ts = 0
    for lane in range(8):
        for step in range(6):
            events.append({"ts": ts, "kind": "edit",
                           "target": f"docs/audits/2026-08-25-note-{lane}.md",
                           "detail": {}})
            ts += 1
        events.append(cmd_event(sup, "python scripts/invariants_run.py --check-all", 0, ts=ts))
        ts += 1
        events.append({"ts": ts, "kind": "commit", "target": "", "detail": {}})
        ts += 1
    write(sup, events)

    assert sup.check() == [], "a committing docs lane must never read as stagnation"


def test_empty_log_is_quiet(sup):
    assert sup.check() == []


def test_corrupt_lines_are_skipped_not_fatal(sup):
    sup.EVENTS.parent.mkdir(parents=True, exist_ok=True)
    sup.EVENTS.write_text(
        "not json\n" + json.dumps({"ts": 1, "kind": "commit", "detail": {}}) + "\n",
        encoding="utf-8",
    )

    assert sup.check() == []


# ------------------------------------------------------------- store rules


def test_record_never_raises_on_unwritable_store(sup, monkeypatch):
    """A broken recorder must not be able to break a turn."""
    monkeypatch.setattr(sup, "EVENTS", Path("/nonexistent-root/x/events.jsonl"))

    sup.record("edit", "a.py")  # must not raise


def test_retention_drops_events_past_the_age_bound(sup):
    now = 1_000_000.0
    old = [{"ts": now - sup.MAX_AGE_SECONDS - 10, "kind": "edit",
            "target": "old.py", "detail": {}} for _ in range(300)]
    write(sup, old)

    sup.record("edit", "new.py", now=now)

    kept = sup.load()
    assert all(e["target"] == "new.py" for e in kept), "stale events must be pruned"


def test_retention_caps_event_count(sup):
    now = 1_000_000.0
    write(sup, [{"ts": now, "kind": "edit", "target": f"f{i}.py", "detail": {}}
                for i in range(sup.MAX_EVENTS + 500)])

    sup.record("edit", "latest.py", now=now)

    assert len(sup.load()) <= sup.MAX_EVENTS

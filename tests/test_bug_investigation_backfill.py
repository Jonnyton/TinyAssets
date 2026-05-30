"""Autonomous backlog intake — backfill_investigations.

The daemon re-enqueues UNRESOLVED bug_investigation work itself (no hand-feeding):
a bug with no succeeded run, nothing in-flight, and < retry-cap failures against
the current canonical gets a fresh dispatcher request. Resolved (succeeded) bugs
are never re-driven; loop version is not part of the dedup.
"""

from __future__ import annotations

import uuid

from workflow.branch_tasks import BranchTask, append_task, read_queue
from workflow.bug_investigation import (
    REQUEST_TYPE_BUG_INVESTIGATION,
    backfill_investigations,
)

CANON = "v5canonbranchdef"
OLD = "oldcheatbranchdef"


def _set(monkeypatch, **env):
    monkeypatch.setenv("WORKFLOW_BUG_INVESTIGATION_BACKFILL", "on")
    monkeypatch.setenv("WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", CANON)
    monkeypatch.delenv("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", raising=False)
    monkeypatch.delenv("WORKFLOW_REQUEST_TYPE_PRIORITIES", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def _task(bug_id, status, *, branch_def_id=CANON, tid=None,
          rtype=REQUEST_TYPE_BUG_INVESTIGATION):
    return BranchTask(
        branch_task_id=tid or str(uuid.uuid4()),
        branch_def_id=branch_def_id,
        universe_id="u",
        inputs={"bug_id": bug_id, "title": "t", "component": "workflow/x.py"},
        status=status,
        request_type=rtype,
        trigger_source="owner_queued",
    )


def _canon_pending(tmp_path):
    return [t for t in read_queue(tmp_path)
            if t.branch_def_id == CANON and t.status == "pending"]


def test_flag_off_is_noop(tmp_path, monkeypatch):
    monkeypatch.delenv("WORKFLOW_BUG_INVESTIGATION_BACKFILL", raising=False)
    monkeypatch.setenv("WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", CANON)
    append_task(tmp_path, _task("BUG-1", "failed", branch_def_id=OLD))
    assert backfill_investigations(tmp_path) == 0


def test_no_canonical_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("WORKFLOW_BUG_INVESTIGATION_BACKFILL", "on")
    monkeypatch.delenv("WORKFLOW_BUG_INVESTIGATION_BRANCH_DEF_ID", raising=False)
    monkeypatch.delenv("WORKFLOW_BUG_INVESTIGATION_GOAL_ID", raising=False)
    append_task(tmp_path, _task("BUG-1", "failed", branch_def_id=OLD))
    assert backfill_investigations(tmp_path) == 0


def test_drives_failed_cheat_branch_bug_carrying_inputs(tmp_path, monkeypatch):
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "failed", branch_def_id=OLD))
    assert backfill_investigations(tmp_path) == 1
    new = _canon_pending(tmp_path)
    assert len(new) == 1
    assert new[0].branch_task_id == "backfill-bug-1-a1"
    assert new[0].request_type == REQUEST_TYPE_BUG_INVESTIGATION
    assert new[0].inputs["bug_id"] == "BUG-1"
    assert new[0].inputs["component"] == "workflow/x.py"  # frontmatter carried


def test_skips_succeeded_forever(tmp_path, monkeypatch):
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "succeeded"))
    assert backfill_investigations(tmp_path) == 0


def test_succeeded_overrides_old_failed(tmp_path, monkeypatch):
    # A cheat-branch failure plus a canonical success => resolved, not driven.
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "failed", branch_def_id=OLD))
    append_task(tmp_path, _task("BUG-1", "succeeded"))
    assert backfill_investigations(tmp_path) == 0


def test_succeeded_under_old_loop_version_parks_bug(tmp_path, monkeypatch):
    # Version-agnostic resolution: a succeeded run under a PRIOR loop version
    # (e.g. the retired cheat branch) parks the bug — a loop-version change /
    # cutover must NOT re-drive bugs the old loop already resolved. Regression
    # for the current-canonical-scoped dedup that re-drove the whole corpus.
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "succeeded", branch_def_id=OLD))
    assert backfill_investigations(tmp_path) == 0


def test_in_flight_under_old_loop_version_skips(tmp_path, monkeypatch):
    # In-flight is also version-agnostic: a pending/running task under any loop
    # version means the bug is already being worked — do not double-enqueue.
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "running", branch_def_id=OLD))
    assert backfill_investigations(tmp_path) == 0


def test_skips_in_flight(tmp_path, monkeypatch):
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "running"))
    append_task(tmp_path, _task("BUG-2", "pending"))
    assert backfill_investigations(tmp_path) == 0


def test_idempotent_does_not_double_enqueue(tmp_path, monkeypatch):
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "failed", branch_def_id=OLD))
    assert backfill_investigations(tmp_path) == 1          # emits a1 (pending)
    assert backfill_investigations(tmp_path) == 0          # a1 now in-flight
    assert len(_canon_pending(tmp_path)) == 1


def test_failed_attempt_retries_with_next_attempt_id(tmp_path, monkeypatch):
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "failed", tid="backfill-bug-1-a1"))
    assert backfill_investigations(tmp_path) == 1
    assert _canon_pending(tmp_path)[0].branch_task_id == "backfill-bug-1-a2"


def test_retry_cap_parks_bug(tmp_path, monkeypatch):
    _set(monkeypatch, WORKFLOW_BUG_INVESTIGATION_BACKFILL_RETRIES="2")
    append_task(tmp_path, _task("BUG-1", "failed", tid="backfill-bug-1-a1"))
    append_task(tmp_path, _task("BUG-1", "failed", tid="backfill-bug-1-a2"))
    assert backfill_investigations(tmp_path) == 0   # 2 failures >= cap 2


def test_max_per_cycle_caps_output(tmp_path, monkeypatch):
    _set(monkeypatch, WORKFLOW_BUG_INVESTIGATION_BACKFILL_MAX="2")
    for i in range(5):
        append_task(tmp_path, _task(f"BUG-{i}", "failed", branch_def_id=OLD))
    assert backfill_investigations(tmp_path) == 2


def test_ignores_non_investigation_tasks(tmp_path, monkeypatch):
    _set(monkeypatch)
    append_task(tmp_path, _task("BUG-1", "failed", branch_def_id=OLD, rtype="branch_run"))
    assert backfill_investigations(tmp_path) == 0

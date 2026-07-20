"""Owner reshape starts one identity-preserving continuation at the routed node."""

from __future__ import annotations

import tinyassets.runs as runs
from tinyassets.daemon_registry import create_daemon, summon_daemon
from tinyassets.daemon_server import (
    initialize_author_server,
    retire_runtime_instance,
    save_branch_definition,
)
from tinyassets.storage import review_queue as rq

_BRANCH_ID = "reshape-continuation-test"
_UNIVERSE_ID = "u-reshape"
_OWNER_ID = "owner-reshape"
_WORKER_ID = "worker-reshape"


def _project_running_revision(universe_dir, task_id: str):
    """Project legacy running state for continuation tests without claiming."""
    from tinyassets.branch_tasks import (
        BranchTask,
        _lease_window,
        _read_raw,
        _write_raw,
        queue_path,
    )

    path = queue_path(universe_dir)
    rows = _read_raw(path)
    for row in rows:
        if row.get("branch_task_id") == task_id:
            heartbeat_at, lease_expires_at = _lease_window()
            row["status"] = "running"
            row["claimed_by"] = "revision-daemon"
            row["worker_owner_id"] = "revision-daemon"
            row["executor_worker_id"] = _WORKER_ID
            row["heartbeat_at"] = heartbeat_at
            row["lease_expires_at"] = lease_expires_at
            _write_raw(path, rows)
            return BranchTask.from_dict(row)
    raise AssertionError(f"missing revision task {task_id}")


class _MutableHeadApi:
    def __init__(self, head: str = "a" * 40) -> None:
        self.head = head

    def get_pull(self, **_kwargs):
        return {"head_sha": self.head}

    def run_call(self, _call):
        return {"ok": True, "status": 200}


def test_partial_run_reachability_includes_conditional_targets():
    from tinyassets.branches import (
        BranchDefinition,
        ConditionalEdge,
        GraphNodeRef,
    )

    branch = BranchDefinition(
        branch_def_id="conditional-revision",
        name="Conditional revision",
        graph_nodes=[
            GraphNodeRef(id="draft"),
            GraphNodeRef(id="accept"),
            GraphNodeRef(id="revise"),
        ],
        conditional_edges=[
            ConditionalEdge(
                from_node="draft",
                conditions={"pass": "accept", "fail": "revise"},
            )
        ],
    )

    assert runs._nodes_reachable_from(branch, "draft") == {
        "draft",
        "accept",
        "revise",
    }


def _branch():
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    nodes = [
        NodeDefinition(
            node_id="intake",
            display_name="Intake",
            prompt_template="INTAKE {request_payload}",
            input_keys=["request_payload"],
            output_keys=["intake_output"],
        ),
        NodeDefinition(
            node_id="investigate",
            display_name="Investigate",
            prompt_template="INVESTIGATE {intake_output}",
            input_keys=["intake_output"],
            output_keys=["investigate_output"],
        ),
        NodeDefinition(
            node_id="draft_patch",
            display_name="Draft",
            prompt_template=(
                "DRAFT investigation={investigate_output} "
                "reshape={reshape_notes}"
            ),
            input_keys=["investigate_output", "reshape_notes"],
            output_keys=["draft_patch_output"],
        ),
    ]
    return BranchDefinition(
        branch_def_id=_BRANCH_ID,
        name="Reshape continuation test",
        graph_nodes=[
            GraphNodeRef(id=node.node_id, node_def_id=node.node_id)
            for node in nodes
        ],
        edges=[
            EdgeDefinition(from_node="START", to_node="intake"),
            EdgeDefinition(from_node="intake", to_node="investigate"),
            EdgeDefinition(from_node="investigate", to_node="draft_patch"),
            EdgeDefinition(from_node="draft_patch", to_node="END"),
        ],
        entry_point="intake",
        node_defs=nodes,
        state_schema=[
            {"name": "request_payload", "type": "str"},
            {"name": "reshape_notes", "type": "str"},
            {"name": "intake_output", "type": "str"},
            {"name": "investigate_output", "type": "str"},
            {"name": "draft_patch_output", "type": "str"},
        ],
    )


def _source_run(tmp_path, monkeypatch, *, branch=None):
    from tests._executor_sim import install_worker_sim
    from tinyassets.api import runs as api_runs

    branch = branch or _branch()
    universe_dir = tmp_path / _UNIVERSE_ID
    universe_dir.mkdir()
    install_worker_sim(monkeypatch)
    monkeypatch.setattr(api_runs, "_request_universe", lambda uid="": uid)
    monkeypatch.setattr(api_runs, "_universe_dir", lambda _uid: universe_dir)

    prompts: list[str] = []

    def provider_call(
        prompt, system, *, role, config=None, universe_context=None,
    ):
        prompts.append(prompt)
        return f"response-{len(prompts)}"

    monkeypatch.setattr(
        "tinyassets.providers.call.call_provider",
        provider_call,
    )
    monkeypatch.setattr(
        "tinyassets.github_http.github_client_from_vault",
        lambda *_args, **_kwargs: _MutableHeadApi(),
    )

    daemon = create_daemon(
        tmp_path,
        display_name="Reshape owner daemon",
        created_by=_OWNER_ID,
        soul_mode="soulless",
    )
    initialize_author_server(universe_dir)
    save_branch_definition(
        universe_dir,
        branch_def=branch.to_dict(),
        _trusted=True,
    )
    runtime = summon_daemon(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id=_UNIVERSE_ID,
        provider_name="claude-code",
        model_name="test-model",
        created_by=_OWNER_ID,
        metadata={"worker_id": _WORKER_ID},
    )
    source_run_id = runs.create_run(
        tmp_path,
        branch_def_id=_BRANCH_ID,
        thread_id="source-thread",
        inputs={"request_payload": "original request"},
        actor=_OWNER_ID,
        universe_id=_UNIVERSE_ID,
        daemon_id=daemon["daemon_id"],
        runtime_instance_id=runtime["runtime_instance_id"],
        worker_id=_WORKER_ID,
    )
    runs.update_run_status(
        tmp_path,
        source_run_id,
        status=runs.RUN_STATUS_INTERRUPTED,
        output={
            "intake_output": "normalized request",
            "investigate_output": "trusted investigation",
            "awaiting_owner_review": {"pr_number": 7},
        },
    )
    route = {
        "target_node": "draft_patch",
        "universe_id": _UNIVERSE_ID,
        "branch_def_id": _BRANCH_ID,
        "run_id": source_run_id,
        "owner_notes": "USE THIS NOTE",
    }
    return universe_dir, source_run_id, route, daemon, runtime, prompts


def _enqueue_revision_task(universe_dir, source_run_id, route):
    rq.project_pr(
        universe_dir,
        destination="Owner/Repo",
        pr_number=7,
        head_sha="a" * 40,
        branch_def_id=_BRANCH_ID,
        universe_id=_UNIVERSE_ID,
        run_id=source_run_id,
    )
    rq.suspend_run_for_review(
        universe_dir,
        run_id=source_run_id,
        destination="Owner/Repo",
        pr_number=7,
        branch_def_id=_BRANCH_ID,
        head_sha="a" * 40,
        universe_id=_UNIVERSE_ID,
    )
    decision = rq.decide_and_resume(
        universe_dir,
        destination="Owner/Repo",
        pr_number=7,
        intent=rq.INTENT_RESHAPE,
        workflow_outcome=rq.WORKFLOW_RESHAPED,
        decided_by=_OWNER_ID,
        expected_head_sha="a" * 40,
        directive={"action": "draft_patch", "route_back": route},
    )
    result = runs.execute_next_review_decision_effect(
        universe_dir,
        worker_id="decision-worker",
        github_api=_MutableHeadApi(),
    )
    assert result["kind"] == "enqueue_revision"
    assert result["executed"] is True
    claimed = _project_running_revision(universe_dir, result["branch_task_id"])
    return decision, claimed


def test_review_revision_terminalizes_if_head_moves_before_consumption(
    tmp_path, monkeypatch
):
    universe_dir, source_run_id, route, daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    rq.project_pr(
        universe_dir,
        destination="Owner/Repo",
        pr_number=7,
        head_sha="a" * 40,
        branch_def_id=_BRANCH_ID,
        universe_id=_UNIVERSE_ID,
        run_id=source_run_id,
    )
    rq.suspend_run_for_review(
        universe_dir,
        run_id=source_run_id,
        destination="Owner/Repo",
        pr_number=7,
        branch_def_id=_BRANCH_ID,
        head_sha="a" * 40,
        universe_id=_UNIVERSE_ID,
    )
    rq.decide_and_resume(
        universe_dir,
        destination="Owner/Repo",
        pr_number=7,
        intent=rq.INTENT_RESHAPE,
        workflow_outcome=rq.WORKFLOW_RESHAPED,
        decided_by=_OWNER_ID,
        expected_head_sha="a" * 40,
        directive={
            "action": "draft_patch",
            "route_back": route,
            "github_call": {
                "params": {"event": "REQUEST_CHANGES", "body": "revise"}
            },
        },
    )
    api = _MutableHeadApi()

    executed = runs.execute_pending_review_decisions(
        universe_dir,
        worker_id="decision-worker",
        github_api=api,
    )
    assert [row["kind"] for row in executed] == [
        "submit_review",
        "enqueue_revision",
        "finalize_run",
    ]

    from tinyassets.branch_tasks import read_queue

    [queued] = read_queue(universe_dir)
    claimed = _project_running_revision(universe_dir, queued.branch_task_id)
    api.head = "b" * 40
    monkeypatch.setattr(
        "tinyassets.github_http.github_client_from_vault",
        lambda *_args, **_kwargs: api,
    )
    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)

    from fantasy_daemon.__main__ import (
        _finalize_claimed_task,
        _try_execute_claimed_branch_task,
    )

    success, error, metadata = _try_execute_claimed_branch_task(
        universe_dir, claimed, daemon["daemon_id"],
    )
    _finalize_claimed_task(
        universe_dir, claimed, success=success, error=error,
    )

    assert success is False
    assert "head_moved" in error
    assert metadata.get("run_id") is None
    [terminal] = read_queue(universe_dir)
    assert terminal.status == "failed"
    assert "head_moved" in terminal.error
    assert not any(
        run["run_name"] == f"branch-task-{claimed.branch_task_id}"
        for run in runs.list_recent_runs(tmp_path, limit=20)
    )


def test_review_revision_terminalizes_if_head_moves_during_execution(
    tmp_path, monkeypatch
):
    universe_dir, source_run_id, route, daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    rq.project_pr(
        universe_dir,
        destination="Owner/Repo",
        pr_number=7,
        head_sha="a" * 40,
        branch_def_id=_BRANCH_ID,
        universe_id=_UNIVERSE_ID,
        run_id=source_run_id,
    )
    rq.suspend_run_for_review(
        universe_dir,
        run_id=source_run_id,
        destination="Owner/Repo",
        pr_number=7,
        branch_def_id=_BRANCH_ID,
        head_sha="a" * 40,
        universe_id=_UNIVERSE_ID,
    )
    rq.decide_and_resume(
        universe_dir,
        destination="Owner/Repo",
        pr_number=7,
        intent=rq.INTENT_RESHAPE,
        workflow_outcome=rq.WORKFLOW_RESHAPED,
        decided_by=_OWNER_ID,
        expected_head_sha="a" * 40,
        directive={
            "action": "draft_patch",
            "route_back": route,
            "github_call": {
                "params": {"event": "REQUEST_CHANGES", "body": "revise"}
            },
        },
    )
    api = _MutableHeadApi()

    executed = runs.execute_pending_review_decisions(
        universe_dir,
        worker_id="decision-worker",
        github_api=api,
    )
    assert [row["kind"] for row in executed] == [
        "submit_review",
        "enqueue_revision",
        "finalize_run",
    ]

    from tinyassets.branch_tasks import read_queue

    [queued] = read_queue(universe_dir)
    claimed = _project_running_revision(universe_dir, queued.branch_task_id)

    def move_head_during_revision(
        _prompt, _system, *, role, config=None, universe_context=None,
    ):
        api.head = "b" * 40
        return "STALE PATCH MUST NOT PERSIST"

    external_writes = []

    def record_external_write(*args, **kwargs):
        external_writes.append((args, kwargs))
        return {}

    monkeypatch.setattr(
        "tinyassets.providers.call.call_provider",
        move_head_during_revision,
    )
    monkeypatch.setattr(runs, "_run_external_write_effectors", record_external_write)
    monkeypatch.setattr(
        "tinyassets.github_http.github_client_from_vault",
        lambda *_args, **_kwargs: api,
    )
    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)

    from fantasy_daemon.__main__ import (
        _finalize_claimed_task,
        _try_execute_claimed_branch_task,
    )

    success, error, metadata = _try_execute_claimed_branch_task(
        universe_dir, claimed, daemon["daemon_id"],
    )
    _finalize_claimed_task(
        universe_dir, claimed, success=success, error=error,
    )

    assert success is False
    assert "head_moved" in error
    assert metadata["run_status"] == runs.RUN_STATUS_FAILED
    assert external_writes == []
    revised = runs.get_run(tmp_path, metadata["run_id"])
    assert revised["status"] == runs.RUN_STATUS_FAILED
    assert "head_moved" in revised["error"]
    assert "STALE PATCH MUST NOT PERSIST" not in str(revised["output"])
    [terminal] = read_queue(universe_dir)
    assert terminal.status == "failed"
    assert "head_moved" in terminal.error


def test_review_revision_head_move_blocks_in_node_enqueue(
    tmp_path, monkeypatch
):
    from tinyassets.branches import (
        BranchDefinition,
        EdgeDefinition,
        GraphNodeRef,
        NodeDefinition,
    )

    enqueue_node = NodeDefinition(
        node_id="draft_patch",
        display_name="Draft and enqueue",
        source_code=(
            "def run(state):\n"
            "    invoke_mcp_action('enqueue_branch_run', "
            f"branch_def_id='{_BRANCH_ID}', inputs={{}})\n"
            "    return {'draft_patch_output': 'stale child requested'}\n"
        ),
        output_keys=["draft_patch_output"],
        tools_allowed=["enqueue_branch_run"],
    ).mark_approved()
    branch = BranchDefinition(
        branch_def_id=_BRANCH_ID,
        name="Review revision enqueue race",
        graph_nodes=[GraphNodeRef(id="draft_patch", node_def_id="draft_patch")],
        edges=[
            EdgeDefinition(from_node="START", to_node="draft_patch"),
            EdgeDefinition(from_node="draft_patch", to_node="END"),
        ],
        entry_point="draft_patch",
        node_defs=[enqueue_node],
        state_schema=[
            {"name": "reshape_notes", "type": "str"},
            {"name": "draft_patch_output", "type": "str"},
        ],
    )
    universe_dir, source_run_id, route, daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch, branch=branch,
    )
    # The enqueue verb validates its target against the worker workspace.
    # Persist the same branch there so the test reaches the durable append.
    initialize_author_server(tmp_path)
    save_branch_definition(tmp_path, branch_def=branch.to_dict(), _trusted=True)

    rq.project_pr(
        universe_dir,
        destination="Owner/Repo",
        pr_number=7,
        head_sha="a" * 40,
        branch_def_id=_BRANCH_ID,
        universe_id=_UNIVERSE_ID,
        run_id=source_run_id,
    )
    rq.suspend_run_for_review(
        universe_dir,
        run_id=source_run_id,
        destination="Owner/Repo",
        pr_number=7,
        branch_def_id=_BRANCH_ID,
        head_sha="a" * 40,
        universe_id=_UNIVERSE_ID,
    )
    rq.decide_and_resume(
        universe_dir,
        destination="Owner/Repo",
        pr_number=7,
        intent=rq.INTENT_RESHAPE,
        workflow_outcome=rq.WORKFLOW_RESHAPED,
        decided_by=_OWNER_ID,
        expected_head_sha="a" * 40,
        directive={
            "action": "draft_patch",
            "route_back": route,
            "github_call": {
                "params": {"event": "REQUEST_CHANGES", "body": "revise"}
            },
        },
    )
    api = _MutableHeadApi()
    executed = runs.execute_pending_review_decisions(
        universe_dir,
        worker_id="decision-worker",
        github_api=api,
    )
    assert [row["kind"] for row in executed] == [
        "submit_review",
        "enqueue_revision",
        "finalize_run",
    ]

    from tinyassets.branch_tasks import read_queue

    [queued] = read_queue(universe_dir)
    claimed = _project_running_revision(universe_dir, queued.branch_task_id)
    monkeypatch.setenv("TINYASSETS_NODE_ENQUEUE_ENABLED", "on")
    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "tinyassets.github_http.github_client_from_vault",
        lambda *_args, **_kwargs: api,
    )

    from tinyassets import daemon_server

    real_get_branch_definition = daemon_server.get_branch_definition

    def move_head_immediately_before_enqueue(base_path, *, branch_def_id):
        result = real_get_branch_definition(
            base_path, branch_def_id=branch_def_id,
        )
        if str(base_path) == str(tmp_path):
            api.head = "b" * 40
        return result

    monkeypatch.setattr(
        daemon_server,
        "get_branch_definition",
        move_head_immediately_before_enqueue,
    )

    from fantasy_daemon.__main__ import _try_execute_claimed_branch_task

    success, error, metadata = _try_execute_claimed_branch_task(
        universe_dir, claimed, daemon["daemon_id"],
    )

    assert success is False
    assert "head_moved" in error
    assert metadata["run_status"] == runs.RUN_STATUS_FAILED
    child_count = sum(
        task.branch_task_id != claimed.branch_task_id
        for task in read_queue(universe_dir)
    )
    assert child_count == 0


def test_review_revision_runs_through_branch_task_lifecycle(tmp_path, monkeypatch):
    universe_dir, source_run_id, route, daemon, runtime, prompts = _source_run(
        tmp_path, monkeypatch,
    )
    _decision, claimed = _enqueue_revision_task(universe_dir, source_run_id, route)
    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)

    from fantasy_daemon.__main__ import _try_execute_claimed_branch_task

    success, error, metadata = _try_execute_claimed_branch_task(
        universe_dir, claimed, daemon["daemon_id"],
    )

    assert success is True, (error, metadata)
    assert error == ""
    revised = runs.get_run(tmp_path, metadata["run_id"])
    assert revised["status"] == runs.RUN_STATUS_COMPLETED
    assert revised["inputs"]["investigate_output"] == "trusted investigation"
    assert revised["inputs"]["reshape_notes"] == "USE THIS NOTE"
    assert revised["owner_user_id"] == _OWNER_ID
    assert revised["daemon_id"] == daemon["daemon_id"]
    assert revised["runtime_instance_id"] == runtime["runtime_instance_id"]
    assert revised["worker_id"] == _WORKER_ID
    assert prompts == [
        "DRAFT investigation=trusted investigation reshape=USE THIS NOTE",
    ]
    statuses = {
        event["node_id"]: event["status"]
        for event in runs.list_events(tmp_path, metadata["run_id"])
        if not event["node_id"].startswith("__")
    }
    assert statuses["intake"] == runs.NODE_STATUS_SKIPPED
    assert statuses["investigate"] == runs.NODE_STATUS_SKIPPED
    assert statuses["draft_patch"] == runs.NODE_STATUS_RAN
    assert runs.get_lineage(tmp_path, metadata["run_id"])["parent_run_id"] == (
        source_run_id
    )


def test_terminal_revision_replay_needs_no_live_runtime(tmp_path, monkeypatch):
    universe_dir, source_run_id, route, daemon, runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    _decision, claimed = _enqueue_revision_task(universe_dir, source_run_id, route)
    monkeypatch.setattr("tinyassets.storage.data_dir", lambda: tmp_path)
    from fantasy_daemon.__main__ import _try_execute_claimed_branch_task

    first = _try_execute_claimed_branch_task(
        universe_dir, claimed, daemon["daemon_id"],
    )
    retire_runtime_instance(tmp_path, instance_id=runtime["runtime_instance_id"])

    replay = _try_execute_claimed_branch_task(
        universe_dir, claimed, daemon["daemon_id"],
    )

    assert first[0] is True, first
    assert replay[0] is True
    assert replay[2]["reused_existing_run"] is True
    runs.update_run_status(
        tmp_path,
        first[2]["run_id"],
        status=runs.RUN_STATUS_FAILED,
        error="terminal revision failure",
    )
    failed_replay = _try_execute_claimed_branch_task(
        universe_dir, claimed, daemon["daemon_id"],
    )
    assert failed_replay[0] is False
    assert failed_replay[1] == "terminal revision failure"
    assert failed_replay[2]["reused_existing_run"] is True
    revised = [
        run
        for run in runs.list_recent_runs(tmp_path, limit=20)
        if run["run_name"] == f"branch-task-{claimed.branch_task_id}"
    ]
    assert len(revised) == 1

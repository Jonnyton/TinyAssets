"""Owner reshape starts one identity-preserving continuation at the routed node."""

from __future__ import annotations

import hashlib
import sqlite3

import pytest

import tinyassets.runs as runs
from tinyassets import credential_broker
from tinyassets.credential_broker import run_context_lookup
from tinyassets.credentials import SecretKind
from tinyassets.daemon_registry import create_daemon, summon_daemon
from tinyassets.daemon_server import (
    initialize_author_server,
    retire_runtime_instance,
    save_branch_definition,
    spawn_runtime_instance,
    update_runtime_instance_status,
)
from tinyassets.storage import review_queue as rq

_BRANCH_ID = "reshape-continuation-test"
_UNIVERSE_ID = "u-reshape"
_OWNER_ID = "owner-reshape"
_WORKER_ID = "worker-reshape"


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


def _source_run(tmp_path, monkeypatch):
    from tests._executor_sim import install_worker_sim
    from tinyassets.api import runs as api_runs

    branch = _branch()
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


def test_start_review_revision_resumes_at_target_with_reshape_notes(
    tmp_path, monkeypatch,
):
    universe_dir, source_run_id, route, _daemon, _runtime, prompts = _source_run(
        tmp_path, monkeypatch,
    )

    revised_run_id = runs._start_review_revision(universe_dir, route)
    runs.wait_for(revised_run_id, timeout=10)

    revised = runs.get_run(tmp_path, revised_run_id)
    assert revised["status"] == runs.RUN_STATUS_COMPLETED
    assert revised["inputs"]["investigate_output"] == "trusted investigation"
    assert revised["inputs"]["reshape_notes"] == "USE THIS NOTE"
    assert "owner_notes" not in revised["inputs"]
    assert prompts == [
        "DRAFT investigation=trusted investigation reshape=USE THIS NOTE",
    ]
    ran_nodes = {
        event["node_id"]
        for event in runs.list_events(tmp_path, revised_run_id)
        if event["status"] == runs.NODE_STATUS_RAN
    }
    assert ran_nodes == {"draft_patch"}
    assert runs.get_lineage(tmp_path, revised_run_id)["parent_run_id"] == source_run_id


def test_start_review_revision_preserves_grant_authoritative_identity(
    platform_vault_env, monkeypatch,
):
    tmp_path = platform_vault_env
    universe_dir, _source, route, daemon, runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )

    revised_run_id = runs._start_review_revision(universe_dir, route)
    runs.wait_for(revised_run_id, timeout=10)

    revised = runs.get_run(tmp_path, revised_run_id)
    assert revised["owner_user_id"] == _OWNER_ID
    assert revised["daemon_id"] == daemon["daemon_id"]
    assert revised["runtime_instance_id"] == runtime["runtime_instance_id"]
    assert revised["worker_id"] == _WORKER_ID
    context = run_context_lookup(tmp_path)(revised_run_id)
    assert context.run_id == revised_run_id
    assert context.universe_id == _UNIVERSE_ID
    assert context.founder_id == _OWNER_ID

    credential_broker.deposit_credential(
        universe_id=_UNIVERSE_ID,
        founder_id=_OWNER_ID,
        provider=credential_broker.GITHUB_PROVIDER,
        destination="owner/repo",
        purpose=credential_broker.GITHUB_WRITE_PURPOSE,
        kind=SecretKind.GITHUB_PAT,
        value=b"reshape-grant-token",
    )
    binding = credential_broker.find_binding(
        _UNIVERSE_ID,
        credential_broker.GITHUB_PROVIDER,
        credential_broker.GITHUB_WRITE_PURPOSE,
        "owner/repo",
    )
    backend = credential_broker.platform_backend()
    grant = backend.mint_job_grant(binding, binding.scope, revised_run_id)
    with backend.resolve_job_grant(
        grant, verify_context=lambda _context: True,
    ) as lease:
        assert lease.reveal() == b"reshape-grant-token"


def test_start_review_revision_rejects_retired_runtime(tmp_path, monkeypatch):
    universe_dir, _source, route, _daemon, runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    retire_runtime_instance(tmp_path, instance_id=runtime["runtime_instance_id"])

    with pytest.raises(RuntimeError, match="live runtime"):
        runs._start_review_revision(universe_dir, route)


@pytest.mark.parametrize("status", ["paused", "restart_requested", "unknown"])
def test_start_review_revision_requires_executable_runtime_status(
    tmp_path, monkeypatch, status,
):
    universe_dir, _source, route, _daemon, runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    update_runtime_instance_status(
        tmp_path,
        instance_id=runtime["runtime_instance_id"],
        status=status,
    )

    with pytest.raises(RuntimeError, match="executable runtime"):
        runs._start_review_revision(universe_dir, route)


def test_start_review_revision_rejects_runtime_from_another_daemon(
    tmp_path, monkeypatch,
):
    universe_dir, source_run_id, route, daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    other_daemon = create_daemon(
        tmp_path,
        display_name="Unrelated daemon",
        created_by=_OWNER_ID,
        soul_mode="soulless",
    )
    unrelated_runtime = spawn_runtime_instance(
        tmp_path,
        universe_id=_UNIVERSE_ID,
        author_id=other_daemon["legacy_author_id"],
        provider_name="claude-code",
        model_name="test-model",
        created_by=_OWNER_ID,
        metadata={"owner_user_id": _OWNER_ID, "worker_id": _WORKER_ID},
    )
    with runs._connect(tmp_path) as conn:
        conn.execute(
            "UPDATE runs SET runtime_instance_id = ? WHERE run_id = ?",
            (unrelated_runtime["instance_id"], source_run_id),
        )

    def must_not_start(*args, **kwargs):
        raise AssertionError("mismatched runtime reached execution")

    monkeypatch.setattr(runs, "execute_branch_async", must_not_start)
    with pytest.raises(RuntimeError, match="runtime identity.*daemon"):
        runs._start_review_revision(universe_dir, route)

    assert daemon["daemon_id"] != other_daemon["daemon_id"]


def test_start_review_revision_rejects_mismatched_existing_run(
    tmp_path, monkeypatch,
):
    universe_dir, source_run_id, route, _daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    revision_key = "\0".join(
        ("owner-reshape", source_run_id, _BRANCH_ID, "draft_patch")
    )
    revised_run_id = hashlib.sha256(revision_key.encode("utf-8")).hexdigest()[:32]
    runs.create_run(
        tmp_path,
        run_id=revised_run_id,
        branch_def_id="unrelated-branch",
        thread_id=revised_run_id,
        inputs={},
        actor=_OWNER_ID,
        universe_id=_UNIVERSE_ID,
    )

    with pytest.raises(RuntimeError, match="existing reshape revision.*match"):
        runs._start_review_revision(universe_dir, route)


def test_prepare_run_rolls_back_partial_revision_creation(tmp_path, monkeypatch):
    run_id = "atomic-review-revision"

    def fail_lineage(*args, **kwargs):
        raise RuntimeError("simulated crash while recording lineage")

    monkeypatch.setattr(runs, "record_lineage", fail_lineage)
    with pytest.raises(RuntimeError, match="recording lineage"):
        runs._prepare_run(
            tmp_path,
            run_id=run_id,
            branch=_branch(),
            inputs={"request_payload": "request"},
            run_name="Owner-requested revision",
            actor=_OWNER_ID,
            universe_id=_UNIVERSE_ID,
            lineage_parent_run_id="source-run",
        )

    assert runs.get_run(tmp_path, run_id) is None
    assert runs.list_events(tmp_path, run_id) == []
    assert runs.get_lineage(tmp_path, run_id) is None


def test_review_revision_resubmits_prepared_run_interrupted_before_submit(
    tmp_path, monkeypatch,
):
    universe_dir, _source, route, _daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    real_get_executor = runs._get_executor

    class CrashBeforeSubmit:
        def submit(self, *args, **kwargs):
            raise RuntimeError("simulated process death before submit")

    monkeypatch.setattr(
        runs,
        "_get_executor",
        lambda **_kwargs: CrashBeforeSubmit(),
    )
    with pytest.raises(RuntimeError, match="before submit"):
        runs._start_review_revision(universe_dir, route)

    assert runs.recover_in_flight_runs(tmp_path) == 1

    with pytest.raises(RuntimeError, match="before submit"):
        runs._start_review_revision(universe_dir, route)
    interrupted = [
        record
        for record in runs.list_recent_runs(tmp_path, limit=20)
        if record["run_id"] != route["run_id"]
    ][0]
    assert interrupted["status"] == runs.RUN_STATUS_INTERRUPTED

    monkeypatch.setattr(runs, "_get_executor", real_get_executor)
    revised_run_id = runs._start_review_revision(universe_dir, route)
    runs.wait_for(revised_run_id, timeout=10)

    revised = runs.get_run(tmp_path, revised_run_id)
    assert revised["status"] == runs.RUN_STATUS_COMPLETED
    assert runs.get_lineage(tmp_path, revised_run_id)["parent_run_id"] == route["run_id"]


def test_review_revision_refuses_interrupted_progress_without_checkpoint(
    tmp_path, monkeypatch,
):
    universe_dir, _source, route, _daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    real_get_executor = runs._get_executor

    class CrashBeforeSubmit:
        def submit(self, *args, **kwargs):
            raise RuntimeError("simulated process death before submit")

    monkeypatch.setattr(
        runs,
        "_get_executor",
        lambda **_kwargs: CrashBeforeSubmit(),
    )
    with pytest.raises(RuntimeError, match="before submit"):
        runs._start_review_revision(universe_dir, route)

    revised_runs = [
        record
        for record in runs.list_recent_runs(tmp_path, limit=20)
        if record["run_id"] != route["run_id"]
    ]
    revised_run_id = revised_runs[0]["run_id"]
    runs.record_event(
        tmp_path,
        runs.RunStepEvent(
            run_id=revised_run_id,
            step_index=runs._PENDING_OFFSET,
            node_id="draft_patch",
            status=runs.NODE_STATUS_RUNNING,
            started_at=runs._now(),
        ),
    )
    monkeypatch.setattr(runs, "_get_executor", real_get_executor)
    assert runs.recover_in_flight_runs(tmp_path) == 1

    with pytest.raises(RuntimeError, match="cannot be safely replayed"):
        runs._start_review_revision(universe_dir, route)

    assert runs.get_run(tmp_path, revised_run_id)["status"] == runs.RUN_STATUS_INTERRUPTED


def test_review_revision_resumes_real_durable_checkpoint(tmp_path, monkeypatch):
    universe_dir, _source, route, _daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )

    def crash_process(*args, **kwargs):
        raise SystemExit("simulated process death during provider call")

    monkeypatch.setattr(
        "tinyassets.providers.call.call_provider",
        crash_process,
    )
    revised_run_id = runs._start_review_revision(universe_dir, route)
    future = runs.get_future(revised_run_id)
    assert future is not None
    with pytest.raises(SystemExit, match="process death"):
        future.result(timeout=10)

    assert runs._has_checkpoint(tmp_path, revised_run_id)
    assert runs.recover_in_flight_runs(tmp_path) == 1

    monkeypatch.setattr(
        "tinyassets.providers.call.call_provider",
        lambda *args, **kwargs: "recovered draft",
    )
    assert runs._start_review_revision(universe_dir, route) == revised_run_id
    runs.wait_for(revised_run_id, timeout=10)

    assert runs.get_run(tmp_path, revised_run_id)["status"] == runs.RUN_STATUS_COMPLETED


def test_review_revision_refuses_checkpoint_after_branch_version_change(
    tmp_path, monkeypatch,
):
    universe_dir, _source, route, _daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )

    def crash_process(*args, **kwargs):
        raise SystemExit("simulated process death during provider call")

    monkeypatch.setattr(
        "tinyassets.providers.call.call_provider",
        crash_process,
    )
    revised_run_id = runs._start_review_revision(universe_dir, route)
    future = runs.get_future(revised_run_id)
    assert future is not None
    with pytest.raises(SystemExit, match="process death"):
        future.result(timeout=10)

    assert runs._has_checkpoint(tmp_path, revised_run_id)
    assert runs.recover_in_flight_runs(tmp_path) == 1
    changed_branch = _branch()
    changed_branch.version += 1
    save_branch_definition(
        universe_dir,
        branch_def=changed_branch.to_dict(),
        _trusted=True,
    )

    with pytest.raises(RuntimeError, match="checkpoint.*branch version"):
        runs._start_review_revision(universe_dir, route)


def test_review_revision_recovers_same_run_after_receipt_crash(
    tmp_path, monkeypatch,
):
    universe_dir, source_run_id, route, _daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    rq.record_effect_receipt(
        universe_dir,
        run_id=source_run_id,
        effect_kind="submit_review_request_changes",
    )
    directive = {"action": "draft_patch", "route_back": route}
    real_record = rq.record_effect_receipt
    crashed = False

    def crash_before_revision_receipt(*args, **kwargs):
        nonlocal crashed
        if kwargs.get("effect_kind") == "revised_run" and not crashed:
            crashed = True
            raise RuntimeError("simulated crash before revised-run receipt")
        return real_record(*args, **kwargs)

    monkeypatch.setattr(rq, "record_effect_receipt", crash_before_revision_receipt)
    with pytest.raises(RuntimeError, match="simulated crash"):
        runs._execute_review_directive(
            universe_dir,
            run_id=source_run_id,
            suspension={},
            directive=directive,
            run_starter=lambda selected: runs._start_review_revision(
                universe_dir, selected,
            ),
        )

    monkeypatch.setattr(rq, "record_effect_receipt", real_record)
    replayed = runs._execute_review_directive(
        universe_dir,
        run_id=source_run_id,
        suspension={},
        directive=directive,
        run_starter=lambda selected: runs._start_review_revision(
            universe_dir, selected,
        ),
    )
    revised_run_id = replayed["effects"]["revised_run_id"]
    runs.wait_for(revised_run_id, timeout=10)

    matching = [
        record
        for record in runs.list_recent_runs(tmp_path, limit=20)
        if record["branch_def_id"] == _BRANCH_ID
        and record["run_id"] != source_run_id
    ]
    assert [record["run_id"] for record in matching] == [revised_run_id]
    receipt = rq.has_effect_receipt(
        universe_dir,
        run_id=source_run_id,
        effect_kind="revised_run",
    )
    assert receipt["detail"]["revised_run_id"] == revised_run_id


def test_review_revision_accepts_concurrent_winner_that_finishes_before_reload(
    tmp_path, monkeypatch,
):
    universe_dir, source_run_id, route, _daemon, _runtime, _prompts = _source_run(
        tmp_path, monkeypatch,
    )
    real_execute = runs.execute_branch_async
    real_get_run = runs.get_run
    winner_finished = False
    served_stale_snapshot = False

    def finish_winner_then_lose_insert(*args, **kwargs):
        nonlocal winner_finished
        outcome = real_execute(*args, **kwargs)
        runs.wait_for(outcome.run_id, timeout=10)
        winner_finished = True
        raise sqlite3.IntegrityError("simulated concurrent insert loser")

    def stale_once_after_winner(base_path, run_id):
        nonlocal served_stale_snapshot
        record = real_get_run(base_path, run_id)
        if winner_finished and not served_stale_snapshot and record is not None:
            served_stale_snapshot = True
            return {**record, "status": runs.RUN_STATUS_QUEUED}
        return record

    monkeypatch.setattr(runs, "execute_branch_async", finish_winner_then_lose_insert)
    monkeypatch.setattr(runs, "get_run", stale_once_after_winner)

    revised_run_id = runs._start_review_revision(universe_dir, route)

    assert served_stale_snapshot
    assert real_get_run(tmp_path, revised_run_id)["status"] == runs.RUN_STATUS_COMPLETED
    lineage = runs.get_lineage(tmp_path, revised_run_id)
    assert lineage["parent_run_id"] == source_run_id

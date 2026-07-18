"""Owner reshape starts one identity-preserving continuation at the routed node."""

from __future__ import annotations

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

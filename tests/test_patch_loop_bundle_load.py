"""Bundle-level §14 concurrency proof for the assembled patch loop.

One load wave executes 24 bound branch runs through the canonical orchestration
path, then drives review decisions, receipts, review-effect draining, and broker
job-grant resolution across three universes.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Barrier

import pytest

from tinyassets.branch_bindings import bind_branch_values
from tinyassets.branches import (
    BranchDefinition,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)
from tinyassets.credential_broker import (
    GITHUB_PROVIDER,
    GITHUB_WRITE_PURPOSE,
    deposit_credential,
    find_binding,
    platform_backend,
)
from tinyassets.credentials import (
    CredentialUnavailable,
    SecretKind,
    VaultErrorCode,
)
from tinyassets.sandbox_policy import ExecutionScope
from tinyassets.storage import review_queue as rq

_UNIVERSE_COUNT = 3
_RUN_COUNT = 24
_DESTINATION = "owner/shared-repo"
_BRANCH_ID = "patch-loop-load"
_SCHEMA = [
    {"name": "target_repo", "type": "str", "is_binding": True},
    {"name": "merge_policy", "type": "str", "is_binding": True},
    {"name": "rendered", "type": "str"},
]


def _load_branch() -> BranchDefinition:
    return BranchDefinition(
        branch_def_id=_BRANCH_ID,
        name="Patch-loop assembled-bundle load proof",
        entry_point="render",
        node_defs=[
            NodeDefinition(
                node_id="render",
                display_name="Render bound policy",
                prompt_template="patch {target_repo} with {merge_policy}",
                input_keys=["target_repo", "merge_policy"],
                output_keys=["rendered"],
            ),
        ],
        graph_nodes=[GraphNodeRef(id="render", node_def_id="render")],
        edges=[
            EdgeDefinition(from_node="START", to_node="render"),
            EdgeDefinition(from_node="render", to_node="END"),
        ],
        state_schema=_SCHEMA,
    )


def _provision_runtime(data_root, *, universe_id: str, founder_id: str):
    from tinyassets.daemon_registry import create_daemon, summon_daemon

    daemon = create_daemon(
        data_root,
        display_name=f"daemon-{universe_id}",
        created_by=founder_id,
    )
    runtime = summon_daemon(
        data_root,
        daemon_id=daemon["daemon_id"],
        universe_id=universe_id,
        provider_name="claude-code",
        model_name="load-test",
        created_by=founder_id,
    )
    return daemon, runtime


class _ReviewApi:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def get_pull(self, *, destination: str, pr_number: int):
        assert destination == _DESTINATION
        return {
            "number": pr_number,
            "head_sha": f"{pr_number:040x}",
            "author_login": "tinyassets-app[bot]",
            "author_type": "Bot",
        }

    def list_pull_reviews(self, *, destination: str, pr_number: int):
        assert destination == _DESTINATION
        assert pr_number > 0
        return []

    def run_call(self, call):
        self.calls.append(call.to_dict())
        return {"ok": True, "status": 200}


@pytest.mark.slow
def test_patch_loop_bundle_concurrent_multi_universe_load(platform_vault_env):
    from tinyassets.api.runs import _resolve_runtime_bindings
    from tinyassets.runs import (
        RUN_STATUS_COMPLETED,
        _execute_branch_core,
        execute_pending_review_decisions,
        get_run,
        initialize_runs_db,
        wait_for,
    )

    data_root = platform_vault_env
    initialize_runs_db(data_root)
    branch = _load_branch()
    universes: dict[str, dict[str, object]] = {}
    for index in range(_UNIVERSE_COUNT):
        universe_id = f"load-u{index}"
        founder_id = f"founder-{index}"
        universe_dir = data_root / universe_id
        universe_dir.mkdir()
        daemon, runtime = _provision_runtime(
            data_root,
            universe_id=universe_id,
            founder_id=founder_id,
        )
        secret = f"github-token-{universe_id}".encode()
        deposit_credential(
            universe_id=universe_id,
            founder_id=founder_id,
            provider=GITHUB_PROVIDER,
            destination=_DESTINATION,
            purpose=GITHUB_WRITE_PURPOSE,
            kind=SecretKind.GITHUB_PAT,
            value=secret,
        )
        binding = find_binding(
            universe_id,
            GITHUB_PROVIDER,
            GITHUB_WRITE_PURPOSE,
            _DESTINATION,
        )
        expected_values = {
            "target_repo": f"owner/repo-{index}",
            "merge_policy": ("manual", "auto", "timer")[index],
        }
        bind_branch_values(
            universe_dir,
            _BRANCH_ID,
            _SCHEMA,
            expected_values,
            actor=founder_id,
        )
        universes[universe_id] = {
            "dir": universe_dir,
            "founder": founder_id,
            "daemon": daemon,
            "runtime": runtime,
            "binding": binding,
            "secret": secret,
            "values": expected_values,
            "runs": [],
        }

    cases = [
        {
            "index": index,
            "universe_id": f"load-u{index % _UNIVERSE_COUNT}",
            "head_sha": f"{index + 1:040x}",
        }
        for index in range(_RUN_COUNT)
    ]
    backend = platform_backend()
    start = Barrier(_RUN_COUNT)

    def exercise(case: dict[str, object]) -> dict[str, object]:
        index = int(case["index"])
        universe_id = str(case["universe_id"])
        head_sha = str(case["head_sha"])
        universe = universes[universe_id]
        start.wait(timeout=30)

        runtime_bindings, refusal = _resolve_runtime_bindings(branch, universe_id)
        assert refusal is None
        queued = _execute_branch_core(
            data_root,
            branch=branch,
            inputs={"request": f"fix-{index}"},
            actor=str(universe["founder"]),
            provider_call=lambda prompt, *_args, **_kwargs: prompt,
            runtime_bindings=runtime_bindings,
            daemon_id=universe["daemon"]["daemon_id"],
            runtime_instance_id=universe["runtime"]["runtime_instance_id"],
            _enqueue_universe_id=universe_id,
            execution_scope=ExecutionScope.bound(universe["dir"]),
        )
        run_id = queued.run_id
        wait_for(run_id, timeout=30)
        run = get_run(data_root, run_id)
        assert run is not None
        assert run["status"] == RUN_STATUS_COMPLETED
        assert run["universe_id"] == universe_id
        assert run["daemon_id"] == universe["daemon"]["daemon_id"]
        assert run["runtime_instance_id"] == universe["runtime"]["runtime_instance_id"]
        assert run["checkpoint_backend"] == "memory"
        rendered = str(run["output"]["rendered"])
        assert rendered == "patch [private binding] with [private binding]"
        assert str(universe["values"]["target_repo"]) not in rendered
        assert str(universe["values"]["merge_policy"]) not in rendered

        universe["runs"].append(run_id)
        rq.project_pr(
            universe["dir"],
            destination=_DESTINATION,
            pr_number=index + 1,
            head_sha=head_sha,
            branch_def_id=_BRANCH_ID,
            universe_id=universe_id,
            run_id=run_id,
        )
        decision = rq.decide_and_resume(
            universe["dir"],
            destination=_DESTINATION,
            pr_number=index + 1,
            intent=rq.INTENT_APPROVE,
            workflow_outcome=rq.WORKFLOW_APPROVED,
            decided_by=str(universe["founder"]),
            expected_head_sha=head_sha,
            directive={
                "action": "merge",
                "github_call": {"params": {"event": "APPROVE"}},
            },
        )
        try:
            grant = backend.mint_job_grant(
                universe["binding"], universe["binding"].scope, run_id,
            )
            with backend.resolve_job_grant(
                grant,
                verify_context=lambda ctx: (
                    ctx.run_id == run_id
                    and ctx.universe_id == run["universe_id"]
                    and ctx.founder_id == universe["founder"]
                ),
            ) as lease:
                resolved = lease.reveal()
        except CredentialUnavailable as exc:
            return {"credential_error": exc.code, "run_id": run_id}

        effect_kind = f"review-decision:{index + 1}:{head_sha}"
        receipt_created = rq.record_effect_receipt(
            universe["dir"],
            run_id=run_id,
            effect_kind=effect_kind,
            detail={"pr_number": index + 1, "head_sha": head_sha},
        )
        return {
            "run_id": run_id,
            "universe_id": universe_id,
            "decision": decision["projection"]["owner_intent"],
            "values": runtime_bindings,
            "resolved": resolved,
            "receipt_created": receipt_created,
            "effect_kind": effect_kind,
            "pr_number": index + 1,
            "head_sha": head_sha,
        }

    results: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=_RUN_COUNT) as pool:
        futures = [pool.submit(exercise, case) for case in cases]
        for future in as_completed(futures):
            results.append(future.result(timeout=60))

    assert len(results) == _RUN_COUNT
    credential_errors = [
        result["credential_error"]
        for result in results
        if "credential_error" in result
    ]
    assert VaultErrorCode.REAUTHORIZATION_REQUIRED not in credential_errors
    assert credential_errors == []

    by_pr = {int(result["pr_number"]): result for result in results}
    assert set(by_pr) == set(range(1, _RUN_COUNT + 1))
    for case in cases:
        pr_number = int(case["index"]) + 1
        universe_id = str(case["universe_id"])
        head_sha = str(case["head_sha"])
        universe = universes[universe_id]
        result = by_pr[pr_number]
        run_id = str(result["run_id"])
        assert result["universe_id"] == universe_id
        assert result["decision"] == rq.INTENT_APPROVE
        assert result["values"] == universe["values"]
        assert result["resolved"] == universe["secret"]
        assert result["receipt_created"] is True
        projection = rq.get_projection(
            universe["dir"],
            destination=_DESTINATION,
            pr_number=pr_number,
        )
        assert projection["owner_intent"] == rq.INTENT_APPROVE
        assert projection["run_id"] == run_id
        receipt = rq.has_effect_receipt(
            universe["dir"],
            run_id=run_id,
            effect_kind=str(result["effect_kind"]),
        )
        assert receipt is not None
        assert receipt["detail"] == {"pr_number": pr_number, "head_sha": head_sha}

    for universe_id, universe in universes.items():
        expected = {
            (int(result["pr_number"]), str(result["head_sha"]))
            for result in results
            if result["universe_id"] == universe_id
        }
        pending = [
            row
            for row in rq.list_decision_effects(universe["dir"])
            if row["kind"] == "submit_review" and row["status"] == "pending"
        ]
        assert {
            (
                int(row["payload"]["pr_number"]),
                str(row["payload"]["expected_head_sha"]),
            )
            for row in pending
        } == expected
        assert {str(row["payload"]["decided_by"]) for row in pending} == {
            str(universe["founder"]),
        }

    review_apis = {universe_id: _ReviewApi() for universe_id in universes}

    def drain(universe_id: str):
        universe = universes[universe_id]
        return execute_pending_review_decisions(
            universe["dir"],
            worker_id=f"review-worker-{universe_id}",
            github_api=review_apis[universe_id],
            expected_owner=str(universe["founder"]),
        )

    with ThreadPoolExecutor(max_workers=_UNIVERSE_COUNT) as pool:
        drained = dict(zip(universes, pool.map(drain, universes), strict=True))

    for universe_id, universe in universes.items():
        expected = {
            (int(result["pr_number"]), str(result["head_sha"]))
            for result in results
            if result["universe_id"] == universe_id
        }
        assert sum(
            item["kind"] == "submit_review" and item["executed"]
            for item in drained[universe_id]
        ) == len(expected)
        assert {
            (
                int(str(call["path"]).split("/")[-2]),
                str(call["params"]["commit_id"]),
            )
            for call in review_apis[universe_id].calls
        } == expected
        assert all(
            row["status"] == "succeeded"
            for row in rq.list_decision_effects(universe["dir"])
        )
        assert len(universe["runs"]) == _RUN_COUNT // _UNIVERSE_COUNT

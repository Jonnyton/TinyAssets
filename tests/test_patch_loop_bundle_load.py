"""Bundle-level §14 concurrency proof for the assembled patch loop.

One load wave drives review decisions, private design-binding resolution, and
broker job-grant mint/resolve for 24 real run records across three universes.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Barrier

import pytest

from tinyassets.branch_bindings import bind_branch_values, load_branch_values
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
from tinyassets.storage import review_queue as rq

_UNIVERSE_COUNT = 3
_RUN_COUNT = 24
_DESTINATION = "owner/shared-repo"
_BRANCH_ID = "patch-loop-load"
_SCHEMA = [
    {"name": "target_repo", "type": "str", "is_binding": True},
    {"name": "merge_policy", "type": "str", "is_binding": True},
]


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


@pytest.mark.slow
def test_patch_loop_bundle_concurrent_multi_universe_load(platform_vault_env):
    from tinyassets.runs import create_run

    data_root = platform_vault_env
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

    cases: list[dict[str, object]] = []
    for index in range(_RUN_COUNT):
        universe_id = f"load-u{index % _UNIVERSE_COUNT}"
        universe = universes[universe_id]
        head_sha = f"{index + 1:040x}"
        run_id = create_run(
            data_root,
            branch_def_id=_BRANCH_ID,
            thread_id=f"thread-{index}",
            inputs={"request": f"fix-{index}"},
            daemon_id=universe["daemon"]["daemon_id"],
            runtime_instance_id=universe["runtime"]["runtime_instance_id"],
        )
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
        cases.append({
            "index": index,
            "universe_id": universe_id,
            "run_id": run_id,
            "head_sha": head_sha,
        })

    backend = platform_backend()
    start = Barrier(_RUN_COUNT)

    def exercise(case: dict[str, object]) -> dict[str, object]:
        index = int(case["index"])
        universe_id = str(case["universe_id"])
        run_id = str(case["run_id"])
        head_sha = str(case["head_sha"])
        universe = universes[universe_id]
        start.wait(timeout=30)
        decision = rq.decide_and_resume(
            universe["dir"],
            destination=_DESTINATION,
            pr_number=index + 1,
            intent=rq.INTENT_APPROVE,
            workflow_outcome=rq.WORKFLOW_APPROVED,
            decided_by=str(universe["founder"]),
            expected_head_sha=head_sha,
            directive={"action": "merge"},
            review_effect={"event": "APPROVE", "branch_def_id": _BRANCH_ID},
        )
        values = load_branch_values(universe["dir"], _BRANCH_ID, _SCHEMA)
        try:
            grant = backend.mint_job_grant(
                universe["binding"], universe["binding"].scope, run_id,
            )
            with backend.resolve_job_grant(
                grant,
                verify_context=lambda ctx: (
                    ctx.run_id == run_id
                    and ctx.universe_id == universe_id
                    and ctx.founder_id == universe["founder"]
                ),
            ) as lease:
                resolved = lease.reveal()
        except CredentialUnavailable as exc:
            return {"credential_error": exc.code, "run_id": run_id}
        effect_kind = f"load-decision-{index}"
        receipt_created = rq.record_effect_receipt(
            universe["dir"],
            run_id=run_id,
            effect_kind=effect_kind,
            detail={"pr_number": index + 1},
        )
        return {
            "run_id": run_id,
            "universe_id": universe_id,
            "decision": decision["projection"]["owner_intent"],
            "values": values,
            "resolved": resolved,
            "receipt_created": receipt_created,
            "effect_kind": effect_kind,
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

    by_run = {str(result["run_id"]): result for result in results}
    for case in cases:
        run_id = str(case["run_id"])
        universe_id = str(case["universe_id"])
        universe = universes[universe_id]
        result = by_run[run_id]
        assert result["universe_id"] == universe_id
        assert result["decision"] == rq.INTENT_APPROVE
        assert result["values"] == universe["values"]
        assert result["resolved"] == universe["secret"]
        assert result["receipt_created"] is True
        projection = rq.get_projection(
            universe["dir"],
            destination=_DESTINATION,
            pr_number=int(case["index"]) + 1,
        )
        assert projection["owner_intent"] == rq.INTENT_APPROVE
        assert rq.has_effect_receipt(
            universe["dir"],
            run_id=run_id,
            effect_kind=str(result["effect_kind"]),
        ) is not None

    for universe in universes.values():
        expected = len(universe["runs"])
        assert len(rq.list_pending_review_effects(universe["dir"])) == expected

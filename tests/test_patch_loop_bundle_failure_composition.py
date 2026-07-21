"""Focused bundle probes for simultaneous S1, S4, and credential failures."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from tinyassets import github_http, runs
from tinyassets.branch_tasks import read_queue
from tinyassets.branches import BranchDefinition
from tinyassets.bug_investigation import retry_pending_investigation_triggers
from tinyassets.credentials import CredentialUnavailable, VaultErrorCode
from tinyassets.daemon_server import initialize_author_server, save_branch_definition
from tinyassets.engine_binding import RetiredCredentialStateError
from tinyassets.storage import review_queue as rq
from tinyassets.wiki import trigger_receipts

_DESTINATION = "Owner/Repo"
_HEAD = "a" * 40
_HANDLER = "branch-composed-failure"


def _credential_failure(kind: str) -> Exception:
    if kind == "retired_state":
        return RetiredCredentialStateError("retired credential state")
    return CredentialUnavailable(kind)


@pytest.mark.parametrize(
    "failure_kind",
    [
        VaultErrorCode.REAUTHORIZATION_REQUIRED,
        VaultErrorCode.DELETE_PENDING,
        "retired_state",
    ],
)
def test_s1_retry_survives_credential_failure_while_s4_rows_stay_queued(
    tmp_path, monkeypatch, caplog, failure_kind
):
    """Credential failure must not consume S4 work or strand the S1 retry."""
    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(tmp_path / "wiki"))
    monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", _HANDLER)
    monkeypatch.setenv("TINYASSETS_REQUEST_TYPE_PRIORITIES", "bug_investigation")
    initialize_author_server(tmp_path)
    save_branch_definition(
        tmp_path,
        branch_def=BranchDefinition(branch_def_id=_HANDLER, name=_HANDLER).to_dict(),
    )

    rq.project_pr(
        tmp_path,
        destination=_DESTINATION,
        pr_number=7,
        head_sha=_HEAD,
        branch_def_id=_HANDLER,
        universe_id=tmp_path.name,
    )
    rq.decide_and_resume(
        tmp_path,
        destination=_DESTINATION,
        pr_number=7,
        intent=rq.INTENT_APPROVE,
        workflow_outcome=rq.WORKFLOW_APPROVED,
        decided_by="owner",
        expected_head_sha=_HEAD,
        directive={
            "action": "merge",
            "github_call": {"params": {"event": "APPROVE"}},
        },
    )
    rq.enqueue_manual_merge(
        tmp_path,
        destination=_DESTINATION,
        pr_number=7,
        expected_head_sha=_HEAD,
        branch_def_id=_HANDLER,
        decided_by="owner",
    )
    trigger_receipts.create_pending(
        request_id="BUG-COMPOSED",
        request_kind="bug",
        request_page="pages/bugs/bug-composed.md",
        branch_def_id=_HANDLER,
        universe_id=tmp_path.name,
        payload_json='{"bug_id":"BUG-COMPOSED","title":"credential outage"}',
    )

    def unavailable(*_args, **_kwargs):
        raise _credential_failure(failure_kind)

    monkeypatch.setattr(github_http, "github_client_from_vault", unavailable)
    monkeypatch.setattr(github_http, "verifier_client_from_vault", unavailable)

    with ThreadPoolExecutor(max_workers=2) as executor:
        review_future = executor.submit(runs.run_review_recovery_for_universe, tmp_path)
        retry_future = executor.submit(
            retry_pending_investigation_triggers,
            tmp_path,
            universe_id=tmp_path.name,
        )
        review_result = review_future.result(timeout=10)
        retry_result = retry_future.result(timeout=10)

    assert retry_result["queued"] == ["BUG-COMPOSED"]
    assert len(read_queue(tmp_path)) == 1
    assert trigger_receipts.pending_attempts(universe_id=tmp_path.name) == []
    assert [row["reason"] for row in review_result["execute_decisions"]] == [
        "no_client"
    ]
    assert [row["reason"] for row in review_result["drain_manual_merges"]] == [
        "no_client"
    ]
    assert rq.list_decision_effects(tmp_path)[0]["status"] == "pending"
    assert len(rq.list_pending_manual_merges(tmp_path)) == 1
    expected_marker = (
        "retired credential state"
        if failure_kind == "retired_state"
        else failure_kind
    )
    assert expected_marker in caplog.text

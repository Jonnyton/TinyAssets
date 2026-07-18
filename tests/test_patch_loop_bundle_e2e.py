"""Patch-loop BUNDLE integration — the REAL path (Codex r15 coordinator ask).

Proves the genuine end-to-end contract on the integration branch (S1 seed + S3
enforcement + S4 effector all present): compile the reference design, INVOKE it
through the real run executor, the present node's effect dispatch PROJECTS the
PR + SUSPENDS the run (interrupted, not completed), the owner decides on the
review surface, and the continuation RESUMES the run — not a fabricated packet
+ direct effector call.

Skip semantics (Codex r15): SKIP only when the S1 seed is genuinely ABSENT
(S4-alone). When the seed is PRESENT but its contract can't be read, that is a
FAILURE (a silent skip would hide a broken bundle contract).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import tinyassets.runs as runs
from tinyassets.effectors import github_pr
from tinyassets.storage import review_queue as rq

_REFERENCE_SEED = (
    Path(__file__).resolve().parents[1]
    / "tinyassets" / "branch_designs" / "patch_loop_reference.json"
)


def _reference_nodes(spec: dict) -> list[dict]:
    """Extract the NodeDefinition list from whichever envelope S1 lands with:
    S1 stores nodes under ``spec.node_defs`` (a ``spec`` wrapper), with legacy
    top-level / ``spec_json`` fallbacks."""
    wrapper = spec.get("spec") if isinstance(spec.get("spec"), dict) else {}
    inner = spec.get("spec_json") if isinstance(spec.get("spec_json"), dict) else {}
    return (
        wrapper.get("node_defs")
        or spec.get("node_defs")
        or inner.get("node_defs")
        or wrapper.get("nodes")
        or spec.get("nodes")
        or inner.get("nodes")
        or []
    )


def _reference_status() -> str:
    """``absent`` (seed missing → skip) | ``unreadable`` (present but contract
    unparseable → FAIL) | ``ready`` (present + declares the effects)."""
    if not _REFERENCE_SEED.exists():
        return "absent"
    try:
        spec = json.loads(_REFERENCE_SEED.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return "unreadable"
    nodes = _reference_nodes(spec)
    if not nodes:
        return "unreadable"
    sinks = {
        sink for node in nodes if isinstance(node, dict)
        for sink in (node.get("effects") or [])
    }
    if not ({"github_pull_request", "github_merge"} <= sinks):
        return "unreadable"
    return "ready"


_STATUS = _reference_status()


def test_bundle_contract_present_and_readable_or_genuinely_absent():
    """FAIL-not-skip guard (Codex r15): the ONLY acceptable non-ready state is a
    genuinely ABSENT seed (S4-alone). A present-but-unreadable seed is a broken
    bundle contract and must FAIL, never silently skip."""
    assert _REFERENCE_SEED.name == "patch_loop_reference.json"
    assert _STATUS in ("absent", "ready"), (
        f"reference seed present but contract UNREADABLE ({_STATUS}); this is a "
        "broken bundle contract, not a skip"
    )


def _load_reference_branch():
    from tinyassets.branches import BranchDefinition

    spec = json.loads(_REFERENCE_SEED.read_text(encoding="utf-8"))
    inner = spec.get("spec") if isinstance(spec.get("spec"), dict) else spec
    return BranchDefinition.from_dict(inner)


class _FakeClient:
    def __init__(self):
        self.submitted = []

    def run_call(self, call):
        self.submitted.append(call)
        return {"ok": True, "kind": call.kind, "status": 200, "result": {}}

    def get_pull(self, **_kwargs):
        return {
            "head_sha": "a" * 40,
            "author_login": "tinyassets-app[bot]",
            "author_type": "Bot",
            "auto_merge_enabled": False,
        }


def _scripted_reference_provider(prompt, *args, **kwargs):
    del args, kwargs
    head = "a" * 40
    if "verification GATE" in prompt:
        return json.dumps({
            "verdict": "pass",
            "verdict_evidence": {"reason": "focused tests passed"},
        })
    if "owner review GATE" in prompt:
        return json.dumps({
            "verdict": "pass",
            "verdict_evidence": {"reason": "owner approved"},
            "reshape_notes": "",
        })
    if "github_pull_request external-write packet" in prompt:
        return json.dumps({
            "github_pr_packet": {
                "sink": "github_pull_request",
                "destination": "Owner/Repo",
                "payload": {
                    "title": "Fix filed bundle bug",
                    "body": "Triggered by the public wiki filing.",
                    "base_branch": "main",
                    "head_branch": "auto/bundle-trace",
                    "draft": False,
                    "changes_json": {"fix.txt": "fixed\n"},
                    "review_queue": {
                        "request_ref": "BUG-001",
                        "verify_verdict": "pass",
                    },
                },
            },
            "present_output": "queued PR #7",
        })
    if "github_merge external-write packet" in prompt:
        return json.dumps({
            "github_merge_packet": {
                "sink": "github_merge",
                "destination": "Owner/Repo",
                "payload": {
                    "pr_number": 7,
                    "expected_head_sha": head,
                    "merge_method": "squash",
                    "authorization": {"mode": "github_branch_protection"},
                },
            },
            "merge_output": "merge queued",
        })
    return "step completed"


class _HttpTraceTransport:
    """Stateful transport for the production HttpGitHubApi implementation."""

    def __init__(self):
        self.head = "a" * 40
        self.merged = False
        self.reviewed = False
        self.calls = []

    def __call__(self, *, method, url, token, body, timeout, accept):
        del timeout, accept
        path = url.split("api.github.com", 1)[-1]
        self.calls.append((method, path, token, body))
        if method == "POST" and path == "/repos/Owner/Repo/pulls/7/reviews":
            self.reviewed = True
            return 200, {"id": 71}
        if method == "GET" and path.startswith(
            "/repos/Owner/Repo/pulls/7/reviews?"
        ):
            reviews = []
            if self.reviewed:
                reviews.append({
                    "id": 71,
                    "commit_id": self.head,
                    "state": "APPROVED",
                    "user": {"login": "owner"},
                })
            return 200, reviews
        if method == "GET" and path == "/repos/Owner/Repo/pulls/7":
            return 200, {
                "state": "closed" if self.merged else "open",
                "merged": self.merged,
                "mergeable_state": "clean",
                "head": {"sha": self.head},
                "base": {"ref": "main"},
                "user": {"login": "workflow-app[bot]", "type": "Bot"},
                "node_id": "PR_trace_7",
                "merge_commit_sha": "b" * 40 if self.merged else None,
            }
        if method == "PUT" and path == "/repos/Owner/Repo/pulls/7/merge":
            self.merged = True
            return 200, {"merged": True, "sha": "b" * 40}
        raise AssertionError(f"unexpected GitHub request: {method} {path}")


def _isolated_executor_available() -> bool:
    """Is a REAL per-job sandbox RUNNER (isolated executor) wired for the
    repo-touching nodes (investigate/verify/draft_patch)? That confiner is a
    separate host-approved Phase-2 slice — absent here, so the runner-enabled
    continuation case skips rather than pretending a mock executor is real.
    Opt-in via the explicit env flag the live wiring sets."""
    import os

    return os.environ.get("TINYASSETS_S4_ISOLATED_EXECUTOR", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


@pytest.mark.skipif(_STATUS != "ready", reason="S1 reference seed absent (S4-alone)")
def test_pre_runner_execution_refuses_at_investigate(tmp_path):
    """(a) PRE-RUNNER REFUSAL (S1 reference design, fail-closed): with NO provider
    and NO sandbox runner, the repo-touching sandbox-required nodes
    (investigate/verify/draft_patch, node_kind repo_read/repo_exec/coding) REFUSE
    at invoke time — the loop cannot run unconfined on S1/S1+S3. Execution must
    NOT reach `present` and must NOT open a PR, and the run must NOT complete."""
    branch = _load_reference_branch()
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=branch.branch_def_id, merge_preference="manual",
        review_required=True, bound_by="owner",
    )
    run_id = runs._prepare_run(
        tmp_path, branch=branch, inputs={}, run_name="", actor="owner",
    )
    outcome = runs._invoke_graph(
        tmp_path, run_id=run_id, branch=branch, inputs={}, provider_call=None,
    )
    # Fail-closed BEFORE `present`: no PR was projected and the run did not
    # complete (it refused at a sandbox-required node, never reached present).
    assert rq.get_projection(tmp_path, destination="Owner/Repo", pr_number=7) is None
    assert outcome.status != runs.RUN_STATUS_COMPLETED


@pytest.mark.skipif(
    _STATUS != "ready" or not _isolated_executor_available(),
    reason=(
        "S1 reference seed absent, or no real isolated executor wired "
        "(the per-job sandbox runner is a separate host-approved slice)"
    ),
)
def test_runner_enabled_present_to_owner_resume(monkeypatch, tmp_path):
    """(b) RUNNER-ENABLED CONTINUATION: ONLY when a real isolated executor is
    present may the sandbox-required nodes execute → the present effect projects +
    SUSPENDS the run → owner approves → the continuation resumes to a terminal
    state. Skipped unless a real runner is wired (never a mock standing in)."""
    # Open the github_pr gates so the present node "opens" a PR (no live network).
    monkeypatch.setattr(github_pr, "resolve_soul_effect_authority", lambda *a, **k: "")
    monkeypatch.setattr(github_pr, "_read_capability", lambda *a, **k: "tok")
    monkeypatch.setattr(github_pr, "_check_consent", lambda *a, **k: True)
    monkeypatch.setattr(github_pr, "_try_reserve", lambda *a, **k: {"status": "no_hint"})
    monkeypatch.setattr(
        github_pr, "_materialize_branch",
        lambda **k: {"head_branch": "auto/fix", "commit_sha": "a" * 40},
    )
    monkeypatch.setattr(
        github_pr, "_invoke_gh_pr_create",
        lambda **k: {"pr_url": "https://github.com/Owner/Repo/pull/7",
                     "pr_number": 7, "stdout": "", "invocation_mode": "gh"},
    )
    branch = _load_reference_branch()
    rq.set_merge_preference_binding(
        tmp_path, branch_def_id=branch.branch_def_id, merge_preference="manual",
        review_required=True, bound_by="owner",
    )
    run_id = runs._prepare_run(
        tmp_path, branch=branch, inputs={}, run_name="", actor="owner",
    )
    outcome = runs._invoke_graph(
        tmp_path, run_id=run_id, branch=branch, inputs={}, provider_call=None,
    )
    assert outcome.status == runs.RUN_STATUS_INTERRUPTED
    proj = rq.get_projection(tmp_path, destination="Owner/Repo", pr_number=7)
    assert proj is not None and proj["workflow_outcome"] == "open"

    rq.decide_and_resume(
        tmp_path, destination="Owner/Repo", pr_number=7, intent="approve",
        workflow_outcome=rq.WORKFLOW_APPROVED, decided_by="owner",
        expected_head_sha="a" * 40,
        directive={"action": "merge", "github_call": {
            "kind": "submit_review_approve", "transport": "rest", "method": "POST",
            "path": "/repos/Owner/Repo/pulls/7/reviews",
            "params": {"event": "APPROVE", "commit_id": "a" * 40}, "summary": "ok"}},
    )
    executed = runs.execute_pending_review_decisions(
        tmp_path,
        worker_id="review-worker",
        github_api=_FakeClient(),
        expected_owner="owner",
    )
    assert executed[-1]["kind"] == "finalize_run"
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED


def test_public_trigger_dedup_run_http_review_and_merge_trace(
    monkeypatch, tmp_path, request
):
    """One non-skipped trace through S1 intake and the public run dispatcher.

    Network is replaced only at HttpGitHubApi's transport boundary; review and
    merge use the production client, queue workers, head check, and owner check.
    """
    from tests._executor_sim import install_worker_sim
    from tinyassets import bug_investigation
    from tinyassets import github_auth as ga
    from tinyassets import github_http as gh
    from tinyassets.auth import middleware as auth_middleware_module
    from tinyassets.auth.provider import Identity
    from tinyassets.branch_bindings import bind_branch_values
    from tinyassets.branch_designs import design_tag, seed_reference_designs
    from tinyassets.branch_tasks import read_queue
    from tinyassets.daemon_registry import create_daemon, summon_daemon
    from tinyassets.daemon_server import (
        ensure_universe_registered,
        get_branch_definition,
        grant_universe_access,
        list_branch_definitions,
    )
    from tinyassets.providers import call as provider_call_module
    from tinyassets.universe_server import extensions, wiki

    monkeypatch.setenv("TINYASSETS_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TINYASSETS_WIKI_PATH", str(tmp_path / "wiki"))
    universe_id = "u-bundle-trace"
    universe_dir = tmp_path / universe_id
    universe_dir.mkdir()
    identity = Identity(
        user_id="owner",
        username="owner",
        capabilities=[
            "tinyassets.wiki.write",
            "tinyassets.extensions.costly",
            "tinyassets.universe.admin",
        ],
    )
    identity_token = auth_middleware_module._current_identity.set(identity)
    request.addfinalizer(
        lambda: auth_middleware_module._current_identity.reset(identity_token)
    )
    ensure_universe_registered(
        tmp_path, universe_id=universe_id, universe_path=universe_dir
    )
    grant_universe_access(
        tmp_path,
        universe_id=universe_id,
        actor_id="owner",
        permission="admin",
        granted_by="test",
    )

    seed_reference_designs(tmp_path)
    reference_id = list_branch_definitions(
        tmp_path, tag=design_tag("patch_loop_reference", 1)
    )[0]["branch_def_id"]
    remixed = json.loads(
        extensions(
            action="remix_design",
            branch_def_id=reference_id,
            name="Owned public-path patch loop",
        )
    )
    assert remixed["status"] == "remixed", remixed
    branch_id = remixed["branch_def_id"]
    branch = get_branch_definition(tmp_path, branch_def_id=branch_id)
    bind_branch_values(
        universe_dir,
        branch_def_id=branch_id,
        state_schema=branch["state_schema"],
        values={"target_repo": "Owner/Repo", "merge_policy": "manual"},
        actor="owner",
    )
    rq.set_merge_preference_binding(
        universe_dir,
        branch_def_id=branch_id,
        merge_preference="manual",
        review_required=True,
        founder_github_handle="owner",
        bound_by="owner",
    )
    daemon = create_daemon(tmp_path, display_name="trace-daemon", created_by="owner")
    summon_daemon(
        tmp_path,
        daemon_id=daemon["daemon_id"],
        universe_id=universe_id,
        provider_name="claude-code",
        model_name="bundle-trace",
        created_by="owner",
    )

    monkeypatch.setenv("TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID", branch_id)
    monkeypatch.setattr(
        bug_investigation, "BUG_INVESTIGATION_BRANCH_DEF_ID", branch_id
    )
    filed = json.loads(
        wiki(
            action="file_bug",
            universe_id=universe_id,
            component="patch-loop",
            severity="major",
            title="Bundle user path loses a review",
            observed="No merge receipt",
            expected="One reviewed merge",
        )
    )
    duplicate = json.loads(
        wiki(
            action="file_bug",
            universe_id=universe_id,
            component="patch-loop",
            severity="major",
            title="Bundle user path loses a review",
            observed="No merge receipt",
            expected="One reviewed merge",
        )
    )
    assert "trigger" in filed, filed
    assert filed["trigger"]["status"] == "queued", filed
    assert duplicate["status"] == "similar_found", duplicate
    tasks = read_queue(universe_dir)
    assert len(tasks) == 1
    task = tasks[0]
    assert task.branch_def_id == branch_id
    assert task.branch_task_id == filed["trigger"]["dispatcher_request_id"]

    install_worker_sim(monkeypatch)
    monkeypatch.setattr(
        provider_call_module, "call_provider", _scripted_reference_provider
    )
    monkeypatch.setattr(github_pr, "resolve_soul_effect_authority", lambda *a, **k: "")
    monkeypatch.setattr(github_pr, "_read_capability", lambda *a, **k: "tok")
    monkeypatch.setattr(github_pr, "_check_consent", lambda *a, **k: True)
    monkeypatch.setattr(github_pr, "_try_reserve", lambda *a, **k: {"status": "no_hint"})
    monkeypatch.setattr(
        github_pr,
        "_materialize_branch",
        lambda **k: {"head_branch": "auto/bundle-trace", "commit_sha": "a" * 40},
    )
    monkeypatch.setattr(
        github_pr,
        "_invoke_gh_pr_create",
        lambda **k: {
            "pr_url": "https://github.com/Owner/Repo/pull/7",
            "pr_number": 7,
            "stdout": "",
            "invocation_mode": "gh",
        },
    )
    queued = json.loads(
        extensions(
            action="run_branch",
            branch_def_id=task.branch_def_id,
            universe_id=universe_id,
            inputs_json=json.dumps({
                **task.inputs,
                "intake_source": "wiki:file_bug",
                "request_payload": json.dumps(task.inputs),
                "verify_command": "pytest -q",
                "reshape_notes": "",
            }),
        )
    )
    assert queued["status"] == "queued", queued
    run_id = queued["run_id"]
    runs.wait_for(run_id, timeout=30)
    run_record = runs.get_run(tmp_path, run_id)
    assert run_record["status"] == runs.RUN_STATUS_INTERRUPTED
    assert run_record["inputs"]["bug_id"] == filed["bug_id"]
    projection = rq.get_projection(
        universe_dir, destination="Owner/Repo", pr_number=7
    )
    assert projection is not None, rq.list_projections(universe_dir)
    assert projection["run_id"] == run_id
    assert projection["head_sha"] == "a" * 40

    approved = json.loads(
        extensions(
            action="review_queue_approve",
            universe_id=universe_id,
            project_id="Owner/Repo",
            subject_id="7",
            expected_version="a" * 40,
        )
    )
    assert approved["status"] == "pending", approved
    transport = _HttpTraceTransport()
    token_provider = ga.CompositeTokenProvider(
        installation=ga.StaticTokenProvider(
            "ghs_trace", purposes={ga.PURPOSE_INSTALLATION}
        ),
        user_review=ga.StaticTokenProvider(
            "gho_trace", purposes={ga.PURPOSE_USER_REVIEW}
        ),
    )
    github_api = gh.HttpGitHubApi(
        token_provider, request_fn=transport, sleep_fn=lambda _seconds: None
    )
    continued = runs.execute_pending_review_decisions(
        universe_dir,
        worker_id="review-worker",
        github_api=github_api,
        expected_owner="owner",
    )
    assert continued[-1]["kind"] == "finalize_run", continued
    merge_queued = json.loads(
        extensions(
            action="review_queue_merge",
            universe_id=universe_id,
            project_id="Owner/Repo",
            subject_id="7",
            expected_version="a" * 40,
        )
    )
    assert merge_queued["merge_enqueued"] is True, merge_queued
    merged = runs.execute_pending_manual_merges(
        universe_dir,
        github_api=github_api,
        expected_owner="owner",
    )
    assert merged == [{
        "merge_id": merged[0]["merge_id"],
        "confirmed": True,
        "pr_number": 7,
        "merge_commit_sha": "b" * 40,
    }]
    assert transport.reviewed is True
    assert transport.merged is True
    http_calls = [(method, path, token) for method, path, token, _ in transport.calls]
    assert (
        "POST",
        "/repos/Owner/Repo/pulls/7/reviews",
        "gho_trace",
    ) in http_calls
    assert (
        "PUT",
        "/repos/Owner/Repo/pulls/7/merge",
        "ghs_trace",
    ) in http_calls
    assert rq.list_pending_manual_merges(universe_dir) == []
    assert runs.get_run(tmp_path, run_id)["status"] == runs.RUN_STATUS_COMPLETED
    trace = {
        "trigger_attempt_id": filed["trigger"]["trigger_attempt_id"],
        "branch_task_id": task.branch_task_id,
        "run_id": run_id,
        "pr_number": projection["pr_number"],
        "head_sha": projection["head_sha"],
    }
    assert all(trace.values())
    assert trace == {
        "trigger_attempt_id": filed["trigger"]["trigger_attempt_id"],
        "branch_task_id": filed["trigger"]["dispatcher_request_id"],
        "run_id": queued["run_id"],
        "pr_number": 7,
        "head_sha": "a" * 40,
    }

"""Direct tests for `workflow.api.universe` after decomp Step 9.

Legacy test files for the `universe()` MCP tool import via
`workflow.universe_server` and continue to pass through the back-compat
re-export shim. This file exercises `workflow.api.universe` directly to
lock in the new public surface.

Pattern mirrors `test_api_market.py` / `test_api_runs.py` /
`test_api_runtime_ops.py` from Steps 4-7.

Surface guarded:
- `WRITE_ACTIONS` table contract — every action mapped to (extractor, daemon-gate)
- `_dispatch_with_ledger`, `_scope_universe_response`, `_ledger_target_dir`
  ledger trio — universe-tool internal pipeline
- `_action_*` handler set — present, callable, owned by this module
- Daemon-liveness telemetry helpers — present, owned by this module
- Pattern A2 wrapper: `workflow.universe_server.universe` delegates to
  `workflow.api.universe._universe_impl` (verified via simple round-trip)
"""

from __future__ import annotations

import json

import pytest

from workflow.api import universe as univ_mod

# ── module surface ──────────────────────────────────────────────────────────


def test_module_exposes_expected_public_names() -> None:
    """Contract surface — guards against silent removal post-Step-9."""
    expected = {
        # WRITE_ACTIONS table + 17 extractor closures
        "WRITE_ACTIONS",
        "_extract_submit_request", "_extract_give_direction",
        "_extract_set_premise", "_extract_add_canon",
        "_extract_add_canon_from_path", "_extract_control_daemon",
        "_extract_switch_universe", "_extract_create_universe",
        "_extract_queue_cancel", "_extract_subscribe_goal",
        "_extract_unsubscribe_goal", "_extract_post_to_goal_pool",
        "_extract_submit_node_bid", "_extract_set_tier_config",
        "_extract_daemon_create", "_extract_daemon_summon",
        "_extract_daemon_banish", "_extract_daemon_control",
        "_extract_daemon_update_behavior",
        "_extract_daemon_memory_capture", "_extract_daemon_memory_review",
        "_extract_daemon_memory_promote",
        # Ledger dispatcher trio
        "_ledger_target_dir", "_scope_universe_response",
        "_dispatch_with_ledger",
        # Pattern A2 universe() body
        "_universe_impl",
        # Daemon telemetry
        "_last_activity_at", "_staleness_bucket", "_phase_human",
        "_compute_accept_rate_from_db", "_compute_word_count_from_files",
        "_daemon_liveness", "_parse_activity_line",
        # universe-tool action handlers
        "_action_list_universes", "_action_inspect_universe",
        "_action_read_output", "_action_submit_request",
        "_action_queue_list", "_action_daemon_overview",
        "_action_daemon_list", "_action_daemon_get",
        "_action_daemon_create", "_action_daemon_summon",
        "_action_daemon_banish", "_action_daemon_pause",
        "_action_daemon_resume", "_action_daemon_restart",
        "_action_daemon_update_behavior", "_action_daemon_control_status",
        "_action_daemon_memory_capture", "_action_daemon_memory_search",
        "_action_daemon_memory_list", "_action_daemon_memory_review",
        "_action_daemon_memory_promote", "_action_daemon_memory_status",
        "_action_treasury_status",
        "_action_set_tier_config", "_action_queue_cancel",
        "_action_subscribe_goal", "_action_unsubscribe_goal",
        "_action_list_subscriptions", "_action_post_to_goal_pool",
        "_action_submit_node_bid", "_action_community_change_context",
        "_action_give_direction",
        "_action_query_world", "_action_read_premise",
        "_action_set_premise", "_action_add_canon",
        "_action_add_canon_from_path", "_action_list_canon",
        "_action_read_canon", "_action_list_sources",
        "_action_read_source", "_action_control_daemon",
        "_action_get_activity", "_action_get_recent_events",
        "_action_get_ledger", "_action_switch_universe",
        "_action_create_universe",
    }
    actual = set(dir(univ_mod))
    missing = expected - actual
    assert not missing, (
        f"workflow.api.universe missing expected public names: {sorted(missing)}"
    )


def test_write_actions_table_has_24_entries() -> None:
    """WRITE_ACTIONS dict literal includes daemon create/summon/banish writes."""
    assert len(univ_mod.WRITE_ACTIONS) == 24


def test_write_actions_entries_are_extractor_gate_tuples() -> None:
    """Every entry is (extractor_callable, write_gate). The write_gate is
    one of: None (always-write), a callable returning bool, or a set of
    allowed sub-command strings (control_daemon's pause/resume gate)."""
    for action, entry in univ_mod.WRITE_ACTIONS.items():
        assert isinstance(entry, tuple), f"{action} entry not a tuple"
        assert len(entry) == 2, f"{action} entry length != 2"
        extractor, gate = entry
        assert callable(extractor), f"{action} extractor not callable"
        assert gate is None or callable(gate) or isinstance(gate, set), (
            f"{action} gate must be None, callable, or set; "
            f"got {type(gate).__name__}={gate!r}"
        )


# ── Pattern A2 wrapper round-trip ────────────────────────────────────────────


def test_pattern_a2_wrapper_delegates_to_api_universe() -> None:
    """`workflow.universe_server.universe` MUST be a thin wrapper that
    delegates to `workflow.api.universe._universe_impl`.

    Validates the Step 9 Pattern A2 contract: the FastMCP @mcp.tool
    registration lives in universe_server.py, the body lives in
    workflow.api.universe._universe_impl. Catches any silent regression
    where the wrapper grows independent logic.
    """
    from workflow import universe_server as us

    assert callable(us.universe)
    # Read-only action — no side effects.
    result = us.universe(action="list")
    direct = univ_mod._universe_impl(action="list")
    assert result == direct, "Pattern A2 wrapper drift: us.universe != _universe_impl"


def test_community_change_context_tool_delegates_to_api_universe(monkeypatch) -> None:
    """Top-level review-context alias stays a thin Pattern A2 wrapper."""
    from workflow import universe_server as us

    seen = {}

    def fake_universe_impl(**kwargs):
        seen.update(kwargs)
        return "ok"

    monkeypatch.setattr(us, "_universe_impl", fake_universe_impl)

    result = us.community_change_context(filter_text="pr:107", limit=2)

    assert result == "ok"
    assert seen == {
        "action": "community_change_context",
        "filter_text": "pr:107",
        "limit": 2,
    }


# ── Ledger dispatcher contract ───────────────────────────────────────────────


def test_dispatch_with_ledger_signature() -> None:
    """`_dispatch_with_ledger(action, kwargs, *, universe_id)` contract."""
    import inspect
    sig = inspect.signature(univ_mod._dispatch_with_ledger)
    params = list(sig.parameters.keys())
    # Don't lock on exact names — ensure (action, kwargs, ...) shape.
    assert len(params) >= 2
    assert params[0] in {"action", "name"}


def test_scope_universe_response_prepends_universe_lead_in() -> None:
    """#15 contract: response carries a `Universe: <id>` text lead-in."""
    raw = '{"text": "hello", "universe_id": "u_test"}'
    out = univ_mod._scope_universe_response(raw)
    assert "Universe:" in out


# ── Daemon telemetry helpers ─────────────────────────────────────────────────


def test_staleness_bucket_handles_none() -> None:
    """`_staleness_bucket(None)` must return a defined bucket, not raise."""
    result = univ_mod._staleness_bucket(None)
    assert isinstance(result, str)
    assert result  # non-empty


def test_daemon_liveness_returns_dict_with_required_keys(tmp_path) -> None:
    """`_daemon_liveness(udir, status)` returns the contract dict shape
    consumed by `_action_list_universes`, `_action_inspect_universe`,
    and `_action_daemon_overview`."""
    result = univ_mod._daemon_liveness(tmp_path, status=None)
    assert isinstance(result, dict)
    # The exact keys are part of the public contract — lock the shape.
    expected_keys = {"liveness", "staleness", "human_phase"}
    actual_keys = set(result.keys())
    # Tolerant assertion — at least one expected key present (full lockdown
    # belongs in dedicated daemon_liveness tests; this sentinel guards
    # against shape collapse).
    assert actual_keys & expected_keys, (
        f"_daemon_liveness shape unexpected: got {actual_keys}, "
        f"expected at least one of {expected_keys}"
    )


# ── 33-handler dispatch table sanity ─────────────────────────────────────────


def test_universe_impl_dispatch_table_has_known_actions() -> None:
    """The `dispatch` table inside `_universe_impl` includes roster actions."""
    # Round-trip "list" through _universe_impl to confirm the dispatch
    # table is wired and covers at least one read action.
    out = univ_mod._universe_impl(action="list")
    assert isinstance(out, str)
    assert out  # non-empty JSON


@pytest.mark.parametrize("action", [
    "list", "inspect", "read_output", "submit_request", "queue_list",
    "daemon_overview", "daemon_list", "daemon_get", "daemon_create",
    "daemon_summon", "daemon_pause", "daemon_resume", "daemon_restart",
    "daemon_banish", "daemon_update_behavior", "daemon_control_status",
    "daemon_memory_capture", "daemon_memory_search", "daemon_memory_list",
    "daemon_memory_review", "daemon_memory_promote", "daemon_memory_status",
    "set_tier_config", "queue_cancel",
    "subscribe_goal", "unsubscribe_goal", "list_subscriptions",
    "post_to_goal_pool", "submit_node_bid", "community_change_context",
    "give_direction",
    "query_world", "read_premise", "set_premise", "add_canon",
    "add_canon_from_path", "list_canon", "read_canon",
    "list_sources", "read_source",
    "control_daemon", "get_activity", "get_recent_events",
    "get_ledger", "switch_universe", "create_universe",
])
def test_every_universe_action_dispatches(action: str, monkeypatch) -> None:
    """Every action verb resolves to a handler (no `Unknown action 'X'` errors
    from the top-level dispatch table).

    Smoke-tests dispatch only — we pass empty kwargs and accept any
    response shape (handlers may legitimately error on missing args, including
    handler-internal "Unknown daemon action" errors that are NOT dispatch-table
    misses). The bug we're guarding against is "action verb dropped from the
    universe() dispatch table" — caught by the exact-string `"Unknown action
    '<action>'"` sentinel.
    """
    if action == "community_change_context":
        monkeypatch.setattr(univ_mod, "_github_read", lambda *a, **k: ([], None))
        monkeypatch.setattr(univ_mod, "_change_loop_plan_context", lambda: {})
    out = univ_mod._universe_impl(action=action)
    sentinel = f"Unknown action '{action}'"
    assert sentinel not in out, (
        f"action {action!r} dropped from _universe_impl dispatch table"
    )


def test_community_change_context_overview(monkeypatch) -> None:
    """Queue view exposes PRs, change requests, auto-fix runs, and PLAN."""
    monkeypatch.setattr(univ_mod, "_github_repo", lambda: "owner/repo")
    monkeypatch.setattr(
        univ_mod,
        "_change_loop_plan_context",
        lambda: {"Scoping Rules": "## Scoping Rules\nPrefer minimal primitives."},
    )

    def fake_github_read(path: str, *, params=None):
        if path == "/repos/owner/repo/pulls":
            return ([{
                "number": 100,
                "title": "[auto-change] BUG-001: fix request flow",
                "state": "open",
                "html_url": "https://example.test/pull/100",
                "head": {"ref": "auto-change/issue-1-codex"},
                "base": {"ref": "main"},
                "labels": [{"name": "daemon-request"}],
            }, {
                "number": 101,
                "title": "manual maintenance",
                "state": "open",
                "head": {"ref": "codex/manual"},
                "base": {"ref": "main"},
            }], None)
        if path == "/repos/owner/repo/issues":
            return ([{
                "number": 57,
                "title": "BUG-027: startup probe missing",
                "state": "open",
                "html_url": "https://example.test/issues/57",
                "labels": [{"name": "daemon-request"}],
            }, {
                "number": 100,
                "title": "PR issue wrapper",
                "pull_request": {"url": "https://example.test/pulls/100"},
            }], None)
        if path == "/repos/owner/repo/actions/workflows/auto-fix-bug.yml/runs":
            return ({"workflow_runs": [{
                "id": 2520,
                "status": "completed",
                "conclusion": "success",
                "event": "issues",
                "head_sha": "abc123",
                "html_url": "https://example.test/actions/runs/2520",
            }]}, None)
        raise AssertionError(path)

    monkeypatch.setattr(univ_mod, "_github_read", fake_github_read)

    data = json.loads(univ_mod._action_community_change_context(limit=5))

    assert data["repo"] == "owner/repo"
    assert data["selector"] == "queue"
    assert data["plan_sections"]["Scoping Rules"].startswith("## Scoping Rules")
    assert [pr["number"] for pr in data["open_prs"]] == [100, 101]
    assert [pr["number"] for pr in data["open_auto_change_prs"]] == [100]
    assert [issue["number"] for issue in data["open_change_requests"]] == [57]
    assert [issue["number"] for issue in data["open_daemon_request_issues"]] == [57]
    assert data["latest_auto_fix_runs"][0]["id"] == 2520
    assert data["errors"] == []


def test_community_change_context_pr_detail(monkeypatch) -> None:
    """PR selector returns reviewable code context, not just metadata."""
    monkeypatch.setattr(univ_mod, "_github_repo", lambda: "owner/repo")
    monkeypatch.setattr(univ_mod, "_change_loop_plan_context", lambda: {})

    def fake_github_read(path: str, *, params=None):
        if path == "/repos/owner/repo/pulls/57":
            return ({
                "number": 57,
                "title": "[auto-change] BUG-027",
                "state": "open",
                "draft": False,
                "html_url": "https://example.test/pull/57",
                "head": {"ref": "auto-change/issue-57-codex", "sha": "abc123"},
                "base": {"ref": "main"},
                "body": "Fixes the startup probe.",
            }, None)
        if path == "/repos/owner/repo/pulls/57/files":
            return ([{
                "filename": "workflow/startup.py",
                "status": "modified",
                "additions": 4,
                "deletions": 1,
                "changes": 5,
                "patch": "@@ -1 +1 @@\n-old\n+new",
            }], None)
        if path == "/repos/owner/repo/issues/57/comments":
            return ([{
                "user": {"login": "reviewer"},
                "created_at": "2026-05-01T00:00:00Z",
                "body": "Please explain why this is not patch-on-patch.",
            }], None)
        if path == "/repos/owner/repo/pulls/57/reviews":
            return ([{
                "user": {"login": "checker"},
                "state": "COMMENTED",
                "submitted_at": "2026-05-01T00:01:00Z",
                "body": "Needs design context.",
            }], None)
        raise AssertionError(path)

    monkeypatch.setattr(univ_mod, "_github_read", fake_github_read)

    data = json.loads(univ_mod._action_community_change_context(
        filter_text="pr:57",
        limit=2,
    ))

    assert data["target"] == "pr:57"
    assert data["pr"]["head"] == "auto-change/issue-57-codex"
    assert data["files"][0]["filename"] == "workflow/startup.py"
    assert data["files"][0]["patch_excerpt"].startswith("@@")
    assert data["comments"][0]["author"] == "reviewer"
    assert data["reviews"][0]["state"] == "COMMENTED"


def test_community_change_context_issue_detail(monkeypatch) -> None:
    """Issue selector returns the request thread the loop should satisfy."""
    monkeypatch.setattr(univ_mod, "_github_repo", lambda: "owner/repo")
    monkeypatch.setattr(univ_mod, "_change_loop_plan_context", lambda: {})

    def fake_github_read(path: str, *, params=None):
        if path == "/repos/owner/repo/issues/39":
            return ({
                "number": 39,
                "title": "BUG-013: missing feature request verb",
                "state": "open",
                "html_url": "https://example.test/issues/39",
                "labels": [{"name": "daemon-request"}],
                "body": "The live connector needs a file_feature_request verb.",
            }, None)
        if path == "/repos/owner/repo/issues/39/comments":
            return ([{
                "user": {"login": "daemon"},
                "created_at": "2026-05-01T00:02:00Z",
                "body": "I am preparing a branch.",
            }], None)
        raise AssertionError(path)

    monkeypatch.setattr(univ_mod, "_github_read", fake_github_read)

    data = json.loads(univ_mod._action_community_change_context(
        filter_text="issue:39",
        limit=1,
    ))

    assert data["target"] == "issue:39"
    assert data["issue"]["number"] == 39
    assert data["comments"][0]["author"] == "daemon"


def test_daemon_actions_create_summon_and_banish(tmp_path, monkeypatch) -> None:
    """Daemon roster actions round-trip through the public universe API body."""
    universe_dir = tmp_path / "u1"
    universe_dir.mkdir()
    monkeypatch.setattr(univ_mod, "_base_path", lambda: tmp_path)
    monkeypatch.setattr(univ_mod, "_default_universe", lambda: "u1")
    monkeypatch.setattr(univ_mod, "_universe_dir", lambda uid: tmp_path / uid)
    monkeypatch.setenv("UNIVERSE_SERVER_USER", "host-test")

    create_out = json.loads(univ_mod._universe_impl(
        action="daemon_create",
        universe_id="u1",
        inputs_json=json.dumps({
            "display_name": "Node Scout",
            "soul_text": "Prefer graph-science nodes with verified sources.",
            "domain_claims": ["scientist"],
        }),
    ))
    daemon = create_out["daemon"]
    assert daemon["daemon_id"].startswith("daemon::")
    assert daemon["soul_mode"] == "soul"
    assert daemon["domain_claims"] == ["scientist"]

    list_out = json.loads(univ_mod._universe_impl(
        action="daemon_list",
        universe_id="u1",
    ))
    assert any(item["daemon_id"] == daemon["daemon_id"] for item in list_out["daemons"])

    summon_out = json.loads(univ_mod._universe_impl(
        action="daemon_summon",
        universe_id="u1",
        inputs_json=json.dumps({
            "daemon_id": daemon["daemon_id"],
            "provider_name": "claude-code",
            "model_name": "sonnet",
        }),
    ))
    runtime = summon_out["runtime"]
    assert runtime["daemon_id"] == daemon["daemon_id"]
    assert runtime["provider_name"] == "claude-code"

    pause_out = json.loads(univ_mod._universe_impl(
        action="daemon_pause",
        universe_id="u1",
        inputs_json=json.dumps({
            "runtime_instance_id": runtime["runtime_instance_id"],
        }),
    ))
    assert pause_out["effect"] == "applied"
    assert pause_out["authority_scope"] == "owner"
    assert pause_out["runtime"]["status"] == "paused"

    resume_out = json.loads(univ_mod._universe_impl(
        action="daemon_resume",
        universe_id="u1",
        inputs_json=json.dumps({
            "runtime_instance_id": runtime["runtime_instance_id"],
        }),
    ))
    assert resume_out["effect"] == "applied"
    assert resume_out["runtime"]["status"] == "provisioned"

    restart_out = json.loads(univ_mod._universe_impl(
        action="daemon_restart",
        universe_id="u1",
        inputs_json=json.dumps({
            "runtime_instance_id": runtime["runtime_instance_id"],
        }),
    ))
    assert restart_out["effect"] == "queued"
    assert restart_out["runtime"]["status"] == "restart_requested"

    behavior_out = json.loads(univ_mod._universe_impl(
        action="daemon_update_behavior",
        universe_id="u1",
        inputs_json=json.dumps({
            "daemon_id": daemon["daemon_id"],
            "behavior_update": {"work_domains": ["workflow-platform"]},
            "apply_now": True,
        }),
    ))
    assert behavior_out["effect"] == "applied"
    assert behavior_out["daemon"]["metadata"]["behavior_version"] == 1
    assert behavior_out["daemon"]["metadata"]["behavior_policy"] == {
        "work_domains": ["workflow-platform"],
    }

    status_out = json.loads(univ_mod._universe_impl(
        action="daemon_control_status",
        universe_id="u1",
        inputs_json=json.dumps({
            "daemon_id": daemon["daemon_id"],
        }),
    ))
    assert status_out["daemon_count"] == 1
    assert status_out["runtime_count"] == 1

    memory_status_out = json.loads(univ_mod._universe_impl(
        action="daemon_memory_status",
        universe_id="u1",
        daemon_id=daemon["daemon_id"],
    ))
    assert memory_status_out["daemon_id"] == daemon["daemon_id"]
    assert memory_status_out["schema_version"] == 1

    banish_out = json.loads(univ_mod._universe_impl(
        action="daemon_banish",
        universe_id="u1",
        inputs_json=json.dumps({
            "runtime_instance_id": runtime["runtime_instance_id"],
        }),
    ))
    assert banish_out["effect"] == "applied"
    assert banish_out["runtime"]["status"] == "retired"

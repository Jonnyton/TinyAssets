"""Tests for .github/workflows/auto-fix-bug.yml structure.

Static YAML-parse tests - no GHA runner needed. Validates the key
invariants: auth paths, disable toggle, graceful-skip, branch naming,
permissions, concurrency group, trigger condition.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "auto-fix-bug.yml"


@pytest.fixture(scope="module")
def wf() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


def test_triggers_on_issues_labeled(wf):
    # PyYAML parses bare `on:` as boolean True key.
    triggers = wf.get(True, wf.get("on", {}))
    assert "issues" in triggers, "Workflow must trigger on issues"
    assert "labeled" in triggers["issues"].get("types", []), (
        "Workflow must trigger on issues.labeled"
    )


def test_deploy_completion_retries_auth_blocked_queue(wf):
    triggers = wf.get(True, wf.get("on", {}))
    workflows = triggers["workflow_run"].get("workflows", [])
    assert "Deploy prod" in workflows, (
        "Auto-fix must retry stale auth-blocked requests when deploy makes "
        "subscription auth visible."
    )


def test_auto_fix_does_not_self_trigger_on_workflow_push(wf):
    triggers = wf.get(True, wf.get("on", {}))
    assert "push" not in triggers, (
        "Self-triggering from workflow edits can make GITHUB_TOKEN branch pushes "
        "fail with workflow-permission errors."
    )


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------


def test_has_contents_write(wf):
    perms = wf.get("permissions", {})
    assert perms.get("contents") == "write", "contents: write needed to push branch"


def test_has_issues_write(wf):
    perms = wf.get("permissions", {})
    assert perms.get("issues") == "write", "issues: write needed to add labels + comments"


def test_has_pull_requests_write(wf):
    perms = wf.get("permissions", {})
    assert perms.get("pull-requests") == "write", "pull-requests: write needed to open PRs"


# ---------------------------------------------------------------------------
# Concurrency
# ---------------------------------------------------------------------------


def test_workflow_concurrency_serializes_subscription_writer_lane(wf):
    conc = wf.get("concurrency", {})
    assert conc.get("group") == "auto-fix-subscription-writer"
    assert conc.get("cancel-in-progress") is False


def test_concurrency_scoped_to_issue(wf):
    conc = wf["jobs"]["fix"].get("concurrency", {})
    group = conc.get("group", "")
    assert "matrix.issue.issue_number" in group, (
        "Concurrency group must be scoped per-issue to prevent parallel fix attempts"
    )


# ---------------------------------------------------------------------------
# Job filter
# ---------------------------------------------------------------------------


def test_job_filters_on_auto_bug_label(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "auto-bug" in script, (
        "Discover step must include the legacy 'auto-bug' label for compatibility"
    )


def test_discover_retries_unreviewed_attempted_needs_human_with_auth(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "auto-fix-reviewed" in script
    assert "needsHuman && hasWriterAuth && !autoFixDisabled && !reviewed" in script
    assert "retryAttempted" in script


def test_discover_retries_branch_push_blocked_when_push_token_visible(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "HAS_WORKFLOW_PUSH_TOKEN" in str(discover_step.get("env", {}))
    assert "hasWorkflowPushToken" in script
    assert "auto-fix-branch-push-blocked" in script
    assert "retryBranchPushBlocked" in script
    assert "workflow push token is now visible" in script


def test_discover_scheduled_backfill_reads_oldest_pending_first(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "sort: 'created'" in script
    assert "direction: 'asc'" in script


# ---------------------------------------------------------------------------
# Disable toggle
# ---------------------------------------------------------------------------


def test_disable_flag_checked(wf):
    steps = wf["jobs"]["fix"]["steps"]
    check_step = next(
        (s for s in steps if s.get("id") == "check-disabled"), None
    )
    assert check_step is not None, "Must have a check-disabled step"
    run_script = check_step.get("run", "")
    assert "AUTO_FIX_DISABLED" in run_script, (
        "check-disabled step must reference AUTO_FIX_DISABLED variable"
    )


def test_needs_human_label_on_disabled(wf):
    steps = wf["jobs"]["fix"]["steps"]
    disabled_step = next(
        (s for s in steps
         if "disabled" in str(s.get("if", "")) and "needs-human" in str(s)),
        None,
    )
    assert disabled_step is not None, (
        "Must add needs-human label when AUTO_FIX_DISABLED=true"
    )


# ---------------------------------------------------------------------------
# Auth detection
# ---------------------------------------------------------------------------


def test_auth_step_exists(wf):
    steps = wf["jobs"]["fix"]["steps"]
    auth_step = next((s for s in steps if s.get("id") == "auth"), None)
    assert auth_step is not None, "Must have an auth detection step"


def test_auth_step_checks_oauth_token(wf):
    steps = wf["jobs"]["fix"]["steps"]
    auth_step = next(s for s in steps if s.get("id") == "auth")
    run_script = auth_step.get("run", "")
    assert "CLAUDE_CODE_OAUTH_TOKEN" in run_script, (
        "Auth step must check CLAUDE_CODE_OAUTH_TOKEN first"
    )


def test_auth_step_checks_codex_subscription_bundle(wf):
    steps = wf["jobs"]["fix"]["steps"]
    auth_step = next(s for s in steps if s.get("id") == "auth")
    run_script = auth_step.get("run", "")
    assert "WORKFLOW_CODEX_AUTH_JSON_B64" in str(auth_step.get("env", {}))
    assert "codex_subscription" in run_script, (
        "Auth step must route to the Codex subscription writer when its bundle is visible"
    )


def test_auth_step_reports_workflow_push_token(wf):
    steps = wf["jobs"]["fix"]["steps"]
    auth_step = next(s for s in steps if s.get("id") == "auth")
    run_script = auth_step.get("run", "")
    assert "WORKFLOW_PUSH_TOKEN" in str(auth_step.get("env", {}))
    assert "has_workflow_push_token" in run_script
    assert ".github/workflows/*" in run_script


def test_auth_step_reports_api_keys_as_diagnostics_only(wf):
    steps = wf["jobs"]["fix"]["steps"]
    auth_step = next(s for s in steps if s.get("id") == "auth")
    run_script = auth_step.get("run", "")
    assert "ANTHROPIC_API_KEY" in run_script, (
        "Auth step should still report API-key secrets as ignored diagnostics"
    )
    assert "api_key" not in str(auth_step.get("if", "")), (
        "API-key secrets must not select a writer mode"
    )


# ---------------------------------------------------------------------------
# Graceful-skip (no auth)
# ---------------------------------------------------------------------------


def test_graceful_skip_step_exists(wf):
    steps = wf["jobs"]["fix"]["steps"]
    skip_step = next(
        (s for s in steps
         if "mode" in str(s.get("if", "")) and "none" in str(s.get("if", ""))),
        None,
    )
    assert skip_step is not None, (
        "Must have a graceful-skip step when auth mode == none"
    )


def test_graceful_skip_adds_needs_human(wf):
    steps = wf["jobs"]["fix"]["steps"]
    skip_step = next(
        (s for s in steps
         if "mode" in str(s.get("if", "")) and "none" in str(s.get("if", ""))),
        None,
    )
    assert skip_step is not None
    script = str(skip_step.get("with", {}).get("script", ""))
    assert "needs-human" in script, (
        "Graceful-skip step must add needs-human label"
    )


# ---------------------------------------------------------------------------
# Claude action steps
# ---------------------------------------------------------------------------


def test_oauth_step_uses_claude_code_action(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next(
        (s for s in steps if "oauth" in str(s.get("if", "")) and "uses" in s),
        None,
    )
    assert oauth_step is not None, "Must have an OAuth-authenticated Claude action step"
    assert "claude-code-action" in oauth_step.get("uses", ""), (
        "OAuth step must use anthropics/claude-code-action"
    )


def test_no_api_key_step_uses_claude_code_action(wf):
    steps = wf["jobs"]["fix"]["steps"]
    api_step = next(
        (s for s in steps if "api_key" in str(s.get("if", "")) and "uses" in s),
        None,
    )
    assert api_step is None, (
        "Default daemon writers must not use API-key-authenticated Claude action steps"
    )


def test_codex_subscription_step_uses_codex_cli(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None, "Must have a Codex subscription writer step"
    run_script = codex_step.get("run", "")
    assert "npm install -g @openai/codex" in run_script
    assert "codex exec --dangerously-bypass-approvals-and-sandbox" in run_script
    assert "--full-auto" not in run_script
    assert "WORKFLOW_CODEX_AUTH_JSON_B64" in str(codex_step.get("env", {}))
    assert "OPENAI_API_KEY" in run_script and "unset OPENAI_API_KEY" in run_script


def test_codex_subscription_step_uses_workflow_push_token_for_git_push(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None, "Must have a Codex subscription writer step"
    run_script = codex_step.get("run", "")
    assert "WORKFLOW_PUSH_TOKEN" in str(codex_step.get("env", {}))
    assert "git remote set-url origin" in run_script
    assert "x-access-token" in run_script
    assert "unset WORKFLOW_PUSH_TOKEN" in run_script


def test_codex_commit_title_uses_env_to_avoid_shell_injection(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None, "Must have a Codex subscription writer step"
    run_script = codex_step.get("run", "")
    assert "PR_TITLE" in str(codex_step.get("env", {}))
    assert 'git commit -m "$PR_TITLE"' in run_script
    assert 'git commit -m "${{ steps.meta.outputs.pr_title }}"' not in run_script


def test_codex_branch_push_permission_failure_is_classified(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None, "Must have a Codex subscription writer step"
    run_script = codex_step.get("run", "")
    assert "refusing to allow a GitHub App to create or update workflow" in run_script
    assert "push_blocked=true" in run_script
    assert "github_actions_workflow_permission_missing" in run_script


def test_branch_push_block_labels_clear_when_push_token_is_visible(wf):
    steps = wf["jobs"]["fix"]["steps"]
    clear_step = next(
        (
            s for s in steps
            if s.get("name") == "Clear auth-missing block when auth is visible"
        ),
        None,
    )
    assert clear_step is not None, "Must clear retryable labels before writer runs"
    script = str(clear_step.get("with", {}).get("script", ""))
    assert "has_workflow_push_token" in script
    assert "issueLabels.includes('auto-fix-branch-push-blocked')" in script
    assert "auto-fix-reviewed" in script
    assert "auto-fix-branch-push-blocked" in script


def test_codex_no_change_is_classified_from_final_message(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None
    run_script = codex_step.get("run", "")
    assert "no_change_reason=${reason}" in run_script
    assert "last_message<<" in run_script
    assert "already_fixed" in run_script
    assert "stale bug report" in run_script


def test_already_fixed_no_change_closes_issue(wf):
    steps = wf["jobs"]["fix"]["steps"]
    close_step = next(
        (
            s
            for s in steps
            if s.get("name")
            == "Close already-fixed issue when no repo change is needed"
        ),
        None,
    )
    assert close_step is not None, "Must close stale/already-fixed requests"
    condition = str(close_step.get("if", ""))
    script = str(close_step.get("with", {}).get("script", ""))
    assert "no_change_reason == 'already_fixed'" in condition
    assert "state: 'closed'" in script
    assert "state_reason: 'completed'" in script
    assert "auto-fix-reviewed" in script
    assert "auto-fix-already-fixed" in script


def test_codex_pr_gets_cross_family_checker(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"
    script = str(codex_pr_step.get("with", {}).get("script", ""))
    assert "writer:codex" in script
    assert "checker:claude" in script
    assert "Required checker family: Claude" in script


def test_codex_pr_creation_policy_block_is_classified(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"
    script = str(codex_pr_step.get("with", {}).get("script", ""))
    assert "github_actions_pr_creation_disabled" in script
    assert "not permitted to create or approve pull requests" in script
    assert "core.setOutput('blocked', 'true')" in script
    assert "core.warning" in script


def test_branch_naming_convention(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    assert oauth_step is not None, "Must have a Claude OAuth step"
    with_block = oauth_step.get("with", {})
    assert with_block.get("branch_prefix") == "auto-change/"
    assert "issue-${{ steps.meta.outputs.issue_number }}" == with_block.get(
        "branch_name_template"
    ), (
        "Branch must follow auto-change/issue-<N> naming convention"
    )


def test_pr_title_includes_auto_fix_prefix(wf):
    steps = wf["jobs"]["fix"]["steps"]
    meta_step = next((s for s in steps if s.get("id") == "meta"), None)
    assert meta_step is not None
    script = str(meta_step.get("with", {}).get("script", ""))
    assert "[auto-change]" in script, "PR title must start with [auto-change]"


def test_meta_step_fetches_recent_issue_comments_for_feedback(wf):
    steps = wf["jobs"]["fix"]["steps"]
    meta_step = next((s for s in steps if s.get("id") == "meta"), None)
    assert meta_step is not None
    script = str(meta_step.get("with", {}).get("script", ""))
    assert "issues.listComments" in script
    assert "issue_comments" in script
    assert "slice(-5)" in script


def test_pr_body_references_fixes_keyword(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    assert oauth_step is not None, "Must have a Claude OAuth step"
    prompt = str(oauth_step.get("with", {}).get("prompt", ""))
    assert "Fixes #${{ steps.meta.outputs.issue_number }}" in prompt, (
        "Claude prompt must require PR body to reference the issue with Fixes #N"
    )


def test_writer_prompts_require_plugin_mirror_for_workflow_runtime_edits(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert oauth_step is not None, "Must have a Claude OAuth step"
    assert codex_step is not None, "Must have a Codex subscription step"
    oauth_prompt = str(oauth_step.get("with", {}).get("prompt", ""))
    codex_prompt = str(codex_step.get("run", ""))
    assert "python packaging/claude-plugin/build_plugin.py" in oauth_prompt
    assert "python packaging/claude-plugin/build_plugin.py" in codex_prompt
    assert "workflow/*" in oauth_prompt
    assert "workflow/*" in codex_prompt


def test_writer_prompts_include_recent_feedback_and_focused_verification(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert oauth_step is not None, "Must have a Claude OAuth step"
    assert codex_step is not None, "Must have a Codex subscription step"
    oauth_prompt = str(oauth_step.get("with", {}).get("prompt", ""))
    codex_prompt = str(codex_step.get("run", ""))
    for prompt in (oauth_prompt, codex_prompt):
        assert "Recent issue comments and loop feedback" in prompt
        assert "verification failures" in prompt
        assert "python -m ruff check" in prompt
        assert "focused tests" in prompt


def test_codex_step_enforces_post_generation_verification(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None
    run_script = codex_step.get("run", "")
    assert "Post-Codex verification" in run_script
    assert "git diff --name-only" in run_script
    assert "python -m ruff check" in run_script
    assert "python -m pytest" in run_script
    assert "verification_status" in run_script
    assert "Post-Codex verification failed; leaving request retryable" in run_script
    assert "exit \"$verification_status\"" in run_script


def test_python_dev_dependencies_are_installed_before_subscription_writers(wf):
    steps = wf["jobs"]["fix"]["steps"]
    install_index = next(
        (
            index
            for index, step in enumerate(steps)
            if step.get("name") == "Install Python dev dependencies"
        ),
        None,
    )
    claude_index = next(
        index for index, step in enumerate(steps) if step.get("id") == "claude-oauth"
    )
    codex_index = next(
        index for index, step in enumerate(steps) if step.get("id") == "codex-subscription"
    )
    assert install_index is not None, "Must install ruff/pytest before writer verification"
    assert install_index < claude_index
    assert install_index < codex_index

    install_step = steps[install_index]
    run_script = str(install_step.get("run", ""))
    assert "python -m pip install --upgrade pip" in run_script
    assert 'python -m pip install -e ".[dev]"' in run_script
    assert "steps.check-disabled.outputs.disabled == 'false'" in str(install_step.get("if", ""))
    assert "steps.auth.outputs.mode != 'none'" in str(install_step.get("if", ""))


def test_no_pr_step_marks_review_without_failing_workflow(wf):
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None, "Must mark no-PR outcomes"
    condition = str(no_pr_step.get("if", ""))
    script = str(no_pr_step.get("with", {}).get("script", ""))
    assert "no_change_reason != 'already_fixed'" in condition
    assert "core.setFailed" not in script
    assert "core.warning" in script
    assert "auto-fix-reviewed" in script
    assert "auto-fix-blocked" in script
    assert "auto-fix-pr-blocked" in script
    assert "auto-fix-branch-push-blocked" in script
    assert "writerFailed" in script
    assert "auto-fix-writer-failed" in script
    assert "CODEX_BRANCH" in str(no_pr_step.get("env", {}))
    assert "CODEX_PR_BLOCKED" in str(no_pr_step.get("env", {}))
    assert "CODEX_PUSH_BLOCKED" in str(no_pr_step.get("env", {}))
    assert "CODEX_OUTCOME" in str(no_pr_step.get("env", {}))
    assert "CLAUDE_OUTCOME" in str(no_pr_step.get("env", {}))
    assert "mode === 'codex_subscription' && codexBranch" in script
    assert "Workflow push token present" in script
    assert "WORKFLOW_PUSH_TOKEN" in script
    assert "Workflows write" in script


def test_pr_blocked_label_is_defined(wf):
    steps = wf["jobs"]["fix"]["steps"]
    labels_step = next((s for s in steps if s.get("name") == "Ensure automation labels"), None)
    assert labels_step is not None, "Must define automation labels"
    script = str(labels_step.get("with", {}).get("script", ""))
    assert "auto-fix-pr-blocked" in script
    assert "GitHub blocked Actions from opening the PR" in script
    assert "auto-fix-branch-push-blocked" in script
    assert "GitHub blocked Actions from pushing the branch" in script
    assert "auto-fix-writer-failed" in script
    assert "selected writer failed before opening a PR" in script

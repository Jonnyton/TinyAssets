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


def test_fix_job_has_bounded_runtime(wf):
    fix_job = wf["jobs"]["fix"]
    assert fix_job.get("timeout-minutes") == 45, (
        "Automated writer spend must be bounded per issue attempt"
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


def test_discover_retries_permission_blocked_when_push_token_visible(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "HAS_WORKFLOW_PUSH_TOKEN" in str(discover_step.get("env", {}))
    assert "hasWorkflowPushToken" in script
    assert "auto-fix-branch-push-blocked" in script
    assert "auto-fix-pr-blocked" in script
    assert "retryPermissionBlocked" in script
    assert "workflow push token is now visible" in script


def test_discover_prioritizes_permission_blocked_before_normal_queue(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    permission_blocked_pass = "await scanAutoLabels({ onlyPermissionBlocked: true });"
    normal_pass = "await scanAutoLabels();"
    assert "onlyPermissionBlocked" in script
    assert "!hasLabel(issue, 'auto-fix-branch-push-blocked')" in script
    assert "!hasLabel(issue, 'auto-fix-pr-blocked')" in script
    assert "ignoreSkip: onlyPermissionBlocked" in script
    assert script.index(permission_blocked_pass) < script.index(normal_pass)


def test_discover_prioritizes_stale_gate_before_normal_queue(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    stale_gate_pass = "await scanAutoLabels({ onlyStaleGate: true });"
    normal_pass = "await scanAutoLabels();"
    assert "const staleGateLabel = 'auto-fix-stale-gate'" in script
    assert "const staleGate = hasLabel(issue, staleGateLabel)" in script
    assert "retryPermissionBlocked || staleGate" in script
    assert "onlyStaleGate" in script
    assert "Prioritized stale-gate issue before normal queue discovery" in script
    assert script.index(stale_gate_pass) < script.index(normal_pass)


def test_discover_skips_issues_that_already_have_linked_open_prs(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "async function linkedOpenPrNumbers(issue)" in script
    assert "github.paginate(github.rest.pulls.list" in script
    assert "state: 'open'" in script
    assert "issueMention.test(text) || branchMention.test(text)" in script
    assert "const linkedPrNumbers = await linkedOpenPrNumbers(issue);" in script
    assert "linked open PR(s)" in script
    assert script.index("const linkedPrNumbers = await linkedOpenPrNumbers(issue);") < (
        script.index("const needsHuman = hasLabel(issue, 'needs-human');")
    )


def test_discover_respects_priority_and_skip_labels(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    priority_loop = "'priority:loop-discipline'"
    priority_layer = "'priority:primitive-layer'"
    priority_surface = "'priority:primitive-surface'"
    normal_scan = "for (const labelName of autoLabels)"
    assert priority_loop in script
    assert priority_layer in script
    assert priority_surface in script
    assert "'await-primitive-layer'" in script
    assert "'complete'" in script
    assert "function shouldSkipIssue" in script
    assert "labels: labelNames.join(',')" in script
    assert script.index(priority_loop) < script.index(priority_layer)
    assert script.index(priority_layer) < script.index(priority_surface)
    assert script.index("for (const priorityLabel of priorityLabelOrder)") < (
        script.index(normal_scan)
    )


def test_discover_skips_sequenced_after_requests_until_pr_lands(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "function prerequisitePrNumbers" in script
    assert "async function hasUnlandedPrerequisitePr" in script
    assert "sequenced[-_ ]after" in script
    assert "github.rest.pulls.get" in script
    assert "pull.merged_at" in script
    assert "has an unlanded prerequisite PR" in script
    assert script.index("if (await hasUnlandedPrerequisitePr(issue))") < (
        script.index("rows.push(issueRow(issue));")
    )


def test_permission_blocked_retry_clears_terminal_labels_when_push_token_visible(wf):
    steps = wf["jobs"]["fix"]["steps"]
    clear_step = next(
        (s for s in steps if s.get("name") == "Clear auth-missing block when auth is visible"),
        None,
    )
    assert clear_step is not None
    script = str(clear_step.get("with", {}).get("script", ""))
    assert "has_workflow_push_token" in script
    assert "auto-fix-branch-push-blocked" in script
    assert "auto-fix-pr-blocked" in script
    assert "auto-fix-reviewed" in script


def test_discover_scheduled_backfill_reads_oldest_pending_first(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "sort: 'created'" in script
    assert "direction: 'asc'" in script


def test_discover_paginates_past_deferred_oldest_issues(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "github.paginate(github.rest.issues.listForRepo" in script
    assert "Scanning ${issues.length} open issue(s)" in script


def test_workflow_dispatch_logs_and_uses_target_issue_input(wf):
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "const dispatchIssueNumber" in script
    assert "context.payload.inputs?.issue_number" in script
    assert "Workflow dispatch requested issue #" in script
    assert "issueFromNumber(dispatchIssueNumber)" in script
    assert "Workflow dispatch did not include issue_number" in script


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
    assert "trigger pull_request checks" in run_script


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


def test_codex_subscription_step_classifies_expired_auth(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None, "Must have a Codex subscription writer step"
    run_script = codex_step.get("run", "")
    assert "codex-exec.log" in run_script
    assert "codex_status=${PIPESTATUS[0]}" in run_script
    assert "refresh_token_reused" in run_script
    assert "token_expired" in run_script
    assert "auth_expired=${auth_expired}" in run_script


def test_codex_subscription_step_uses_workflow_push_token_for_git_push(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None, "Must have a Codex subscription writer step"
    run_script = codex_step.get("run", "")
    assert "WORKFLOW_PUSH_TOKEN" in str(codex_step.get("env", {}))
    assert "git remote set-url origin" in run_script
    assert "x-access-token" in run_script
    assert 'git config --local --unset-all "http.https://github.com/.extraheader"' in run_script
    assert "http.https://github.com/${GITHUB_REPOSITORY}.extraheader" in run_script
    assert "unset WORKFLOW_PUSH_TOKEN" in run_script


def test_checkout_uses_fresh_main_for_auto_change_branch_bases(wf):
    steps = wf["jobs"]["fix"]["steps"]
    checkout_step = next((s for s in steps if s.get("name") == "Checkout"), None)
    assert checkout_step is not None, "Must check out the repo before writers run"
    with_block = checkout_step.get("with", {})
    assert with_block.get("ref") == "main"
    assert with_block.get("fetch-depth") == 0


def test_codex_branch_is_created_from_fresh_origin_main(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert codex_step is not None, "Must have a Codex subscription writer step"
    run_script = codex_step.get("run", "")
    assert "git fetch origin main --prune" in run_script
    assert 'git checkout -B "$branch" "origin/main"' in run_script
    assert 'git checkout -B "$branch"\n' not in run_script


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


def test_ready_for_checker_label_is_defined(wf):
    steps = wf["jobs"]["fix"]["steps"]
    labels_step = next((s for s in steps if s.get("name") == "Ensure automation labels"), None)
    assert labels_step is not None, "Must define automation labels"
    script = str(labels_step.get("with", {}).get("script", ""))
    assert "ready_for_checker" in script
    assert (
        "matured through source, duplicate, stale-base, design-note, and scope-split "
        "pre-checks before checker escalation"
    ) in script


def test_codex_ready_for_checker_requires_pre_checker_self_review(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"
    script = str(codex_pr_step.get("with", {}).get("script", ""))
    assert "async function selfReviewLoopPr" in script
    assert "source check failed" in script
    assert "duplicate check failed" in script
    assert "stale-base check failed" in script
    assert "scope-split check failed" in script
    assert "Pre-checker self-review blocked `ready_for_checker`" in script
    assert "labels: ['ready_for_checker']" in script
    assert script.index("const selfReviewFailures = await selfReviewLoopPr(pr)") < (
        script.index("labels: ['ready_for_checker']")
    )
    assert script.index("const selfReviewFailures = await selfReviewLoopPr(pr)") < (
        script.index("labels: ['writer:codex', 'checker:claude']")
    )
    assert script.index("labels: ['writer:codex', 'checker:claude']") < (
        script.index("labels: ['ready_for_checker']")
    )


def test_claude_ready_for_checker_requires_pre_checker_self_review(wf):
    steps = wf["jobs"]["fix"]["steps"]
    claude_pr_step = next((s for s in steps if s.get("id") == "claude-pr"), None)
    assert claude_pr_step is not None, "Must find and label Claude-created PRs"
    script = str(claude_pr_step.get("with", {}).get("script", ""))
    assert "async function selfReviewLoopPr" in script
    assert "source check failed" in script
    assert "duplicate check failed" in script
    assert "stale-base check failed" in script
    assert "scope-split check failed" in script
    assert "Pre-checker self-review blocked `ready_for_checker`" in script
    assert "labels: ['ready_for_checker']" in script
    assert script.index("const selfReviewFailures = await selfReviewLoopPr(pr)") < (
        script.index("labels: ['ready_for_checker']")
    )
    assert script.index("const selfReviewFailures = await selfReviewLoopPr(pr)") < (
        script.index("labels: ['writer:claude', 'checker:codex']")
    )
    assert script.index("labels: ['writer:claude', 'checker:codex']") < (
        script.index("labels: ['ready_for_checker']")
    )


def test_codex_pr_creation_uses_workflow_push_token_for_checks(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"
    with_block = codex_pr_step.get("with", {})
    assert with_block.get("github-token") == (
        "${{ secrets.WORKFLOW_PUSH_TOKEN || github.token }}"
    ), (
        "Codex PR creation must prefer WORKFLOW_PUSH_TOKEN so pull_request "
        "checks fire on loop-created PRs."
    )


def test_codex_pr_creation_policy_block_is_classified(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"
    script = str(codex_pr_step.get("with", {}).get("script", ""))
    assert "github_actions_pr_creation_disabled" in script
    assert "not permitted to create or approve pull requests" in script
    assert "core.setOutput('blocked', 'true')" in script
    assert "core.warning" in script


def test_codex_pr_creation_closes_stale_superseded_issue_prs(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"
    script = str(codex_pr_step.get("with", {}).get("script", ""))
    assert "issueBranchRoot = `${branchPrefix}issue-${issueNumber}`" in script
    assert "issueBranchPrefix = `${issueBranchRoot}-`" in script
    assert "headRef !== issueBranchRoot" in script
    assert "!headRef.startsWith(branchPrefix)" in script
    assert "compareCommitsWithBasehead" in script
    assert "Number(compare.behind_by || 0) > 0" in script
    assert "auto-fix-superseded" in script
    assert "state: 'closed'" in script
    assert "superseded by #${pr.number}" in script


def test_superseded_label_is_defined(wf):
    steps = wf["jobs"]["fix"]["steps"]
    labels_step = next((s for s in steps if s.get("name") == "Ensure automation labels"), None)
    assert labels_step is not None, "Must define automation labels"
    script = str(labels_step.get("with", {}).get("script", ""))
    assert "auto-fix-superseded" in script
    assert "Older auto-change PR was closed" in script


def test_stale_gate_label_is_defined(wf):
    steps = wf["jobs"]["fix"]["steps"]
    labels_step = next((s for s in steps if s.get("name") == "Ensure automation labels"), None)
    assert labels_step is not None, "Must define automation labels"
    script = str(labels_step.get("with", {}).get("script", ""))
    assert "auto-fix-stale-gate" in script
    assert "blocking the gated queue" in script


def test_branch_naming_convention(wf):
    steps = wf["jobs"]["fix"]["steps"]
    meta_step = next((s for s in steps if s.get("id") == "meta"), None)
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    assert meta_step is not None, "Must have request metadata step"
    assert oauth_step is not None, "Must have a Claude OAuth step"
    meta_script = str(meta_step.get("with", {}).get("script", ""))
    assert "const branchPrefix" in meta_script
    assert "design-note-draft/" not in meta_script
    assert "auto-change/" in meta_script
    assert "core.setOutput('branch_prefix', branchPrefix)" in meta_script
    with_block = oauth_step.get("with", {})
    assert with_block.get("branch_prefix") == "${{ steps.meta.outputs.branch_prefix }}"
    assert "issue-${{ steps.meta.outputs.issue_number }}" == with_block.get(
        "branch_name_template"
    ), (
        "Branch must follow the filing-shape branch prefix plus issue-<N>"
    )


def test_meta_step_extracts_reconciliation_artifacts(wf):
    steps = wf["jobs"]["fix"]["steps"]
    meta_step = next((s for s in steps if s.get("id") == "meta"), None)
    assert meta_step is not None
    script = str(meta_step.get("with", {}).get("script", ""))
    assert r"body.match(/\*\*Wiki path:\*\*\s*`([^`]+)`/i)" in script
    assert "core.setOutput('wiki_path', wikiPath)" in script
    assert "const expectedBranchTask = `${branchPrefix}issue-${issue.issue_number}`" in script
    assert "core.setOutput('expected_branch_task', expectedBranchTask)" in script


def test_discovery_retries_attempted_without_terminal_receipt(wf):
    steps = wf["jobs"]["discover"]["steps"]
    discover_step = next((s for s in steps if s.get("id") == "discover"), None)
    assert discover_step is not None
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "const incompleteAttempt = attempted && !reviewed && !needsHuman" in script
    assert "options.retryAttempted || incompleteAttempt" in script
    assert "has no terminal receipt" in script


def test_pr_title_prefix_uses_filing_shape(wf):
    steps = wf["jobs"]["fix"]["steps"]
    meta_step = next((s for s in steps if s.get("id") == "meta"), None)
    assert meta_step is not None
    script = str(meta_step.get("with", {}).get("script", ""))
    assert "const filingShape" in script
    assert "'[auto-change]'" in script
    assert "'[design-note]'" not in script
    assert "core.setOutput('filing_shape', filingShape)" in script
    assert "prTitlePrefix" in script


def test_project_design_prompt_uses_skills_and_brain_pages(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert oauth_step is not None, "Must have a Claude OAuth step"
    assert codex_step is not None, "Must have a Codex subscription step"
    oauth_prompt = str(oauth_step.get("with", {}).get("prompt", ""))
    codex_prompt = str(codex_step.get("run", ""))
    for prompt in (oauth_prompt, codex_prompt):
        assert ".agents/skills/using-agent-skills/SKILL.md" in prompt
        assert ".agents/skills/<skill>/SKILL.md" in prompt
        assert "Filing shape:" in prompt
        assert "architectural/project-design filings" in prompt
        assert "do not draft `docs/design-notes/proposed/` by default" in prompt
        assert "pages/concepts/" in prompt
        assert "pages/plans/" in prompt


def test_project_design_branches_use_auto_change_not_design_note(wf):
    steps = wf["jobs"]["fix"]["steps"]
    meta_step = next((s for s in steps if s.get("id") == "meta"), None)
    assert meta_step is not None
    script = str(meta_step.get("with", {}).get("script", ""))
    assert "const architecturalKinds = new Set(['project-design'])" in script
    assert "const branchPrefix = 'auto-change/'" in script
    assert "const prTitlePrefix = '[auto-change]'" in script
    assert "design-note-draft/" not in script


def test_ready_for_checker_blocks_project_design_design_note_autopromote(wf):
    steps = wf["jobs"]["fix"]["steps"]
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    claude_pr_step = next((s for s in steps if s.get("id") == "claude-pr"), None)
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"
    assert claude_pr_step is not None, "Must find and label Claude-created PRs"
    for step in (codex_pr_step, claude_pr_step):
        script = str(step.get("with", {}).get("script", ""))
        assert "compare.files" in script
        assert "docs/design-notes/proposed/" in script
        assert "project-design requests must not auto-promote" in script
        assert "pages/concepts/" in script
        assert "pages/plans/" in script
        assert "runtime guardrail" in script


def test_meta_step_fetches_recent_issue_comments_for_feedback(wf):
    steps = wf["jobs"]["fix"]["steps"]
    meta_step = next((s for s in steps if s.get("id") == "meta"), None)
    assert meta_step is not None
    script = str(meta_step.get("with", {}).get("script", ""))
    assert "issues.listComments" in script
    assert "issue_comments" in script
    assert "slice(-5)" in script


def test_meta_step_defaults_non_final_patch_phases_to_part_of(wf):
    steps = wf["jobs"]["fix"]["steps"]
    meta_step = next((s for s in steps if s.get("id") == "meta"), None)
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert meta_step is not None, "Must have request metadata step"
    assert oauth_step is not None, "Must have a Claude OAuth step"
    assert codex_step is not None, "Must have a Codex subscription writer step"
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"

    meta_script = str(meta_step.get("with", {}).get("script", ""))
    assert "function issueLinkKeyword" in meta_script
    assert "requestKind !== 'patch'" in meta_script
    assert "final_phase" in meta_script
    assert "matchAll" in meta_script
    assert "Number(match[1]) < Number(match[2])" in meta_script
    assert "'Part of'" in meta_script
    assert "core.setOutput('issue_link_line'" in meta_script

    prompt = str(oauth_step.get("with", {}).get("prompt", ""))
    assert "${{ steps.meta.outputs.issue_link_line }}" in prompt

    codex_run = str(codex_step.get("run", ""))
    assert codex_step.get("env", {}).get("ISSUE_LINK_LINE") == (
        "${{ steps.meta.outputs.issue_link_line }}"
    )
    assert '-m "$ISSUE_LINK_LINE"' in codex_run
    assert '"Fixes #${{ steps.meta.outputs.issue_number }}"' not in codex_run

    codex_pr_script = str(codex_pr_step.get("with", {}).get("script", ""))
    assert codex_pr_step.get("env", {}).get("ISSUE_LINK_LINE") == (
        "${{ steps.meta.outputs.issue_link_line }}"
    )
    assert "process.env.ISSUE_LINK_LINE" in codex_pr_script
    assert "body: [" in codex_pr_script
    assert "issueLinkLine," in codex_pr_script


def test_pr_body_references_issue_link_output(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    assert oauth_step is not None, "Must have a Claude OAuth step"
    prompt = str(oauth_step.get("with", {}).get("prompt", ""))
    assert "${{ steps.meta.outputs.issue_link_line }}" in prompt, (
        "Claude prompt must use the computed issue link line"
    )


def test_writer_pr_bodies_reconcile_request_surfaces(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert oauth_step is not None, "Must have a Claude OAuth step"
    assert codex_pr_step is not None, "Must create a PR for Codex-authored changes"
    oauth_prompt = str(oauth_step.get("with", {}).get("prompt", ""))
    codex_env = str(codex_pr_step.get("env", {}))
    codex_script = str(codex_pr_step.get("with", {}).get("script", ""))
    for text in (oauth_prompt, codex_script):
        assert "Request artifact reconciliation" in text
        assert "Wiki page" in text
        assert "GitHub issue" in text
        assert "Branch task" in text
        assert "PR artifact" in text
    assert "WIKI_PATH" in codex_env
    assert "EXPECTED_BRANCH_TASK" in codex_env


def test_writer_steps_record_issue_side_artifact_receipts(wf):
    steps = wf["jobs"]["fix"]["steps"]
    claude_pr_step = next((s for s in steps if s.get("id") == "claude-pr"), None)
    codex_pr_step = next((s for s in steps if s.get("id") == "codex-pr-create"), None)
    assert claude_pr_step is not None, "Must find and label Claude-authored PRs"
    assert codex_pr_step is not None, "Must create Codex-authored PRs"
    claude_script = str(claude_pr_step.get("with", {}).get("script", ""))
    codex_script = str(codex_pr_step.get("with", {}).get("script", ""))
    for script in (claude_script, codex_script):
        assert "Auto-fix artifact receipt" in script
        assert "issue_number: issueNumber" in script
        assert "Child invocation receipt" in script
        assert "Terminal outcome: `pr-opened`" in script
        assert "pr.html_url" in script
        assert "labels: ['auto-fix-reviewed']" in script


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


def test_writer_prompts_enforce_bounded_logged_proposed_mode(wf):
    steps = wf["jobs"]["fix"]["steps"]
    oauth_step = next((s for s in steps if s.get("id") == "claude-oauth"), None)
    codex_step = next((s for s in steps if s.get("id") == "codex-subscription"), None)
    assert oauth_step is not None, "Must have a Claude OAuth step"
    assert codex_step is not None, "Must have a Codex subscription step"
    oauth_prompt = str(oauth_step.get("with", {}).get("prompt", ""))
    codex_prompt = str(codex_step.get("run", ""))
    for prompt in (oauth_prompt, codex_prompt):
        assert "Autonomous spend guardrails" in prompt
        assert "logged/proposed mode" in prompt
        assert "single issue" in prompt
        assert "Do not start background jobs" in prompt
        assert "recursive workflow_dispatch" in prompt
        assert "external paid services" in prompt
        assert "at most one narrow working-tree patch" in prompt


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
    assert "WIKI_PATH" in str(no_pr_step.get("env", {}))
    assert "EXPECTED_BRANCH_TASK" in str(no_pr_step.get("env", {}))
    assert "CODEX_OUTCOME" in str(no_pr_step.get("env", {}))
    assert "CLAUDE_OUTCOME" in str(no_pr_step.get("env", {}))
    assert "mode === 'codex_subscription' && codexBranch" in script
    assert "Workflow push token present" in script
    assert "WORKFLOW_PUSH_TOKEN" in script
    assert "Workflows write" in script
    assert "Pull requests write" in script


def test_no_pr_comment_records_terminal_artifact_receipt(wf):
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None, "Must mark no-PR outcomes"
    script = str(no_pr_step.get("with", {}).get("script", ""))
    assert "Request artifact reconciliation" in script
    assert "Wiki page" in script
    assert "GitHub issue" in script
    assert "Branch task" in script
    assert "PR artifact: `not created`" in script
    assert "Child invocation receipt" in script
    assert "Terminal outcome" in script
    assert "writer-failed-before-pr" in script
    assert "context.runId" in script


def test_no_pr_step_heals_existing_open_pr_receipt(wf):
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None, "Must mark no-PR outcomes"
    script = str(no_pr_step.get("with", {}).get("script", ""))
    assert "Auto-fix PR exists" in script
    assert "pr-opened-existing" in script
    assert "PR artifact: #${pr.number} (${pr.html_url})" in script
    assert "labels: ['auto-fix-reviewed']" in script


def test_no_pr_comment_distinguishes_successful_writer_from_pr_policy_block(wf):
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None, "Must mark no-PR outcomes"
    script = str(no_pr_step.get("with", {}).get("script", ""))
    assert "Writer child invocation: `succeeded`" in script
    assert "Auto-fix branch pushed: `true`" in script
    assert "Remaining blocker: GitHub Actions PR creation policy" in script
    assert "Do not treat this as a failed child invocation" in script


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
    assert "auto-fix-auth-expired" in script
    assert "expired or revoked" in script


def test_retry_clears_stale_writer_failure_labels(wf):
    steps = wf["jobs"]["fix"]["steps"]
    clear_step = next(
        (s for s in steps if s.get("name") == "Clear auth-missing block when auth is visible"),
        None,
    )
    assert clear_step is not None, "Must clear stale failure labels before retry"
    script = str(clear_step.get("with", {}).get("script", ""))
    assert "auto-fix-auth-expired" in script
    assert "auto-fix-writer-failed" in script


def test_expired_codex_auth_stays_human_visible_not_reviewed_terminal(wf):
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None, "Must mark no-PR outcomes"
    env = str(no_pr_step.get("env", {}))
    script = str(no_pr_step.get("with", {}).get("script", ""))
    assert "CODEX_AUTH_EXPIRED" in env
    assert "writer-auth-expired-before-pr" in script
    assert "writerFailed && !codexAuthExpired" in script
    assert "auto-fix-auth-expired" in script
    assert "Remaining blocker: refresh `WORKFLOW_CODEX_AUTH_JSON_B64`" in script


# ---------------------------------------------------------------------------
# Slice B: retry-exhaustion + tier-fairness
# ---------------------------------------------------------------------------


def test_discover_treats_exhausted_label_as_terminal_skip(wf):
    """Issues labeled auto-fix-exhausted must be skipped by the discover scan."""
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "'auto-fix-exhausted'" in script
    # The skipLabels constant must include the exhausted label so shouldSkipIssue rejects it.
    assert (
        "const skipLabels = ['await-primitive-layer', 'complete', 'auto-fix-exhausted']" in script
    ), "auto-fix-exhausted must be in skipLabels so exhausted issues drop from active scan"


def test_discover_sorts_needs_human_retries_to_back_for_tier_fairness(wf):
    """Within a label tier, needs-human retries should sort by ascending retry count so they
    don't starve fresh candidates (the #918→#922 head-of-line blocking pattern)."""
    discover_step = wf["jobs"]["discover"]["steps"][0]
    script = str(discover_step.get("with", {}).get("script", ""))
    assert "function retryCountForIssue(issue)" in script
    assert "auto-fix-retries-(\\d+)" in script or "auto-fix-retries-" in script
    assert "issues.sort(" in script
    assert "retryCountForIssue(a)" in script
    assert "retryCountForIssue(b)" in script
    # Tier fairness comment must explain the rationale.
    lower = script.lower()
    assert "head-of-line" in lower or "starv" in lower or "fairness" in lower


def test_no_pr_step_reads_current_retry_count_and_computes_next(wf):
    """The needs-human terminal step must compute the next retry count and decide whether to
    exhaust based on MAX_RETRIES."""
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None
    script = str(no_pr_step.get("with", {}).get("script", ""))
    assert "MAX_RETRIES" in script
    assert "process.env.LOOP_MAX_RETRIES" in script
    assert "github.rest.issues.get" in script  # must refetch to read current labels
    assert "auto-fix-retries-" in script
    assert "nextRetries = currentRetries + 1" in script
    assert "exhausted = nextRetries > MAX_RETRIES" in script


def test_no_pr_step_applies_exhausted_label_when_budget_burned(wf):
    """At MAX_RETRIES, the step must label auto-fix-exhausted and drop needs-human so the
    discover scan stops re-picking the issue."""
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None
    script = str(no_pr_step.get("with", {}).get("script", ""))
    # exhausted branch applies auto-fix-exhausted instead of needs-human
    assert "labels.push('auto-fix-exhausted')" in script
    assert "labels.push('needs-human', `auto-fix-retries-${nextRetries}`)" in script
    # needs-human must be removed on exhaustion so retry-condition can't fire on next scan
    assert "removeLabel" in script
    assert "name: 'needs-human'" in script


def test_no_pr_step_removes_prior_retry_label_to_keep_series_unique(wf):
    """Only one auto-fix-retries-N label should be live at a time — bumping requires removing
    the prior label before adding the new one. Otherwise the regex max() would pick the wrong
    value over time and counters would drift."""
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None
    script = str(no_pr_step.get("with", {}).get("script", ""))
    assert "name: `auto-fix-retries-${currentRetries}`" in script
    # 404 (label not present) must be tolerated, not thrown.
    assert "error.status !== 404" in script


def test_no_pr_step_comment_records_retry_count_and_exhaustion_status(wf):
    """The comment posted on each retry/exhaustion event must surface the retry counter so
    host can see it without inspecting labels."""
    steps = wf["jobs"]["fix"]["steps"]
    no_pr_step = next(
        (s for s in steps if s.get("name") == "Mark needs-human if no PR opened"),
        None,
    )
    assert no_pr_step is not None
    script = str(no_pr_step.get("with", {}).get("script", ""))
    assert "Auto-fix exhausted" in script
    assert "Retry budget" in script or "Retry counter" in script
    assert "loop will retry when root cause clears" in script
    assert "loop-consent PR" in script or "host can re-open" in script.lower()


def test_ensure_labels_step_defines_auto_fix_exhausted(wf):
    """The label management step must pre-declare auto-fix-exhausted with a stable color and
    description so GH Actions doesn't have to invent one on first apply."""
    steps = wf["jobs"]["fix"]["steps"]
    ensure_step = next(
        (s for s in steps if s.get("name") == "Ensure automation labels"),
        None,
    )
    assert ensure_step is not None
    script = str(ensure_step.get("with", {}).get("script", ""))
    assert "name: 'auto-fix-exhausted'" in script
    assert "exhausted its retry budget" in script

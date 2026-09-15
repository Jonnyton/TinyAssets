# Failure-history implementation verification

September 15, 2026 UTC, Windows, isolated retain-failed-conversation-turns
worktree. Base 89a335578a1576a1b4253375e6d900a770338009; implementation is still
uncommitted at this checkpoint. No user workflows, credentials or live history
were changed. Fable5.1 pre-build round 1 is complete; implementation round 2
has not been dispatched. No PR, deployment or rendered failure-history proof.

## Local checks

Session 14767 completed with 320 passed, two deprecation warnings, no skips,
46.78s. Command:

```text
python -m pytest -q tests/test_conversation_failure_history.py tests/test_conversation_failure_readers.py tests/test_conversation_store.py tests/test_conversation_execution_history.py tests/test_conversation_memory.py tests/test_converse_handle.py tests/test_app_failure_history.py tests/test_onboarding_app.py tests/test_automation_context_scheduler.py tests/test_get_status_primitive.py --tb=short
```

Covers safe closed notices, atomic original-text/platform pairs, retention,
failed writes, read-only legacy stores, five reader projections, principal
isolation, account deletion, no fake execution receipts, saved/unsaved UI,
refresh without automatic replay, and refusing to resend truncated originals.
Transport uncertainty explicitly does not claim that no actions occurred.

The separate reader cohort produced 119 passed and three Windows symlink
privilege failures. Exact clean base 89a335 in failed-history-base-proof ran
`python -m pytest -q tests/test_automation_live_context.py tests/test_shared_background_self.py --tb=short`
and produced 39 passed and the same three failed cases:

- AutomationContextTests.test_symlink_escape_rejected
- AutomationContextTests.test_universe_symlink_to_another_home_rejected
- ConversationPagingTests.test_invalid_selectors_and_symlink_refuse

Each fails at symlink creation with WinError 1314, before the guard under test.
This set comparison is not Linux proof and no quarantine entry was added.

## Linux verification blocked before collection

The first `python scripts/linux_oracle.py -- -q ...` failed because Docker's
Linux engine pipe was absent. Starting installed Docker Desktop normally did
not restore it. Its backend log at 06:36:31 UTC reports Inference-manager
startup failure at the dockerInference socket: file cannot be accessed / invalid
filename syntax. The local test never reached collection. No factory reset,
Docker-data deletion, security change or claim of Linux success was made.
The two owned docker-info child processes (50168 and19176) were verified by
PID/command line and stopped September15 06:55UTC; oracle session51858 then
exited1 with no Linux engine. Docker Desktop and its data were not stopped,
reset or deleted. Ubuntu WSL is available with Python3.12.3 but has none of
the required pytest/fastmcp/lancedb/pydantic environment; it is not this oracle.

Canonical `python WebSite/brand/render_marks.py` and
`python packaging/claude-plugin/build_plugin.py` completed: only the expected
app provenance checksum changes, 444 runtime files staged, import probe passed.
Ruff and strict OpenSpec validation pass. Required hosted Linux CI remains
the available verification path; a draft cannot land before review and checks.

Before landing: complete plugin/brand generation, exact-head independent review,
Linux tests through a functioning approved test environment, normal CI, protected
deployed SHA/canary and a rendered owner failure-refresh-next-message conversation.

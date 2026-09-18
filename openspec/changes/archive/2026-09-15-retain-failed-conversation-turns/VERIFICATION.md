# Failure-history implementation verification

## Final deployed and rendered evidence, September15,2026 UTC

PR3856 merged07:32:20UTC as43479ccda60013b68ec303fda5a27356f792e2a5 from
reviewed25ec71052b5929d576923d8e56212b25a2d19edd. Final Fable5.1 round3
APPROVE183s/exit0; independent14app-history tests passed8.36s. Public receipt:
https://github.com/Jonnyton/TinyAssets/pull/3856#issuecomment-5676271542.

Required LinuxPython3.11 run34940621608 passed with zero NEW failures:
18093passed54skipped10deselected,5known failures/2known collection errors.
Downloaded JUnit artifact10385936389 inspected:14app-history+29conversation-
history+6readers+3Linux symlink cases all pass,52total0failed0skipped.
This resolves the Windows fixture limitation below without a quarantine change.

Build34942213879/deploy34942509946 passed. Protected deployed_sha.py
--assert-contains43479ccda600 at07:36:53UTC and public mcp_public_canary.py
--url https://tinyassets.io/mcp --assert-handles passed. Later descendant
2c902151a47a verified in deploy34943847005 at07:52:34UTC with the same gates.

Rendered Chrome/original-owner app mission9023, not direct MCP:
- Exact Retest your workflow checklist returned six smoke passes on43479ccda600
  at00:48PDT,8runs all finished. Webhook0314d1cd87634c0c,
  contention4d555751feeb4254, recoveryeabec8494de6419f.
- Saved Automatic, no default/credential changes: harmless greeting Can you
  answer a simple hello now? produced a real sign-in failure at00:49PDT.
  Correct Platform notice label, no answering receipt on failed turn.
- Reload retained verbatim greeting+safe notice+explicit Send it again. No
  automatic replay; did not click retry. Codex chosen for next messages only.
- Asked What happened to my last message? At00:53PDT agent identified the exact
  greeting and sign-in notice, preserved diagnostic uncertainty, and answered
  hello. No diagnostic clue was supplied in the question.
- A second reload retained BOTH failure and successful follow-up, no duplicate
  greeting or automatic resend. Read visibly through the Chrome extension.

General provider-auth failure remains separate. No private workflows, second-
user credentials or grants changed. No independent customer clean use is yet
visible; a separate post-fix watch records that limit. Historical checks below
are superseded where they say review/deployment/live proof remains pending.

September 15, 2026 UTC, Windows, isolated retain-failed-conversation-turns
worktree. Base 89a335578a1576a1b4253375e6d900a770338009; first implementation
committed df09debecd54c0fc2c0433b73d79b1365d19884a as draft PR3856. No user
workflows, credentials or live history were changed. Fable5.1 round2 completed
353s/ADAPT on that head,29 independent tests passed5.95s. Its one required
live-copy correction is being applied; not yet approved, deployed or proven
through a real failure-refresh-next-message conversation.

Round2 correction, September15 07:06UTC: live typed/voice failures preserve
the richer server error, setup holds preserve note/CTA, missing live copy uses
the fixed notice, and ordinary failed execution still warns before retry.
`python -m pytest -q tests/test_app_failure_history.py tests/test_onboarding_app.py tests/test_conversation_failure_history.py tests/test_conversation_failure_readers.py --tb=short`
passes176 tests33.27s/no skips after3 failing live-copy regressions were observed.
Canonical brand/plugin generation was rerun; the final exact-head review
remains required. No stored diagnostic representation changed in this correction.

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

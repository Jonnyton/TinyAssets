# Scheduled monitoring candidate verification

September 19, 2026 UTC; branch `codex/hostless-revert-acceptance`.
Shape review: `2026-09-19-scheduled-monitor-shape-fable.md` (ADAPT,
four required changes implemented). This record is local proof, not deployed
acceptance or exact-head approval.

## Candidate scope

`scripts/revert_loop_canary.py` distinguishes positively recognized confined
legacy-evidence absence from malformed status, refusal and transport failure.
Its fixed producer reason reaches Actions outputs directly. New pure
`scripts/uptime_observations.py` gives measured red priority over unknown;
unknown prevents green and warns that recovery is unavailable. The workflow
records a versioned measured-red sentinel and checks the prior exact run/attempt
receipt instead of whole-workflow failure. Absent hosted rendered capability
is explicitly unknown without invoking the browser/LLM harness.

No public API/authority, tenant data, model binding, user workflow, installer,
container retention, or production mutation. Full execution-quality/rendered
coverage and existing incident disposition remain open in the concern.

## Commands and results

Both environments ran this exact 13-file cohort:

```text
python -m pytest -q tests/test_uptime_observations.py tests/test_revert_loop_canary.py tests/test_current_executor_liveness.py tests/test_last_activity_canary.py tests/test_uptime_canary_workflow.py tests/test_uptime_canary_layer2.py tests/test_uptime_canary_concurrency.py tests/test_canary_scripts_import_smoke.py tests/test_mcp_public_canary.py tests/test_mcp_tool_canary.py tests/test_wiki_canary_transport.py tests/test_wiki_canary.py tests/test_uptime_canary.py
```

Windows Python 3.14: **344 passed, zero skips**, one existing Starlette
deprecation warning. Native-WSL Docker oracle, Python 3.11.16 / git 2.47.3 /
bubblewrap 0.12.0: **344 passed, zero skips**, one existing AnyIO warning.
Linux invocation, substituting the same test list after `-q`:

```text
wsl -d Ubuntu --cd /mnt/c/Users/Jonathan/.codex/worktrees/hostless-revert-acceptance/TinyAssets -- env GIT_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git/worktrees/TinyAssets47 GIT_COMMON_DIR=/mnt/c/Users/Jonathan/Projects/TinyAssets/.git GIT_WORK_TREE=/mnt/c/Users/Jonathan/.codex/worktrees/hostless-revert-acceptance/TinyAssets python3 scripts/linux_oracle.py -- -q <same 13 test files>
```

Ruff passes on both edited scripts and the four edited/new test modules;
`git diff --check` passes; OpenSpec strict validation passes. Red-first
checkpoint was four failures before runtime/workflow changes (producer reason
missing; bare prior workflow failure falsely opens an incident); later malformed
payload cases were also red before implementation.

Local actionlint is unavailable on both Windows and Ubuntu WSL. No global tool
installation was attempted. Hosted workflow lint remains a required release
check; no local actionlint pass is claimed. Exact-head independent approval,
hosted checks and fresh scheduled-result acceptance remain pending.

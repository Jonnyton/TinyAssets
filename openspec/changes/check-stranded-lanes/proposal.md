# Detect stranded local lanes

## Why

Finished work repeatedly remains only on local disk after a publish step fails or
never creates a remote branch and pull request. `scripts/worktree_status.py`
cannot detect the dominant case because it enumerates only registered Git
worktrees; standalone shallow clones such as
`.codex-scratch-uptime-canary-1461/` are outside that inventory. Draft PR #1514
established that blind spot while keeping suspected causes such as push
authentication and subagent write redirection explicitly unproven.

## What Changes

- Add a read-only `scripts/check_stranded_lanes.py` command.
- Enumerate registered worktrees together with known sibling and scratch-clone
  locations, de-duplicated by resolved path.
- Report and exit 2 when a checkout is ahead of its own `origin/main` and lacks
  either a pushed branch or a pull request.
- Report unreadable or indeterminate checkouts as `UNKNOWN` and exit 2, including
  Git dubious-ownership failures, without modifying safe-directory config.
- Add integration-focused tests with real temporary Git repositories and
  injectable remote/PR boundaries.

## Impact

- New capability delta: `harness-coordination`.
- New files: `scripts/check_stranded_lanes.py`,
  `tests/test_check_stranded_lanes.py`.
- No hook, session-start, CI, `STATUS.md`, or `AGENTS.md` wiring in this change.
- No writes, pushes, cleanup, deletion, or Git configuration changes at runtime.

## Context

The scheduled task currently starts `powershell.exe` directly. PowerShell can
hide its window only after process creation, so Windows still exposes a console
that can receive a close/control event. Provider subprocesses have the same
problem when the resolved CLI is a `.CMD` shim. Separately, a linked worktree's
`.git` file points outside the worktree to the primary repository's common Git
directory; Codex receives only the worktree as an additional writable root.

The first overnight run demonstrated that watchdog identity recovery is sound,
but also demonstrated that terminal-result semantics conflate a durable
dependency blocker with a recoverable commit/push/PR failure.

## Goals / Non-Goals

**Goals:**

- Keep the tray and worker process trees consoleless from process creation.
- Give write-capable Codex workers the minimum additional filesystem root
  required for linked-worktree Git operations.
- Resume the same admitted lane immediately after a delivery-infrastructure
  failure.
- Make the publication route and terminal-result distinction explicit.

**Non-Goals:**

- Parallel workers or unbounded execution.
- Automatic bypass of CI, review, branch protection, or genuine host gates.
- Recovery or merging of the three preserved overnight lanes in this change.

## Decisions

1. **Use a windowless script host for Task Scheduler.** The scheduled action
   invokes `wscript.exe`, which starts the existing PowerShell tray script with
   window style `0` and waits for it. This avoids the initial console that
   `powershell.exe -WindowStyle Hidden` cannot prevent. The alternative,
   retaining direct PowerShell startup, preserves the observed close-to-kill
   race.

2. **Use `CREATE_NO_WINDOW` for provider subprocesses on Windows.** The flag
   applies at process creation and covers `.CMD` shims. Other platforms keep
   the existing zero flag.

3. **Resolve the Git common directory and make write mode explicit.** For
   write-capable Codex runs, the launcher resolves `git rev-parse
   --path-format=absolute --git-common-dir` from the assigned worktree and
   passes it through `--add-dir`. Codex protects Git metadata even under an
   added workspace-write root, so explicit write mode uses
   `danger-full-access` with `approval_policy=never`. This does not weaken the
   supported Windows host's existing effective boundary: its Codex wrapper
   already bypasses the OS sandbox, and the worker brief already declares the
   worktree/claim/review/CI/budget controls as the safety boundary. Read-only
   workers retain the read-only sandbox and receive no Git metadata root.

4. **Classify delivery infrastructure as `FAILED`, not `BLOCKED`.** `BLOCKED`
   remains reserved for a durable task, host, review, dependency, or policy
   gate. Failure to stage, commit, push, create a PR, or invoke the selected
   publication route preserves the admission and consumes the bounded failure
   budget, causing a fresh worker to resume the same worktree. The worker brief
   names `git` plus `gh` as the supported publication path.

## Risks / Trade-offs

- **A write worker is not OS-sandboxed** -> require the explicit `--write`
  invocation, isolate it in the assigned worktree, and retain exact
  branch/worktree/claim/review/CI/budget gates; read-only peers remain
  sandboxed.
- **A permanent publication outage retries repeatedly** -> existing finite
  consecutive-failure and runtime budgets stop the loop.
- **Script-host quoting can break paths with spaces** -> keep argument assembly
  inside the VBS launcher and cover the installed action and launcher contract
  with regression tests.

## Migration Plan

1. Land the launcher, supervisor, tests, spec, and runbook together.
2. Re-run the idempotent autostart installer to replace the scheduled action.
3. Allow the watchdog to resume the existing run or start a fresh bounded run.
4. Roll back by reinstalling the prior scheduled action; drain state and
   preserved worker worktrees are independent of the launcher.

## Open Questions

None.

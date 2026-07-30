## Context

The controller is intentionally a stable detached worktree. Moving that
worktree while the Python process is running would mix loaded code from one
revision with scripts and coordination files from another. Not moving it means
its working-tree `STATUS.md` inevitably becomes stale as drain workers merge
and retire rows.

Admission already fetches and creates a clean worktree from `origin/main`, so
it correctly rejected the stale hint. The bug is the earlier selection step:
it keeps offering the same old row and spends the finite failure budget on a
known-invalid candidate.

## Goals / Non-Goals

**Goals:**

- Select from the exact current `origin/main` coordination state.
- Keep the live controller checkout stable.
- Preserve working-tree claim inspection for provider sessions and admitted
  worktrees.
- Fail closed on fetch/ref errors and retain mechanical admission revalidation.

**Non-Goals:**

- Cloud migration of the drain or BYOC activation.
- Automatic worktree cleanup.
- New task-priority policy, parallel workers, or larger failure budgets.
- Replacing STATUS/OpenSpec coordination with a new queue.

## Decisions

### Claim checking accepts an explicit Git ref

`claim_check.py --status-ref <ref>` reads `STATUS.md` using
`git show <ref>:STATUS.md` and feeds that text into the existing parser and
classifier. Without the option it retains the current working-tree behavior.
The helper does not fetch, mutate refs, or change claim state.

Stale-claim activity lookup uses the same explicit history ref, rather than the
controller checkout's old `HEAD`. Option-like, whitespace-bearing, and
revision/path-delimited ref inputs are rejected before Git invocation. This
keeps classification in one canonical implementation instead of duplicating
STATUS parsing inside the supervisor.

### The controller refreshes before selection

A new supervisor helper runs `git fetch --prune origin`, then invokes the
existing candidate snapshot with `--status-ref origin/main`. The main
pre-dispatch selection and post-block alternative check use this helper.
The subprocess boundary decodes the claim helper's explicitly UTF-8 JSON as
UTF-8, rather than the Windows console code page.

Admission revalidation does not: its newly created worktree contains the
controller's just-written claim, which is intentionally newer than
`origin/main`.

### Fetch/ref failures stay observable and bounded

A failed fetch or invalid ref raises the same candidate-snapshot failure path
already logged by the supervisor. It does not silently fall back to the stale
working tree. Ordinary failure and time budgets remain authoritative.

## Risks / Trade-offs

- **A merge races after fetch** — admission fetches and revalidates again, so
  the race fails closed.
- **Extra network traffic** — one bounded fetch per selection is acceptable for
  a sequential drain and preferable to invalid worker launches.
- **Local provider sessions need dirty-tree visibility** — `--status-ref` is
  opt-in; default behavior remains unchanged.
- **Windows decodes JSON with the ambient code page** — both the claim helper's
  Git read and the supervisor's JSON read specify UTF-8 explicitly.
- **Ref argument injection** — subprocess arguments are passed as a list, not a
  shell string, and option-like/path-delimited inputs are rejected before Git.

## Migration Plan

1. Land and archive the focused change.
2. Update the detached controller checkout to the merged commit while no
   supervisor child is running.
3. Restart the scheduled watchdog after the terminal red run.
4. Verify the next candidate snapshot matches current `origin/main` and that an
   already-retired row is not retried.
5. Roll back by restoring the prior controller commit; run artifacts remain
   compatible.

## Open Questions

None for this bounded fallback repair. The cloud-universe target is reviewed in
PR #1870 and is deliberately outside this change.

## Context

Mechanical admission derives a bounded slug from a human STATUS task label and
stores both values. The admitted worker received the human label in
`_PURPOSE.md`, but its terminal contract only said `<target-or-dash>`.
`parse_result` accepted only a slug token, so the valid-looking
`DRAIN_RESULT: BLOCKED main-red round 2 -` was rejected and consumed the final
failure strike. The worker artifact, admission, branch, and worktree remain
intact.

## Goals / Non-Goals

**Goals:**

- Give an admitted worker an unambiguous exact terminal target.
- Accept a literal human label by converting it through the same slug function
  used by admission.
- Reconcile one previously invalid artifact when upgraded code can parse it.

**Non-Goals:**

- Accept ambiguous templates, multiple markers, arbitrary URLs, or unknown
  statuses.
- Reset unrelated failures or retry a worker whose artifact remains invalid.
- Change candidate ordering, concurrency, or failure-budget sizes.

## Decisions

1. Parse the terminal marker structurally: split the status from the remainder,
   split the final PR-or-dash token from the target, validate the target
   character set, then slugify the target. This retains a one-line,
   three-field wire result while tolerating the controller's own human labels.
   Expanding the old regex without canonicalization was rejected because
   admission comparison would still fail.
2. For admitted workers, append the exact slug to the final contract and state
   that the human label must not be substituted. Parser tolerance remains
   defense in depth, not the primary instruction.
3. At supervisor startup, when and only when `last_result.status` is
   `INVALID_RESULT`, inspect the artifact named by the attempt number stored in
   that result record, never the mutable latest-attempt counter. If it now
   parses and satisfies the preserved admission, subtract the one parser strike
   and apply it through the normal result state transition. This is
   deterministic replay, not a general failure reset. For a pre-change state
   that lacks the attempt field, infer the current counter only when the
   persisted state is already terminal `failure-budget`; running and
   `invalid-result` states remain ineligible for that fallback.

## Risks / Trade-offs

- **A permissive target parser could hide malformed output** → allow only the
  bounded label character set and continue rejecting placeholders, pipes,
  duplicate markers, and invalid terminal tokens.
- **Replay could double-apply a result** → gate it on the persisted
  `INVALID_RESULT` status and replace that state atomically before dispatch.
- **A valid replayed merge could be stale** → reuse ordinary admission and
  GitHub merge verification rather than bypassing result handling.

## Migration Plan

1. Land the parser, explicit prompt, replay path, tests, and spec delta.
2. Update the detached controller checkout to the merged `origin/main`.
3. Restart the watchdog; the preserved terminal `failure-budget` state safely
   infers and replays attempt 5 even though that pre-change result record lacks
   the new exact-attempt field.
4. Roll back by stopping the scheduled watchdog and reverting the PR; preserved
   run artifacts remain available for diagnosis.

## Open Questions

None.

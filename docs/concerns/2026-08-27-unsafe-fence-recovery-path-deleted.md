# The recovery path for a live production fence state was deleted with the fence still armed

**Filed:** 2026-08-27
**Severity:** P1 — the state it recovers from has occurred in production, fences
all five containers, and now has no documented way out
**Verified:** 2026-08-27 against `814b4f06`

## The finding

PR #2442 deleted the `recover-unsafe` job from `deploy-prod.yml`. That job was
the **only** way to recover a droplet stuck at `phase=unsafe_fenced`. The fence
that produces that state is still armed.

**The fence is live.** `scripts/retire_cheat_loop_deploy_fence.py` is staged to
the droplet by three workflows that all still run:

```
.github/workflows/install-host-services.yml:65
.github/workflows/p0-outage-triage.yml:78
.github/workflows/restart-daemon.yml:64
```

and `deploy/compose.yml:292` still documents its behaviour ("`retire_cheat_loop_
deploy_fence.py` deletes any container mounting …").

**The state is real, not theoretical.** The script's own comment, `:3571`:

> Observed live 2026-08-05 after recovery 31048315265: `phase=unsafe_fenced`,
> `removal_phase=removed`, all five expected containers present and Exited

All five containers Exited is an outage. It happened, and it took a
`recover-unsafe` run (`31048315265`) to get out.

**Nothing can drive recovery now:**

```
$ grep -rln "unsafe_fence_source_run_id\|Recover canonical unsafe fence" .github/workflows/
(no output)
```

## This was an accident, not a retirement

The deliberate removal is specified, and it is explicitly gated on work that
has not happened. `openspec/changes/archive/2026-08-26-retire-cheat-loop/tasks.md:145`:

> - [ ] **2.5a** *After task 2.5's locked migration and final rescan succeed*,
>   delete `scripts/retire_cheat_loop_deploy_fence.py`, its product-specific
>   deploy, […] task-2.1 fence artifact or host helper. **Restore the surviving
>   workflows** to […]

Tasks **2.1, 2.5 and 2.5a are all unchecked**, and the change was archived on
2026-08-26 with them unchecked — which is sanctioned (AGENTS.md: *"a change idle
14 days is not in flight — archive it and re-propose"*) and is **not** evidence
the work completed.

So the intended order was: run the locked migration, then delete the fence AND
its recovery together. What happened instead was: delete the recovery, keep the
fence.

**The orphans confirm it.** Every support file `recover-unsafe` staged is still
in the tree, referenced by nothing:

| File | State |
|---|---|
| `deploy/recovery-restart-no.yml` | present, orphaned |
| `deploy/tinyassets-recovery-reconcile.service` | present, orphaned |
| `scripts/validate_host_runtime_hmac_pair.py` | present, orphaned |
| `scripts/validate_agent_interchange_hmac.py` | present, orphaned |

A deliberate retirement per 2.5a would have taken these with it. Leaving four
support files and the fence itself, while removing only the entry point, is the
signature of an incidental deletion inside a 2,628-line rewrite.

## What the deleted job did

`workflow_dispatch`, gated on `inputs.unsafe_fence_source_run_id != ''`, then:
validate the interchange and idempotency HMACs → install a recovery SSH key →
dump fence state read-only → validate the host HMAC pair → resolve an immutable
recovery image and refuse a revision predating the stop-writer floor → pull it
on the host → **"Recover canonical unsafe fence"**, staging the fence script,
`recovery-restart-no.yml` and the reconcile unit by sha.

Note the ownership gate is `source_run_id`, which is sticky and is not the same
as the `run_id` an artifact exposes — see [[fence-recovery-source-run-id-is-sticky]].
Whoever restores this should not assume those are interchangeable.

## Resolving this

Two coherent end states. Either is fine; the current one is neither.

1. **Restore the recovery path** — re-add `recover-unsafe` (or an equivalent
   dispatch-only workflow) so the armed fence has an exit. Smallest change that
   makes the system consistent again.
2. **Finish 2.5a properly** — run task 2.5's locked migration, then remove the
   fence, its three workflow call sites, the four orphaned support files, the
   host artifact, and `tests/test_retire_cheat_loop_deploy_fence.py` (17 of the
   `heavy-tests` failures) together.

**Do not** delete the 6 failing assertions that reference `recover-unsafe` until
one of those is done. They are currently the only thing in the repo asserting
that an armed fence has a recovery path.

## How it was found

Triaging the 81 failing assertions in `tests/test_deploy_prod_workflow.py`
(see [full-tests-permanently-red](2026-08-27-full-tests-permanently-red.md)),
which had left this as an open question for the founder — *"deliberate or
accident?"*. It is answerable from the repo, and the answer is accident.

# The engine's run-rate cap (20 per hour per universe) stalls a normal GitHub job

**Filed:** 2026-08-29, from the live naive-user retest.
**Verified:** yes — `run_graph rate limit reached (max 20 per 60m); try again
shortly.` returned to the founder's universe at 22:43Z, in the founder's
presence, on the third attempt at a one-line README change.
**Severity:** P2 — it is a deliberate security control doing what it was
built for, and it also stops the founder's own job mid-flight with nothing
the founder can do but wait.

## The claim

`tinyassets/engine_mcp_server.py` caps engine-triggered runs at
`_RUN_GRAPH_RATE_MAX = 20` per `_RUN_GRAPH_RATE_WINDOW_S = 3600` rolling
seconds, per universe (Codex gate #5: a prompt-injected engine must not be
able to spam an already-approved effect branch — open many PRs, say). The
constants are hard-coded; there is no per-universe knob.

A served GitHub job spends one run per API call: read the ref, create the
branch, read the file, write the file, open the PR — five runs when
everything works. On 2026-08-29 the file write corrupted the file twice
(`docs/concerns/2026-08-29-file-writes-need-model-generated-base64.md`), so
the honest retries — read the bad blob, repair, re-read `main`, reset —
spent the hour's budget, and the clean third attempt was refused at the
write step. The universe reported it plainly ("I'm not going to claim either
happened when they didn't") and asked to be sent back in "after the run
window clears". The founder's standing rule is that a turn runs until
finished unless the user interrupts it; here the platform interrupted it.

## What is in tension

- The cap bounds **how often** an approved effect fires; the approved-source
  gate bounds **what** fires. Both are right to exist.
- But the cap cannot tell a prompt-injected loop from a founder watching the
  thread and asking for another try, and it counts every run — including
  the read-only ones (`GET` a ref, `GET` a blob) that carry no effect.

## Options (decide, then spec — it is an authority/limits change)

1. **Count only runs that carry an external write** (`effects` declared on a
   node). Reads stop consuming the budget; today's job would have spent ~6
   of 20, not 20. Smallest change, keeps the injection defence on writes.
2. **Per-universe knob** like `absolute_cap_s`/`idle_timeout_s`
   (`run_rate_max` in the universe context), founder-settable through the
   app, default 20. Keeps the control, hands the dial to the owner.
3. **Founder-present exemption**: a run triggered inside a served founder
   turn (the founder is in the conversation) is not the injection case the
   cap targets. Riskiest to reason about; a served turn can still be
   injected through fetched content.

Option 1, then 2 if a real job still hits it. Not 3 alone.

## How to resolve this file

Delete it when a one-line file change with one retry completes through the
live app without meeting the cap, and the chosen option is in
`openspec/specs/` with the count rule stated.

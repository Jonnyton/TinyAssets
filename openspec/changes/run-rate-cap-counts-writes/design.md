## Context

The engine run cap (`_RUN_GRAPH_RATE_MAX = 20` per rolling hour per
universe) is the effect-spam bound from Codex gate #5: a prompt-injected
engine must not be able to spam an already-approved effect branch. It
counted every engine-triggered run the same, which stalled a normal GitHub
job with one honest retry (2026-08-29 22:43Z, live, in the founder's
presence). The concern's option 1 — count only runs that carry an external
write — cannot be applied up front: the packet an effect fires (verb, path,
body) is model-authored at run time, so a branch cannot be classified as
read-only before it runs.

## Goals / Non-Goals

- Goals: keep the injection bound exactly as strong at admission time;
  stop charging the write budget for runs that provably wrote nothing;
  bound read-only runs separately; make the accounting survive the real
  orderings (fast runs settling before their bind, failed runs, runs whose
  status is rewritten after their effects fired).
- Non-goals: per-universe knobs (option 2), founder-present exemptions
  (option 3), any change to WHAT may run (approved-source gate, grants).

## Decisions

- **Charge at admission, settle at the end.** Every engine-triggered run,
  scheduled automation run and engine write is admitted as `write`,
  atomically (`BEGIN IMMEDIATE` count-and-insert, schema migration inside
  the same transaction). Settlement happens once the run's fate is known.
- **Tickets, not "the newest row".** `admit_detail` returns
  `Admission(ticket, refused_by)`; the ticket is the ledger row id and the
  caller binds it to the run id (`attach_run`) the moment the id exists.
  Concurrent admissions cannot cross-bind.
- **Settlement is a two-state ledger of its own.** A `settlements` table
  keyed by run id records the FINAL kind the run proved: `read` (every
  fired effect was a `GET`/`HEAD` authenticated call, or nothing fired) or
  `write` (anything else). A `write` settlement is final: a later `read`
  settlement for the same run — for instance a FAILED status written after
  the effects already fired because provider-authority release failed —
  cannot override it. A settlement that arrives before the bind is applied
  at bind time. Settlement rows expire two hours after they are written,
  pruned on every settle and every admission, so a browser run that never
  binds leaves at most two hours of rows.
- **Failed runs settle as reads, unless they already settled as writes.**
  `update_run_status(FAILED|CANCELLED)` calls the same settle path with no
  fired effects; the `write`-is-final rule above makes this safe for a run
  whose effects fired before the status was rewritten.
- **Two caps, one ledger.** `write` rows count against 20/h; rows of any
  kind against 60/h (5 runs + up to 5 retunes = 10 per job attempt, 20 with
  a full retry, 3x that). Every refusal names the cap that refused.
- **Storage shape.** `admissions(universe_id, ts, kind DEFAULT 'write',
  run_id DEFAULT '')` — two additive columns, an old ledger's rows count as
  writes; `settlements(run_id PRIMARY KEY, kind, ts)`. The ledger lives
  under the canonical data-dir resolver, never the CWD; its parent is
  created if missing; a symlinked or out-of-tree ledger is refused.

## Risks / Trade-offs

- A `GET` with side effects on the far side is out of HTTP semantics; for
  the GitHub API that motivates this it is not real, but the generic
  connector can reach any HTTPS service, so "read" is a statement about
  owner-approved endpoints, not something the platform enforces.
- Settlement rows for never-bound runs cost one small row per run for two
  hours; measured ~86 bytes each.
- Two windows of the same universe cannot cross-bind, but a fail-open
  admission during a ledger error records nothing (`ADMITTED_UNRECORDED`),
  which is the existing fail-open contract for `run_graph`.

## Migration Plan

Additive; no data rewrite. First touch of an old ledger migrates it inside
the admission transaction. Rollback is dropping the code; the extra columns
and table are inert to the old code.

## Open Questions

- Whether `write_graph`/remix/brain should ever settle (they are durable
  engine mutations, kept as unattached writes on purpose).

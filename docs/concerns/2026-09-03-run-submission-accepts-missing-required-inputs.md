# Run submission accepts missing required branch inputs

**Filed:** 2026-09-03
**Verified:** 2026-09-03, live founder app on production
`6039f6fe70d826eb6914e670a8f0b269f32729cb`.
**Severity:** P2 — an invalid run is admitted and recorded before the user is
told which inputs the branch required.

## Source (sanitized)

The founder asked the served universe to retest its complex-workflow smoke
branches. Two prompt branches were admitted with empty run inputs and failed
inside execution before any provider call: the sequential branch lacked its
declared `topic`, and the parallel branch lacked its declared `subject`.

The conversation itself is private and is not copied here. Exact universe,
binding, branch, and run identifiers are intentionally omitted.

## What is true

`run_graph.inputs_json` is documented as optional. The branch read guidance
tells the chatbot to fill the state schema, and state-schema defaults are seeded
correctly when present, but submission does not reject a required unresolved
input before creating the run. The compiler therefore reports the missing key
only after the run has entered execution.

The two live smoke branches were repaired separately in the founder's private
universe: their declared `topic` / `subject` inputs now carry stored smoke-test
defaults while their placeholder-driven prompt behavior remains intact. That
branch hygiene does not remove the reusable platform defect.

## Acceptance target

Before queueing, charging admission, calling a provider, or firing an effect,
the run surface should detect required inputs that are not supplied, defaulted,
or produced by an earlier reachable node. It should refuse immediately with a
stable machine-readable reason, the exact sorted missing keys, and enough type
or example-shape guidance for a chatbot to retry correctly. The refusal should
create no run row.

This is a public `run_graph` behavior change, so it needs an OpenSpec proposal
before code and cross-client rendered proof after deployment. The delivery WIP
queue is already full (`run-provider-authority`, `workspace-node`,
`run-usage-budgets`, and `script-authoring-surface`), so this finding remains a
concern rather than bypassing the admission wall.

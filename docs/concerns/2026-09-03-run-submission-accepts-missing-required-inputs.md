# Run submission accepts missing required branch inputs

**Filed:** 2026-09-03
**Verified:** 2026-09-03, read-only observation through the live founder app on
production `6039f6fe70d826eb6914e670a8f0b269f32729cb`.
**Severity:** P2 — an invalid run is admitted and recorded before the user is
told which inputs the branch required.

## Source (sanitized)

The founder asked the served universe to retest user-owned workflows. Runs with
unresolved required inputs were admitted and failed inside execution before any
provider call.

The conversation itself is private and is not copied here. Exact universe,
binding, branch, run, prompt, input, default, and topology details are
intentionally omitted. The affected branches are user-owned state, not
maintainer fixtures or platform deliverables. Patches must not repair, retain,
revert, or delete them; only the user or that universe's bound agent may change
or delete them through the ordinary user-scoped branch lifecycle.

## What is true

`run_graph.inputs_json` is documented as optional. The branch read guidance
tells the chatbot to fill the state schema, and state-schema defaults are seeded
correctly when present, but submission does not reject a required unresolved
input before creating the run. The compiler therefore reports the missing key
only after the run has entered execution.

The condition of any particular user branch is neither a completion criterion
nor acceptance evidence for this platform defect.

## Capability boundary

This concern owns one generic behavior: invalid run submissions must be refused
before admission. It does not make Patches the owner of a user's branch or
collapse the full branch lifecycle into this one change. Create, inspect, edit,
run, and delete remain ordinary user-scoped capabilities exercised by the user
or the user's bound universe agent. Existing lifecycle and authority behavior
must compose with the new preflight and must not gain a maintainer bypass.

## Acceptance target

Before queueing, charging admission, calling a provider, or firing an effect,
the run surface should detect required inputs that are not supplied, defaulted,
or produced by an earlier reachable node. It should refuse immediately with a
stable machine-readable reason, the exact sorted missing keys, and enough type
or example-shape guidance for a chatbot to retry correctly. The refusal should
create no run row or run id.

Acceptance uses an isolated, maintainer-owned test universe and a simulated
user/bound-agent identity, never a founder or customer universe. It proves:

1. The owner can create a disposable branch with a required input, inspect that
   contract, and edit the branch through ordinary served primitives.
2. Running without the required value returns the stable pre-admission error
   and causes no queue, provider, billing, effect, or persisted-run activity.
3. Supplying a valid value, or an owner-authored stored default where the schema
   permits one, admits the run normally.
4. A different identity and a maintainer lane gain no inspect, edit, run, or
   delete authority over the private branch from this change.
5. The owner can delete the disposable branch through the ordinary served
   primitive; subsequent inspect, edit, run, and delete attempts return the
   existing not-found/authority-safe result.

After deployment, rendered live proof is performed by the founder or their
bound universe agent through ordinary user-scoped primitives. If that actor
chooses to create a disposable branch, that actor also inspects, edits, runs,
and deletes it. The maintainer records only the sanitized capability outcome,
never private branch content or identifiers, and never performs the mutation.

This is a public `run_graph` behavior change, so it needs an OpenSpec proposal
before code and cross-client rendered proof after deployment. The delivery WIP
queue is already full (`run-provider-authority`, `workspace-node`,
`run-usage-budgets`, and `script-authoring-surface`), so this finding remains a
concern rather than bypassing the admission wall.

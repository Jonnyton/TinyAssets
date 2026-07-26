# Connector tool-selection accuracy

## Why

The connector's behavioral surface is *prose*: the server `instructions` block plus the
`control_station` prompt tell a host chatbot which of the seven canonical handles to reach for.
Every feature that needs the chatbot to behave differently adds more of it. Nothing measures
whether that prose still works.

This is the surviving risk from retired task 2.9 of the `universe-personification` change
(Codex review 2026-07-22, finding 4), carried forward as task 6.3 of
`reconcile-universe-personification-relay`. The original task was a regression test proving
*embodiment* did not degrade tool-selection accuracy. Embodiment was live-falsified and removed, so
there is no embodiment prompt left to regress — but the underlying failure mode outlived it:

> **connector instruction density vs tool-selection accuracy** — as the shipped `instructions`
> and `control_station` prompt grow, does the host chatbot still pick the right handle?

The failure is silent and user-facing. A chatbot that answers a "talk to my universe" turn by
calling `read_graph` instead of `converse` does not error — it returns a plausible, wrong-shaped
response, and the founder never reaches their universe. `mcp_public_canary.py --assert-handles`
cannot catch this: it proves the seven handles are *advertised*, not that they are *chosen*. The
`first-contact` flow depends specifically on `converse` being picked first on an opening message,
which is exactly the behavior most exposed to instruction drift.

The gap is that correctness here is currently unstatable. There is no labelled prompt set, no
baseline number, and no stated tolerance — so no proposed prose change can be evaluated, and
`reconcile-universe-personification-relay` task 6.3 cannot be discharged until those exist.

## What Changes

- **Define the subject under test**: the connecting chatbot's handle choice, given the shipped
  server `instructions` + `control_station` prompt, over the canonical handles
  (`read_graph`, `write_graph`, `run_graph`, `read_page`, `write_page`, `converse`, `get_status`).
- **Introduce a labelled, versioned prompt→expected-handle dataset** as the fixed measurement
  instrument, with integrity rules (every label is a canonical handle; every handle is covered; no
  duplicate prompts) enforced by tests rather than by review.
- **Define the metrics**: top-1 correct-handle rate over the dataset, plus the
  `converse`-first-on-opening rate the `first-contact` flow depends on, reported separately because
  a regression confined to opening turns is invisible in a pooled average.
- **Define the permitted regression** — the maximum tolerated drop against a recorded baseline —
  and make a proposed connector-prose change that exceeds it a failing gate.
- **Ship the scoring harness** that turns a recorded rendered-chatbot run into those metrics and
  fails loudly on incomplete coverage, so the gate cannot be passed by a partial run.

Deliberately **not** in scope: automating the measurement itself. Handle choice is a property of the
host chatbot, so the observations come from a rendered `ui-test` session through the live connector
(AGENTS.md § Quality Gates: direct MCP calls are supporting evidence, not user-surface proof). The
harness scores a recorded run; it does not simulate one.

## Impact

- Affected capability: `live-mcp-connector-surface` (owns the prompt catalog and the canonical
  seven-handle set). Adds requirements; changes no existing one.
- New artifacts: a versioned dataset, a scoring harness, and dataset-integrity tests.
- Discharges task 6.3 of `reconcile-universe-personification-relay`, which is in turn one of the
  gates on that change's task 6.11 (`sync-specs`).
- **No runtime behavior changes.** No handle is added, removed, renamed, or rewired, so the
  advertised surface asserted by `mcp_public_canary.py --assert-handles` is untouched.
- Interacts with `universe-personification-and-relay`: any future personification text added to the
  sanctioned channels (server `instructions`, `control_station`) becomes a change that must clear
  this gate. That is the point — the retired task's intent was a regression guard, and this is the
  instrument it needed.

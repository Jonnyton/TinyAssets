# Pre-build review: carrying a node deadline through the invocation path

September 23, 2026. Independent review of root's proposed shape, by the Claude
lane on `codex/reliability-next` (base `1f121719`). Analysis preceded
implementation; this artifact was written at closeout in the same lane.

## Premise correction

The brief cited `docs/concerns/2026-09-22-provider-execution-evidence.md` and
`docs/reviews/2026-09-22-provider-execution-evidence-localization.md`. **Neither
file exists** in this tree, and no file in `docs/` or `openspec/` references
either name. The nearest real evidence is
`docs/concerns/2026-09-21-provider-tool-wait-observation.md` and
`docs/concerns/2026-09-21-tool-wait-diagnostic-followups.md`. The localization
below therefore comes from reading the runtime directly, not from the cited docs.

## Verdict on root's proposed shape

**AGREE, in part, with one component split off as unjustified-as-stated.**

### AGREE — cancel work not yet started

`tinyassets/graph_compiler.py:341` `_run_with_timeout` submits every provider /
source_code call to a shared 8-worker pool and waits
`future.result(timeout=timeout_s)`. The deadline is measured from `submit()`,
not from worker-allocated start — the module comment at `graph_compiler.py:305`
already said so and deferred it ("Fine for single-run today"). On expiry it
raised `NodeTimeoutError` and **never called `future.cancel()`** — `.cancel()`
appeared nowhere in the file. A call that spent its entire budget queued
therefore became terminal and then *started*, driving a provider call nobody
awaits, holding a worker, strictly outside the deadline that admitted it.

`concurrent.futures.Future.cancel()` is the right-sized correction precisely
because of what it cannot do: by contract it returns `False` once the work has
been picked up, so it is structurally incapable of interrupting a started call.
Settlement and uncertain-effect protection are preserved by the API's own
guarantee, not by a convention a later edit could erode.

### DISAGREE_CONCERN — "subtract elapsed queue/admission time before launch"

Real defect, wrong-sized as a same-lane change. The provider cap is
`ModelConfig(timeout=..., absolute_cap_s=timeout_s)` built **once per node
closure** at `graph_compiler.py:1192`, outside `_fn`. A call that starts partway
through its budget still receives the node's *full* timeout as its cap, so it
outlives the node deadline by the queue wait. But correcting it means computing
the deadline per invocation inside the worker: mutating the shared `_node_cfg`
in place would be a cross-invocation race under parallel fan-out, since one
compiled closure serves concurrent invocations. That is a different change with
its own review surface, and it is not needed to close the abandonment path —
once queued work is cancelled, the residual overrun is bounded by the queue wait
on work that genuinely started. Recorded in-place at `graph_compiler.py:305`
rather than left implicit.

### AGREE — the stated prohibitions

No auto-replay of unknown effects, no treating a requested model as reported
identity, no blanket timeout raise. The landed change does none of these: it
adds one `future.cancel()` call and touches no timeout value.

## Scope honesty

This closes one concrete abandonment path. It does **not** explain the
historical intermittent parallel/idle failures — `6ffec5e973734074` still lacks
tool-phase evidence and its cause remains unknown, per the 09-21 observation
concern. Nothing here should be cited as retiring that issue.

## Evidence

- RED on unchanged runtime: `tests/test_node_timeout_queue_cancellation.py`
  `test_queued_work_never_starts_once_its_node_is_terminal` failed; the
  companion settlement guard passed, establishing it as a real baseline rather
  than a test written to the fix.
- GREEN after: 37 passed across
  `test_node_timeout_queue_cancellation.py`, `test_node_timeout.py`,
  `test_graph_compiler_empty_response.py`.
- Windows only. Not run under `scripts/linux_oracle.py`; the change touches no
  sandbox, filesystem or process-limit behaviour, but CI remains authoritative.
- No independent cross-family review: agent dispatch was prohibited for this
  lane. Root supplies the opposite-family review.

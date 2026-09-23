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

**AGREE on both components.** One was initially split off as wrong-sized; that
objection was mine, it did not survive re-verification, and it is withdrawn below.

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

### DISAGREE_CONCERN — withdrawn on re-verification; now AGREE and implemented

Originally filed as "real defect, wrong-sized as a same-lane change." **That
blocker was my own and it did not survive re-checking**, so it is withdrawn.
Two premises behind it were wrong: the submitted callables are defined *inside*
`_fn`, so the queue wait is measurable on the worker without touching
`_run_with_timeout`'s contract; and `ModelConfig` is `@dataclass(frozen=True)`,
so the race I feared is impossible by construction and `dataclasses.replace`
gives a per-invocation config for free. Implemented as `_deadline_cfg()`.

The original reasoning, kept for the record: The provider cap is
`ModelConfig(timeout=..., absolute_cap_s=timeout_s)` built **once per node
closure** at `graph_compiler.py:1192`, outside `_fn`. A call that starts partway
through its budget still receives the node's *full* timeout as its cap, so it
outlives the node deadline by the queue wait. But correcting it means computing
the deadline per invocation inside the worker: mutating the shared `_node_cfg`
in place would be a cross-invocation race under parallel fan-out, since one
compiled closure serves concurrent invocations. That is a different change with
its own review surface, and it is not needed to close the abandonment path —
once queued work is cancelled, the residual overrun is bounded by the queue wait
on work that genuinely started. That reasoning held only for the *mutation* shape;
a fresh per-invocation config sidesteps it entirely.

One real bug surfaced while implementing it: a fixed 1s floor on the remaining
budget would RAISE a sub-second node's timeout (a 0.5s node handed a 1.0s cap)
— "never just raise all timeouts" violated under cover of lowering one.

**That first correction was itself wrong, and the lead review caught it** (see
the round-2 section below). `min(1.0, timeout_s)` stops the cap exceeding the
node's timeout but re-grants the queue wait for every node at or under a
second: a 0.9s node that queued 0.4s was handed 0.9s again. There is now no
floor at all beyond strict positivity.

### AGREE — the stated prohibitions

No auto-replay of unknown effects, no treating a requested model as reported
identity, no blanket timeout raise. The landed change does none of these: it
cancels queued work and hands a started call a cap that is only ever SMALLER
than the node's own declared timeout, never larger — the sub-second floor bug
above was exactly the case where that could have inverted, and it is pinned.

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
- GREEN after: 40 passed across
  `test_node_timeout_queue_cancellation.py`, `test_node_timeout.py`,
  `test_graph_compiler_empty_response.py`.
- A one-off failure of
  `test_runner_emits_node_timeout_event_and_marks_run_failed` during this lane
  was chased to a PRE-EXISTING boundary flake, not a regression: the unchanged
  tree measured 5.06s/4.85s against its own `wait_for(timeout=5.0)`, the changed
  tree 4.70s/4.41s, and both pass 3/3. Filed as
  `docs/concerns/2026-09-23-node-timeout-runner-test-sits-on-its-own-deadline.md`.
- Windows only. Not run under `scripts/linux_oracle.py`; the change touches no
  sandbox, filesystem or process-limit behaviour, but CI remains authoritative.
- No independent cross-family review: agent dispatch was prohibited for this
  lane. Root supplies the opposite-family review.

---

## Round 2 — corrections from the independent lead review

Receipt: [`2026-09-23-queued-deadline-lead-review.md`](2026-09-23-queued-deadline-lead-review.md)
(Codex lead, reviewing head `5e5678de` against `1f121719`; verdict **ADAPT**).
Two concrete contract holes, both accepted and corrected here. No broadening:
the historical intermittent-failure cause and the router internals stay out of
scope, exactly as the receipt asks.

### Finding 1 — remaining-budget floor: **AGREE**

`min(_MIN_REMAINING_PROVIDER_CAP_S, timeout_s)` is not a safe floor, it is the
full node timeout for every node at or under a second. A 0.5s node that queued
0.4s got 0.5s, not the remaining 0.1s — the queue wait handed straight back.
The reviewer's premise checks out: `ModelConfig.stream_timeout_profile()` runs
every knob through `_pos()`, which accepts any finite positive float, so the
absolute cap needs no 1s floor.

The floor is gone. `_MIN_POSITIVE_PROVIDER_CAP_S = 0.001` replaces it and is an
epsilon, not a budget — `_pos()` *discards* a non-positive cap in favour of the
600s default, so zero would invert the correction far worse than the old floor
did. The legacy integer-seconds `timeout` scalar keeps `max(1, int(remaining))`,
now documented for what it is: a representation limit of a field that cannot
express a sub-second budget, identical to the floor the per-node config already
carries, never raised above it. The streaming path reads `absolute_cap_s`.

The old test asserted only `cap <= original`, which the reviewer is right to
call insufficient — it passes on a cap of 29.999s for a 30s node. Both cap
tests now pin the cap from *both* sides against the actual measured wait.

### Finding 2 — worker pickup after the deadline: **AGREE**

`future.cancel()` returns `False` once a worker has the item, and nothing
orders the caller's post-deadline `cancel()` against that pickup. The previous
module comment acknowledged the losing case and then let the work run with a
fresh positive provider budget — so the spec's no-new-work-after-the-deadline
claim rested on scheduling luck.

`_run_with_timeout` now wraps every submitted callable in a worker-entry
deadline check: past the deadline, it raises `_DeadlineExpiredBeforeStart`
(a `NodeTimeoutError` subclass, so no handler anywhere needs to change) instead
of invoking the call. Budget remaining → the call starts normally. The check
precedes the first line of the wrapped call, so nothing already started is
touched and nothing is replayed. It sits in the shared helper as the reviewer
suggested, so it covers every path routed through the shared pool.

Honest scope on the "queued source_code" half: `source_code` nodes do **not**
route through `_run_with_timeout` today — they carry their own sandbox-runner
timeout — so they are covered the moment they do, and not before. The spec now
says exactly that rather than implying the guarantee is already theirs.

### Flake guidance — accepted

The cap tests no longer sleep-and-assume the caller enqueued. `_EnqueueSignallingPool`
signals the actual `submit()`, the wait is timed from that signal, and the
assertions use two hard bounds derived from measurements (`lower_wait` from the
interval the worker was provably still held after enqueue; `upper_wait` from a
timestamp taken inside the provider call) rather than a nominal sleep duration.
The race test uses a controlled executor stub whose `cancel()` always loses and
whose callable the test itself invokes, so the pickup happens after the
deadline by construction, never by luck.

### Round-2 evidence

Head under test: `5e5678de` + this commit.

- RED on the unchanged runtime (`git show HEAD:tinyassets/graph_compiler.py`
  swapped in, tests unchanged): 2 failed, 5 passed —
  `test_remaining_budget_has_no_floor_that_regrants_the_queue_wait` and
  `test_work_reaching_a_worker_after_the_deadline_is_never_started`. One test
  per finding, each red for its own finding's reason.
- GREEN after: `tests/test_node_timeout_queue_cancellation.py` 7 passed.
- Regression set: `test_node_timeout_queue_cancellation.py`,
  `test_node_timeout.py`, `test_graph_compiler_empty_response.py`.
- `python -m ruff check` clean on both changed files;
  `packaging/claude-plugin/build_plugin.py` re-run for mirror parity.
- Windows only, as in round 1. No sandbox/filesystem/process-limit surface is
  touched, so the Linux oracle is not indicated; CI stays authoritative.
- Still no cross-family review from this lane — dispatch remains prohibited
  here. Root supplies the independent final review and tests.

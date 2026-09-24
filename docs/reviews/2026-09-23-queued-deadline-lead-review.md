# Independent queued-deadline review

September23,2026 UTC. Codex lead reviewed Claude head5e5678de in
wf-reliability-next against1f121719. **ADAPT**, narrowly, before release.

AGREE: cancel a not-yet-started Future; preserve already-started work settlement;
immutable per-invocation ModelConfig; no speculative claim about historical idle
failures. Changes are provider-neutral and bounded; no new public/storage shape.

Two concrete contract holes in the submitted correction:

1. graph_compiler._deadline_cfg floors remaining cap at min(1,node timeout).
   For a0.5s node after0.4s queueing this grants0.5s, not the remaining0.1s.
   The new test only asserts cap<=original, so misses the stated requirement.
   ModelConfig.stream_timeout_profile accepts every finite positive float, so
   the absolute cap needs no1s floor. Keep any legacy scalar compatibility
   floor separate and describe it honestly. Tighten a deterministic test to
   remaining budget, including the sub-second case.
2. future.cancel() may lose to worker pickup after the admitted deadline. The
   worker currently launches the provider anyway with the same positive floor,
   explicitly acknowledged by the new module comment. Cancellation alone cannot
   prove the spec's no-new-work-after-deadline claim. Add a worker-entry deadline
   check before invoking unstarted work, ideally shared in _run_with_timeout so
   queued source_code is also covered. Positive remaining work may begin; an
   already-expired call must not be given a fresh provider budget. Do not kill
   work already started and do not add automatic replay. Prove the race with a
   controlled executor/clock, not scheduling luck.

Tests that sleep and assume the caller has enqueued can flake under load.
Use enqueue/worker events or a controlled clock for these targeted regressions.
Source-code runtime budget propagation and router-internal retries/admission
are not silently claimed fixed by this queue-only patch. Align spec scope with
actual guarantees. No request for an unrelated hardening or redesign pass.

---
severity: note
title: Workflow capacity cooldown is lost on non-exhaustion exits
filed: '2026-09-30'
summary: A withheld source cooldown is settled only when the entire node order exhausts, not on later authorization failure, cancellation, or success on another source.
---

Review of run-capacity-fallthrough at b3a37d37 (initially c7f2293b plus staged changes).

`tinyassets/providers/router.py:1377` withholds cooldown for workflow callers
owning siblings. `tinyassets/foreground_run_provider.py:1278` settles it only
when `next_candidate` returns None. A first unknown-scope 429 records a boundary,
then cancellation detected by `_authorize_attempt` (`:944`) raises before the
second invocation. The loop has no finally; `close` (`:1399`) only releases the
claim. The source remains hot for subsequent runs. A held second response
(`:1304`) or success on another accepted source (`:1326`) also loses the debt.
Boundaries are node-local; the next node does not inherit them. A cooling failure
is logged and discarded (`:1253`), although the loop does continue to other sources.

Verified with an in-process probe invoking the real `_call_captured_prompt` and
real capacity-boundary decoder: first diagnostic was a side-effect-free,
unknown-scope 429, second call raised ProviderAuthorityHeldError; cooling was
called zero times. Existing parity suite: 22 passed. No runtime edits by reviewer.

Track withheld cooldowns through all exits, preserving a source that actually
recovers while settling abandoned sources. Cover cancellation and switching to a
different accepted source, including a following node in the same run.

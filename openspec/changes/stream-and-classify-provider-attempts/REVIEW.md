# Slice 1 review — CODEX REJECT (2026-08-19), rework required

Codex confirmed the streaming reader architecture is SOUND (OS-pipe probe: split
JSON, blank lines, unterminated final line, 1 MiB concurrent stderr, thinking,
terminal result all handled; malformed → protocol_error; thinking excluded from
relay; result canonical). But REJECTED on real-schema + fail-closed + route-
coverage blockers. Do NOT land until these are fixed and re-reviewed.

## BLOCKERS (must fix)

### A. Real Claude 2.1.236 `system/api_retry` schema (Critical)
The CLI emits `error` (string `"rate_limit"`/`"overloaded"`), `error_status`
(429/529), `retry_delay_ms`. `_extract_api_retry` expects `error_type`/`category`
+ `retry_after*` → returns `{failure_class:None}` for both → a real exhausted retry
becomes generic ProviderError or `provider_idle_timeout`, retry-after lost. FIX
`_extract_api_retry` to the REAL fields. ALSO handle top-level `rate_limit_event`
(empirical trace: `rate_limit_info.status`/`resetsAt`; status!="allowed" => limited).

### B. Idle watchdog vs a known retry wait (Critical-adjacent)
`_raise_timeout` doesn't consult the last typed retry. A 60s provider retry wait is
relabeled `provider_idle_timeout` at 30s. FIX: when an api_retry with `retry_delay_ms`
is in flight, extend the idle budget to cover it (retry wait ≠ hang), or classify the
stall as rate_limited with that retry_after.

### C. Missing heartbeat/tool-progress liveness (Required)
`_normalize_stream_obj` ignores top-level `tool_progress` and `system/tool_heartbeat`
(and — from the trace — `system/thinking_tokens`, `thinking_delta`, hooks, status). A
tool/reasoning active >30s with only heartbeats is killed. FIX: reset the watchdog on
ANY recognized protocol event (heartbeat kind for all non-relayed events); only RELAY
text/result. A hung process emits nothing, so this still catches real hangs.

### D. Absolute-cap vs "progress past 300s" spec conflict (Required — reconcile)
DEFAULT_ABSOLUTE_CAP_S=120 kills a turn streaming a text delta every 20s for 10 min,
contradicting the provider-routing scenario ("a long but progressing turn is not
failed for elapsed time"). FIX: raise the absolute cap to a generous safety net
(e.g. 600s) so a genuinely progressing turn survives well past 300s; idle (30s) stays
the primary fast-hang control. Update tests to actually prove past-300s progress.

### E. Cancellation / unexpected-exit leaks the subprocess (Required)
`_read_stream` `finally` only cancels `stdin_task`; it does NOT kill/reap `proc` nor
cancel/await `stderr_task` on caller-cancellation or an unexpected reader exception
(probe: `killed_after_caller_cancel: False`). FIX: `finally` must `_terminate(proc)`
+ cancel & await both tasks on every exit path. Also await `stdin_task.cancel()`.

### F. Policy-routing path preserves OLD cooldown (Required)
`call_with_policy` (router.py:1075) catches rate-limit/overload as generic unavailable
and idle/deadline as ProviderTimeoutError with fixed cooldowns (1081-1092). The new
failure-class cooldown semantics must apply on this path too. Also `ProviderAuthorityHeldError`
must be preserved (not swallowed as generic ProviderError) on the policy path.

### G. Ingress still sleeps on the reply critical path (Required)
`converse` (universe_intelligence.py:818) calls `extract_learning` → its `call_provider`
(:435) omits `retry_on_exhaustion=False`, so `call.py:307` runs 2/4s tenacity waits
BEFORE the visible reply. FIX: pass `retry_on_exhaustion=False` there, and/or move
learning extraction OFF the reply critical path (per the design memo).

### H. Fail-closed: failure notice recorded as a universe message (Critical)
`deliver_app_event` (app_ingress.py:331) `_record_universe(notice, receipt)` records
speaker "universe" with no terminal provider result — violates fail-closed ("no final
conversation record until a terminal result"). FIX: do NOT record a failure notice as
a universe utterance (record it as a system/error note, or not at all).

### I. Honest notice details (Required)
`_failure_notice` renders `provider_overloaded` as "rate-limited" (:390) — give it its
own wording. Bare/unclassified exhaustion still uses substring capacity wording (:408) —
route it through failure_class.

### J. Classify EOF-without-terminal-result (Required)
`_read_stream` (:674) raises unclassified `ProviderError` on truncated stream; classify
it (e.g. `provider_protocol_error` truncated). The test currently BLESSES the unclassified
behavior — fix the test too.

### K. Telemetry on failures (Required)
side_effect_state / terminal / ttft / last-progress-age / exit are only on the success
ProviderResponse; attach them to the raised exceptions / ProviderAttemptDiagnostic so the
router + notice can reason about them.

### L. Sync-wrapper timeout vs absolute cap (Required)
`call_sync` times out at `config.timeout + 30`; if `config.timeout` is set below the
stream absolute cap, the request returns failure while the subprocess keeps running
(possible effects). Reconcile: sync cap ≥ absolute cap + margin, and kill the subprocess
on sync timeout.

## TEST ADEQUACY (the change-#1 lesson — do NOT fabricate schemas)
Fixtures MUST use the REAL Claude 2.1.236 schemas Codex documented (api_retry:
error/error_status/retry_delay_ms; rate_limit_event: rate_limit_info.status/resetsAt),
NOT payloads shaped to match the implementation. Add: retry-delay > idle-timeout (not
killed as idle); heartbeat/tool-progress + thinking-only stretch kept alive; caller-
cancellation kills the subprocess; full converse→extract_learning no-sleep; failure
notice NOT recorded as a completed universe message; policy-router cooldown by class;
past-300s progressing survives; blank/split/stderr in the unit suite; real 429/529
api_retry → provider_rate_limited/overloaded with retry_after. Reference trace:
scratchpad/claude_stream_trace_sample.jsonl.

## Out of scope for Slice 1 (note, don't fix here)
- `_app_events` synchronous ingress serialization (event-loop head-of-line blocking) is
  Slice 2 (durable admission + bounded workers). Do not make it worse; the real fix is
  Slice 2.

Full verdict: scratchpad/codex_review_slice1_verdict.txt.

## Round 2/3 resolution (Codex re-reviews #1 + #2 → fixed by hand)

Codex re-review #1 confirmed A,B,C,E,G,H,J,L core FIXED; re-review #2 confirmed
B,C,F(narrow),G,H,I,J FIXED. All remaining CORRECTNESS blockers are now resolved
(hand-fixed + tested, 202 passing):
- **F fallback regression (re-review #2, self-inflicted):** the first F fix
  (`if tried>0: raise`) over-broadly suppressed genuine cross-provider fallback.
  Corrected: suppress the fall-through ONLY when a side effect was possible
  (`side_effect_state in possible|committed`); clean failures fall through so
  Codex fallback still fires. Tests: `test_policy_idle_after_a_tool_started_does_not_double_execute`
  + `test_policy_clean_failure_still_falls_back_to_the_role_chain` (real classifier).
- **A (typed retry masked by exit-1):** the typed api_retry/rate_limit classification
  now runs BEFORE the exit-1/crash heuristics. Tests: `test_real_429/529_then_quick_exit_1_*`.
- **E (unbounded reap):** the finally now bounds `proc.wait()` reap with a 5s
  `wait_for` so a wedged process can't hang cancellation; CancelledError still propagates.
- **I:** substring→capacity removed; unclassified exhaustion → honest generic; the
  two gate-gaming tests corrected; the task blessing reverted.
- Misleading `test_fallback_fires_when_preferred_exhausted` renamed to reflect it is
  a graph-propagation test (real router fallback now covered in the stream test file).

## ACCEPTED hardening residuals (NOT correctness; founder land-decision)
- **K (observability):** `ProviderAttemptDiagnostic` does not carry terminal/TTFT/
  progress-age/exit; those are lost from the `call()` aggregate (call_with_policy
  attaches the full telemetry). The load-bearing fields for the honest user notice
  (failure_class + retry_after) ARE on the aggregate. Remaining loss is operator
  observability (`get_run.error_detail`), not user-facing behavior.
- **L (wedged-loop backstop):** the INNER `asyncio.wait_for` cancels the coroutine
  and kills the subprocess on the normal timeout (tested). The OUTER `future.result`
  timeout is a backstop only for a wedged event loop; it does not force-cancel the
  thread. Rare edge; the subprocess-kill path is covered for the normal case.
- **split-JSON pipe test:** `asyncio.StreamReader.readline()` reassembles partial
  OS reads internally, so a byte-split test at the reader boundary is largely moot;
  blank/unterminated/concurrent-stderr framing IS covered.

These three are tracked as follow-up hardening; the founder's actual capacity-mislabel
bug and all its correctness paths are fixed + verified.

# Tasks — raise-served-concurrency-budget

## 1. Budget ceiling + per-call decoupling
- [x] 1.0 CORE FIX: decouple per-call output from the aggregate ceiling in
      `tinyassets/providers/router.py` — when `cfg.max_tokens is None` reserve a
      bounded `_SERVED_PER_CALL_MAX_TOKENS` (65_536, capped to the ceiling), not
      the whole binding ceiling (Codex 2026-08-22 critical: the real prod-path
      brick).
- [x] 1.1 Raise `_MAX_TOKENS` (32_768 → 4_000_000) and `_MAX_COST_MICROUNITS`
      (10_000_000 → 400_000_000) in `tinyassets/provider_serving_binding.py`,
      with a comment stating it is a concurrency runaway guard, not a spend cap.
- [x] 1.2 Mirror the ceiling change into the packaging runtime.

## 2. Regression proof
- [x] 2.0 Router-level test: production `max_tokens=None` reserves the bounded
      per-call amount, NOT the ceiling
      (`test_served_none_max_tokens_reserves_bounded_per_call_not_whole_ceiling`).
- [x] 2.1 Test: many concurrent in-flight reservations for one binding all admit
      (`test_many_concurrent_reservations_share_one_binding_without_bricking`).
- [x] 2.2 Oracle test: the prior 32_768 ceiling bricked the second concurrent
      turn (`test_prior_32k_cap_bricked_the_second_concurrent_turn`).
- [x] 2.3 Linux/CI two-thread test: two concurrent `max_tokens=None` router
      calls both reach the provider (`test_two_concurrent_served_none_max_tokens_calls_both_reach_provider`;
      skipped on Windows where msvcrt serializes readers).
- [x] 2.4 Full `tests/test_provider_served_router.py` green + ruff clean.

## 3. Review + rollout
- [ ] 3.1 Opposite-provider (Codex) shape review of the ceiling change.
- [ ] 3.2 Merge + deploy; confirm prod `release_state.git_sha` contains it.
- [ ] 3.3 Re-bind the founder binding so it adopts the new ceiling.
- [ ] 3.4 Live proof: concurrent turns across ≥2 surfaces succeed without
      "budget exhausted".

## Follow-ups (post-live hardening — prose, not tracked tasks)

Deferred to later hardening, out of scope here: (a) auto-heal existing bindings
to the current ceiling on deploy so no manual re-bind is needed (must be
evaluated against the Codex-gated reserve logic before touching it); (b) divide
the byte-based `estimated_input_tokens` proxy by a bytes/token factor so
reservations are not ~4× inflated; (c) if per-user host capacity ever needs a
hard bound, add explicit bounded host-capacity admission with load proof rather
than relying on the aggregate ceiling.

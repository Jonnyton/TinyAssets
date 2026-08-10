# Tasks — wire user-provided engine runtimes

## Slice 3a — self_hosted_endpoint runtime (no money; safe first slice)
- [x] 1.1 Add `SelfHostedProvider` (OpenAI-compatible chat client) that targets a
      per-call `engine_endpoint`; name `self-hosted`. No platform credential.
- [x] 1.2 Engine-source resolution hook in the router: when the universe config's
      `engine_source == "self_hosted_endpoint"` and `engine_endpoint` is set,
      route the call to `self-hosted` bound to that endpoint, bypassing the
      fallback chain (single provider, NO platform fallback). Applied in
      `call()`, `call_with_policy()`, and `call_judge_ensemble()` so no entry
      point leaks to the platform chain.
- [x] 1.3 Fail-closed: unset/unreachable endpoint raises a clear error; never
      falls through to the platform chain.
- [x] 1.4 Tests: self-host routes to the endpoint; fail-closed on unset/unreachable;
      other engine sources unaffected; mirror parity rebuilt (build_plugin.py).

## Slice 3b — market_rented runtime (money-critical; design + Codex review FIRST)
- [ ] 2.1 `SpendLedger` (durable, per-universe): record each metered call's cost;
      `remaining(universe, cap)`; atomic reserve-then-commit so concurrent calls
      cannot exceed the cap.
- [ ] 2.2 `OpenRouterBrokerProvider`: platform OpenRouter key (credential-blind
      path), per-universe `market_model`; before each call, reserve against the
      ledger under the universe's `spending_cap`; fail closed at/over the cap with
      a clear "raise your ceiling" signal; commit actual cost after the call.
- [ ] 2.3 Engine-source resolution: `engine_source == "market_rented"` routes to
      the broker with the universe's model + cap.
- [ ] 2.4 Tests: spend accumulates; call at/over cap fails closed (no spend);
      concurrent calls cannot exceed cap (reserve atomicity); ledger durable.
- [ ] 2.5 Codex cross-family security review BEFORE merge (money + fail-closed).

## Cross-cutting
- [ ] 3.1 Delta-spec `provider-routing`: engine-source-driven runtime routing +
      ceiling enforcement requirements + scenarios.
- [ ] 3.2 `ui-test` rendered chatbot proof: set self-host / market engine, run a
      turn, confirm it executes on the chosen runtime (post-deploy).

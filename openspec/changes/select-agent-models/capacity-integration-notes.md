# Capacity integration evidence, September10 2026

Next implementation within existing tasks2.2/2.3, not a new proposal or as-built
claim. Current integrated runtime ffbc918f stops safely; candidate continuation is
still unwired. An opposite-family review must check these external-source-derived
classification choices before implementation, per AGENTS.md.

Official sources read September10 05:56UTC:

- https://openrouter.ai/docs/api_reference/limits documents account/key credit
  limits and distinguishes platform429 from upstream429; status alone cannot
  prove model-local exhaustion. Platform limit responses carry X-RateLimit fields.
- https://openrouter.ai/docs/api_reference/errors-and-debugging documents typed
  error.metadata.error_type, Retry-After, and errors inside successful HTTP bodies
  after processing began. Empty output can still incur charge.

Implications to verify, not yet implemented: normalize at the protocol boundary,
not by model names or arbitrary error-message substrings. Preserve unknown scope
conservatively; a second connection/key is not independent account capacity.
Carry typed evidence through router aggregation without cooling every model for
a proven model-only failure. Do not treat a200 error body as pre-dispatch zero
usage, or moderation/auth/schema errors as permission to cycle models. Honor
retry hints and accepted free-only ceilings without raising credit limits or
requesting broader authority automatically.

Existing implementation seams: model_policy.Exhaustion/order_models already
orders scoped advisory candidates; provider diagnostics currently retains only
failure_class/retry_after, and api_key_http_provider currently maps bare429/5xx
to provider-wide exceptions. universe_intelligence.converse currently constructs
UniverseContext without model_selection, so saved/current/default consumption
still needs authenticated ingress integration. Do not enable a picker merely
because its preferences can be stored.

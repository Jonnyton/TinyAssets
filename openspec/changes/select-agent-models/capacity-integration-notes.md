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

## Concrete next runtime contract for review

Add a private immutable normalized capacity signal: scope model/account/unknown,
sanitized failure kind and optional finite nonnegative retry delay. A protocol
boundary may supply it only for an admitted selected HTTP agent inference; legacy
text/CLI classification remains unchanged. No raw message substring, remote model
name or caller config grants scope. The discovery protocol contract owns decoding.

For OpenRouter's documented status semantics:402 is account/key-credit exhaustion;
503 (no available provider satisfying this model's routing requirements) is model
unavailability;429 is unknown/shared unless documented structured evidence proves
narrower scope. Do not infer model-only from an upstream provider name/code alone.
Unknown scope conservatively excludes same-provider siblings in the advisory
kernel; absence of authenticated account identity never proves an independent key.
Authentication, moderation, malformed input, generic500/502, unknown transport and
partial successful bodies remain holds, not capacity fallbacks in this slice.

Represent this exception as ProviderError, not ProviderUnavailableError, so a
post-dispatch failure keeps conservative reservation settlement rather than being
reported as zero usage. Thread its typed scope through ProviderAttemptDiagnostic
and AllProvidersExhaustedError. A model-only signal must not apply the existing
whole-provider cooldown; account/unknown may retain that cooldown. Honor bounded
Retry-After; invalid/missing hints stay unknown, not invented timestamps.

The runner then consumes a finite advisory plan of immutable ModelRefs prepared
from existing order_models, never a grant. Before every candidate it re-enters
the current selected serving-authority path. After a recorded inference-only
capacity failure it may call begin_round(after_failed_inference=True), preserving
completed tool history and all previous launch/accounting rows. No retry of a
started/ambiguous tool, no implicit return to the original prompt, no cycling to
an exhausted account. Legacy pins and explicit empty fallback tails remain held.
Tests must exercise real composition: model capacity after a known result,
account/unknown exclusion, revocation before replacement, and free-only price
ceilings on every actual POST. Saved/current/public ingress remains the next
connection to this same plan, not a parallel authority or preference store.

## Why

Provider routing already returns model evidence internally, but the shared
`call_provider(...)` bridge discards it and exposes only text. The universe
reply and its separate learning-extraction call are therefore unauditable, and
the process-global `_last_provider` accessor cannot safely attribute
overlapping calls.

## What Changes

- Add an immutable, result-local provider-attempt receipt for each provider
  bridge result, including reply, fallback, exhaustion, and forced-mock paths.
- Keep `call_provider(...) -> str` source and return compatibility; add an
  explicit result-returning path for callers that need the text and its receipt.
- Distinguish the reply and learning-extraction phases and require both
  `converse` writer calls to retain their own receipt.
- Report provider, model, model family, credential kind, and authority class
  without credential values, auth-home paths, tokens, keys, or raw error text.
- Preserve bounded fallback and exhaustion evidence on the same returned or
  raised call result, including each skipped or failed attempt in routing order.
- Leave any durable or public receipt sink gated on an explicit owner,
  authorization policy, retention policy, and schema; this change does not
  invent one.
- Declare #1606 / R2-1a a blocker for applying the change so receipt authority
  semantics are based on the settled fail-closed routing boundary.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-routing`: Extend the provider call bridge contract with
  concurrency-safe, result-local attempt receipts while preserving its legacy
  string-returning API.

## Impact

The future implementation is expected to affect the provider call bridge,
provider response/diagnostic types, and the two writer-call sites in universe
intelligence, with focused compatibility, concurrency, fallback, exhaustion,
and redaction tests. This proposal itself is spec-only: it does not modify
runtime code, tests, canonical specs, credential-vault behavior, persistence,
or public MCP responses.

## Context

`ProviderRouter.call()` already returns an immutable `ProviderResponse` with
text, provider, model, family, latency, and degraded state. The synchronous
bridge in `tinyassets/providers/call.py` narrows that envelope to `str` and
updates `_last_provider`, so a caller cannot bind the model evidence to the
specific result it received. `_last_provider` is process-global and can be
overwritten by another call before a consumer reads it.

`tinyassets.universe_intelligence.converse()` makes two logically distinct
writer calls: one produces the founder-facing reply and one extracts proposed
learning. Their evidence must not be conflated. Provider routing also retries
full-chain exhaustion and may return an explicit fallback or forced-mock
response, so a receipt that describes only the final provider would hide
material routing behavior.

This change is constrained by the PLAN Providers requirement to preserve
fallback evidence and fail loudly, the cross-cutting separation of generator
and learning channels, and the state/artifact rule that durable evidence needs
an explicit owner. #1606 / R2-1a is an apply blocker because credential
authority cannot be classified reliably until the universe routing boundary is
settled.

## Goals / Non-Goals

**Goals:**

- Bind provider-attempt evidence immutably to the exact result or error from
  one bridge invocation.
- Preserve `call_provider(...) -> str` for every existing caller.
- Give result-aware callers a typed result containing text and one receipt.
- Keep reply and learning-extraction receipts separate under concurrent calls.
- Define provider, model, family, credential-kind, and authority-class
  semantics without exposing secret material.
- Represent success, retry/fallback, forced-mock, missing-router, and exhausted
  outcomes without pretending synthetic text came from a provider.

**Non-Goals:**

- Implement runtime behavior, tests, or canonical-spec sync in this lane.
- Change provider selection, retry count, fallback policy, or credential-vault
  behavior.
- Remove or repair the legacy `_last_provider` accessor for unrelated callers.
- Persist, log, publish, or add receipts to an MCP response.
- Treat a receipt as proof of output quality, authorization, billing, or
  credential validity.

## Decisions

### 1. Make a result-returning primitive the core; keep the string API as a wrapper

The implementation will add a result-returning bridge operation whose immutable
result contains `text` and a `ProviderAttemptReceipt`. Existing
`call_provider(...)` will delegate to it and return only `.text`, preserving its
signature, return type, fallback strings, and exception behavior.

The receipt will be assembled from the `ProviderResponse` returned for that
same invocation. No receipt field may be populated by reading
`_last_provider`, another module-global "last call" slot, or a later status
query. The legacy accessor may continue to be updated for existing consumers,
but it is explicitly non-authoritative for receipts.

Alternative considered: change `call_provider` to return an envelope. Rejected
because it would break a wide internal call surface for no receipt benefit.
Alternative considered: read `_last_provider` after the string call. Rejected
because interleaving makes the attribution racy by construction.

### 2. Use one immutable call receipt with ordered immutable attempt entries

Each bridge invocation will allocate one opaque `call_id`, record the routing
`role` and caller-supplied `phase`, and produce an immutable receipt with:

- `outcome`: `provider_success`, `explicit_fallback`, `forced_mock`,
  `exhausted`, or `error`;
- `route_condition`: `none`, `chain_exhausted`, `router_missing`, or
  `provider_error`, so the reason routing stopped remains distinct from how
  returned text was produced;
- final `provider`, `model`, and `family`, copied from the successful
  `ProviderResponse`, or absent when no provider produced the returned text;
- final `credential_kind` and `authority_class`;
- `degraded` and `latency_ms` when a provider response supplies them; and
- ordered attempt entries across every full-chain retry wave, each with its
  retry ordinal, provider name, `succeeded` / `failed` / `skipped` status,
  stable reason class, and the credential/authority classification known at
  that attempt boundary.

The attempt list records routing decisions, not prompts, outputs, raw exception
messages, environment values, or credential handles. An attempt skipped before
credential resolution is `unknown` rather than guessed from its provider name.

On final `AllProvidersExhaustedError`, the same immutable receipt is attached to
the raised error. Other existing exception types remain unchanged; if the
bridge observed an attempt before raising, it attaches the receipt without
wrapping or replacing the exception.

Alternative considered: store only the winning provider. Rejected because it
hides fallback and exhaustion. Alternative considered: reuse the router's
mutable diagnostic list directly. Rejected because the bridge must aggregate
multiple retry waves and enforce redaction at its boundary.

### 3. Separate credential mechanism from authority origin

`credential_kind` answers how the provider authenticated:

- `llm_subscription`: subscription CLI/session material;
- `llm_api_key`: API-key material;
- `local`: no remote credential because the provider executes locally;
- `none`: no provider authenticated, as on synthetic or pre-invocation paths;
- `unknown`: a provider ran but the mechanism could not be proven.

`authority_class` answers whose authority permitted the call:

- `universe`: material resolved from the explicitly selected universe vault or
  its materialized auth home;
- `host`: host process material used only for a host-local call with no
  resolved universe;
- `local`: a local provider requiring no external credential;
- `none`: no provider invocation;
- `unknown`: an invocation whose authority origin could not be proven.

The provider execution boundary must classify these values from the auth
resolution used for that exact call, then thread them through the same
`ProviderResponse`; the receipt must not infer them from provider names or
ambient environment after completion. A successful remote universe-scoped call
must never report `host`. Applying this rule waits for #1606 / R2-1a to settle
the fail-closed routing boundary.

No receipt or attempt may include tokens, keys, base64 material, cookies,
authorization headers, environment values, credential record IDs, auth-home
paths, prompts, completions, or raw exception text.

### 4. Keep reply and learning phases independently attributable

The result-aware bridge accepts a bounded phase value:
`reply`, `learning`, or `unspecified`. Generic callers default to
`unspecified`; `converse` must use `reply` for the founder-facing generation and
`learning` for extraction.

Universe intelligence will gain a result-aware internal path that returns the
reply plus its ordered per-phase receipts. Its existing `converse(...) -> str`
surface remains a wrapper. Learning failure remains non-fatal to the reply, but
its failure/exhaustion receipt cannot overwrite or replace the reply receipt.
Concurrent turns must retain distinct call IDs and result-owned receipt
objects, regardless of completion order.

Alternative considered: one turn-level receipt with a mutable "last phase".
Rejected because the learning call would overwrite the evidence for the text
shown to the founder.

### 5. Synthetic and exhausted outcomes remain explicit

An explicit fallback or forced mock returns its configured text with no winning
provider/model/family and with `credential_kind=none` and
`authority_class=none`. Any real attempts made before an explicit fallback
remain in the receipt. `outcome=explicit_fallback` may therefore pair with
`route_condition=chain_exhausted`, `provider_error`, or `router_missing`; a
forced mock pairs with `route_condition=none`. Exhaustion without fallback
still raises rather than producing text, and the error carries the ordered
receipt. `route_condition=router_missing` is distinct from
`route_condition=chain_exhausted`.

This preserves current fallback behavior while preventing synthetic text from
being mislabeled as provider output.

### 6. No durable, log, or public sink in this change

The receipt exists only on the in-memory result or raised error. The
implementation must not write it to logs, a database, run receipts, wiki pages,
conversation history, or an MCP response.

A follow-up OpenSpec change is required before any sink is added. That change
must name the owning capability and define authorization/visibility,
universe/run/turn correlation, schema versioning, retention/deletion, size and
cardinality limits, redaction, failure semantics, and whether the sink is
operator-only or user-visible. Existing generic run receipts are not selected
implicitly because `converse` is not guaranteed to own a run ID and their
current ACL/retention limitations are a separate contract.

### 7. Application waits for the routing-authority blocker

The spec artifacts may be reviewed and landed independently. No runtime
implementation task begins until #1606 / R2-1a has landed or an explicitly
named successor has settled:

- fail-closed universe credential isolation;
- `allowed_providers` behavior for the selected engine; and
- the call-local source of credential-kind and authority-class evidence.

After that blocker clears, the implementer rebases, rereads the canonical
provider-routing and credential-vault specs, and adapts this delta if their
semantics changed.

## Risks / Trade-offs

- **Receipt enums drift from auth resolution** → define them at the provider
  boundary, validate exhaustively, and block apply until #1606/R2-1a settles.
- **Compatibility wrapper hides evidence from legacy callers** → keep it for
  stability and migrate only the two audited universe-intelligence calls to the
  result-aware path.
- **Aggregating retry waves adds memory** → keep the existing three-wave bound,
  store only redacted structured fields, and never capture prompt/output text.
- **Attaching evidence to arbitrary exceptions can fail** → verify the chosen
  exception-local carrier without changing existing exception identity or
  masking the original error.
- **A later sink creates privacy or ACL leaks** → require a separate reviewed
  OpenSpec change; this change forbids implicit persistence and publication.
- **`unknown` can be mistaken for safe authority** → specify it as absence of
  proof, never as authorization or a successful fail-closed check.

## Migration Plan

1. Wait for #1606 / R2-1a or its declared successor to settle and release the
   provider-routing authority boundary.
2. Rebase and reconcile this delta with the then-current canonical
   `provider-routing` and `credential-vault` specs.
3. Add result/receipt types and redacted attempt aggregation while retaining
   the existing string wrapper.
4. Migrate only the reply and learning call sites to the result-aware path.
5. Prove legacy string/error compatibility, interleaving isolation, phase
   separation, fallback/exhaustion evidence, and secret redaction.
6. Sync the provider-routing delta only after implementation and review.

Rollback removes the result-aware call sites and types while leaving
`call_provider(...) -> str` unchanged. No persisted-data rollback is needed
because this change defines no sink.

## Open Questions

- Which durable or public artifact should eventually own these receipts, if
  any? This is deliberately unresolved and gated to a separate OpenSpec change;
  it does not block the result-local contract.

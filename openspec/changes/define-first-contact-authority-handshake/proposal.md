## Why

First-contact birth now creates and binds a user's home universe without spending platform resources, but the next execution transition has no exact contract for proving that compute and model access belong to the requester or came from a market grant the requester accepted. Without that seam, a newborn contact can remain unusable or an implementation can accidentally consume maintainer credentials, quota, accounts, or hardware.

## What Changes

- Define one immutable, request-scoped execution-authority value that binds the authenticated principal, target universe, request, permitted phases, provider/resource constraints, authority source, expiry/revocation state, and replay-safe evidence.
- Define delegation rules for a universe founder, organization collaborator, and acting chatbot so access to a universe never implies permission to spend another principal's compute or model account.
- Define how requester-owned BYOC references and accepted-market grants become eligible authority without putting raw secrets in chatbot messages, tool arguments, logs, receipts, or market records.
- **BREAKING**: Replace the public raw-API-key `set_engine` input with out-of-band requester-authenticated credential enrollment; no compatibility shim may continue accepting secrets through chatbot/MCP JSON.
- Define workload-specific completeness and the intersection rule: persistent engine ceiling, request grant, and phase scope can only narrow one another.
- Define structured held, partial-phase, and success outcomes for reply generation, learning extraction, and later graph execution, with no ambient fallback.
- Define redacted, race-safe per-phase receipts and accepted-market grant validation requirements, including audience, expiry, revocation, budget, idempotency, and replay protection.
- Keep all runtime implementation blocked until draft PR #1606 supplies the persistent ceiling, R2-1b supplies its result-object receipt seam, and an opposite-provider security review returns `approve` or an accepted `adapt`.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `identity-auth-and-access-control`: Refine the existing first-contact authority requirements into an implementation-ready request/delegation/grant/phase/receipt contract.
- `credential-vault`: Replace recoverable plaintext/base64 custody and public raw-key intake with authenticated out-of-band enrollment, encrypted custody, and scoped ephemeral secret vending.

## Impact

- Planning contract only in this change; it does not invoke a provider, use a key, consume quota, contact a market, or change runtime behavior.
- Future implementation will affect first-contact resolution, provider routing, credential-vault references, accepted-market grant verification, universe reply/extraction propagation, graph execution, and provider receipts.
- Removing direct GitHub token resolution also requires coordinated migration of `auto_ship_pr` and GitHub PR effectors to owner/destination/purpose/job/expiry-scoped broker leases with external-effect regression gates.
- Draft PR #1606 remains the R2-1a prerequisite rather than being duplicated. R2-1b remains the only race-safe provider result/receipt path.
- The existing `universe-creation` change retains lifecycle ownership and the high-level authority invariant; this change supplies the exact authority seam needed to implement its remaining tasks.
- After current owners clear, this change supersedes/refines only `universe-creation` authority tasks 2.1-4.7; that change retains birth, lifecycle, migration, and final end-to-end acceptance ownership. Market selection/agreement formation, training group formation, and settlement remain in their paid-market/distributed-execution successor changes.

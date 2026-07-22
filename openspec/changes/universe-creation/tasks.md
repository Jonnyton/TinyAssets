> **Residual change (reconciled 2026-07-22).** Checked items are verified
> prerequisites already present in canonical specs/runtime. Unchecked items are
> the only implementation work owned by this change. Provider/security runtime
> work remains gated on requester/market authority dependencies and
> opposite-provider security review.

## 1. Verified Prerequisites

- [x] 1.1 Verify creation generates an opaque lowercase `u-`+ULID serial when no id is supplied and rolls back partial roots.
- [x] 1.2 Verify creation seeds the linked root OKF soul bundle and omits duplicate starter `self/`, `soul/`, `notes.json`, and `activity.log` artifacts for new universes.
- [x] 1.3 Verify opening authenticated `converse` with create scope can reserve, materialize, and bind exactly one founder home while `get_status` remains a pure read; without create scope it writes no binding and returns a structured home-create/load error with `auth_scope_required: true`.
- [x] 1.4 Verify the authenticated first-contact path resolves through founder home context rather than a host-global active-universe marker.
- [x] 1.5 Reclassify the remaining work under `identity-auth-and-access-control` and `universe-lifecycle-and-soul`; remove the obsolete proposed `universe-creation` capability delta.
- [x] 1.6 Validate the reconciled active change strictly and confirm its residual deltas remain unsynced while implementation tasks are open.

## 2. Execution-Authority Contract Tests

- [ ] 2.1 Add a requester-owned success test proving a complete requester compute/model bundle permits the universe intelligence to generate a reply which the chatbot relays/renders verbatim.
- [ ] 2.2 Add an accepted-market success test proving accepted compute and, when separately required, model-access grants permit execution and are recorded as market authority.
- [ ] 2.3 Add missing and partial authority tests proving birth/binding may complete but no provider is invoked and the result is `held` / `setup_required` with `universe_id`, missing elements, and BYOC/market paths.
- [ ] 2.4 Add hostile ambient-credential tests proving project-maintainer, project-founder, and platform-operator credentials, quota, auth homes, cloud chains, hardware, and accounts are never selected for a requester workload.
- [ ] 2.5 Add routing/fallback tests proving retries can use only providers admitted by the immutable authority bundle and hold when that set is exhausted.
- [ ] 2.6 Add phase-boundary tests proving reply generation and learning extraction use the same authority bundle, may select different providers admitted for their respective phases, and never invoke an uncovered provider.
- [ ] 2.7 Add receipt tests proving each invocation records phase, provider, and `requester_owned` or `accepted_market` authority without recording secrets.

## 3. Execution-Authority Implementation

- [ ] 3.1 Implement the requester BYOC authority resolver for compute and separately required model access.
- [ ] 3.2 Implement accepted-market compute/model grant resolution and bind it to the requester's accepted offer.
- [ ] 3.3 Construct an immutable complete authority bundle and pass only its eligible provider set into selection and fallback.
- [ ] 3.4 Isolate provider child processes from ambient maintainer credential sources with a reviewed allowlisted environment/home/profile boundary.
- [ ] 3.5 Return the structured `held` / `setup_required` envelope without provider invocation when the bundle is absent, partial, or loses all eligible fallbacks.
- [ ] 3.6 Thread the same bundle through universe reply generation and learning extraction; keep the chatbot as relay/renderer only.
- [ ] 3.7 Persist redacted per-phase authority receipts linked to the request and accepted market grant where applicable.

## 4. Lifecycle Residuals

- [ ] 4.1 Add tests proving public `POST /v1/universes` cannot create a universe, then remove or reject the route.
- [ ] 4.2 Add tests proving every public birth path generates its own serial and rejects caller-selected ids, then enforce the boundary without breaking internal migration tooling.
- [ ] 4.3 Add tests and implementation for the root universe index keyed by immutable id with learned-name projection from `identity.md`.
- [ ] 4.4 Inventory descriptive-id roots and live references, then implement an atomic, rollback-safe migration to generated serial roots.
- [ ] 4.5 Verify migrated bindings and read/write/run/status references resolve only the serial id after migration.
- [ ] 4.6 Remove duplicate `self/`, `soul/`, and brain-archive directories plus empty starter notes/logs from existing roots while preserving non-empty historical runtime data.

## 5. Security and Release Gates

- [ ] 5.1 Obtain opposite-provider security review of provider-specific environment, cloud-chain, auth-home, local-subscription, hardware, and market-grant isolation before runtime implementation lands.
- [ ] 5.2 Run focused auth, first-contact, provider-routing, learning-extraction, receipt, universe-lifecycle, migration, and HTTP tests.
- [ ] 5.3 Re-run strict OpenSpec validation after implementation and before syncing or archiving this change.
- [ ] 5.4 Verify the success and setup-required paths through a rendered chatbot conversation using the live connector.
- [ ] 5.5 Freshness-stamp post-fix production evidence that real users complete first contact without consuming maintainer resources; leave a monitoring item if no clean use is visible yet.

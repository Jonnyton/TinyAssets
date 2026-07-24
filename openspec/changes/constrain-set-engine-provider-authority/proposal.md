## Why

`set_engine` currently records a preferred provider without constraining
`allowed_providers`, so a failed user-selected engine may fall through to an
unchosen provider, consume unrelated quota, or cross a privacy boundary. Draft
PR #1606 proves much of the founder-key path but is over-scoped and blocked;
this declared successor preserves that work while defining the smallest
provider-destination authority contract needed by universe creation, BYOC,
market compute, and provider receipts.

## What Changes

- **BREAKING:** Every universe publishes an explicit provider ceiling.
  `None` is a pre-cutover legacy encoding only; new/unassigned universes and
  every new `set_engine` transition use explicit deny-all until ready.
- BYO Anthropic-family assignments publish `["claude-code"]`; BYO
  OpenAI-family assignments publish `["codex"]`.
- Self-hosted and host-daemon assignments publish `[]` until a separate
  source-specific activation binds executable provider authority.
  Market-rented intent always remains `[]` in the ordinary provider router;
  accepted-market work uses the signed remote-executor path instead.
- One strict execution-route resolver accepts only canonical BYO service
  values and their matching writer hints. Aliases, unknown values, and
  mismatches fail before mutation.
- Assignment becomes one per-universe, cross-process transition:
  deny-all quarantine, credential/source update where applicable, then atomic
  publication of one coherent final assignment.
- Effective request authority is the intersection of the fresh persistent
  assignment ceiling and a separate immutable request-level eligible set.
  Omitted universe authority fails closed; only enumerated
  non-request-reachable host operations may receive an identity-validated,
  non-serializable bootstrap capability.
- Every routing attempt reloads or validates the fresh non-secret ceiling,
  including retries, policy overrides, judge ensembles, hard pins, and calls
  holding an older `UniverseContext`.
- **BREAKING:** Providers replace the one-phase `complete(...)` contract with
  router-minted immutable `ProviderInvocation` plus two-phase
  `start(...) -> ProviderLaunchHandle -> result()`, so authority is frozen
  under admission and network completion occurs after unlock.
- Launch has a short bounded deadline distinct from model completion; partial
  starts, cancellation, timeout, and child/request reaping have one terminal
  owner backed by a secret-free durable launch identity that
  startup/assignment reconcile after process death.
- Accepted-market execution remains deny-all in the ordinary provider router
  and uses only the paid-market/distributed-execution owner's signed remote
  executor path.
- The ceiling is defined as provider-destination authority, not proof of
  credential-source isolation. Credential isolation remains gated on the
  separate fail-closed auth-overlay work.
- Reconciliation is explicit: this change is the declared narrow successor to
  draft PR #1606. It will selectively retain reviewed assignment, migration,
  and deployment-fence work; generic auth stripping remains with the
  provider-auth overlay; #1606 closes without merge after retained work and
  ownership are recorded.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `provider-routing`: Require `set_engine` to publish and route against a
  fail-closed, fresh, per-universe provider-destination ceiling.
- `universe-lifecycle-and-soul`: Require every newborn universe to persist an
  explicit unassigned, deny-all engine state within atomic creation.

## Impact

- Behavioral contract: `openspec/specs/provider-routing/spec.md`
- Planned runtime includes universe creation/assignment and config, provider
  authority/context/base/router/call bridge/error handling, every provider call
  site, packaged mirrors, the selected #1606 migration/deployment-fence subset,
  and exact focused tests. Files are claimed only after dependency release and
  a complete `call_provider` inventory.
- After #1660 receives its required opposite-provider verdict and accepted
  requester-authority semantics fold into the current `universe-creation`
  owner, a declared subordinate `provider-authority-propagation` change lands
  only the typed universe/host-local carrier and exhaustive non-enforcing
  call-site threading before this change enables enforcement. It consumes the
  accepted request-authority contract rather than creating a competing type.
- Planned verification covers engine assignment/source, allowlist, request
  intersection, auth-snapshot races, host-token forgery, journal crashes,
  concurrency/load, and assignment-to-router integration.
- Coordination gates: retained-work split from draft PR #1606 including its
  universe-creation edits; PR #1484 releases canonical and packaged
  `api/universe.py`; PR #1623 and its prerequisite stack release the canonical
  provider-routing spec; the provider-auth overlay lands or partitions exact
  ownership; #1660 receives an accepted verdict; #1617 is dispositioned; and
  the subordinate provider-authority transport owner lands.
- Downstream consumers: `universe-creation` must pass a distinct request
  eligible set; `provider-attempt-receipts` separately depends on credential
  isolation and owns call-local evidence; paid-market execution requires a
  named accepted-grant activation owner; enumerated non-request-reachable
  host operations must receive the genuine bootstrap-minted host-local
  capability explicitly.
- No claim is made that this change alone isolates host credentials, grants
  market compute, or makes unimplemented engine sources executable.

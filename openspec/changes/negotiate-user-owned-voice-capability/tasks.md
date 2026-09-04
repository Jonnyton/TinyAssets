## 1. Design gate

- [x] 1.1 Obtain one bounded Claude Opus cross-family review of the proposal, design, delta specs, and exact authority/storage surface; resolve evidence-backed blockers before implementation.

## 2. Capability substrate

- [x] 2.1 Add the connection-capability ledger table, canonical descriptor validation, idempotent configure/revoke methods, transaction-local deletion cascade, secret-free reads, and migration/delete/re-provision tests.
- [x] 2.2 Add authenticated `write_graph target=connection operation=configure_provider_capability` wiring that derives (rather than accepts) the current founder provider's exact live connection/grant, requires owner plus admin authority, and cannot widen authority.

## 3. Voice resolution

- [x] 3.1 Replace `voice-connection.json` with current-serving-provider capability resolution that reuses the existing serving-authority/custody verifier and rechecks the exact capability, owner, universe, connection, grant, credential rotation, endpoint, and method at session time.
- [x] 3.2 Add focused server tests for ready, unpowered, unsupported subscription provider, undeclared/malformed/stale capability, cross-owner/provider refusal, revoke, connection delete/re-provision, credential rotation, disclosure identity changes, and credential-blind session exchange.

## 4. Single-control product flow

- [x] 4.1 Make the composer Voice control start immediately when ready, focus the existing unpowered-provider request when no provider serves, and use the existing connection/request surface for a powered provider's capability gap; remove the separate Voice unlock modal.
- [x] 4.2 Extend deterministic browser tests for the complete ready/unpowered/remediable-incompatible/unremediable-incompatible/disabled/start state machine, disclosure invalidation, and bounded mid-session revocation teardown, with no microphone or network request before readiness.
- [x] 4.3 Keep current-provider capability discovery and the existing provider-connection remediation reachable from the Voice control while Voice session gates are off; preserve the closed session endpoint.
- [x] 4.4 Prove an unsupported subscription binding opens the existing connection surface without requesting microphone access or starting a Voice session.

## 5. Durable truth and delivery

- [x] 5.1 Record the founder-approved one-control/current-provider capability rule in `PLAN.md`, update the Voice handoff, and delete the resolved no-binding concern when the product path is complete.
- [x] 5.2 Build the runtime mirror, run focused and required gates plus an exact-head opposite-provider implementation review, then land and deploy with both Voice-specific gates still off.
- [x] 5.3 Prove disabled/unpowered/incompatible states through the rendered app and run the authenticated public canary; record ready-state proof as a founder-only host action if no eligible already-authorized provider exists.
- [ ] 5.4 After the authenticated app derives an eligible already-authorized current provider and Jonathan explicitly authorizes the bounded proof, stop for his rendered ready-state and live microphone acceptance; never ask him to name a derivable binding or enable Voice merely to complete this change.

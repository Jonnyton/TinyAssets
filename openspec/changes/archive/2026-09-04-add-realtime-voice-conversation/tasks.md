## 1. Contract and independent review

- [x] 1.1 Obtain an opposite-provider architecture/security review of the proposal, design, and delta specs; resolve evidence-backed blockers before implementation.
- [x] 1.2 Record universe authority as the capability boundary and the native/store handoff as durable design state; remove the obsolete request for a separate founder key or proof budget.

## 2. Safe reversible server slice

- [x] 2.1 Implement and catalog an off-by-default, provider-neutral voice policy and authenticated session-broker boundary that uses only an exact owner/universe HTTP connection grant through the credential-blind proxy and makes no paid call in tests.
- [x] 2.2 Add deterministic server tests for disabled, anonymous, missing-home, missing/invalid/symlinked binding, cross-owner, exact grant, success, session-endpoint allowlisting, bounded SDP validation, upstream failure, no-cache, and secret-redaction behavior.

## 3. Shared client slice

- [x] 3.1 Implement the accessible voice state machine, versioned first-use disclosure, teardown, bounded reconnect, and explicit ambiguous-delivery recovery behind the server-reported flag.
- [x] 3.2 Add a mockable WebRTC adapter for `tinyassets.voice.v1` that requires the narrow `converse(message)` tool, invokes the canonical MCP operation once, preserves exact returned text, and handles barge-in without paid network use.
- [x] 3.3 Extend the deterministic browser harness for state transitions, permission denial, teardown, barge-in, reconnect, duplicate prevention, and canonical text-history continuity.

## 4. Native and rollout readiness

- [ ] 4.1 Add coordinated iOS/Android microphone permissions and store privacy copy without changing signing, enrollment, publication, or release ownership.
- [ ] 4.2 Run focused tests, lint, OpenSpec validation, public canary, rendered browser conversation, and one real-device voice pass only after that test universe already has a compatible user-bound `tinyassets.voice.v1` connection. Do not request a separate credential or budget merely to satisfy this task.
- [x] 4.3 Obtain opposite-provider implementation review, document staged rollout/monitoring/kill-switch evidence, sync specs, and archive only after the change lands.

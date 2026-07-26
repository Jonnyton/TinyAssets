## ADDED Requirements

### Requirement: The canonical write handle exposes one strict accepted-market engine action

The live connector SHALL expose accepted-market activation only as
`write_graph(target="engine", action="activate_accepted_market", graph_id,
market_acceptance, idempotency_key)` under the existing seven-handle catalog.
It MUST NOT add a handle, overload the live `target="universe"` birth path or
`target="request"`, revive the legacy `universe` handle, accept free-form text
as authority, accept a raw secret, or require a desktop or web application.
Unknown engine actions, missing fields, extra fields, numeric coercions, and
unsupported schema versions SHALL fail before mutation.

`market_acceptance` SHALL be a closed object containing exactly:
`schema_version="accepted-market-activation/v1"`, `request_id`,
`request_version`, `request_digest`, `selection_receipt_id`,
`selection_receipt_digest`, `quote_id`,
`quote_version`, `quote_digest`, `fulfillment_descriptor_id`,
`fulfillment_descriptor_version`, `fulfillment_descriptor_digest`, `currency`,
`budget_micros`, `spend_cap_micros`, `fee_schedule_version`,
`demand_commitment_digest`, `acceptance_policy_digest`,
`settlement_policy_version`, `deadline`, and `quote_expires_at`.

All IDs inside `market_acceptance` SHALL be 1-128 ASCII characters matching
`[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`. The top-level idempotency key SHALL
retain `write_graph`'s 16-128 ASCII-character bound and match
`[A-Za-z0-9][A-Za-z0-9._:-]{15,127}`. Digests SHALL be exactly 64 lowercase
hex characters. `currency` SHALL equal the rehydrated current
`ValidatedQuote.settlement_currency` and match
`[A-Za-z0-9][A-Za-z0-9._:-]{0,15}` without case normalization;
`MarketRequest` is not a currency owner and has no currency field.
`fee_schedule_version` and
`settlement_policy_version` SHALL be owner-native ASCII strings of 1-128
characters matching `[A-Za-z0-9][A-Za-z0-9._:-]{0,127}`.
`request_version`, `quote_version`, `fulfillment_descriptor_version`,
`deadline`, `budget_micros`, and `spend_cap_micros` SHALL be strict JSON
integers within positive signed 64-bit range; Boolean, float, decimal string,
overflow, zero, and negative coercions SHALL fail. The paid-market agreement
owner's published `canonical_market_max_micros` SHALL be positive and no
greater than signed 64-bit range, with
`0 < spend_cap_micros <= budget_micros <= canonical_market_max_micros`.
`quote_expires_at` SHALL be the deterministic public rendering of the current
`ValidatedQuote.expires_at` integer Unix epoch seconds as whole-second UTC
RFC 3339 `YYYY-MM-DDTHH:MM:SSZ`. The server SHALL parse the caller string back
to integer Unix epoch seconds and require exact equality with the raw current
owner value; fractional seconds, a non-`Z` offset, normalization drift, or
formatting alone cannot become owner truth. Deadline and raw quote expiry
SHALL exactly match current owner records, remain valid, and fit their
owner-defined horizon. Any grammar, bound, unit, or time-encoding change
requires a new schema version.

#### Scenario: chatbot submits a well-shaped activation

- **WHEN** an authenticated connector client calls `write_graph` with target `engine`, action `activate_accepted_market`, an exact graph ID, idempotency key, and the closed v1 market-acceptance object
- **THEN** the connector routes the command to the accepted-market activation owner without changing the advertised seven-handle set
- **AND** no Request or BranchTask is created merely by this engine action

#### Scenario: ambiguous or authority-bearing input is rejected

- **WHEN** activation uses free-form text, an unknown field, a wrong live target, a legacy handle, an actor/tenant/provider/host/credential/wallet/grant field, or a non-integer spend cap
- **THEN** the connector returns a typed validation refusal and performs no activation mutation

### Requirement: Connector activation results are typed, faithful, and credential-blind

The connector SHALL return a faithful structured result and bounded text
rendering for success, refusal, conflict, and repair. Success SHALL identify
the universe, action, `engine_source`, assignment state,
`fulfillment_class="accepted_market"`, accepted quote ID/version, bounded
spend and currency, idempotency outcome, and a safe next step. Results MUST
NOT expose a raw signature, B2/B13 grant, lease capability, provider
credential, secret, host address, wallet token, actor/tenant override, or
internal authority carrier.

Authorization and current-message liveness SHALL be checked before replay
lookup. A replayed historical success SHALL identify its historical
idempotency outcome separately from the re-derived current engine-assignment
state; it MUST NOT render current `remote_ready` when the mandate is now held,
expired, revoked, fenced, or cancelled, and MUST NOT reactivate it.

Refusal SHALL distinguish malformed/stale acceptance, authorization failure,
budget conflict, quote expiry, quote/fee/policy drift, cancellation,
unavailable or oversubscribed capacity, unavailable requester funding,
dependency unavailability, and same-key/different-body conflict. Repair SHALL
distinguish an absent, expired, revoked, fenced, cancelled, overspent, or
inconsistent market mandate, per-job quote/capacity/funding path, or B2 grant
and advertise only accepted-market actions proven completable on the live
connector.

#### Scenario: successful activation renders safe confirmation

- **WHEN** activation commits successfully
- **THEN** structured content and text agree on the exact universe, accepted quote/version, spend bound, remote-ready state, and idempotency outcome
- **AND** neither representation contains a secret or positive-authority carrier

#### Scenario: historical replay renders current truth

- **WHEN** same-body replay finds a historical successful activation whose mandate or assignment is now held
- **THEN** structured content and text report the historical replay plus current held/repair state rather than current remote-ready success
- **AND** the replay creates no agreement, mandate, reservation, assignment, renewal, or execution side effect

#### Scenario: invalid mandate or per-job authority renders repair without fallback

- **WHEN** an accepted-market universe cannot re-derive its current B13-bound market mandate or obtain the exact fresh per-job quote, capacity consumption, requester-funding reservation, and B2 grant
- **THEN** the connector renders a typed accepted-market repair or renewal state
- **AND** it does not advertise maintainer, local, BYOC, free, desktop-only, or generic engine-less fallback

### Requirement: Public activation cutover requires connector and concurrency proof

The action SHALL remain unadvertised as completable and production-inactive
until paid-market agreement, a B13-bound non-executable market mandate,
per-job executable quote/capacity/requester-funding consumption and B2
production, execution admission, the activation transaction, and pre-routing
remote dispatch are integrated.
Cutover MUST pass strict schema and authority-mutation tests, section 14
concurrency/load proof, canonical public canaries, and a rendered chatbot
conversation through `https://tinyassets.io/mcp`.

#### Scenario: newborn Tier-1 user proves the complete path

- **WHEN** a newborn authenticated Tier-1 user sees current market terms, explicitly accepts them, activates the exact universe, and sends the next `converse` through the rendered live connector
- **THEN** the conversation completes through current accepted-market remote authority without maintainer quota or a desktop
- **AND** the proof records the rendered prompt/result and applicable trace or screenshot

#### Scenario: incomplete dependency blocks completable advertising

- **WHEN** any paid-market mandate, fresh per-job quote, capacity, requester-funding, B2/B13, execution-admission, activation, dispatch, canary, or load-proof gate is incomplete
- **THEN** the connector does not describe accepted-market activation as a completable live path and global Tier-1 cutover remains blocked

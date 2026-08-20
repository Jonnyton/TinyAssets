# BYO LLM deposit surface

## ADDED Requirements

### Requirement: Only the universe owner deposits, with a server-derived identity

The connector SHALL expose a chatbot operation that places the authenticated
caller's own Claude or Codex subscription material into that universe's vault as a
single owned `llm_subscription` record. The depositor identity SHALL be derived
server-side from the authenticated request subject only — never from a payload
field or environment variable. The operation SHALL require the caller to be the
universe **owner/founder**, evidenced by an explicit `admin` ACL grant on that exact
universe, and SHALL NOT accept a mere `write` ACL. Authentication material SHALL be
accepted base64-encoded for transport only; the server SHALL decode it, store the
Claude token or the Codex `auth.json` base64 string in the vault's canonical field,
and SHALL NOT accept a caller-asserted owner, generation, or credential identifier.
A deposit for any service other than `claude` or `codex` SHALL be rejected loudly
without writing anything.

#### Scenario: Owner deposits a Claude subscription token

- **WHEN** the authenticated owner (holding the universe `admin` grant) submits the
  operation with service `claude` and their base64-encoded OAuth token
- **THEN** the server decodes the token, writes one `llm_subscription` record owned
  by the owner, and records the owner as the credential depositor
- **AND** the universe's Claude subscription auth becomes resolvable for serving

#### Scenario: Owner deposits a Codex auth bundle as a base64 string

- **WHEN** the authenticated owner submits the operation with service `codex` and a
  base64-encoded `auth.json`
- **THEN** the server stores it as a base64 string in the single Codex
  `llm_subscription` record owned by the owner, materializable to `CODEX_HOME/auth.json`
- **AND** the server never stores raw decoded bytes in place of the base64 string

#### Scenario: A write collaborator, not the owner, is refused

- **WHEN** an authenticated caller who holds only a `write` (not `admin`) ACL on the
  universe submits the deposit operation
- **THEN** the operation is refused as if the resource were absent, and no vault,
  ownership, custody, binding, or serving state is mutated

#### Scenario: Anonymous caller is refused before any vault touch

- **WHEN** an unauthenticated caller submits the deposit operation
- **THEN** the operation is refused before the vault is read or written
- **AND** the refusal does not reveal whether the universe or a credential exists

#### Scenario: Unsupported service is rejected loudly

- **WHEN** a deposit names a service other than `claude` or `codex`
- **THEN** the operation fails with an explicit error and writes nothing

### Requirement: A stranger cannot deposit into another universe's credential slot

The deposit surface SHALL bind a service's credential to the first owner who
deposits it and SHALL refuse to transfer that ownership to a different principal
through this path. A principal who is not the recorded credential owner SHALL NOT be
able to overwrite, adopt custody of, or serve on that credential, regardless of any
ACL they hold. A caller who is not the owner of the *target* universe SHALL be
unable to deposit into it, and every refusal SHALL leave zero vault, ownership,
custody, binding, and serving mutations.

#### Scenario: Another universe's founder cannot deposit into the victim universe

- **WHEN** a caller who is the admin/founder of universe A submits a deposit whose
  target is universe B, which they do not own
- **THEN** the deposit is refused and universe B's vault and ownership state are
  unchanged

#### Scenario: A write collaborator cannot seize an empty credential slot

- **WHEN** a write-ACL collaborator (not the owner) submits a deposit for a service
  that has no credential yet in that universe
- **THEN** the deposit is refused before any write, so the collaborator never becomes
  the credential owner

#### Scenario: A non-owner cannot overwrite an existing owned credential

- **WHEN** a principal other than the recorded credential owner submits a deposit for
  a service that already has an owned record in that universe
- **THEN** the write is refused as an ownership transfer that requires a dedicated
  flow, and the existing owned record is unchanged

### Requirement: Re-deposit upserts one slot and preserves every unrelated credential

A repeat deposit by the recorded owner for a service that already has a record SHALL
replace that single service slot in place rather than accumulating a second record,
and SHALL leave every other credential (other services, GitHub/VCS, Slack/social,
API keys) byte-for-byte intact.

#### Scenario: Re-depositing Claude leaves Codex, GitHub, and Slack untouched

- **WHEN** the owner re-deposits a Claude token in a universe that also holds a Codex
  subscription, a GitHub token, and a Slack connection
- **THEN** only the single Claude `llm_subscription` slot is replaced
- **AND** the Codex, GitHub, and Slack credentials are preserved unchanged

### Requirement: The deposit response, logs, exceptions, and graph state carry no secret

The deposit operation SHALL NOT leak the credential anywhere beyond the chatbot
transport's own inherent exposure. On the chatbot transport the base64
`auth_material_b64` unavoidably appears in the MCP request and the model/connector
context — the caller pastes it into the chat — which is inherent to the chatbot path
and is the reason the secure browser transport is a prerequisite for multi-tenant use
(see the requirement below). Beyond that inherent exposure, the operation SHALL return
only a non-secret projection — status, service, a next-step hint, and the target
`agent_binding_id` plus the current `expected_revision` needed to chain the serving
re-point. It SHALL NOT return, log, or echo the token bytes, the decoded material, or
any credential digest, and error and exception messages SHALL NOT carry secret
material. The server SHALL NOT itself persist the base64 value into graph state, run
evidence, or any store other than the owner-scoped credential vault.

#### Scenario: Deposit response and logs carry no secret

- **WHEN** a deposit succeeds or fails on a malformed credential
- **THEN** the response and any emitted log or exception contain neither the submitted
  token, its decoded form, nor any credential digest
- **AND** a successful response carries the `agent_binding_id` and `expected_revision`
  for the subsequent `bind_serving_provider` step

### Requirement: The deposit result directs the owner to the existing serving re-point

The deposit operation SHALL NOT itself enable serving. Its result SHALL name the
existing two-step re-point — `write_graph target=agent_binding
operation=bind_serving_provider` then `operation=set_serving` — and SHALL provide the
current binding revision so the caller can supply the post-bind revision to
`set_serving`. There SHALL be no `switch_provider` operation.

#### Scenario: Owner follows the hint to serve on the deposited provider

- **WHEN** the owner performs `bind_serving_provider` for the deposited provider using
  the returned binding and revision, then `set_serving {enabled:true}` with the
  post-bind revision
- **THEN** the universe serves conversational turns on the owner's deposited
  subscription and never on an ambient host credential

### Requirement: The chatbot transport is gated to a single founder until the secure browser transport ships

The chatbot `connect_llm` transport SHALL be treated as a single-founder self-risk
surface and SHALL NOT be relied upon for any second user, because it necessarily
exposes the pasted credential to the MCP request and model/connector context. The
secure browser transport (`byo-llm-deposit-browser-form`, WorkOS AuthKit, no
token-in-chat) is an **enforceable prerequisite** — not a recommendation — and MUST be
the deposit entry point before the deposit surface is offered to, or usable by, any
principal other than the vetted single founder. Multi-tenant deposit SHALL remain
blocked until that browser transport is the deposit entry point for non-founder
principals. This gate is normative: it is a MUST, not a SHOULD.

#### Scenario: A second user cannot be onboarded through the chatbot transport

- **WHEN** the platform is prepared to onboard a principal other than the vetted single
  founder to deposit their own subscription
- **THEN** the secure browser transport is required as that principal's deposit entry
  point, and the chatbot `connect_llm` path is not offered to them
- **AND** the single-founder dogfood window is the only context in which the chatbot
  transport is an accepted deposit path

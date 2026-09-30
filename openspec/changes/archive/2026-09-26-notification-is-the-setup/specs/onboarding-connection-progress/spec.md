# onboarding-connection-progress (delta)

## ADDED Requirements

### Requirement: The connect request is the whole model setup

An unpowered universe's synthesized `sys_connect_llm` request SHALL carry the
`connect` action with `use: "model"` and a `setup` object. `setup.shapes` SHALL
list the shapes the app completes itself. While the universe is unpowered,
`setup.primary` SHALL carry the installed first-power preset's id, label,
display name, key page and manual-key opt-in, read from installed data. The
app SHALL present model setup only inside this request, and SHALL NOT render a
full-page setup screen, vendor-specific cards or a raw credential-deposit
select. A powered universe SHALL see the same request collapsed as an optional
"Connect another LLM" with no primary sign-in.

#### Scenario: unpowered sign-in
- **WHEN** an owner whose universe has no current serving connection signs in
- **THEN** the app shows the universe's chat with the connect request open and first
- **AND** no provider sign-in starts until the owner taps the primary button

#### Scenario: powered universe
- **WHEN** the universe is powered
- **THEN** the connect request is collapsed, titled "Connect another LLM", and offers no first-power sign-in

### Requirement: The guided sign-in finishes in two taps with no model call

Tapping the primary button SHALL start the preset's PKCE sign-in. On return,
the app SHALL redeem the code once and then answer the returned free-only
`bind_model_access` request in the same step. The request text beside the
button states free models only and no purchase, so a second approval screen
SHALL NOT appear. Every step before the first reply SHALL be deterministic:
exchange, connection and grant, catalogue fetch, free-model selection and
serving bind. None SHALL call a model. The resulting serving source SHALL be
the universe's own connection, owned by its owner.

#### Scenario: round trip
- **WHEN** the owner approves at the provider and returns
- **THEN** the universe serves on its own connection with free-only access, and no model was called during setup
- **AND** no free-model request remains pending

#### Scenario: reconnect after a product disconnect
- **WHEN** the owner disconnects the connection on the Account page and signs in again from the request
- **THEN** the universe serves again on its own connection

### Requirement: Only an explicit answer counts

The app SHALL treat a setup answer as successful only when the result
reports `status: "answered"`. An empty, non-JSON, failed or thrown result
SHALL keep the request and offer a one-tap "Finish connecting". After any
answer attempt, the app SHALL re-read what powers the universe. While the
universe is unpowered, a single pending free-model request SHALL be finished
from the connect request, not shown as a second card.

#### Scenario: the daemon restarts mid-approval
- **WHEN** the answer's result is missing or unreadable
- **THEN** the app says nothing was lost and offers Finish connecting, which retries the same request

### Requirement: Other shapes use the same connect action

The request SHALL offer an API key with an endpoint, and the owner's own
server, as explicit fields: an https model URL, a key and a model id. The app
SHALL raise one `connect` ask with `uses.model` and answer it with the key in
the same tap. The key SHALL leave the page before any request, never ride the
ask, and never be sent over a non-https or credential-bearing URL.

#### Scenario: answer not confirmed
- **WHEN** the answer to the raised ask fails
- **THEN** the ask stays pending in the rail for the owner to finish there

### Requirement: Setup text is the owner's language

A free-model approval sentence SHALL name models and limits, and SHALL NOT
contain agent binding, provider definition or grant ids. A turn refused
because nothing serves the universe SHALL return `setup_required`, with a
note that points at the connect request and without the "actions may already
have occurred" caution. Account connection rows SHALL carry a human `label`.
A guided connection's label is its preset's display name.

#### Scenario: message sent while unpowered
- **WHEN** an unpowered owner sends a message
- **THEN** the reply says nothing ran and points at the connect request

## REMOVED Requirements

### Requirement: Observe credential saving and enabling separately
**Reason**: The subscription-CLI token card it governed is deleted from the app
(vendor-neutral slice 6; Hard Rule 3). The server route stays until slice 7.
**Migration**: Existing subscription users are unaffected. A command-runner
connection replaces the card in slice 3 and slice 4.

### Requirement: Signup handoff guidance is truthful and discoverable
**Reason**: Replaced by the short note inside the connect request, which keeps
the truthful part. It promises no automatic return and says to come back and
tap again if sign-up leaves the owner on the provider's site.
**Migration**: None.

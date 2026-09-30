# Onboarding connection progress

## Purpose

Connect the model a universe runs on, entirely inside the one synthesized
connect request, and show truthful progress while doing it — without replaying
credentials or carrying work across logins.

The subscription-CLI token control this capability was first written around is
gone (`notification-is-the-setup`, slice 6: no vendor-specific setup card, no
full-page setup screen, no raw credential-deposit select), so the two
requirements that governed it were removed rather than reworded. What remains is
vendor-neutral by construction: the app shows whichever acquisition preset is
INSTALLED and names no provider itself.

Those two removals are removals of BROWSER behaviour only. The authenticated
server routes behind them stay registered and functional; nothing here says a
server capability was withdrawn.

## Requirements

### Requirement: Pending requests belong to their original login

Sign-out SHALL invalidate the connection attempt and the MCP transport login
generation immediately. Delayed work SHALL neither modify the new login's UI
nor send the previous login's arguments under the new bearer. This fence SHALL
apply to initial handshakes and every automatic transport recovery path.

#### Scenario: Delayed credential request encounters a session rejection
- **WHEN** a credential request returns 401 or 404 after sign-out or a login change
- **THEN** it is not replayed or refreshed under the replacement login
- **AND** a delayed handshake cannot proceed to deposit the original token
- **AND** stale handshakes cannot clear a replacement login's session

### Requirement: Manual OpenRouter acquisition preserves free-model approval

The signed-in app SHALL offer explicit manual-key recovery for the installed
OpenRouter free-model bootstrap preset through the existing same-origin model
connection ingress, without requiring existing inference or an OAuth callback.
The operation MUST reuse the owner-scoped bootstrap and its ordinary unanswered
model-access request; depositing a key MUST NOT enable model execution, approve
access, change saved preferences, or permit paid models or paid fallback.
Manual recovery SHALL require `manual_key_entry` equal to boolean true in the
trusted installed acquisition document, never caller metadata. Absence, false,
non-boolean values and a newly installed preset without opt-in MUST refuse.
The installed endpoint and matching owner-filtered bearer discovery contract
MUST validate before home creation or credential deposit.

The SERVER's part of this is unchanged and stays inert: preparation returns an
ordinary UNANSWERED model-access request and changes no access by itself. What
changed with `notification-is-the-setup` is which gesture answers it. The owner's
tap on Connect inside the request is now the explicit approval, and the app
answers the prepared request in that same tap rather than presenting a second
confirmation screen. The approval sentence is on screen beside the button before
the tap, so nothing is approved unseen — but "access changes only after a
SEPARATE approval" is no longer the behaviour and must not be claimed.

#### Scenario: Unpowered owner supplies their key
- **WHEN** the current live owner of an empty home explicitly submits a valid key
- **THEN** the server uses only the installed preset's endpoint and eligibility policy
- **AND** preparation on its own enables nothing: it returns an unanswered
  model-access request
- **AND** the owner's Connect tap, made against the approval sentence shown beside
  it, is what answers that request

#### Scenario: Wrong authority or changed setup
- **WHEN** the account is deleted or deleting, ownership or home changes, or setup is no longer empty before a mutation
- **THEN** acquisition refuses without resurrecting the account or replacing its connections
- **AND** a concurrent acquisition cannot silently overwrite the winning setup

#### Scenario: Caller tries to expand provider access
- **WHEN** a request includes a caller-selected endpoint, owner, model, grant or policy, or an unsupported preset
- **THEN** the server refuses it before any credential deposit or provider request
- **AND** a key with broader provider permissions cannot enable paid model selection

#### Scenario: Another preset is installed without manual recovery authority
- **WHEN** an otherwise valid installed preset lacks the explicit trusted boolean opt-in
- **THEN** manual acquisition refuses before home creation or credential deposit
- **AND** adding a request field cannot grant that capability

### Requirement: Manual key handling is bounded and non-replaying

The app SHALL clear the manual input before its first asynchronous operation,
send the key only in the bounded authenticated same-origin JSON request, and
exclude it from URLs, browser storage, chat, logs, errors and responses. The
server MUST reject malformed or oversized input without echoing it. Pending
submissions SHALL remain tied to their original login and SHALL NOT replay.

#### Scenario: Submission outcome is uncertain
- **WHEN** deposit or discovery times out or the browser loses the response
- **THEN** the app reports incomplete or unconfirmed setup rather than connected
- **AND** it offers only user-directed state recovery without retaining or resending the key

#### Scenario: Login changes while the request is pending
- **WHEN** the user signs out or changes login during the manual request
- **THEN** the old result cannot alter the new login's UI or issue a new request under that login

### Requirement: The provider's sign-in page names the connection

An installed acquisition preset MAY carry `authorize_params`: fixed, non-secret query parameters the provider documents for its authorize page (for example a key label), so the user sees what they are connecting rather than a generic "An app". They are installed data, not code or caller input. They MUST NOT set or override the flow's own `callback_url`, `code_challenge` or `code_challenge_method`; a malformed map (a non-string, empty, oversized, non-ASCII key, non-printable value, or more than 8 entries) MUST make the preset invalid.

#### Scenario: A labelled preset starts sign-in
- **WHEN** an owner starts sign-in for a preset whose `authorize_params` names the key
- **THEN** the authorize URL carries that label alongside the flow's own parameters
- **AND** a preset parameter that names a flow parameter never replaces the flow's value

### Requirement: A connected universe's connect entry is optional, not outstanding

The rail's synthesized `sys_connect_llm` entry SHALL remain present once a
universe is powered — it is the only route to adding a second source — but it
SHALL report `status: optional` rather than `pending`, and it SHALL NOT be
counted among the requests waiting on the user. The app SHALL render an optional
entry collapsed and visually distinct from an ask, and the rail heading SHALL NOT
claim work is waiting when every entry is optional. An entry with no `status`, or
one the client does not recognize, SHALL be treated as a real ask.

The unpowered state is unchanged: its entry stays `pending` and `sticky`.

#### Scenario: A powered universe has nothing waiting
- **WHEN** the owner's universe has a current serving binding
- **THEN** the connect entry is `status: optional`, `sticky: false`, still answerable, and no entry reports `pending`
- **AND** the rail heading stops saying work is waiting, while the entry stays visible and openable

#### Scenario: One real ask still asks
- **WHEN** any non-optional request is in the rail beside the optional connect entry
- **THEN** the heading asks again and only the connect entry renders as optional

#### Scenario: An unpowered universe still blocks
- **WHEN** no serving binding exists
- **THEN** the connect entry remains `pending` and `sticky` with its first-power sign-in

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
- **WHEN** the owner arrives at a powered universe
- **THEN** the connect request is collapsed, titled "Connect another LLM", and offers no first-power sign-in

#### Scenario: the universe becomes powered while its setup is open
- **WHEN** setup succeeds in the request the owner had opened
- **THEN** the entry loses its first-power sign-in and is titled "Connect another
  LLM", and MAY remain expanded until the rail is closed — the open entry is the
  one the owner was just using, so collapsing it out from under them is not
  required (cross-family review, 2026-09-26: the rail's open-entry id is not
  cleared on success, and this says so rather than promising a collapse that does
  not happen)

### Requirement: The guided sign-in finishes in two taps with no model call

Tapping the primary button SHALL start the preset's PKCE sign-in. On return,
the app SHALL redeem the code once and then answer the returned
`bind_model_access` request in the same step. The request text beside the
button states free models only and no purchase, so a second approval screen
SHALL NOT appear. Every step before the first reply SHALL be deterministic:
exchange, connection and grant, catalogue fetch, free-model selection and
serving bind. None SHALL call a model. The resulting serving source SHALL be
the universe's own connection, owned by its owner.

The request the app adopts is identified by ACTION TYPE and by there being
exactly one of it — not by its access being free (cross-family review,
2026-09-26). So: none pending folds nothing; exactly one folds, whatever access
it carries; two or more fold neither and both stay as their own cards. The
free-only promise is carried by the approval sentence the owner reads beside the
button, which is rendered from the request itself, not by the selection. The
server's own bootstrap is what makes the free-only request in the first place, so
the ordinary path is free-only in practice — but a `bind_model_access` request
from somewhere else would be adopted too, and the spec says so rather than
implying a filter that does not exist.

#### Scenario: round trip
- **WHEN** the owner approves at the provider and returns
- **THEN** the universe serves on its own connection with free-only access, and no model was called during setup
- **AND** no free-model request remains pending

#### Scenario: reconnect after a product disconnect
- **WHEN** the owner disconnects the connection on the Account page and signs in again from the request
- **THEN** the universe serves again on its own connection

### Requirement: Only an explicit answer counts, on the guided path

On the GUIDED sign-in path the app SHALL treat a setup answer as successful only
when the result reports `status: "answered"`. An empty, non-JSON, failed or thrown
result SHALL keep the request and offer a one-tap "Finish connecting", and after
any answer attempt the app SHALL re-read what powers the universe.

Scoped to that path deliberately, because it is the guarantee that is actually
implemented (cross-family review, 2026-09-26). The API-key / own-server path is
weaker and this requirement does not claim otherwise: on failure it directs the
owner to finish the ask in the ordinary rail, whose generic handler treats a
non-error result as sent, and it does not re-read serving or offer the one-tap
finish — the owner pastes the key again. Closing that gap is a follow-up
(`docs/concerns/2026-09-26-endpoint-setup-failure-is-weaker-than-the-guided-path.md`);
until it lands, the narrower sentence is the true one.

#### Scenario: the daemon restarts mid-approval
- **WHEN** the GUIDED answer's result is missing or unreadable
- **THEN** the app says nothing was lost and offers Finish connecting, which retries the same request

#### Scenario: the endpoint answer fails
- **WHEN** an API-key or own-server answer fails
- **THEN** the ask stays pending in the rail and the owner finishes it there,
  without an automatic re-read of what powers the universe

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

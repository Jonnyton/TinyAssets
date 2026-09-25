# agent-access-controls (delta)

## ADDED Requirements

### Requirement: The owner's agent can read everything it holds in one call

`read_graph target=access` SHALL return, for the caller's own universe only,
every channel connection with its `access` mode, every active channel
consent, every workspace consent, the accepted model sources with their
spending ceilings (`cost_caps: null` meaning free models only), the requests
still waiting on the owner with their `origin` and whether they are
withdrawable, and the owner's standing "don't ask again" decisions. It SHALL
carry no credential material. It SHALL be served on the served engine surface
(graph pinned) and on the connector.

#### Scenario: readback after a grant
- **WHEN** the owner's agent approves a consent for `(authenticated_external_call, hooks.example)` and then reads `target=access`
- **THEN** `channel_consents` contains that sink and destination

#### Scenario: another user's universe
- **WHEN** a principal without an `admin` ACL row on universe A reads `target=access` for A
- **THEN** the reply is a not-found envelope and no section of A is returned

### Requirement: The owner's agent can take a channel consent back

`source_channel` SHALL accept `action=revoke` with `{channel_type|sink,
destination}` for the caller's own universe. It SHALL revoke the active
consent and return the post-state read from the enforcement store
(`active: false`), with status `revoked`, or `not_held` when no active consent
existed. `source_code` SHALL be refused. Revoking a `workspace` consent SHALL
be allowed, even though the agent cannot grant one.

#### Scenario: revoke then use
- **WHEN** the agent revokes a consent it holds
- **THEN** `is_consent_active` for that pair is false, and `target=access` no longer lists it

#### Scenario: revoke on another user's universe
- **WHEN** a non-owner calls revoke for universe A
- **THEN** the call is refused with `auth_failed` and A's consent stays active

### Requirement: The agent can withdraw its own stale request

`write_graph target=pending_request operation=withdraw` SHALL move a request
from `pending` to `withdrawn`, recording the given reason, only when the
request is still pending and its `origin` is `agent`. A request's `origin`
SHALL be set by the server, never by the asker. Platform-raised requests
SHALL be `origin=platform`. A withdrawal SHALL write no standing decision.
The synthesized model-connection entry SHALL NOT be withdrawable.

#### Scenario: withdraw a stale ask
- **WHEN** the agent withdraws its own pending request
- **THEN** the request reads `status=withdrawn` with the reason, it is not in the pending list, and a later answer reports `already_resolved`

#### Scenario: withdraw what the owner already answered
- **WHEN** the agent withdraws a request whose status is no longer `pending`
- **THEN** it is refused with `already_resolved` and the status is unchanged

#### Scenario: withdraw a platform ask
- **WHEN** the agent withdraws a request with `origin=platform`
- **THEN** it is refused with `not_withdrawable`

#### Scenario: withdraw on another user's universe
- **WHEN** a non-owner withdraws a request in universe A
- **THEN** the reply is a not-found envelope and the request stays pending

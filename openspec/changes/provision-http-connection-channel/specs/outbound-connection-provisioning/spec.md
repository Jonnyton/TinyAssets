# outbound-connection-provisioning (delta)

## ADDED Requirements

### Requirement: A universe owner can provision a generic http connection

The connector SHALL expose `write_graph target=connection operation=connect_http`
so a universe's owner can provision a generic outbound `http` connection that the
universe's graphs can later act on via the `authenticated_external_call` effector.
The operation SHALL be owner-only (authenticated + an explicit `admin` ACL row on
the target universe), deposit the supplied credential into the per-universe vault
(never echoing it), create an `http`-typed `ConnectionLedger` connection with a
non-empty, validated endpoint allow-list and the `bearer` single-secret auth scheme
(Slice 1 scope; `none`/`basic`/`header`/`oauth1a` deferred), and grant that
connection to the universe. The primitive is channel-agnostic: it hard-codes no
service — the owner supplies host, path, and secret, so an unanticipated channel
works identically. Creation and grant SHALL be idempotent with deterministic ids.
Every *refusal* (auth, validation, conflict) SHALL happen before any write, leaving
zero mutation. A rare mid-provision infrastructure fault SHALL leave only INERT
partial state (a connection with no grant, or a credential with no connection —
neither able to authorize a call), which the idempotent retry completes; it SHALL
never leave a usable half-connection.

#### Scenario: Owner provisions an http connection

- **GIVEN** an authenticated owner (admin ACL) of a universe
- **WHEN** they call connect_http with a destination key, a bearer secret, and at
  least one `{host, path_template, methods}` endpoint
- **THEN** the credential is stored in the per-universe vault under
  `vault://http/<destination>`, an `http` connection with that endpoint allow-list
  is created and granted to the universe, and a redacted projection is returned
  (`connection_id`, `grant_id`, `destination`, `auth_scheme`, `allowed_endpoints`)
  with the secret never echoed

#### Scenario: Non-owner or anonymous is refused

- **GIVEN** a caller who is anonymous, or is authenticated but lacks an `admin`
  ACL row on the universe
- **WHEN** they call connect_http
- **THEN** an anonymous caller gets `authentication_required` and an
  authenticated non-admin gets a uniform `not_found` (existence-probe safe); in
  both cases no credential, connection, or grant is created
- **AND** a second admin who is not the connection's owner is refused with
  `connection_conflict` before any vault write (ownership is not transferable
  through this surface)

#### Scenario: Invalid provisioning input is rejected fail-closed

- **GIVEN** connect_http input with an empty endpoint allow-list, an unsupported
  auth scheme (e.g. `oauth1a`), or a credential-ownership transfer to a different
  owner
- **WHEN** the operation runs
- **THEN** it returns a specific error, deposits nothing, and creates no
  connection or grant (atomic, fail-closed)

#### Scenario: Idempotent re-provisioning rotates the secret, policy is immutable

- **GIVEN** an owner who already provisioned a connection for a destination
- **WHEN** they call connect_http again for the same destination with an identical
  policy (same owner, type, class, auth scheme, scopes, credential_ref, and
  endpoint allow-list)
- **THEN** the existing connection/grant are returned (deterministic ids), not
  duplicated, and the secret is rotated to the new value
- **AND** if any immutable field differs — including a changed endpoint allow-list,
  or a non-owner admin — the call returns `connection_conflict` before any vault
  write, so a re-provision never silently keeps the old egress policy under a
  rotated secret (changing policy requires revoke-then-reprovision)

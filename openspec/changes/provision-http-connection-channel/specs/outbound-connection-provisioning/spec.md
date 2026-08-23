# outbound-connection-provisioning (delta)

## ADDED Requirements

### Requirement: A universe owner can provision a generic http connection

The connector SHALL expose `write_graph target=connection operation=connect_http`
so a universe's owner can provision a generic outbound `http` connection that the
universe's graphs can later act on via the `authenticated_external_call` effector.
The operation SHALL be owner-only (authenticated + an explicit `admin` ACL row on
the target universe), deposit the supplied credential into the per-universe vault
(never echoing it), create an `http`-typed `ConnectionLedger` connection with a
non-empty, validated endpoint allow-list and a supported single-secret auth scheme
(`none`/`bearer`/`basic`/`header`), and grant that connection to the universe.
Creation and grant SHALL be idempotent with deterministic ids and conflict-checks,
and SHALL fail closed (nothing mutated) on any error.

#### Scenario: Owner provisions an http connection

- **GIVEN** an authenticated owner (admin ACL) of a universe
- **WHEN** they call connect_http with a destination key, a supported auth scheme,
  a secret, and at least one `{host, path_template, methods}` endpoint
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

#### Scenario: Idempotent re-provisioning

- **GIVEN** an owner who already provisioned a connection for a destination
- **WHEN** they call connect_http again for the same destination with matching
  ownership
- **THEN** the existing connection/grant are returned (deterministic ids), not
  duplicated; a genuine ownership/type conflict returns `connection_conflict`

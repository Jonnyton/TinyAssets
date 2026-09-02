# http-connections-and-outbound-authority (delta)

## ADDED Requirements

### Requirement: A connection is granted exactly or in full

Every outbound connection SHALL carry one `access_mode`, either `exact` or
`full`. `exact` is the existing grant: the declared endpoints, verbs and
repositories, and nothing else. `full` means everything the credential
itself can do on the channel's declared hosts. Every existing connection,
and every connection whose mode cannot be read, SHALL be `exact`: a
migration must never widen a grant somebody already made.

No wildcard SHALL be stored. The mode is the authority; endpoint rows,
git scopes and consent rows keep their existing grammar, so no `*/*` can
reach `require_git_scope`, the git transport, or a consent key.

#### Scenario: a connection created without a mode
- **WHEN** a connection is created and no `access_mode` is given
- **THEN** it is `exact`

#### Scenario: a row written before the column existed
- **WHEN** a connection row carries an empty `access_mode`
- **THEN** it reads as `exact`

### Requirement: Full admits the channel, never the safety checks

On a `full` connection the outbound driver SHALL admit any path, any query
and any of the permitted verbs once the request host matches one of the
connection's declared hosts, and SHALL refuse any other host. Every check
that is not the endpoint template SHALL run unchanged: the canonical HTTPS
parse (scheme, userinfo, port, dot segments, encoded separators, double
encoding), the verb allowlist, and the DNS resolution plus
globally-routable-address validation that run after the allowlist and
immediately before the socket. A connection with no declared endpoints
SHALL admit nothing in either mode.

#### Scenario: any path on a declared host
- **WHEN** a `full` connection requests `/` or any deeper path with any query on a declared host
- **THEN** the request is admitted

#### Scenario: a host the channel never declared
- **WHEN** a `full` connection requests a host outside its declared set
- **THEN** the request is refused

#### Scenario: a declared host that resolves to a private address
- **WHEN** a `full` connection's declared host resolves to a loopback or private address
- **THEN** the request is refused before any socket is opened

### Requirement: Full covers every repository the key reaches

On a `full` connection `has_git_scope` SHALL return true for any well-formed
repository and any git kind, and the workspace SHALL treat checkout, push and
provision consents as satisfied for any repository on the connection's git
host. The connection, host and revocation checks SHALL stay exact in both
modes, and a caller SHALL NOT be able to declare its own grant full: the mode
comes from the stored connection.

#### Scenario: a repository the grant never named
- **WHEN** a `full` connection checks out a repository with no consent row
- **THEN** the checkout proceeds

#### Scenario: the same connection revoked
- **WHEN** a revoked connection is `full`
- **THEN** it grants nothing

### Requirement: One ask, and one sentence that says all of it

`request_from_user` SHALL accept `"access": "full"` on `connect_http` and
`extend_http`. A full `extend_http` SHALL carry no endpoints and no scopes; a
full `connect_http` SHALL name 1 to 4 `hosts` and no endpoints or scopes, and
those hosts SHALL be validated by the same parser the deposit uses. Any other
`access` value SHALL be refused rather than narrowed.

The tab SHALL render one sentence naming the destination, the hosts, and --
when the channel's git host is a recognised forge -- clone, push and building
the repository in the universe's sandbox. It SHALL NOT render a wildcard, and
SHALL NOT claim a host serves git when that is not known.

A later widening on a `full` channel SHALL answer `already_held`, in either
direction, so the agent acts instead of asking again.

#### Scenario: a full ask that also names endpoints
- **WHEN** an ask carries `access: full` and `endpoints`
- **THEN** it is refused

#### Scenario: a widening on a channel already granted in full
- **WHEN** an `extend_http` ask names a channel whose connection is `full`
- **THEN** the verdict is `already_held` and no tab is raised

### Requirement: Removing a key revokes what it authorized

`remove_http` SHALL revoke every consent keyed on the removed connection, and
no consent keyed on any other connection. A re-deposit under the same
destination SHALL start with no consents.

#### Scenario: two connections in one universe
- **WHEN** one connection is removed
- **THEN** its consents are revoked and the other connection's stay active

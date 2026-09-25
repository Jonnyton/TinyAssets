# universe-connection-oauth (delta)

## ADDED Requirements

### Requirement: A connect request prefers OAuth when the provider offers it

For every `connect` ask, the platform SHALL decide whether the provider offers
OAuth that covers the request. Sign-in endpoints (authorize, token,
registration) SHALL come only from standard discovery rooted at the
connection's own declared hosts (RFC 9728 protected-resource metadata, then
RFC 8414 or OpenID configuration on the server it names). The ask's `oauth`
MAY state the `scopes` the use needs and a public `client_id`, and SHALL NOT
name an endpoint or issuer. It SHALL NOT use per-provider code. The consent
sentence SHALL name every host the sign-in contacts. An offer SHALL
require all of the following:

- the authorization-code grant;
- PKCE S256;
- every requested scope, when the server lists its scopes;
- a public client, either supplied or dynamically registrable.

When there is an offer, signing in SHALL be the request's primary action and
key fields SHALL be optional. When there is none, the ask SHALL be a key
paste, and the requester SHALL be told the reason.

#### Scenario: a provider that offers OAuth
- **WHEN** an agent raises a `connect` ask for an API whose resource metadata names an authorization server supporting PKCE S256 and the requested scopes
- **THEN** the stored ask carries the resolved offer, the response says `primary: "sign_in"`, the rail's primary action is "Sign in with <authorize host>", and key paste is secondary

#### Scenario: a provider that does not
- **WHEN** discovery finds no authorization server, or it lacks S256 or a requested scope
- **THEN** the ask requires key fields and the response carries `oauth_unavailable` with the reason

#### Scenario: a forged offer
- **WHEN** an ask's `oauth` names an authorize, token or registration URL or an issuer, or carries anything but `scopes` and `client_id`, or any client secret
- **THEN** the ask is refused

### Requirement: Signing in answers the connect request

Signing in SHALL use authorization code + PKCE for a public client, with the
fixed callback `/mcp/app/model-callback/connect` and the flow handle as
`state`. The flow SHALL be bound to one owner, one universe, one pending
request and the exact action shown, and SHALL be redeemable once. When the
server supports RFC 9207, the callback's `iss` SHALL equal the discovered
issuer. The stored bundle's token URL SHALL equal the discovered token URL
the owner approved. The code
exchange SHALL deposit the tokens through the same answer path as a pasted
key, under auth scheme `oauth2`. No token SHALL be returned to the app or
crossed over MCP.

#### Scenario: the owner signs in
- **WHEN** the owner taps Sign in, approves at the provider and returns
- **THEN** the request is answered, the connection exists with auth scheme `oauth2`, and it serves calls with the access token

#### Scenario: replay or another owner
- **WHEN** the returned code is redeemed a second time, or by another owner or universe, or with the wrong verifier
- **THEN** nothing is redeemed or deposited

### Requirement: OAuth connections refresh generically

The credential-blind broker SHALL send an `oauth2` connection's current access
token. It SHALL refresh before expiry, and once when the service answers 401.
Refresh SHALL be single-flight per connection across threads and processes, so
no single-use refresh token is sent twice. A rotated refresh token SHALL be
persisted through the vault's atomic write before the new access token is
used; the vault SHALL be held before the refresh token is spent, so a
rotated token is never lost to lock contention. A failed refresh SHALL surface as a connection failure record with stage
`connection`, class `auth`, and the token endpoint's own bounded detail.

#### Scenario: expiry
- **WHEN** a call is made within the refresh window of the token's expiry
- **THEN** the token is refreshed before the call, and the rotated refresh token is the one stored

#### Scenario: concurrent callers
- **WHEN** several calls on one expiring connection start at once
- **THEN** exactly one refresh reaches the token endpoint and every call succeeds

#### Scenario: refresh refused
- **WHEN** the token endpoint refuses the refresh
- **THEN** the call fails with `{stage: connection, class: auth, provider_detail}` and nothing is sent to the service

### Requirement: OAuth tokens stay in their universe

An `oauth2` token bundle SHALL be written only by a completed sign-in. It SHALL
NOT be pasteable, and SHALL NOT be sent under any other auth scheme. It SHALL
be readable only from the owning universe's vault, through that universe's
grant.

#### Scenario: another universe
- **WHEN** another owner or universe tries to start, redeem or use an OAuth connection that is not theirs
- **THEN** it is refused, and the provider is never contacted with the owner's tokens

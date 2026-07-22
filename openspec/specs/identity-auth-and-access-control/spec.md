# Identity, Auth, and Access Control

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

WorkOS OAuth 2.1 resource-server auth with anonymous-read/authenticated-write posture, pre-dispatch 401 write challenges, founder home auto-birth, and two-axis authorization (universe visibility plus ownership ACL).
## Requirements
### Requirement: Auth provider is selected by configuration, defaulting to no-auth

The server SHALL select its auth provider at startup from the `UNIVERSE_SERVER_AUTH`
environment variable: `workos` selects the WorkOS AuthKit provider (the server acting
as an OAuth 2.1 Resource Server that validates AuthKit-issued bearer JWTs);
`true`/`1`/`yes`/`oauth` selects the legacy self-hosted OAuth provider; `optional`/`resolve`
selects the optional OAuth provider; any other value (including unset) selects the dev
no-auth provider. The provider factory lives in `tinyassets/auth/provider.py`.

#### Scenario: WorkOS mode selects the Resource Server provider
- **WHEN** `UNIVERSE_SERVER_AUTH=workos` and the provider factory runs
- **THEN** the WorkOS AuthKit provider is created as an OAuth Resource Server
- **AND** it validates AuthKit bearer JWTs rather than running its own authorization flow

#### Scenario: unset config yields the dev no-auth provider
- **WHEN** `UNIVERSE_SERVER_AUTH` is unset or an unrecognized value
- **THEN** the dev (no-auth) provider is created
- **AND** local and test flows run without authentication

### Requirement: Anonymous read, authenticated write (resolve-always posture)

In the WorkOS and optional providers the server SHALL keep anonymous reads open while
requiring an authenticated principal for every write, costly, or admin effect. These
providers report `is_auth_required()` false (anonymous callers are never rejected outright)
and `resolve_always_writes()` true, and the base class derives `writes_require_identity()`
from those flags so both the pre-dispatch write challenge and the tool-layer scope gate engage.
As-built limitation: the dev provider leaves writes open for local/test flows; the resolve-always
posture applies only to the OAuth-backed providers.

#### Scenario: anonymous read is allowed
- **WHEN** an anonymous caller invokes a read-effect action on a public universe
- **THEN** the request succeeds without authentication

#### Scenario: anonymous write is refused
- **WHEN** an anonymous caller attempts a write/costly/admin effect under a resolve-always provider
- **THEN** the action is refused because no authenticated identity is present

### Requirement: Bearer JWT validation is fail-closed, RS256-pinned, and audience-bound

When resolving a WorkOS bearer token the server SHALL pin the accepted signature algorithm to
RS256 (defending against algorithm-substitution), bind validation to the AuthKit issuer, require
the `exp` and `sub` claims, and reject any token whose subject is missing or `anonymous`. Audience
binding to the registered MCP resource indicator (`WORKOS_MCP_RESOURCE`) SHALL be required by
default; construction fails closed when it is absent. Token resolution logic lives in
`tinyassets/auth/workos_provider.py`. As-built limitation: audience validation may be disabled
only by explicitly setting `WORKOS_ALLOW_NO_AUDIENCE` truthy, which is intended for local/dev use
and logs a warning; production must leave it unset.

#### Scenario: a same-issuer token without required claims is rejected
- **WHEN** a bearer token is signed by the issuer but lacks a valid `sub` or `exp`
- **THEN** token resolution returns no identity and the caller is treated as anonymous

#### Scenario: audience binding is required in production configuration
- **WHEN** the WorkOS provider is constructed without `WORKOS_MCP_RESOURCE` and without the dev opt-out
- **THEN** construction fails closed rather than accepting any same-issuer token

### Requirement: Anonymous writes on pure-write handles draw a pre-dispatch 401 challenge

Before dispatch, the auth middleware SHALL classify each anonymous `POST` `tools/call` against a
registry of pure-write MCP handles and, when the call targets a registered pure-write handle under
a write-gating provider, answer an RFC 9728 `401` with a `WWW-Authenticate` header pointing at the
Protected Resource Metadata so the client launches OAuth. Exactly four handles opt into this registry —
`write_graph`, `run_graph`, `write_page`, and `converse` — because mixed read/write dispatch tools must
not be challenged (that would break anonymous public reads). A present-but-invalid bearer token SHALL
answer `401` with `error="invalid_token"`. Anonymous request bodies SHALL be buffered only up to a
1 MiB cap, above which the request answers `413` without reading the remainder. The middleware lives in
`tinyassets/auth/middleware.py`.

#### Scenario: anonymous call to a pure-write handle is challenged
- **WHEN** an anonymous `tools/call` targets `write_graph` under a resolve-always provider
- **THEN** the server answers `401` with a `WWW-Authenticate` challenge before dispatch
- **AND** the client can start the OAuth flow from the advertised resource metadata

#### Scenario: oversized anonymous body is rejected
- **WHEN** an anonymous request body exceeds the 1 MiB cap
- **THEN** the server answers `413` without buffering the rest of the body

#### Scenario: missing-token challenge is gated on require-auth
- **WHEN** a bearer token is absent on the MCP endpoint and `WORKOS_REQUIRE_AUTH` is truthy
- **THEN** the server answers a missing-credentials `401` so the connector launches OAuth
- **AND** when `WORKOS_REQUIRE_AUTH` is not truthy the connector may connect anonymously and still read

### Requirement: Protected Resource Metadata advertises the AuthKit issuer and OIDC scopes only

In WorkOS mode the server SHALL advertise, at the Protected Resource Metadata endpoint
(`/.well-known/oauth-protected-resource` and its `/mcp`-prefixed mirror), the AuthKit issuer as the
authorization server plus the registered MCP resource indicator, and SHALL list only standard OIDC
scopes (`openid`, `profile`, `email`, `offline_access`).
It SHALL NOT advertise internal `tinyassets.*` action scopes, because AuthKit cannot issue them and
per-action authorization is enforced at the Resource Server via founder grants, not via OAuth scopes.
The metadata is produced in `tinyassets/auth/wellknown.py`.

#### Scenario: WorkOS PRM lists only OIDC scopes
- **WHEN** a client fetches the Protected Resource Metadata in WorkOS mode
- **THEN** the advertised authorization server is the AuthKit issuer and the resource indicator is present
- **AND** `scopes_supported` contains only OIDC scopes and no internal `tinyassets.*` scope

### Requirement: Founder home auto-births exactly once on first authenticated contact

The server SHALL, on the first authenticated `converse` call with no `graph_id` (the founder's opening
relay, and the only handle that performs first-contact birth), ensure the founder has a home universe.
It SHALL check the create scope BEFORE reserving any home id, so a founder lacking create scope leaves
no phantom binding and the conversation entry returns a creation failure with
`auth_scope_required=true`. Reservation SHALL be atomic (an `INSERT ... ON
CONFLICT DO NOTHING` on the founder key) so concurrent first-contact calls across worker threads yield
exactly one home id, and materialization SHALL be serialized so a reserved id is created once, with
success defined as the universe's `soul.md` being present. After successful materialization and
binding, the resolver SHALL return the bound home id to the originating `converse` entry path.
Whether that conversation can select and invoke universe intelligence is a subsequent
authority/execution decision outside this birth contract; successful birth SHALL NOT guarantee
provider execution or a first-person reply. Anonymous sessions SHALL never trigger birth. Both `get_status` and the
`read_graph target=status` alias SHALL pass through as pure reads without first-contact birth. This
logic lives in `tinyassets/api/first_contact.py` with the atomic claim in
`tinyassets/daemon_server.py`.

Per the 2026-07-22 host directive
(`docs/design-notes/2026-07-22-first-contact-birth-moves-to-converse.md`), birth moved off
`get_status` and its `allow_first_contact_birth` parameter was deleted, because a mutating *opening*
call proved refusable in production: the assistant declined to call `get_status` on the grounds that
its own tool description advertised a side effect. The 2026-07-15 commitment this replaces — a founder
never needs to know an incantation — is upheld, since the opening message is itself the relay.

#### Scenario: first authenticated converse births one home
- **WHEN** an authenticated founder with create scope and no bound home issues their opening `converse` with no `graph_id`
- **THEN** exactly one home universe is reserved, materialized, and bound to the founder
- **AND** the originating conversation entry continues with that bound home as its target
- **AND** completion of birth does not by itself assert that provider execution or a first-person reply succeeded

#### Scenario: read-only founder leaves no phantom binding
- **WHEN** an authenticated founder lacking create scope issues their opening `converse` with no home
- **THEN** no home binding is created
- **AND** the result reports that the home could not be created or loaded with `auth_scope_required=true`

#### Scenario: anonymous first contact never births
- **WHEN** an anonymous session calls `converse` or `get_status`
- **THEN** no home universe is created

#### Scenario: get_status never births
- **WHEN** an authenticated founder with create scope and no bound home calls `get_status`
- **THEN** no home universe is created and the call is a pure read
- **AND** a repeated call returns the identical snapshot

### Requirement: The permission actor is the authenticated subject with no environment fallback

The permission actor SHALL be exactly the authenticated request subject, resolving to `anonymous` when
unauthenticated, with no environment-variable fallback. No universe-server environment variable SHALL
ever confer write authority over a universe. The actor resolver lives in `tinyassets/api/permissions.py`.

#### Scenario: unauthenticated request resolves to anonymous
- **WHEN** a request carries no authenticated identity
- **THEN** the permission actor is `anonymous`
- **AND** no environment variable can substitute a privileged actor

### Requirement: Access is controlled on two orthogonal axes — visibility and ownership

Universe access SHALL be decided on two independent axes: visibility (`public_read`, where a universe
with no recorded rule is publicly readable by default, private only when explicitly set, and failing
closed on any real rules-read error) and ownership (a `universe_acl` grant set of `read`/`write`/`admin`).
Anonymous callers SHALL be able to read public universes only; reads of a private universe and all writes
SHALL require the appropriate grant (`write` or `admin` for writes). An admin grant SHALL NOT make a
universe private — visibility and ownership are not conflated. Privileged dispatch actions SHALL
additionally pass a per-action scope gate that accepts either the fine-grained action scope or the coarse
effect grant. This model lives in `tinyassets/api/permissions.py` and the scope gate in
`tinyassets/auth/middleware.py`.

#### Scenario: anonymous reads public but not private
- **WHEN** an anonymous caller reads a universe with no visibility rule
- **THEN** the read is allowed
- **AND** the same caller reading a `public_read=False` universe is denied

#### Scenario: write requires a write or admin grant
- **WHEN** an authenticated actor without a `write`/`admin` grant attempts a universe write
- **THEN** the write is denied even though the actor is authenticated

#### Scenario: rules-read error fails closed
- **WHEN** the visibility rule for a universe cannot be read due to a real error
- **THEN** the universe is treated as not publicly readable

# BYO LLM deposit browser form

## ADDED Requirements

### Requirement: Owner deposits through a browser form without the token entering chat

The platform SHALL offer a browser deposit transport in which the universe owner
signs in through the identity provider and submits their Claude/Codex subscription
credential through a web form, so the token never enters any chatbot transcript or
model context. The transport SHALL authenticate the owner to a validated subject
using the same resource-server token validator the `/mcp` endpoint uses, then perform
the deposit as that subject through the same owner-scoped vault write as the chatbot
deposit path, with equivalent owner-scoping and fail-closed behavior. It SHALL NOT
introduce a second, independent credential writer.

#### Scenario: Owner deposits through the browser form

- **WHEN** the owner completes an identity-provider sign-in in the browser and posts
  their subscription credential to the deposit form
- **THEN** the server verifies the owner's authenticated subject and deposits the
  credential owned to that subject through the chatbot path's owner-scoped vault write
- **AND** the token is never placed into any chat transcript or model context

#### Scenario: Deposit inherits the owner-only rule

- **WHEN** the authenticated browser subject is not the owner/admin of the target
  universe
- **THEN** the deposit is refused with no vault, ownership, custody, binding, or
  serving mutation, identical to the chatbot path

### Requirement: The deposit flow carries state without cookies via signed tokens

Because the edge strips `Set-Cookie` on the MCP path, the flow SHALL carry its
callback-CSRF state and its deposit session in signed, self-contained tokens with a
server-side expiry, never in cookies. The callback SHALL reject a missing, altered,
or expired state token, and the form POST SHALL reject a missing, altered, or expired
session token, writing nothing in either case. The OAuth `redirect_uri` SHALL be a
fixed literal and SHALL NOT be reflected from request input.

#### Scenario: Tampered or expired state is rejected

- **WHEN** the callback receives a state token that is absent, altered, or past its
  expiry
- **THEN** the callback refuses to exchange the code and no credential is written

#### Scenario: Unauthenticated form post deposits nothing

- **WHEN** the form POST arrives without a valid, unexpired signed session proof
- **THEN** the request is refused and no credential is written

### Requirement: The form routes are a narrow, ordered exemption from the MCP bearer challenge

The `/mcp/connect` and `/mcp/connect/*` routes SHALL be exempted from the MCP bearer
401 challenge that applies to `/mcp` and other `/mcp/*` paths, and SHALL be matched
ahead of that challenge, so that the flow's own signed-state and signed-session
validation is the sole authentication boundary for these routes. The exemption SHALL
be scoped to exactly these routes and SHALL NOT make any other `/mcp` path reachable
without authentication.

#### Scenario: Connect routes are reachable but no other /mcp path is opened

- **WHEN** an anonymous browser requests `GET /mcp/connect/login`
- **THEN** the login route runs its own logic instead of returning the MCP bearer 401
- **AND** an anonymous request to `/mcp` or any non-connect `/mcp/*` path still
  returns the 401 challenge

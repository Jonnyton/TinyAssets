# Universal inbound webhook — delta specs

## ADDED Requirements

### Requirement: A branch can be triggered by an inbound webhook via an unguessable per-branch URL

The platform SHALL expose a stable inbound receiver at `POST /hooks/<token>` where `<token>`
is an unguessable secret minted per (branch, universe). A POST to a valid token SHALL enqueue
a run of exactly that branch, executed as that branch's owning universe, with the request body
supplied as run input. The token SHALL map to exactly one branch and one universe, so an
inbound POST can never trigger a different branch or act as a different universe.

#### Scenario: A valid token runs its bound branch as the owning universe

- **WHEN** an HTTP `POST /hooks/<token>` arrives with a valid token
- **THEN** exactly the branch bound to that token is enqueued to run
- **AND** the run's actor is the token's owning universe (never another universe, never a
  platform/host identity)
- **AND** the request body is passed to the run as input, preserved verbatim

#### Scenario: An unknown or malformed token is refused without disclosure

- **WHEN** a POST arrives with a token that matches no binding (unknown, revoked, or malformed)
- **THEN** the receiver responds 404 with no body that distinguishes "no such token" from
  "revoked" from "malformed" (no enumeration signal), and enqueues nothing

#### Scenario: One universe's token cannot trigger another universe's branch

- **WHEN** a token minted for universe A's branch is used
- **THEN** only universe A's branch runs, as universe A — there is no input or header on the
  request that can redirect the run to another branch, universe, or identity

#### Scenario: An oversized or unreadable body is refused, not run

- **WHEN** a POST body exceeds the receiver's size cap or cannot be read
- **THEN** the request is refused (413/400) and no branch is enqueued

### Requirement: Minting and revoking a branch's inbound token is a user-controlled, per-universe operation

A universe's founder SHALL be able to mint an inbound webhook token for one of their own
branches and revoke it, through the user surface (MCP/chatbot), using only their own universe's
authority. Minting SHALL NOT require any platform code change per channel — the same token
works for any channel able to POST to the URL.

#### Scenario: The founder mints a token for their own branch and gets the URL

- **WHEN** the founder requests an inbound webhook for a branch they own
- **THEN** a fresh unguessable token is minted, bound to that (branch, universe), and the full
  `https://<domain>/hooks/<token>` URL is returned for them to paste into the channel's webhook
  settings

#### Scenario: A founder cannot mint a token for a branch they do not own

- **WHEN** a caller requests an inbound webhook for a branch owned by a different universe
- **THEN** the request is refused; a token can only be minted for a branch the caller's own
  universe owns

## MODIFIED Requirements

### Requirement: Agent Village Observes Durable Coordination State

The `command_center` runtime SHALL serve a zero-build browser interface and a JSON state endpoint that aggregate detected provider sessions, `STATUS.md` claims, worktree status, recent file/git/activity signals, local universes, and reachable public MCP state. Missing transcripts, provider homes, worktree probes, or remote platform data MUST degrade to absent or explicitly unavailable state rather than fabricated agents, universes, or health. The CLI SHALL default to loopback. Every server process SHALL use either a minimum-strength operator-supplied ASCII token or a newly generated high-entropy token. Static bootstrap assets and the liveness probe MAY be unauthenticated, but every private state, chat, or provider API request SHALL require the matching token in `X-Village-Token`, compared in constant time. Malformed or non-ASCII bearer headers SHALL fail closed with an unauthorized response. Query-string tokens SHALL NOT authenticate any API request. The browser SHALL accept a share token from the URL fragment, remove that fragment from visible history, retain the token for no longer than the browser session, and send it only in the request header. When the browser lacks a valid token, it SHALL display a persistent access-required message that directs the operator to the printed share URL.

#### Scenario: Remote world data is unreachable

- **WHEN** the configured public MCP endpoint cannot be read
- **THEN** the snapshot keeps local coordination and universe evidence available
- **AND** it identifies the remote world as unavailable without synthesizing remote entities

#### Scenario: Zero-config startup is authenticated

- **WHEN** the command center starts without an operator-supplied token
- **THEN** it generates a high-entropy token before serving requests
- **AND** a private API request without that token is rejected

#### Scenario: Static bootstrap does not disclose private state

- **WHEN** a browser requests the app shell or liveness probe without a token
- **THEN** the server may return that static or health response
- **AND** requests for state, chat, or provider data remain unauthorized

#### Scenario: Fragment bootstrap uses header-only API authentication

- **WHEN** the operator opens the printed share URL
- **THEN** the browser obtains the token from the fragment and removes it from visible history
- **AND** subsequent private API requests carry `X-Village-Token` without a token query parameter

#### Scenario: Query bearer is rejected

- **WHEN** a private API request supplies the correct token only as `?token=`
- **THEN** the server returns unauthorized

#### Scenario: Malformed bearer fails closed

- **WHEN** a private API request supplies a non-ASCII bearer header
- **THEN** the server returns unauthorized without raising an unhandled exception

#### Scenario: Browser starts without a bearer

- **WHEN** the app shell loads without a fragment or session token
- **THEN** the browser persistently explains that access is required
- **AND** it directs the operator to reopen the share URL printed by the server

### Requirement: Agent Village Writes Only Through Explicit Talk And Hire Actions

The command center SHALL remain read-only except for explicit authenticated talk and hire requests. It SHALL reject missing, malformed, negative, or greater-than-64-KiB request lengths and non-object JSON before invoking collector code. Talking to an agent SHALL append a durable inbox/chat record and SHALL dispatch a provider CLI only when dispatch mode is enabled. Talking to a running local universe SHALL write an engine-compatible note; talking to a dormant universe SHALL pin an inbox note. Hiring SHALL validate the universe and advertised provider capability, MAY update the universe's preferred-writer preset, and SHALL spawn peer CLI work only for a provider marked available and dispatchable. Hosted or market capacity MUST remain disabled and honestly labeled while that execution stack is absent.

#### Scenario: Cross-site-shaped write has no bearer

- **WHEN** a talk or hire request arrives without the matching `X-Village-Token`
- **THEN** the server returns unauthorized before reading or invoking the requested action
- **AND** no inbox, universe, preset, or provider process is mutated

#### Scenario: Oversized write is rejected before collector invocation

- **WHEN** an authenticated talk or hire request declares a body greater than 64 KiB
- **THEN** the server rejects the request without reading a truncated prefix
- **AND** no collector action runs

#### Scenario: Agent talk without dispatch mode

- **WHEN** an authenticated user sends a valid message to an agent while dispatch mode is disabled
- **THEN** the command center appends the message to that agent's durable village inbox and chat history
- **AND** it starts no provider CLI process

#### Scenario: Unsupported market hire is refused

- **WHEN** an authenticated hire request selects hosted or market capacity advertised as unavailable
- **THEN** the command center returns a validation failure and spawns no worker
- **AND** the response preserves the current coming-later limitation

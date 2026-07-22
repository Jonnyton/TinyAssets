## MODIFIED Requirements

### Requirement: Read-Open, Write-Challenged Authentication Boundary

Pure-read handles (`read_graph`, `read_page`, and the `read_graph target=status` alias) SHALL remain callable anonymously. Pure-write / costly-effect handles (`write_graph`, `run_graph`, `write_page`, `converse`) SHALL answer an anonymous `tools/call` with an HTTP 401 + `WWW-Authenticate` challenge pre-dispatch so the MCP client launches OAuth, since a tool-JSON rejection would not prompt sign-in. `converse` is the connector's opening call: it is founder-only, relays the founder's turn to the universe's own intelligence, and for an authenticated founder with no home universe it resolves-or-creates and binds that home as a one-time onboarding side effect before continuing the originating conversation entry. Completion of that provisioning step SHALL NOT by itself assert that downstream provider execution or a first-person reply succeeded. `get_status` and the `read_graph target=status` alias are both pure reads (`readOnlyHint=True`) and never provision. Per the 2026-07-22 host directive (`docs/design-notes/2026-07-22-first-contact-birth-moves-to-converse.md`) birth moved off `get_status`, because a mutating *opening* call proved refusable in production — the assistant declined to call it, citing the side effect its own tool description advertised, which contradicted the shipped instruction to call it first.

#### Scenario: Anonymous write handle triggers an OAuth challenge

- **WHEN** an unauthenticated client calls `write_graph`, `run_graph`, `write_page`, or `converse`
- **THEN** the server answers HTTP 401 with a `WWW-Authenticate` header pre-dispatch, launching the OAuth sign-in flow

#### Scenario: Anonymous read handle stays open

- **WHEN** an unauthenticated client calls `read_graph` or `read_page`
- **THEN** the read is served without an auth challenge

#### Scenario: First-contact provisioning via converse

- **WHEN** an authenticated founder with no home universe issues their opening `converse` with no `graph_id`
- **THEN** a home universe is created and bound and the originating conversation entry continues with that home as its target
- **AND** completion of provisioning does not by itself assert that provider execution or a first-person reply succeeded
- **AND** a later `converse` for the same founder reaches the same home with no further creation

#### Scenario: get_status never provisions

- **WHEN** an authenticated founder with no home universe calls `get_status`
- **THEN** no universe is created and the call is a pure read (`readOnlyHint=True`)

#### Scenario: The read alias never provisions

- **WHEN** any caller invokes `read_graph(target="status")`
- **THEN** no universe is created

#### Scenario: Non-founder is refused converse

- **WHEN** an anonymous or non-owner caller reaches `converse` for a universe they do not own
- **THEN** the reply is an auth error and no message is relayed to the universe intelligence

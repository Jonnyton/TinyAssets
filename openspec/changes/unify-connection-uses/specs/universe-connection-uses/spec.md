# universe-connection-uses (delta)

## ADDED Requirements

### Requirement: One connection serves platforms and models

A universe connection SHALL declare what it is used for. `uses.call` lets
workflow effects call it, and it is the default. `uses.model{wire, models,
billing}` lets the universe run its model on it. Both uses SHALL share one
connection, grant, allowlist, vault credential and credential-blind broker.
No vendor-specific code SHALL be needed to connect a model or platform.

#### Scenario: a model nobody wrote code for
- **WHEN** an owner connects an endpoint that speaks a bundled wire dialect,
  with a static model list and `free` or `flat` billing
- **THEN** a model turn with tools runs on it through the broker at the
  endpoint's own path, and no platform code names the vendor

#### Scenario: a platform nobody wrote code for
- **WHEN** an owner connects an API with `uses.call` and a constant header
- **THEN** a workflow `authenticated_external_call` reaches it with the
  credential and the constant header applied by the broker

### Requirement: The connect request is the setup

The request rail SHALL accept a `connect` action: the `connect_http` fields
plus `uses` and `constant_headers`, validated by the same code as
`connect_http`. The rail sentence SHALL name the models, the billing and the
constant headers. One owner answer SHALL do three things:

- deposit the credential to the vault, and nowhere else;
- create the connection and grant;
- record the uses and register the model source.

When the universe has no current serving model and the connection declares a
model use, the answer SHALL make it the universe's serving source. The access
SHALL be explicit and limited to the declared models, with free-only cost caps.
A universe that already has a serving model SHALL be left unchanged.

#### Scenario: unpowered universe
- **WHEN** the owner answers a `connect` ask with a model use and nothing powers the universe
- **THEN** the universe serves on that connection with access to exactly the declared models and no spending

#### Scenario: powered universe
- **WHEN** the owner answers a `connect` ask with a model use and the universe already serves
- **THEN** serving is unchanged and the connection is available to select

#### Scenario: a model use with nowhere to post
- **WHEN** an exact `connect` ask declares a model use but no POST endpoint
- **THEN** the ask is refused before anything is shown or stored

### Requirement: Wire dialects are bundled data resolved by structure

Model wire formats SHALL be bundled documents named by structure
(`chat_messages`, `content_blocks`). Each document declares:

- the message dialect and the tool dialect;
- where the system prompt goes;
- the text path;
- the headers the wire itself needs;
- the agent envelope, for dialects that support tools.

Stored rows that use the historical names (`openai_chat`,
`anthropic_messages`) SHALL resolve to the same installed wire unchanged. An
unknown wire SHALL be refused.

#### Scenario: stored alias
- **WHEN** a stored definition names `openai_chat`
- **THEN** it executes the same wire as `chat_messages`, and selection treats the two as one dialect

### Requirement: Declared models and billing

A model use SHALL list 1-64 models as `{id, tools, context}`, and its
billing SHALL be `free` or `flat`. A declared model use SHALL be refused on a
connection that has a priced `model_discovery` catalogue, or whose grant's
model source has accepted access with cost caps. Where both exist, the
catalogue SHALL decide. Declared models SHALL be admitted as
unmetered, owner-configured evidence without a catalogue fetch. They SHALL
grant nothing without accepted model access. `metered` billing SHALL be
refused here and SHALL need a priced `model_discovery` source contract.

#### Scenario: the agent relabels a paid model as free
- **WHEN** a model use declaring a catalogue's paid model as `free` is written to a connection with a priced catalogue
- **THEN** it is refused, and selection still reads the catalogue's prices and the owner's caps

#### Scenario: metered without prices
- **WHEN** a model use declares `metered` billing
- **THEN** it is refused with a pointer to the priced source contract

### Requirement: Constant headers are non-secret and cannot replace auth

A connection's constant headers SHALL be at most 16 valid header tokens with
single-line values of at most 256 characters. The following SHALL be refused:

- any name the broker forbids (for example `Authorization`, `Host`, or a
  framing header);
- any credential-style name (for example `X-Api-Key` or `X-Auth-Token`);
- any value that looks like a credential.

A request header that matches an auth header case-insensitively SHALL be
dropped before auth is applied.

The broker SHALL apply constant headers over a node's same-named headers,
case-insensitively, and the auth scheme SHALL be applied after them. If the
headers cannot be read, dispatch SHALL fail.

#### Scenario: a node sends an older version header
- **WHEN** a node sends `x-api-version: 1` and the connection declares `X-Api-Version: 2`
- **THEN** the request carries only `X-Api-Version: 2`

### Requirement: The owner's agent configures non-secret fields

`write_graph target=connection operation=configure` SHALL set
`constant_headers` on a connection the caller owns that is granted to the
universe. It SHALL be available on both the served surface and the public
connector. It SHALL never touch the secret, endpoints or serving selection.
It SHALL never create or change a model use, because a model list and its
billing need the owner's answer to a `connect` ask.
A connection the caller does not hold SHALL return the uniform `not_found`.
`read_graph target=connections` SHALL show each connection's uses and
constant headers.

#### Scenario: agent adds a version header
- **WHEN** the agent configures `constant_headers` on a held connection
- **THEN** later calls carry it and `read_graph target=connections` shows it

## ADDED Requirements

### Requirement: Graph handles manage cross-user node connections
Canonical graph handles SHALL expose receiver contracts and lifecycle, sender
output links, delivery and receipt inspection through the same validated boundary
for connector callers and every provider-backed served app agent.

#### Scenario: Two users collaborate through ordinary conversation
- **WHEN** one user asks the app agent to accept a chosen deliverable from a selected user and that user asks their own agent to connect and send a node output
- **THEN** each agent can author its own workflow, manage its side of the connection and inspect the permitted outcome
- **AND** no operator edits either user's private workflow or adds a provider-specific tool

#### Scenario: Contract inspection remains narrow
- **WHEN** a permitted sender inspects a receiving address
- **THEN** the result includes the advertised description, contract and generation
- **AND** excludes the receiver's private graph, credentials, other senders and other deliveries

#### Scenario: Receipt read is authenticated
- **WHEN** an unrelated authenticated account or an anonymous caller supplies a delivery identifier
- **THEN** the request reveals no delivery record or artifact

#### Scenario: Exposed controls match advertised handles
- **WHEN** canonical tools and the served engine tool list are checked after deployment
- **THEN** the existing canonical handle set is unchanged and supported collaboration actions are usable through both routes

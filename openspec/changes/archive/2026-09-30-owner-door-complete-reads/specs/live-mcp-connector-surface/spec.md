# live-mcp-connector-surface (delta)

## ADDED Requirements

### Requirement: The connector bounds reads only as a model-door projection

The connector's single-result ceiling SHALL apply to `read_graph` replies as a
projection at the model door. It SHALL NOT be the path by which the owner's own
app reads its data; the app reads through the owner door
(`onboarding-web-app`). The connector's ceiling-exempt set SHALL contain only
reads whose contract a truncation marker would break: `run_file` and
`conversation` (caller-bounded chunks carrying a cursor) and `conversation_turn`
(the universe's committed reply, the same payload `converse` returns). No entry
SHALL exist because a first-party client reads it.

#### Scenario: A model-sized reply is bounded visibly
- **WHEN** a `read_graph` reply on the connector exceeds the ceiling
- **THEN** the reply is the truncation marker with `truncated: true`, the original size and a narrowing hint
- **AND** the owner door serving the same read returns the complete document

#### Scenario: The pending-request read is complete before any projection
- **WHEN** an owner has more pending requests than any former default page
- **THEN** `read_graph target=pending_requests` builds the complete list before the ceiling is applied
- **AND** `limit` does not cut the owner's own pending rows

## MODIFIED Requirements

### Requirement: Shared unpowered model catalogue
The read_graph handle SHALL accept target=model_options without changing its
arguments. On the connector (the model door) its structured reply is the bounded
catalogue projection; the complete document is served to the owner by the owner
door. The read SHALL
require the authenticated owner's complete current home and explicit admin ACL.
It SHALL NOT create a home, agent, assignment, preference or inference grant.

#### Scenario: Unpowered current home
- **WHEN** the owner has a complete home but no serving agent or working model
- **THEN** the read returns available registered inventory or an empty catalogue
- **AND** unavailable sources and missing saved model references remain distinguishable

#### Scenario: Unknown or foreign scope
- **WHEN** an explicit graph is not the current owned home or lacks admin access
- **THEN** the read refuses without disclosing that graph's model inventory
- **AND** omitted scope never resolves to a designated public universe

#### Scenario: Complete choices at the owner door, a projection at the model door
- **WHEN** approved discovery returns more models than fit one model-context reply
- **THEN** the owner door (`POST /app/api/read` with `target=model_options`) returns every protocol-bounded choice
- **AND** the connector's `read_graph target=model_options` returns the bounded `compact_model_options` projection, identical to `target=model_options_summary`, whose cursor reaches every model exactly once
- **AND** neither door silently hides a model: the projection always carries the catalogue totals

#### Scenario: Registration is not execution authority
- **WHEN** an owned registered HTTP source has approved discovery but is not accepted for inference
- **THEN** its models remain visible with source_not_accepted and no execution candidates
- **AND** server-derived bind keys and complete existing model_access constraints are provided separately

#### Scenario: Freshness and source-level reasons
- **WHEN** a source is revoked or expires during refresh
- **THEN** that source loses its model rows without concealing independent sources
- **AND** a changed home, admin scope, serving binding or assignment refuses the whole snapshot
- **AND** source failures are a separate channel, not invented empty model identifiers

#### Scenario: Existing native default
- **WHEN** the owner has a current legacy native serving chain
- **THEN** its provider default is visible as legacy_single_provider
- **AND** the read neither invents an actual model name nor grants expanded model selection

#### Scenario: Existing legacy HTTP configuration
- **WHEN** the current legacy serving chain survives the read's final authority fence
- **THEN** legacy_source identifies its provider, bind key and configured fixed model
- **AND** these fields are not actual answering-model receipts or newly admitted candidates
- **AND** revocation during refresh clears the legacy-source projection

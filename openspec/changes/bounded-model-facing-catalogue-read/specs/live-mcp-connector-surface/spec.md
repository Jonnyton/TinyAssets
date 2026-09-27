# live-mcp-connector-surface (delta)

## ADDED Requirements

### Requirement: A bounded model-facing read of the owned model catalogue

The `read_graph` handle SHALL accept `target=model_options_summary`, returning the
same owned catalogue as `target=model_options` in a projection bounded
independently of how many models the sources enumerate. It SHALL require the
authenticated owner's complete current home and explicit admin ACL, exactly as
`target=model_options` does, and SHALL NOT create a home, agent, assignment,
preference or inference grant.

The projection SHALL carry, per source, the number of models that source offers,
how many of those are selectable, and the head of the platform's existing
candidate ordering; and, for the catalogue as a whole, the current choice, the
total number of models, the number selectable, and the count of unavailable
references. It SHALL accept `query` as a filter over model id and provider
reference, and `output_offset` as an opaque cursor over the remaining rows. It
SHALL NOT introduce a new parameter on `read_graph`.

Every reply SHALL carry the catalogue's totals beside the rows it returned, so a
page never conceals how many choices exist. Ordering SHALL be the existing
candidate order; this read SHALL NOT rank models itself, and a model outside that
order SHALL remain reachable rather than omitted.

#### Scenario: A large source does not outgrow the reply
- **WHEN** an owned source enumerates more models than fit a single bounded reply
- **THEN** the reply is bounded, reports that source's full model count, and returns the head of the existing candidate order
- **AND** the total number of models and the number selectable are present

#### Scenario: The rest is reachable, and reachable exactly once
- **WHEN** a caller pages with the `next_offset` each reply returns, until `next_offset` is null
- **THEN** every model in the catalogue is returned exactly once across those pages
- **AND** no model is skipped by the cursor's first page

#### Scenario: A filter never hides the catalogue's size
- **WHEN** a `query` matches no model
- **THEN** the reply returns no rows and reports zero matching
- **AND** it still reports the catalogue's true total number of models

#### Scenario: A model this universe never verified stays distinguishable
- **WHEN** the catalogue contains a row whose availability was established by another universe
- **THEN** the projection preserves that row's availability basis, that it is not selectable, and the reason it is not
- **AND** a row this universe verified itself remains distinguishable from it

#### Scenario: Unknown or foreign scope
- **WHEN** an explicit graph is not the current owned home or lacks admin access
- **THEN** the read refuses without disclosing that graph's model inventory
- **AND** a refusal is never reshaped into a projection that parses as catalogue data

### Requirement: A single tool result on the connector is bounded, and says when it was

Every `read_graph` and `get_status` reply the connector returns SHALL bound its
`structured_content` to a ceiling on a single tool result, not only its text
content block.

When a reply exceeds that ceiling it SHALL be replaced by a marker carrying: that
it was truncated, the original size, the ceiling applied, the size returned, a
verbatim leading portion of the original, and one line naming the narrowing
parameters of the target that produced it. The marker itself SHALL be within the
ceiling. Truncation SHALL NOT be silent: a reply MUST never be reduced without
the marker, because a caller that cannot tell it received a prefix will report
that prefix as the whole answer.

`target=model_options` SHALL be the sole exemption from this ceiling, because the
requirement "Shared unpowered model catalogue" requires its complete document for
the owner's picker. The exempt set SHALL be stated in this specification, and
adding a target to it SHALL require amending this requirement.

#### Scenario: An oversized read is marked, not clipped
- **WHEN** a read's structured reply exceeds the single-result ceiling
- **THEN** the caller receives the truncation marker with the original size and the ceiling
- **AND** the marker names how to narrow that target's read
- **AND** the marker is itself within the ceiling

#### Scenario: A reply within the ceiling is unchanged
- **WHEN** a read's structured reply is within the ceiling
- **THEN** it is returned unchanged, with no marker and no reformatting

#### Scenario: Only the picker's catalogue is exempt
- **WHEN** `target=model_options` returns more than the ceiling
- **THEN** the complete document is returned, because the picker's requirement demands it
- **AND** no other target is exempt

## MODIFIED Requirements

### Requirement: Shared unpowered model catalogue
The read_graph handle SHALL accept target=model_options without changing its
arguments or direct string/structured-adapter return contract. The read SHALL
require the authenticated owner's complete current home and explicit admin ACL.
It SHALL NOT create a home, agent, assignment, preference or inference grant.

Its advertised description SHALL state that it returns the complete catalogue,
that a large source makes that reply very large, and that a caller reading it
into a model's context SHALL use `target=model_options_summary` instead. This
target SHALL remain complete: the bounded reply for a model is the separate
target, never a narrowing of this one.

#### Scenario: Unpowered current home
- **WHEN** the owner has a complete home but no serving agent or working model
- **THEN** the read returns available registered inventory or an empty catalogue
- **AND** unavailable sources and missing saved model references remain distinguishable

#### Scenario: Unknown or foreign scope
- **WHEN** an explicit graph is not the current owned home or lacks admin access
- **THEN** the read refuses without disclosing that graph's model inventory
- **AND** omitted scope never resolves to a designated public universe

#### Scenario: Complete choices, not a first-page sample
- **WHEN** approved discovery returns more models than the default read limit
- **THEN** all protocol-bounded choices survive in structured content
- **AND** limit does not silently hide models from this catalogue target
- **AND** the single-result ceiling does not apply to this target

#### Scenario: Registration is not execution authority
- **WHEN** an owned registered HTTP source has approved discovery but is not accepted for inference
- **THEN** its models remain visible with source_not_accepted and no execution candidates
- **AND** server-derived bind keys and complete existing model_access constraints are provided separately

#### Scenario: Freshness and source-level reasons
- **WHEN** a source is revoked or expires during refresh
- **THEN** that source loses its model rows without concealing independent sources
- **AND** a changed home, admin scope, serving binding or assignment refuses the whole snapshot

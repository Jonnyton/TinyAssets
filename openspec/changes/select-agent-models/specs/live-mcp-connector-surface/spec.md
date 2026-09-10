## ADDED Requirements

### Requirement: Shared unpowered model catalogue
The read_graph handle SHALL accept target=model_options without changing its
arguments or direct string/structured-adapter return contract. The read SHALL
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

#### Scenario: Complete choices, not a first-page sample
- **WHEN** approved discovery returns more models than the default read limit
- **THEN** all protocol-bounded choices survive in structured content
- **AND** limit does not silently hide models from this catalogue target

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

### Requirement: Converse accepts non-authoritative current model choice
The authenticated converse handle SHALL accept optional model_choice using the
existing versioned preferences document. Omission SHALL use supported saved
preferences or preserve absent-policy legacy behavior. A current override SHALL
replace the entire current order without modifying saved defaults or authority.

#### Scenario: One-turn explicit choice
- **WHEN** an authorized owner supplies valid explicit model_choice
- **THEN** this turn captures that primary and exact fallback tail
- **AND** the saved row and generation remain unchanged

#### Scenario: One-turn automatic choice
- **WHEN** model_choice requests automatic mode
- **THEN** this turn clears the saved primary and uses eligible automatic ordering
- **AND** it does not append the old default as an explicit fallback

#### Scenario: Invalid or unauthorized choice
- **WHEN** the document is malformed, unsupported, outside supported owner scope or accepted authority
- **THEN** the runtime refuses before launch without widening access

#### Scenario: Cross-client compatibility
- **WHEN** the changed tool is tested through ChatGPT and Claude
- **THEN** both render structured results and final narration without wedging
- **AND** protected canary --assert-handles and deployed-SHA gates remain required

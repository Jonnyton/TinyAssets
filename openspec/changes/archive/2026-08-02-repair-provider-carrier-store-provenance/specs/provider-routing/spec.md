## ADDED Requirements

### Requirement: Background carrier mint authority is store-proven
The system SHALL mint a background provider carrier only from a one-use,
process-bound proof issued after the durable authority store commits the exact
reservation transition from `reserved` to `launch_started`; receipt, claim,
reservation, identifier, or recomputed digest records alone grant no mint
authority.

#### Scenario: Self-consistent forged reservation grants nothing
- **WHEN** a caller derives a new reservation identifier and invocation key from otherwise valid receipt and claim records, recomputes the reservation digest, and marks the forged record `launch_started`
- **THEN** the forged record cannot obtain a mint proof, mint a carrier, or validate a provider call
- **AND** the durable invocation, token, and cost ledger remains the sole launch authority

#### Scenario: Winning store arm mints once
- **WHEN** the authority store commits the first valid arm of a reserved invocation
- **THEN** it issues one opaque mint proof bound to that exact armed reservation digest and the issuing process
- **AND** mint-proof reuse, launch replay, a different reservation digest, or a different process fails before provider selection

#### Scenario: Carrier cannot cross a process fork
- **WHEN** a carrier or unconsumed mint proof is copied into a process other than its issuer
- **THEN** validation or minting fails before acquiring a copied process lock or selecting a provider

#### Scenario: Registry publication is cleanup-safe
- **WHEN** the system publishes a mint proof or carrier into its active process registry
- **THEN** cleanup is installed before the identity becomes active
- **AND** abandoned-object verification does not depend on immediate reference-count collection

#### Scenario: Packaged runtime preserves the same authority boundary
- **WHEN** provider-carrier authority changes in the canonical runtime
- **THEN** the packaged Claude-plugin model and store enforce byte-equivalent store provenance, one-use, and process boundaries

## ADDED Requirements

### Requirement: Storage observations distinguish measurable footprint from complete attribution
Existing admin-only resource status SHALL report bounded metadata-only logical
file-footprint observations separately from unavailable complete attributed
storage. It SHALL preserve existing authority, policy and accounting without
new databases, record mutations, quota changes or file-content reads.

#### Scenario: Authorized owner reads a footprint
- **WHEN** the current universe admin reads status and safe traversal succeeds
- **THEN** the response reports capture time, logical regular-file bytes and categories for permanent workspace, provider runtime, other universe files and lease-attributed scratch
- **AND** it discloses no paths, file names, lease identities or other owners' usage

#### Scenario: Attribution is incomplete
- **WHEN** local footprint is observed but shared-root records and unowned scratch cannot be attributed
- **THEN** those exclusions remain explicit and complete attributed storage remains unavailable rather than equaling the measured footprint

#### Scenario: Walk cannot cover its scope
- **WHEN** traversal meets a link, unsafe path, inaccessible or changing file, unsupported host or work bound
- **THEN** coverage is partial or unavailable with a sanitized reason, not fabricated complete zero

#### Scenario: Cached measurement does not cache authority
- **WHEN** a cached snapshot exists but the caller no longer has current admin authority
- **THEN** it is not returned
- **AND** authorized cache hits retain the original measurement time and declared staleness bound

#### Scenario: Measurements do not create a scan stampede
- **WHEN** simultaneous status requests arrive
- **THEN** same-scope work shares one bounded scan and distinct-scope concurrency is bounded without changing user-work quotas


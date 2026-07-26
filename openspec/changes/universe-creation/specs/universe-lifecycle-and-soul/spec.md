## ADDED Requirements

### Requirement: Public universe birth has one self-serializing contract
Every public universe-birth entry point SHALL use the shared lifecycle service, generate its own opaque `u-`+lowercase-ULID `universe_id`, and accept no caller-selected universe id or creation-time identity. Public `POST /v1/universes` SHALL NOT create a universe; internal migration and explicit dev tooling are outside this public boundary.

#### Scenario: first-contact birth self-serializes
- **WHEN** an authenticated founder without a living home triggers public first-contact birth
- **THEN** the service generates the new immutable serial and does not accept a caller-selected id

#### Scenario: HTTP cannot create a universe
- **WHEN** a caller submits `POST /v1/universes`
- **THEN** no universe root, index row, ACL grant, or founder-home binding is created

### Requirement: The universe index projects learned identity onto immutable ids
The root universe index SHALL be keyed by immutable `universe_id`. Creation SHALL add one row for the generated serial, and an accepted learned-name change in the universe's `identity.md` SHALL update only the display-name projection for that same row without changing its key or runtime operation id.

#### Scenario: creation adds an unnamed serial row
- **WHEN** a blank universe is created
- **THEN** the index contains exactly one row keyed by its immutable serial and no invented self-name

#### Scenario: learned name updates the existing row
- **WHEN** a governed learning event accepts a new self-name in `identity.md`
- **THEN** the index updates the learned-name projection on the existing serial row without creating a new id

### Requirement: Existing descriptive roots migrate atomically to serial roots
The lifecycle migrator SHALL assign a generated immutable serial to each existing descriptive-id universe root, stage and verify the replacement root, update founder bindings and all live runtime references atomically, and retain rollback metadata until reference-integrity checks succeed. After migration, read, write, run, and status operations SHALL resolve the serial id rather than the old descriptive id.

#### Scenario: successful existing-root migration
- **WHEN** an existing descriptive-id root and its references pass preflight checks
- **THEN** its data is available under one generated serial root and all live bindings and operation references resolve that serial

#### Scenario: failed migration rolls back
- **WHEN** staging, verification, or reference replacement fails
- **THEN** the original root and references remain usable and no half-migrated root is treated as a living universe

### Requirement: Existing roots drop duplicate empty starter artifacts without losing history
After a root is migrated, cleanup SHALL remove duplicate `self/`, `soul/`, and brain-archive directories and empty starter `notes.json` or `activity.log` files that are not part of the canonical root soul bundle. Cleanup SHALL preserve non-empty historical notes and logs until an explicit typed runtime destination and verified migration exist.

#### Scenario: duplicate empty artifacts are removed
- **WHEN** a migrated root contains duplicate model directories, brain archives, or empty starter notes/logs with no canonical reader
- **THEN** cleanup removes those artifacts and the canonical root soul bundle remains readable

#### Scenario: non-empty historical runtime data is preserved
- **WHEN** a migrated root contains non-empty historical notes or activity logs without a typed destination
- **THEN** cleanup preserves that data and reports it for a later explicit migration

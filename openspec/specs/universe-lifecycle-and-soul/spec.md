# Universe Lifecycle and Soul

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

How a universe is created, identified, seeded with an OKF soul bundle, taught via governed `soul.edit` writes, and ended via the confirm-gated clean-slate reset.

## Requirements

### Requirement: Universe identity is an opaque, time-sortable serial

A universe SHALL be identified by an opaque serial of the form `u-` followed by a
26-character lowercase Crockford base32 ULID (48-bit millisecond timestamp + 80
bits of randomness), matching the regex `^u-[0-9a-hjkmnp-tv-z]{26}$`. The serial
is generated exactly once at creation, is immutable and time-sortable, is used
directly as the universe's on-disk directory name, and SHALL NOT be re-derived
from a display name or learned identity. Identity generation lives in
`tinyassets.ids`, kept isolated so the format has a single source of truth.

#### Scenario: a generated serial matches the canonical format
- **WHEN** `new_universe_id()` produces a serial
- **THEN** it starts with `u-` and its 26-character body uses only the lowercase Crockford alphabet (`i`, `l`, `o`, `u` excluded)
- **AND** `is_universe_serial()` returns true for it and false for any non-conforming string

#### Scenario: serials sort by creation time
- **WHEN** two serials are generated with increasing timestamps
- **THEN** the earlier-timestamp serial sorts lexicographically before the later one, because the leading 10 characters encode the millisecond timestamp

### Requirement: Universe creation is atomic and self-serializing

The `create_universe` action (`tinyassets/api/universe.py`) SHALL generate a fresh
serial when no `universe_id` is supplied, and MAY accept an explicit id for
dev/existing-universe operations. It SHALL reject a supplied id that contains a
path separator (`/` or `\`) or begins with `.`, and SHALL refuse to overwrite a
directory that already exists. If any step after the directory is created fails,
the partial directory SHALL be removed (rollback via `rmtree`) so a failed create
never leaves a bare or half-seeded directory that would later read as a living
universe.

#### Scenario: create without an id generates a serial
- **WHEN** `create_universe` is called with no `universe_id`
- **THEN** a fresh `u-`+ULID serial is generated and used as the new universe directory name
- **AND** the response reports `status: created` for that serial

#### Scenario: a path-traversal id is rejected
- **WHEN** `create_universe` is called with a `universe_id` containing `/`, `\`, or a leading `.`
- **THEN** the call returns an `Invalid universe_id.` error and no directory is created

#### Scenario: a partial create is rolled back
- **WHEN** creation fails after the universe directory has been created (e.g. bundle seeding raises)
- **THEN** the partially created directory is removed before the error is returned
- **AND** an `OSError` is surfaced as an error envelope while any other exception re-raises after cleanup

### Requirement: Creation seeds a blank, linked OKF soul bundle

Creation SHALL seed one linked OKF concept-document bundle of 13 baseline files
rooted at `soul.md` (`tinyassets.universe_bundle.seed_okf_bundle`): `index.md`,
`log.md`, `soul.md`, `soul.edit.md`, `identity.md`, `founder.md`, `orgchart.md`,
`projects.md`, `goals.md`, `body.md`, `origin.md`, `soul_versions/index.md`, and
`soul_versions/0001.md`. Non-reserved files SHALL carry OKF frontmatter with a
non-empty `type`; the learned concept documents SHALL be stamped
`status: not-learned` so a blank universe is unnamed and unlearned. Reserved
structural files (`index.md`, `log.md`, `soul_versions/index.md`) SHALL carry no
concept frontmatter (root `index.md` carries only `okf_version`). Creation SHALL
NOT write `self/`, `soul/`, `notes.json`, or `activity.log`. The bundle SHALL
track the latest-main OKF spec rather than pinning a copy.

As-built limitation: not all 13 files are stamped `status: not-learned`. Only the
seven learned concept documents (`identity.md`, `founder.md`, `orgchart.md`,
`projects.md`, `goals.md`, `body.md`, `origin.md`) carry that flag. `soul.md`
(the operational entrypoint, whose `okf_source`/`edit_authority` frontmatter is
preserved verbatim) and `soul.edit.md` (the policy document) are OKF concept
documents without a learned-status flag; `soul_versions/0001.md` is a verbatim
snapshot of `soul.md`.

As-built limitation: the OKF format is tracked at `latest-main` (spec version
`0.1`), not a pinned copy, so the seeded shape can drift with the upstream OKF
SPEC over time.

#### Scenario: all baseline files are written and forbidden files are absent
- **WHEN** `seed_okf_bundle` seeds a fresh universe directory
- **THEN** every one of the 13 baseline files exists on disk
- **AND** none of `self`, `soul`, `notes.json`, `activity.log` is created

#### Scenario: concept documents carry OKF type; reserved files do not
- **WHEN** the seeded files are parsed
- **THEN** every non-reserved file has YAML frontmatter with a non-empty `type` that parses via `yaml.safe_load`
- **AND** `log.md` and `soul_versions/index.md` carry no frontmatter and root `index.md` carries only `okf_version`

#### Scenario: a blank universe reads back unnamed
- **WHEN** `read_universe_soul` reads a freshly seeded universe
- **THEN** it returns a soul whose learned name is empty
- **AND** `soul.md` records `okf_tracking: latest-main` and links `soul.edit.md` as its edit authority

### Requirement: Authenticated creation grants founder ownership and binds a home

When the create request is authenticated, the founder SHALL be granted `admin`
ACL on the new universe, the universe SHALL be registered in the universes index,
and the universe SHALL be bound as the founder's home only when the founder has no
living home already (no binding, or a binding whose directory lacks a `soul.md`).
An authenticated founder create SHALL NOT write the host-global `.active_universe`
marker; an anonymous/dev (single-tenant tray) create SHALL write it so the local
daemon switches to the new universe.

#### Scenario: founder create grants ownership without clobbering the active marker
- **WHEN** an authenticated founder creates a universe
- **THEN** an `admin` grant is recorded for the founder and the universe is registered in the index
- **AND** the `.active_universe` marker is not written for that create

#### Scenario: home binds only when no living home exists
- **WHEN** an authenticated founder without a living home (no binding, or a binding to a directory missing `soul.md`) creates a universe
- **THEN** that universe is bound as the founder's home
- **AND** a later create by a founder who already has a living home does not reassign the home

#### Scenario: anonymous create switches the local daemon
- **WHEN** an unauthenticated (dev/tray) create runs
- **THEN** the `.active_universe` marker is written with the new serial so the daemon switches to it

### Requirement: Governed soul edits are the sole learning-write path

Changes to a universe's soul SHALL flow through `apply_soul_edit`
(`tinyassets.soul_edit`), which treats each edit as a proposed learning event, not
a blind overwrite. An edit SHALL require non-empty `source` and `context`, SHALL
update only files listed in the universe's own `soul.edit.md` "Governed files"
section (the authority is read from that file, not a hardcoded list; a missing or
empty policy file blocks all edits), and SHALL reject filenames that are not
governed or that attempt path traversal. Each updated governed file SHALL have its
frontmatter flipped to `status: learned` with `learned_from`/`learned_at`
recorded — except `soul.md`, whose frontmatter is preserved verbatim. Every
accepted edit SHALL append `log.md` and write a new numbered snapshot under
`soul_versions/`. An optional `name` SHALL record the universe's learned self-name
in `identity.md`, allowing a name-only edit with no body.

#### Scenario: a governed edit learns and records provenance
- **WHEN** `apply_soul_edit` updates `identity.md` with a `source` and `context`
- **THEN** the file body is written, its frontmatter `type` is preserved, and `status` flips to `learned` with `learned_from` set to the source
- **AND** `log.md` gains an entry and a new `soul_versions/NNNN.md` snapshot is written and indexed

#### Scenario: non-governed and path-traversal targets are rejected
- **WHEN** an edit targets a file not listed in `soul.edit.md` (e.g. `projects.md`, `orgchart.md`) or a traversal path (e.g. `../evil.md`, `soul_versions/0001.md`)
- **THEN** the edit raises `SoulEditError` and no file is changed

#### Scenario: the governed list is read from the policy file
- **WHEN** `identity.md` is removed from the `soul.edit.md` "Governed files" section and an edit then targets `identity.md`
- **THEN** the edit is rejected because authority lives in the policy file, not a hardcoded list

#### Scenario: missing source or context is rejected
- **WHEN** an edit is submitted with an empty `source` or empty `context`
- **THEN** it raises `SoulEditError` because an edit is a learning event, not a blind overwrite

### Requirement: Soul edits are serialized and compare-and-swap guarded

`apply_soul_edit` SHALL hold a per-universe cross-platform lock (`.soul.lock`,
msvcrt on Windows / fcntl on POSIX) across the whole read→write→snapshot section
so the snapshot number — allocated from a directory listing — cannot collide under
concurrency. When `expected_versions` (filename → sha256 of the content the caller
last read via `current_soul_versions`) is supplied, the write SHALL be a
compare-and-swap: if a governed file changed since it was read, the edit is
rejected and the file is left untouched rather than clobbering the newer state.
Every accepted edit SHALL produce a distinct snapshot even when two edits carry
identical content.

#### Scenario: a stale expected version is rejected without clobbering
- **WHEN** an edit passes an `expected_versions` hash that no longer matches the on-disk content
- **THEN** the edit raises `SoulEditError` and the governed file is unchanged

#### Scenario: concurrent edits allocate distinct snapshots
- **WHEN** multiple threads apply soul edits to the same universe at once
- **THEN** every edit succeeds under the lock and each is assigned a distinct `soul_versions/NNNN.md` file with no collisions or lost updates

### Requirement: Clean-slate reset is the only lifecycle-end

There SHALL be no per-universe delete operation; the only teardown is a
confirm-gated clean-slate reset (`tinyassets.reset.reset`) that removes every
universe directory, the `.active_universe` marker, and the universe-scoped and
hosted-daemon tables at once, returning the platform to "no universe, no daemon".
Without `confirm` the reset SHALL only plan (mutating nothing), and it SHALL be
idempotent when run repeatedly. The reset SHALL preserve the branch commons
(`branch_definitions`, `branch_versions`, `goals`, `gate_claims`,
`canonical_bindings`), the entire `.runs.db` run history, and the `wiki/` commons.

As-built limitation: reset is all-or-nothing across every universe; a single
universe cannot be removed on its own.

#### Scenario: a dry run reports but deletes nothing
- **WHEN** `reset` runs with `confirm=False`
- **THEN** it returns a plan listing the universe directories, marker presence, and row counts to clear
- **AND** no directory, marker, or table row is actually removed

#### Scenario: a confirmed reset clears universes and daemons but preserves the commons
- **WHEN** `reset` runs with `confirm=True`
- **THEN** every universe directory, the `.active_universe` marker, and the universe-scoped and daemon tables are cleared
- **AND** `branch_definitions`, `goals`, `.runs.db`, and the `wiki/` directory survive

#### Scenario: reset is idempotent
- **WHEN** `reset(confirm=True)` runs a second time after a first successful reset
- **THEN** it reports no universe directories, no rows to clear, and no marker, without error

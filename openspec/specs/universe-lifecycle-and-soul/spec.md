# Universe Lifecycle and Soul

> As-built baseline (2026-07-19, change `spec-out-existing-platform`): describes landed behavior on `main` at baseline time, known limitations included. Future behavior changes arrive as OpenSpec change deltas against this capability.

## Purpose

How a universe is created, identified, seeded with an OKF soul bundle, taught via governed `soul.edit` writes, and ended via the confirm-gated clean-slate reset.
## Requirements
### Requirement: A universe exists because an ownership row names it

A universe SHALL be a directory under the data root that an ownership row names:
a `universe_acl` grant of any permission, or a `founder_home` binding. A home
binding SHALL count alongside an ACL grant, because first contact binds the home
before any grant is written. Ownership SHALL be matched EXACTLY — a universe id
is simultaneously a path component and an authority key matched with exact SQL,
so no resolver may answer with a spelling other than the one it was given. A
directory whose ownership row differs from its name in case is therefore not a
universe: hidden, never deleted, and reported as at-risk by
`scripts/universe_ownership_inventory.py` so the missing row is written rather
than guessed. A name beginning with `.` SHALL never resolve as a universe
whatever a row says.

Every reader SHALL apply this predicate — both the readers of "which universes
exist" and the readers of one universe's content or metadata by explicit id:
enumeration, `inspect`, `switch_universe`, the `available` list those two publish
on a miss, the visibility backfill and readiness enumeration, the
branch-dependents scan, the platform work probe, the default/home resolvers, and
`visibility_permits` itself, through which `read_page` (via the wiki gate) and
explicit-id `get_status` reach a universe. A capability SHALL NOT be granted on a
universe nobody owns: withholding discovery does not retract a
`visibility_level` already declared, so a gate on visibility alone leaves an
already-declared directory readable by id.

A configuration pointer — the host-global `.active_universe` marker or
`UNIVERSE_SERVER_DEFAULT_UNIVERSE` — SHALL NOT by itself make a directory a
universe; an unowned configured default SHALL answer only when no universe is
owned at all (a fresh install naming what it is about to create). The `available`
list SHALL additionally apply the `discover_existence` visibility gate.

Creation SHALL claim the owner BEFORE the directory exists, and SHALL revoke that
grant if any later create step fails, reporting a revoke failure to the caller
because a grant on a universe that does not exist silently holds the id. An
unauthenticated create SHALL be refused before anything is written.

When the ownership store cannot be read, a direct-id reader SHALL refuse with a
store-unavailable error rather than "not found", an enumeration SHALL return
nothing, and a capability predicate SHALL deny. The filesystem path index
(`sync_universes_from_filesystem`) SHALL remain unfiltered, because a restored
directory must be indexed before anything can grant on it; indexed SHALL NOT
imply owned. An unowned directory SHALL become invisible and unreadable, and
SHALL NOT be deleted by any reader.

#### Scenario: an unowned directory is invisible and unreadable
- **WHEN** a directory under the data root has no `universe_acl` grant and no `founder_home` binding
- **THEN** enumeration omits it, reading it by id answers "not found", selecting it answers "not found", the visibility backfill declares no level for it, and the directory and its contents remain on disk

#### Scenario: an operational store is not a universe without any denylist
- **WHEN** the data root holds operational directories such as `lancedb`, `daemon_wikis`, `cloud-automation-inputs`, `scratch`, or a past prune's archive
- **THEN** none of them is enumerated or readable by id, with no list of reserved names consulted

#### Scenario: a not-found answer publishes only owned, discoverable universes
- **WHEN** a caller asks for an id that does not exist
- **THEN** the `available` list contains only directories somebody owns whose declared level permits `discover_existence` for that caller

#### Scenario: an unowned universe grants no capability by explicit id
- **WHEN** a directory nobody owns carries a `visibility_level=public` row written by an earlier backfill, and a caller asks for its page content or its status by explicit id
- **THEN** both are refused, because `visibility_permits` requires an ownership row before any capability

#### Scenario: a directory whose row differs only in case is not a universe
- **WHEN** a directory named `U-Mine` is named by an ownership row reading `u-mine`
- **THEN** it is not owned, is not enumerated, is not readable, and remains on disk

#### Scenario: creation claims the owner before the directory
- **WHEN** an authenticated founder creates a universe
- **THEN** the admin grant exists before the directory is made, so the creator's own seeding reads are permitted
- **AND** an unauthenticated create is refused before any directory or grant is written
- **AND** a failure in a later create step revokes the grant, reporting a revoke failure to the caller

#### Scenario: a pointer is not a grant
- **WHEN** `.active_universe` or `UNIVERSE_SERVER_DEFAULT_UNIVERSE` names an unowned directory while at least one universe is owned
- **THEN** the default resolver returns an owned universe instead

#### Scenario: an unreadable ownership store says so
- **WHEN** the ownership lookup raises while reading a universe by id
- **THEN** the refusal names the store as unavailable rather than reporting the universe as not found

#### Scenario: an owned id with no directory is not readable
- **WHEN** an ownership row names an id whose directory is absent
- **THEN** it is neither enumerated nor readable by id

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
When creation is authenticated, the implementation SHALL attempt universe-index
registration before founder mutation, but registration failure SHALL be logged
and ignored. It SHALL then grant the founder `admin` ACL and bind the universe
as the founder's home only when no living home exists. An authenticated create
SHALL NOT write the host-global `.active_universe` marker; an anonymous/dev
create SHALL write it. If a later create step raises, rollback SHALL remove the
new universe directory when `shutil.rmtree` succeeds. Rollback SHALL swallow a
cleanup `OSError`, which can leave a partial directory, and SHALL NOT compensate
an index row, ACL grant, or host-global marker already written before the
failure. The ordinary flow has no fallible step after successful home binding.

#### Scenario: registration failure is best-effort
- **WHEN** index registration raises during an authenticated create
- **THEN** the failure is logged and creation continues to the founder grant and conditional home-binding steps

#### Scenario: founder create grants ownership without clobbering the active marker
- **WHEN** an authenticated founder creates a universe and the founder mutations succeed
- **THEN** an `admin` grant is recorded for the founder
- **AND** the `.active_universe` marker is not written for that create

#### Scenario: home binds only when no living home exists
- **WHEN** an authenticated founder without a living home creates a universe
- **THEN** that universe is bound as the founder's home
- **AND** a later create by a founder who already has a living home does not reassign the home

#### Scenario: rollback attempts directory cleanup without compensating earlier state
- **WHEN** a create step raises after an index row, ACL grant, or host-global marker has already been written
- **THEN** rollback attempts to remove the newly created universe directory
- **AND** does not compensate those earlier durable writes
- **AND** a cleanup `OSError` is swallowed, so a partial directory can remain

#### Scenario: anonymous create switches the local daemon
- **WHEN** an unauthenticated dev/tray create runs
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

### Requirement: Universe switching is publicly write-gated before its scope-specific helper
The public `universe(action = "switch_universe")` dispatcher SHALL classify switching as a write and SHALL run named action-scope authorization followed by target-universe write ACL authorization before invoking the switch helper. An anonymous public caller or an authenticated caller without the required scope and target `write` or `admin` access SHALL receive the applicable authorization error before the helper can change `.active_universe`. An authorized authenticated request reaching the helper SHALL require a non-empty id naming an existing universe, return `status = "selected"` and `scope = "request"`, and SHALL NOT write the host-global marker; the caller is instructed to pass the selected id on each subsequent call. The helper's anonymous branch, reachable only by a direct/internal helper invocation rather than the public dispatcher, SHALL write the selected id directly to `.active_universe` and return `status = "switching"` with the current approximate restart note. Authentication decisions SHALL use request identity rather than an environment actor fallback, and the marker write SHALL NOT claim atomic replacement or cross-process serialization.

#### Scenario: Anonymous public switching is denied before the helper
- **WHEN** an anonymous caller invokes the public `universe` dispatcher with `action = "switch_universe"` and an existing target id
- **THEN** action-scope or write-ACL authorization rejects the call before the anonymous marker-writing helper branch
- **AND** `.active_universe` is not changed

#### Scenario: Authenticated public switching requires scope and target write access
- **WHEN** an authenticated caller lacks either the required action scope or target-universe `write` or `admin` access
- **THEN** the public dispatcher returns the applicable authorization error without invoking the switch helper

#### Scenario: Authenticated selection is request-scoped
- **WHEN** an authenticated request with the required action scope and target write access selects an existing universe
- **THEN** the result reports `selected` with request scope
- **AND** the host-global `.active_universe` marker is not created or changed

#### Scenario: Direct helper rejects a missing id
- **WHEN** the low-level switch helper is invoked directly without `universe_id`
- **THEN** it returns `universe_id is required` and writes no marker

#### Scenario: Direct helper rejects an unknown universe
- **WHEN** the low-level switch helper is invoked directly with an id whose directory does not exist
- **THEN** it returns a not-found error plus the non-hidden directory names currently available under the universe root
- **AND** it writes no marker

#### Scenario: Direct anonymous helper selection is host-global
- **WHEN** an anonymous internal caller invokes the switch helper directly for an existing universe and the marker write succeeds
- **THEN** `.active_universe` contains the selected id and the result reports `switching`

#### Scenario: Direct anonymous marker failure is returned
- **WHEN** an anonymous internal caller invokes the helper directly for an existing universe but writing `.active_universe` raises `OSError`
- **THEN** the result reports the marker-write failure instead of reporting a successful switch

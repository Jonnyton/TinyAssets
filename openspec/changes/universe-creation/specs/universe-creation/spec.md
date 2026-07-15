## ADDED Requirements

### Requirement: Single creation route
The system SHALL expose exactly one universe creation route: MCP
`universe action=create_universe`. No HTTP route SHALL create universes, and no
hidden or wrapped duplicate creation route SHALL remain.

#### Scenario: MCP creates a universe
- **WHEN** a user requests universe creation through `universe action=create_universe`
- **THEN** the system creates the universe through that route and returns the new `universe_id`

#### Scenario: HTTP create is unavailable
- **WHEN** a client calls `POST /v1/universes`
- **THEN** the system does not create a universe

### Requirement: WorkOS-authenticated founder identity
The system SHALL use WorkOS AuthKit as the production Authorization Server for
MCP founder identity. Workflow MCP SHALL act as a Resource Server: it SHALL
publish Protected Resource Metadata, validate incoming bearer JWTs against
AuthKit metadata/JWKS, validate issuer and audience, and use token `sub` as the
immutable `founder_id`. Self-issued anonymous-subject tokens SHALL NOT count as
authenticated founder identity.

#### Scenario: Valid WorkOS token resolves founder
- **WHEN** a request includes a valid WorkOS AuthKit bearer token
- **THEN** the server resolves `founder_id` from token `sub`
- **AND** action-scope enforcement can use that principal

#### Scenario: Anonymous caller cannot create a universe
- **WHEN** a request has no valid WorkOS AuthKit bearer token
- **AND** the caller requests `universe action=create_universe`
- **THEN** the system rejects the create request
- **AND** no universe directory, home binding, or universe-index row is created

#### Scenario: Public reads can remain anonymous
- **WHEN** a request has no valid WorkOS AuthKit bearer token
- **AND** the caller requests a public read action
- **THEN** the system may serve the read without creating a founder or home universe

#### Scenario: Anonymous caller cannot write
- **WHEN** a request has no valid WorkOS AuthKit bearer token
- **AND** the caller requests any MCP write, create, run, costly, admin, ledger, or state-changing action
- **THEN** the system rejects the request
- **AND** no universe brain file, wiki page, run, ledger row, branch-use instance, or state is changed

### Requirement: MCP writes are scoped to the founder's own universe
The system SHALL allow an authenticated founder to write only to their own
bound/home universe brain through MCP. Public reads MAY cross universe
boundaries, but MCP writes to another universe's soul, identity, canon, wiki,
runtime goals, body, org chart, files, or state SHALL be rejected. Branch and
commons request surfaces SHALL NOT grant write access to another universe brain.

#### Scenario: Founder writes own universe brain
- **WHEN** an authenticated founder requests a write to their own bound/home universe brain
- **AND** the request has the required action scope
- **THEN** the system may perform the write

#### Scenario: Founder cannot write another universe brain
- **WHEN** an authenticated founder requests a write to a universe not bound to that founder
- **THEN** the system rejects the write
- **AND** the target universe's brain files and state are unchanged

#### Scenario: Cross-universe interactions are proposals or requests
- **WHEN** a user submits a patch request, Branch edit proposal, alternative Branch proposal, or Goal proposal for a public branch/commons surface
- **THEN** the system records the submission on the appropriate request/proposal surface
- **AND** it does not mutate another universe's brain

### Requirement: Universe visibility is explicit and confirmation-gated
The system SHALL keep universe ownership/write authority separate from
public/private read visibility. An owner/admin grant SHALL NOT by itself make a
universe private. Public read visibility SHALL be controlled by the explicit
universe visibility rule (`public_read`). Taking a universe private or making a
private universe public again SHALL be a user-facing confirmed action; the
system SHALL NOT flip visibility silently as a side effect of creation, owner
binding, ACL grants, sync, branch runs, or mobile connection.

#### Scenario: Owner grant does not change public readability
- **WHEN** the system grants a founder admin ownership of a universe
- **THEN** the founder can write that universe
- **AND** the universe's public read visibility is unchanged

#### Scenario: Taking a universe private requires confirmation
- **WHEN** an authenticated owner requests to make a public universe private
- **THEN** the system presents the visibility change and consequences for confirmation
- **AND** the system changes `public_read` to false only after confirmation
- **AND** anonymous and non-granted users can no longer read that universe

#### Scenario: Making a universe public requires confirmation
- **WHEN** an authenticated owner requests to make a private universe public
- **THEN** the system presents the visibility change and consequences for confirmation
- **AND** the system changes `public_read` to true only after confirmation
- **AND** anonymous callers can read public surfaces without write authority

#### Scenario: Private universe remains owner-hostable
- **WHEN** a universe is private
- **THEN** the founder MAY host it on their computer, their phone, or a synced phone/computer setup
- **AND** the public MCP service SHALL NOT expose its private brain contents to anonymous or non-granted callers

### Requirement: First MCP contact enters the founder's home universe persona
The system SHALL resolve default MCP contact through the authenticated founder,
not through a host-global active-universe marker. When an authenticated founder
connects without requesting a specific universe, the system SHALL enter that
founder's home universe. If the founder has no home universe, the first
authenticated status contact SHALL AUTO-CREATE and bind a blank seed home
universe (host decision 2026-07-15, supersedes the 2026-07-02 opt-in birth: a
connected founder always has a home and MUST NOT have to know to ask for their
first one) and return a compact welcome card (platform description + a first
step the founder can say). The auto-birth SHALL respect the create scope — a
founder whose token lacks the create scope SHALL instead receive the compact
awaiting-creation card (a status read is NOT a create-scope bypass), and no
`founder_home` binding SHALL be left for a founder who could not create. The
home-id reservation SHALL be atomic so concurrent first-contact yields exactly
one home (no double-birth). Additional universes beyond the first remain
explicit (`universe action=create_universe`). The system SHALL NOT use a
root-global `.active_universe` marker to decide which universe a chatbot speaks
as.

#### Scenario: New founder first contact auto-creates and binds the home universe
- **WHEN** an authenticated founder holding the create scope with no home universe makes first MCP contact (`get_status` without a specific universe)
- **THEN** the system auto-creates one blank seed universe through the universe creation contract
- **AND** binds that universe to the founder as the founder's home universe
- **AND** grants the founder `admin` on it and records the create in the universe ledger
- **AND** returns a compact welcome card (`first_contact.event = universe_created` with the new `universe_id`) inviting the founder to introduce themselves
- **AND** does NOT clobber the host-global `.active_universe` marker

#### Scenario: Read-only founder first contact does not birth a universe
- **WHEN** an authenticated founder whose token lacks the create scope makes first MCP contact with no home universe
- **THEN** the system returns the compact awaiting-creation card (`first_contact.event = no_universe_yet`)
- **AND** creates no universe and leaves no `founder_home` binding

#### Scenario: Existing founder first contact enters learned persona
- **WHEN** an authenticated founder connects to MCP
- **AND** that founder already has a home universe
- **THEN** the system loads that home universe's learned soul/persona
- **AND** the chatbot speaks in first person as that universe
- **AND** platform status is available as supporting evidence, not the default voice

#### Scenario: Explicit universe selection is not global
- **WHEN** an authenticated founder explicitly chooses a different authorized universe
- **THEN** that selection applies only to the current client/session or request scope
- **AND** it does not change any root-global active universe marker for other users

### Requirement: Generated immutable universe id
The system SHALL generate exactly one opaque immutable serial at creation time,
and that serial SHALL be the `universe_id`. The generated serial SHALL use the
format `u-` followed by a 26-character lowercase ULID. Creation SHALL NOT derive
`universe_id` from a user-provided display name or learned identity. The
`universe_id` SHALL be the universe directory name.

#### Scenario: Blank universe receives one generated id
- **WHEN** a blank universe is created
- **THEN** the response contains one generated `universe_id`
- **AND** the `universe_id` matches `u-[0-9a-hjkmnp-tv-z]{26}`
- **AND** the universe is stored under a directory with that exact id
- **AND** there is no second code serial created later for the same universe

#### Scenario: Provided text does not become id
- **WHEN** a creation request includes text, premise, or display metadata
- **THEN** the generated `universe_id` remains opaque and independent of that text

### Requirement: Soul identity is learned after creation
The system SHALL NOT set the universe's persona name during creation. The
universe's self-name SHALL be learned later through the OKF soul bundle rooted
at `soul.md`.

#### Scenario: Created universe is unnamed
- **WHEN** a blank universe is created
- **THEN** its persona name is empty or unknown
- **AND** `soul.md` links to `identity.md`
- **AND** `identity.md` records identity as not learned yet

#### Scenario: Display metadata is not persona identity
- **WHEN** a client needs a display label for UI purposes
- **THEN** that label is stored only as metadata
- **AND** it does not populate the learned name in `soul.md` or `identity.md`

### Requirement: Universe index records ids and learned names
The system SHALL maintain a readable root universe index keyed by immutable
`universe_id`. Each row SHALL point to the universe brain directory and display
the current learned name from that universe's `identity.md` when one exists.
Write, run, status, and explicit universe-selection operations SHALL resolve a
universe by immutable `universe_id`.

#### Scenario: Creation adds serial row
- **WHEN** a blank universe is created
- **THEN** the root universe index contains one row for the generated immutable `universe_id`
- **AND** the learned name is empty, unknown, or not learned yet
- **AND** operations resolve the universe by that generated `universe_id`

#### Scenario: Learned name updates index row
- **WHEN** `identity.md` learns or changes the universe's name
- **THEN** the root universe index row for that same immutable `universe_id` is updated
- **AND** the immutable `universe_id` remains the operation key

### Requirement: Creation seeds baseline files
The creation route SHALL initialize the blank universe baseline as a linked OKF
bundle: `index.md`, `log.md`, `soul.md`, `soul.edit.md`, `identity.md`,
`founder.md`, `orgchart.md`, `projects.md`, `goals.md`, `body.md`, `origin.md`,
`soul_versions/index.md`, and `soul_versions/0001.md`. `soul.md` SHALL be the
central editable soul entrypoint. New universe creation SHALL NOT create
separate `self/`, `soul/`, `notes.json`, or `activity.log` baseline files.

#### Scenario: Blank baseline exists immediately
- **WHEN** creation returns success
- **THEN** the new universe directory contains `index.md`, `log.md`, `soul.md`, `soul.edit.md`, `identity.md`, `founder.md`, `orgchart.md`, `projects.md`, `goals.md`, `body.md`, `origin.md`, `soul_versions/index.md`, and `soul_versions/0001.md`
- **AND** it does not contain a new `self/` directory
- **AND** it does not contain a new `soul/` directory
- **AND** it does not contain `notes.json` or `activity.log`

#### Scenario: Status read is idempotent
- **WHEN** `get_status` is called for a newly created universe
- **THEN** it may read or verify the linked OKF soul bundle
- **AND** it does not need to create initial soul files for the first time

#### Scenario: Baseline files are linked
- **WHEN** a blank universe is created
- **THEN** every baseline file is linked from `index.md`, `log.md`, `soul.md`, or `soul_versions/index.md`

### Requirement: `soul.md` follows latest OKF
The creation route SHALL write `soul.md` as an OKF concept document following
the latest `okf/SPEC.md` on GitHub at
`https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`.
The file SHALL include parseable YAML frontmatter, a non-empty `type`, and
producer-defined metadata recording the OKF source URL and latest-main tracking
policy.

#### Scenario: Created soul is OKF-shaped
- **WHEN** a blank universe is created
- **THEN** `soul.md` starts with YAML frontmatter
- **AND** the frontmatter includes `type: Universe Soul`
- **AND** the frontmatter records the OKF spec URL and latest-main tracking policy
- **AND** the body is readable markdown

#### Scenario: Blank soul local links resolve
- **WHEN** a blank universe is created
- **THEN** every local markdown link in `soul.md` resolves to a generated file
- **AND** `soul.md` lists `orgchart.md` with the other open questions

### Requirement: `soul.edit` is an OKF edit-policy file
The system SHALL create `soul.edit.md` as an OKF concept document whose concept
id is `soul.edit`. `soul.edit.md` SHALL describe how the universe learns changes
to its own soul. The MCP user-facing operation MAY be `universe
action=soul.edit`, but that execution path SHALL read and follow
`soul.edit.md`. A successful soul edit SHALL update only the explicitly changed
governed soul files according to the policy: `soul.md`, `identity.md`,
`founder.md`, `body.md`, or `origin.md`. Accepted soul edits SHALL append
`log.md` and write a `soul_versions/` snapshot. `orgchart.md`, `projects.md`,
and `goals.md` SHALL NOT be listed as governed `soul.edit` files.

#### Scenario: Created soul links real edit policy
- **WHEN** a blank universe is created
- **THEN** `soul.md` declares edit authority `soul.edit`
- **AND** `soul.md` links to `soul.edit.md`
- **AND** `soul.edit.md` exists and has `type: Soul Edit Policy`
- **AND** `soul.edit.md` contains hard rules, not open questions
- **AND** `soul.edit.md` does not list `orgchart.md`, `projects.md`, or `goals.md` as governed files

#### Scenario: Soul edit versions the model
- **WHEN** an authorized caller invokes `universe action=soul.edit` for a universe
- **THEN** the execution path reads `soul.edit.md`
- **AND** the canonical `soul.md` entrypoint or governed soul files are updated according to that policy
- **AND** `log.md` records the edit history
- **AND** a new `soul_versions/` snapshot is written

#### Scenario: Soul changes are learned
- **WHEN** a caller asks to change the soul
- **THEN** the change is treated as proposed learning with source/context
- **AND** the system does not treat arbitrary caller text as direct replacement for the soul

### Requirement: Body is learned embodiment
The creation route SHALL create `body.md` as the universe's learned embodiment
document. `body.md` SHALL describe body by analogy: the universe is the brain;
live platforms, applications, interfaces, hosted services, and other interactive
surfaces are body surfaces; text that lands in the real world is voice; Branches
the universe runs are hands taking actions; and real-world feedback is sensory
input. Creation SHALL NOT invent body details before real surfaces, actions, or
feedback have been built or observed.

#### Scenario: Body starts unlearned
- **WHEN** a blank universe is created
- **THEN** `index.md` links to `body.md`
- **AND** `soul.md` links to `body.md`
- **AND** `body.md` records that no body is learned yet
- **AND** `body.md` includes the body/personification analogy
- **AND** `body.md` does not claim live platforms, applications, voice, hands, or senses that have not been built or observed

### Requirement: Org chart is learned organization with founder on top
The creation route SHALL create `orgchart.md` as the universe's learned
organization map. `orgchart.md` SHALL state that the founder confirmed by the
oath is always the top anchor. Roles, teams, daemons, collaborators,
delegations, responsibilities, and reporting lines below the founder SHALL be
learned from actual work or authority decisions. Creation SHALL NOT invent
departments, titles, people, daemons, or reporting lines.

#### Scenario: Org chart starts with only the fixed anchor rule
- **WHEN** a blank universe is created
- **THEN** `index.md` links to `orgchart.md`
- **AND** `orgchart.md` records that no organization is learned yet
- **AND** `orgchart.md` states that the oath-confirmed founder is always the top
- **AND** `orgchart.md` does not claim any learned roles, teams, daemons, collaborators, delegations, or reporting lines

### Requirement: Founder projects are distinct from runtime goals and branches
The creation route SHALL create `projects.md` for founder projects and things
the founder is building. `projects.md` SHALL be an index of project names,
one-line summaries, and links to project files when project-specific files are
needed. `goals.md` SHALL describe runtime goals this universe runs and the
Branch uses/runs attached to those goals. A commons Branch MAY be reusable across
many Goals and universes; every universe run/use of a Branch SHALL be connected
to a Goal.

#### Scenario: Projects file exists
- **WHEN** a blank universe is created
- **THEN** `index.md` links to `projects.md`
- **AND** `projects.md` states that it is a one-line project index with pointers to project files as needed
- **AND** `projects.md` records founder projects as not learned yet

#### Scenario: Goals are runtime goals with branches
- **WHEN** a blank universe is created
- **THEN** `goals.md` describes runtime goals and attached Branch uses/runs, not founder projects
- **AND** `goals.md` points founder projects to `projects.md`
- **AND** `goals.md` states that universe runs/uses of Branches must be attached to goals

### Requirement: Branches are run by universes
The system SHALL treat Branch execution as an action performed by a universe,
not directly by a human MCP user. A human user MAY ask their own universe to
adopt, run, or remix a Branch. Each Branch run SHALL be recorded as a separate
runtime instance attached to that universe's Goal. Multiple universes MAY use
the same Branch as separate instances, and a universe MAY remix a Branch into
its own variant without overwriting the shared Branch.

#### Scenario: User asks own universe to run a Branch
- **WHEN** an authenticated founder asks their own bound/home universe to run a Branch
- **AND** the target runtime Goal exists or is created through the Goal contract
- **THEN** the universe is the runnable actor
- **AND** the Branch run is recorded as that universe's goal-bound Branch-use instance

#### Scenario: Multiple universes use same Branch separately
- **WHEN** two universes use the same commons Branch
- **THEN** each universe has its own separate runtime instance
- **AND** each run is attached to that universe's own Goal context

#### Scenario: User cannot directly run a Branch as themselves
- **WHEN** an MCP user requests direct human execution of a Branch outside a universe context
- **THEN** the system rejects direct execution
- **AND** instructs the user to route the run through their own universe

### Requirement: Universe roots use serial ids
The universe directory name SHALL be the immutable serial `universe_id`.
Runtime operations SHALL use that same `universe_id` as the universe key.

#### Scenario: Universe data is in clean shape
- **WHEN** a universe is reset to the clean shape
- **THEN** its root directory name matches its immutable `universe_id`
- **AND** supported write/run/status operations use the serial `universe_id`

#### Scenario: New create uses generated serial id
- **WHEN** a user creates a new universe
- **THEN** the new universe id uses the generated serial contract

#### Scenario: Duplicate self model is removed from the clean brain
- **WHEN** an existing universe contains `self/`
- **THEN** baseline reset removes that stale duplicate brain folder
- **AND** supported persona/status operations read the root OKF soul bundle
- **AND** new universe creation does not create `self/`

#### Scenario: Brain archives are not part of the baseline
- **WHEN** a universe has a brain archive folder from a previous shape
- **THEN** baseline reset removes it
- **AND** the clean starting brain does not include hidden stale brain archives

#### Scenario: Empty starter files are removed
- **WHEN** an existing universe contains `notes.json` whose content is `[]`
- **OR** it contains a zero-byte `activity.log`
- **THEN** the clean baseline reset removes those files
- **AND** new universe creation does not create `notes.json` or `activity.log`

#### Scenario: Historical runtime notes and logs are not erased
- **WHEN** an existing universe contains non-empty `notes.json` or `activity.log`
- **THEN** the clean baseline reset leaves that file in place as runtime data
- **AND** that file is not treated as part of the starting brain baseline

### Requirement: Clearing universe brains preserves branch commons
The system SHALL keep branch commons outside the universe-brain clearing path.
Branch definitions, goal catalogs, completed-run records, outcome metrics, and
other branch-lookup surfaces SHALL remain unless the caller explicitly requests
a branch-commons reset.

#### Scenario: Clearing all universes keeps branch commons
- **WHEN** all universe brain directories and founder home-universe bindings are cleared
- **THEN** branch definitions remain available for lookup
- **AND** goal catalogs, run metrics, and outcome records remain available
- **AND** the next authenticated founder first contact creates a new blank seed home universe

### Requirement: Mobile clients are first-class universe hosts
The system SHALL treat future iOS and Android clients as first-class MCP
clients and possible universe hosts, even before the full apps are built. A
mobile client SHALL use the same WorkOS founder identity and universe creation
contract as desktop/web MCP clients. Mobile-specific features SHALL be additive
client capabilities, not alternate universe identity or creation routes.

#### Scenario: Mobile auth uses platform standards
- **WHEN** a mobile client authenticates a founder
- **THEN** it uses WorkOS/OIDC-backed founder identity
- **AND** it stores local credentials/tokens only in platform secure storage
- **AND** it supports platform passkey/credential flows where available

#### Scenario: Mobile app integrity is a signal, not identity
- **WHEN** an iOS or Android app calls a protected MCP write/sync action
- **THEN** the backend MAY evaluate platform app-integrity signals
- **AND** those signals do not replace WorkOS founder identity or universe ownership checks

#### Scenario: Basic Android test app uses the same contract
- **WHEN** a basic Android test app is built for iteration
- **THEN** it calls the same MCP auth, status/read, and confirmed write/sync surfaces
- **AND** it does not introduce a second create route, second id format, or mobile-only brain shape

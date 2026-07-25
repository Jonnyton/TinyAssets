## ADDED Requirements

### Requirement: Branch authorship and authority derive from the authenticated subject
The system SHALL derive new branch/node authorship, approval/publisher/receipt provenance, and every branch authority decision from the request-local, credential-validated subject. It MUST NOT use an environment-derived fallback or caller-supplied `actor`, `author`, `approved_by`, publisher, `owner`, or `force` value as authority or newly persisted provenance. Branch creation, composite build, node authoring, source approval, version publication, git attribution, and authoring receipts SHALL persist the authenticated subject and SHALL fail closed when that subject is required but absent. Authorized cross-branch reuse SHALL preserve already-authorized copied source provenance rather than relabeling it as caller-authored.

#### Scenario: Caller attempts to choose another author
- **WHEN** an authenticated caller creates a branch or node, builds a branch, approves source, or publishes/receipts a branch operation while supplying another identity
- **THEN** every newly persisted actor/provenance field is server-bound to the authenticated subject rather than the caller-supplied identity

#### Scenario: Authorized reuse preserves source provenance
- **WHEN** an authenticated caller reuses an authorized public or owner-private source node
- **THEN** copied original authorship and approval provenance remains attributable to its source and is not relabeled as caller-created

#### Scenario: Environment identity exists without an authenticated subject
- **WHEN** a private-branch read or branch mutation has no credential-validated subject but the process environment names the branch author
- **THEN** the environment value grants no authority and the operation fails closed

#### Scenario: Authenticated author accesses their branch
- **WHEN** the credential-validated subject equals the stored branch author
- **THEN** author-only reads and writes remain available subject to their other existing gates

#### Scenario: Environment identity cannot become a listing viewer
- **WHEN** a request has no authenticated subject while process environment identity names a private branch author
- **THEN** `list_branches` exposes no private row or private-derived count, and `scope=mine` returns the stable empty list/count

#### Scenario: Authenticated author lists their private branch
- **WHEN** an authenticated subject lists branches they authored
- **THEN** their own private branches remain visible without exposing another subject's private rows

#### Scenario: Reusable-node search uses the authenticated viewer
- **WHEN** a caller searches reusable nodes
- **THEN** candidates, reuse counts, ranking, and result counts derive only from public branches plus that authenticated subject's private branches, with no environment-inherited or foreign-private contribution

### Requirement: Branch-selector reads preserve not-found equivalence
The system SHALL apply one shared selector-resolution and branch-read authority helper to `get_branch`, `describe_branch`, `validate_branch`, and `fork_tree` before constructing branch-derived output. Name resolution MUST use the credential-validated request subject rather than environment identity. A foreign private branch and a nonexistent branch MUST return the byte-identical JSON envelope `{"error": "Branch '<selector>' not found."}` using the original caller-supplied ID or name, with no resolved canonical ID, existence, author, visibility, structure, validation, lineage, or projection metadata.

#### Scenario: Non-owner describes a private branch by exact ID
- **WHEN** an authenticated subject requests `describe_branch` for another author's private branch
- **THEN** the response is byte-identical to describing a nonexistent branch with that requested ID

#### Scenario: Non-owner validates a private branch by exact ID
- **WHEN** an authenticated subject requests validation for another author's private branch
- **THEN** the response contains only the canonical not-found envelope

#### Scenario: Guessed private name does not reveal the canonical ID
- **WHEN** a caller supplies another author's private branch name while process environment identity names that author
- **THEN** resolution grants no authority and the not-found envelope contains the original name rather than the stored branch ID

#### Scenario: Owner reads a private branch
- **WHEN** the authenticated subject is the author of the requested private branch
- **THEN** existing get, describe, validate, lineage, and node-search output remains available

#### Scenario: Public branch remains readable
- **WHEN** any otherwise-authorized caller reads a public branch
- **THEN** the existing public response shape and content remain unchanged

### Requirement: Cross-branch reuse respects source read authority
The system SHALL authorize a `node_ref.source` branch and a `fork_from` source branch through the shared branch-read helper before reading or copying any node body, `node_defs`, source code, prompt template, tool allowance, approval provenance, or other source content. A denied source MUST produce the canonical not-found envelope and no partial destination mutation.

#### Scenario: Foreign private node reference is denied before copy
- **WHEN** a caller adds a node whose `node_ref.source` names another author's private branch
- **THEN** the operation returns the canonical not-found envelope and copies no source fields into the destination

#### Scenario: Foreign private fork source is denied before clone
- **WHEN** a caller builds a branch whose `fork_from` version belongs to another author's private branch
- **THEN** the operation returns the canonical not-found envelope before cloning `node_defs` or other branch content

#### Scenario: Own private source can be reused
- **WHEN** the authenticated author references their own private branch as a node or fork source
- **THEN** existing authorized reuse behavior remains available

#### Scenario: Public source reuse remains available
- **WHEN** a caller references a public branch as a node or fork source
- **THEN** existing public reuse behavior remains unchanged

### Requirement: Branch lineage disclosure follows branch read authority
The system SHALL authorize the requested lineage root and every ancestor through the shared branch-read helper. An unreadable ancestor MUST terminate traversal without a placeholder, count, or metadata row. Descendant enumeration SHALL use the authenticated subject as viewer so public descendants and that subject's own private descendants are included while foreign private descendants are excluded.

#### Scenario: Foreign private root is not enumerable
- **WHEN** a non-owner requests a fork tree rooted at another author's private branch
- **THEN** the response is the canonical not-found envelope

#### Scenario: Unreadable ancestor terminates lineage
- **WHEN** a readable descendant references an ancestor the caller cannot read
- **THEN** traversal stops before that ancestor and exposes no placeholder, count, ID, name, author, or version metadata for it

#### Scenario: Owner sees own private descendant
- **WHEN** an author requests descendants that include their own private fork
- **THEN** the private fork is included alongside readable public descendants

#### Scenario: Non-owner does not see foreign private descendant
- **WHEN** another subject requests the same descendants
- **THEN** the foreign private fork contributes no row or count

### Requirement: Branch mutation and deletion require author authority
The system SHALL resolve every mutation/deletion target through the shared readable-branch helper, then require the credential-validated subject to equal the stored branch author before `add_node`, `connect_nodes`, `set_entry_point`, `add_state_field`, `update_node`, `patch_nodes`, `approve_source_code`, `patch_branch`, or `delete_branch` changes state. A foreign private target and missing selector MUST return the same original-selector not-found envelope. A readable non-owned target MUST return a generic author-authority denial that exposes no stored author or target internals. Batch, empty-selection, and exact-ID forms MUST NOT bypass either gate. Caller-supplied `force` SHALL apply only to an already-authorized commit-conflict path and MUST NOT relax or alter an authority denial.

#### Scenario: Non-author mutation is denied
- **WHEN** a caller attempts any branch mutation against a branch authored by another subject
- **THEN** the operation is denied before state changes and the branch remains byte-equivalent to its pre-call state

#### Scenario: Foreign private mutation is not an existence oracle
- **WHEN** a caller mutates another author's private branch by ID or guessed name
- **THEN** the response matches the missing-selector not-found envelope, preserves the original selector, and exposes no stored author

#### Scenario: Empty patch selection cannot mutate all foreign nodes
- **WHEN** a non-author calls a batch patch form whose empty selection would otherwise target every node
- **THEN** author authority denies the operation before target expansion

#### Scenario: Non-author deletion preserves the branch
- **WHEN** a caller requests deletion of another author's branch by exact ID
- **THEN** deletion is denied and the branch plus its versions remain present

#### Scenario: Force cannot bypass author authority
- **WHEN** a non-author supplies `force=true` to patch another author's branch
- **THEN** the authority denial is unchanged and does not instruct the caller to retry with force

#### Scenario: Authorized force still resolves a commit conflict
- **WHEN** the authenticated author encounters an existing supported commit conflict and supplies force
- **THEN** the existing conflict-resolution behavior remains available after author authority succeeds

### Requirement: Branch action classification remains defense in depth
The system SHALL keep every branch mutation and deletion action classified as non-read during legacy-action retirement and registry migration. Action-scope classification MUST NOT replace object-level author authority, and missing action metadata MUST fail closed rather than default a mutating action to read.

#### Scenario: Registry migration omits a mutating branch action
- **WHEN** the action-scope registry lacks metadata for a branch mutation or deletion handler
- **THEN** dispatch denies the action rather than treating it as read

#### Scenario: Write scope does not grant foreign ownership
- **WHEN** a caller has the outer write/action scope but is not the branch author
- **THEN** object-level author authority still denies mutation or deletion

### Requirement: Stored versions and branch-adjacent actions preserve branch authority
The system SHALL resolve every stored branch version to its parent `branch_def_id` and apply the parent branch read boundary before direct version execution, version-derived inspection, or personal canonical use. Goal-wide canonical and selector bindings and globally readable Goal protocol steps SHALL accept only public-parent branches/versions because other users can execute or enumerate them. A missing parent definition SHALL fail closed. Goal list/search/get/protocol output SHALL omit unreadable legacy canonical, selector, and protocol pointers and SHALL recompute branch and gate-summary counts from readable branches; personal canonical resolution SHALL use the credential-validated request subject. `goals action=bind`, `gates action=claim`, `claim_from_branch_run`, and branch-scoped `record_conformance_pack` SHALL require branch author authority before branch/run material is read or state is attached. Claim retraction/bonus lifecycle, exact/listed conformance packs, gate claims, Goal metric/common-node/archive projections, gate/quality leaderboards and recommendations, and gate-event citations SHALL derive branch visibility only from the credential-validated request subject before returning records, IDs, actors, counts, ranks, cap influence, or selector inputs. New globally readable gate events SHALL cite only public-parent branch versions, and legacy unreadable citations SHALL be filtered from event get/list/leaderboard output. Remix recording SHALL require readable-parent plus author-owned-child authority and server-bound attribution; provenance traversal SHALL expose only readable roots/ancestors/edges. Scheduler/subscription creation SHALL require target-branch author authority, persist the request subject as owner, and list/mutate only that subject's rows without trusting an owner argument. Dry branch inspection SHALL use the same private-or-missing read envelope as other branch reads.

#### Scenario: Foreign private version is executed directly
- **WHEN** a caller supplies a version whose parent is another author's private branch to `run_branch_version`
- **THEN** the response matches a missing-version denial and no provider call, run row, output, snapshot field, or parent branch ID is exposed

#### Scenario: Global canonical or selector targets a private parent
- **WHEN** a Goal owner attempts to bind an active version whose parent branch is private
- **THEN** the bind is denied before canonical/selector history or Goal state changes, even when the Goal owner authored that private branch

#### Scenario: Global Goal protocol targets a private branch
- **WHEN** a Goal owner attempts to define a globally readable protocol step whose branch is private
- **THEN** the definition is denied before Goal or protocol state changes, even when the Goal owner authored that private branch

#### Scenario: Legacy Goal pointers reference unreadable branches
- **WHEN** Goal list, search, get, or get-protocol encounters a private or missing canonical, selector, or protocol branch that the request subject cannot read
- **THEN** output omits the pointer/step and every derived branch/gate count while preserving the Goal's non-branch public fields

#### Scenario: Personal canonical targets the caller's private parent
- **WHEN** an authenticated subject binds or runs a personal canonical whose parent is their own private branch
- **THEN** the existing personal behavior remains available without making that version globally runnable

#### Scenario: Caller binds another author's branch to a Goal
- **WHEN** a caller invokes `goals action=bind` for a branch they do not author
- **THEN** the operation is denied before `goal_id`, mirrored storage, or git state changes

#### Scenario: Caller attaches gate evidence to another author's branch
- **WHEN** a caller claims a gate rung, claims from a run, or records a branch-scoped conformance pack for a branch they do not author
- **THEN** the operation is denied before run output is disclosed or claim/conformance state is persisted

#### Scenario: Environment identity affects a private projection
- **WHEN** a request without an authenticated subject lists gate claims, conformance packs, Goal metrics/common nodes/archive candidates, gate or quality leaderboards/recommendations, or gate-event citations while process identity names a private branch author
- **THEN** the private branch contributes no record, ID, row, rank, count, cap displacement, recommendation, or selector input

#### Scenario: Exact gate lifecycle request targets a foreign private branch
- **WHEN** a caller retracts or performs a bonus lifecycle action on a claim, or gets/lists a conformance pack attached to another author's private branch
- **THEN** the response matches the corresponding missing branch/record envelope and exposes no claimant, Goal owner, host actor, evidence, stake, pack, or lifecycle metadata

#### Scenario: Globally readable gate event cites a private branch version
- **WHEN** a caller attempts to attest an event with a private-parent version citation
- **THEN** the citation is denied before event persistence, even when the caller owns the private branch

#### Scenario: Legacy gate event contains an unreadable citation
- **WHEN** an existing gate event or gate-event leaderboard contains a foreign-private or missing-parent version citation
- **THEN** get/list/leaderboard output omits that citation and all citation-derived counts/ranks without revealing the parent branch ID

#### Scenario: Caller records a remix over foreign branches
- **WHEN** a caller names an unreadable parent or non-owned child branch while supplying arbitrary attribution actors
- **THEN** the operation returns the corresponding not-found/author denial before edge or credit persistence and any accepted attribution actor is the request subject

#### Scenario: Provenance chain crosses an unreadable branch
- **WHEN** provenance traversal reaches a foreign-private or missing root, ancestor, or edge endpoint
- **THEN** traversal returns no placeholder, actor, credit, ID, edge, or derived count beyond the last readable boundary

#### Scenario: Caller schedules another author's branch
- **WHEN** a caller schedules or subscribes another author's branch while supplying that author's `owner_actor`
- **THEN** the request is denied before schedule/subscription persistence and the caller-supplied actor grants no authority

#### Scenario: Caller enumerates or mutates another actor's schedule
- **WHEN** a caller supplies another actor's owner or an exact foreign schedule/subscription ID to list, pause, unpause, unschedule, or unsubscribe
- **THEN** the server uses only the request subject and returns the same empty/not-found envelope as an unknown row without exposing target metadata

#### Scenario: Caller dry-inspects a foreign private branch
- **WHEN** a caller requests `dry_inspect_node` or `dry_inspect_patch` for another author's private branch
- **THEN** the response matches the missing-branch envelope and exposes no graph, node, validation, or patch-preview material

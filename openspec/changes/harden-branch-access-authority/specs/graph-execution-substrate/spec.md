## ADDED Requirements

### Requirement: Branch authorship and authority derive from the authenticated subject
The system SHALL derive new branch/node authorship, approval/publisher/receipt provenance, branch-action ledger attribution, and every branch-module authority decision owned by this change from the request-local, credential-validated subject. It MUST NOT use an environment-derived fallback or caller-supplied `actor`, `author`, `approved_by`, publisher, `owner`, or `force` value as authority or newly persisted provenance. Branch creation, composite build, node authoring, source approval, branch-module version publication, git attribution, authoring receipts, and global branch-action ledger rows SHALL persist the authenticated subject and SHALL fail closed when that subject is required but absent. Authorized cross-branch reuse SHALL preserve already-authorized copied source provenance rather than relabeling it as caller-authored.

#### Scenario: Caller attempts to choose another author
- **WHEN** an authenticated caller creates a branch or node, builds a branch, approves source, or publishes/receipts a branch operation while supplying another identity
- **THEN** every newly persisted actor/provenance field is server-bound to the authenticated subject rather than the caller-supplied identity

#### Scenario: Authorized reuse preserves source provenance
- **WHEN** an authenticated caller reuses an authorized public or owner-private source node
- **THEN** copied original authorship and approval provenance remains attributable to its source and is not relabeled as caller-created

#### Scenario: Environment identity exists without an authenticated subject
- **WHEN** a private-branch read or branch mutation has no credential-validated subject but the process environment names the branch author
- **THEN** the environment value grants no authority and the operation fails closed

#### Scenario: Environment identity cannot author the public action ledger
- **WHEN** a branch write has no credential-validated subject while process environment identity names a user
- **THEN** no branch mutation or global ledger row is persisted with that environment-derived actor

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
The system SHALL apply one shared selector-resolution and branch-read authority helper to `get_branch`, `describe_branch`, `validate_branch`, and `fork_tree` before constructing branch-derived output. Name resolution MUST use the credential-validated request subject rather than environment identity. A foreign private branch and a nonexistent branch MUST return the byte-identical JSON envelope `{"error": "Branch '<selector>' not found."}` using the original caller-supplied ID or name, with no resolved canonical ID, existence, author, visibility, structure, validation, lineage, or projection metadata. When an otherwise-readable branch stores `fork_from`, get/describe output SHALL include that version pointer only when its parent branch is readable to the same subject.

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

#### Scenario: Readable branch points to an unreadable parent
- **WHEN** get or describe reads a branch whose stored `fork_from` version belongs to a parent branch the subject cannot read
- **THEN** the response omits the `fork_from` pointer and all parent-derived metadata

### Requirement: Cross-branch reuse respects source read authority
The system SHALL authorize a `node_ref.source` branch and every `fork_from` version through shared branch/version-read helpers before reading, copying, or attaching any node body, `node_defs`, source code, prompt template, tool allowance, approval provenance, lineage pointer, or other source content. Missing and denied `node_ref.source` selectors MUST return the byte-identical branch envelope `{"error": "Branch '<selector>' not found."}`; missing and denied `fork_from` selectors MUST return the byte-identical version envelope `{"error": "Branch version '<selector>' not found."}`. Both preserve the original caller-supplied selector and cause no partial destination mutation.

#### Scenario: Foreign private node reference is denied before copy
- **WHEN** a caller adds a node whose `node_ref.source` names another author's private branch
- **THEN** the operation returns the canonical not-found envelope and copies no source fields into the destination

#### Scenario: Foreign private fork source is denied before clone
- **WHEN** a caller builds a branch whose `fork_from` version belongs to another author's private branch
- **THEN** the operation returns the canonical not-found envelope before cloning `node_defs` or other branch content

#### Scenario: Missing and denied reuse sources are indistinguishable
- **WHEN** the same action probes a missing versus foreign-private `node_ref.source` branch or `fork_from` version
- **THEN** both return the byte-identical canonical not-found envelope with the original selector and persist no destination content or lineage

#### Scenario: Patch attempts to set an unreadable fork parent
- **WHEN** an authorized destination author uses `set_fork_from` with a version whose parent branch they cannot read
- **THEN** the response matches a missing version and no lineage pointer is attached

#### Scenario: Own private source can be reused
- **WHEN** the authenticated author references their own private branch as a node or fork source
- **THEN** existing authorized reuse behavior remains available

#### Scenario: Public source reuse remains available
- **WHEN** a caller references a public branch as a node or fork source
- **THEN** existing public reuse behavior remains unchanged

### Requirement: Branch lineage disclosure follows branch read authority
The system SHALL authorize the requested lineage root and every ancestor through shared branch/version-read helpers. `set_fork_from` SHALL authorize the parent version before persisting a lineage edge. An unreadable ancestor MUST terminate traversal without a placeholder, pointer, count, or metadata row. Descendant enumeration SHALL use the authenticated subject as viewer so public descendants and that subject's own private descendants are included while foreign private descendants are excluded.

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

### Requirement: Branch authority remains isolated under connector load
The graph-execution capability SHALL own scenario ID `branch-authority-isolation` at `scenario_version=1` as an applicable, required entry in the shared production-load-evidence registry, classified as release-blocking because branch privacy is a public connector invariant. The registry entry SHALL name its classification justification, real canonical connector/storage substrate requirements, adapter reference, invariant-oracle references, no-fault declaration, and threshold references. The scenario SHALL exercise at least 1,000 concurrent canonical `/mcp` sessions representing at least 100 credential-distinct subjects and at least 10,000 admitted mixed operations over subject-private and shared-public branches, including list/search/read, denied foreign-private access, source reuse, lineage, and own mutation/deletion. On a `real` canonical connector and storage substrate, authorization-bound request acceptance/denial SHALL have p99 latency below 3 seconds and no unexplained 5xx response; every admitted authorized effect SHALL reconcile exactly once within 60 seconds; and unauthorized disclosures, reuse, mutations, or deletions SHALL be zero. Raw evidence and verdicts SHALL conform to the production-load-evidence manifest and oracle contracts. A shaped or mock run MUST NOT satisfy this release gate.

#### Scenario: Concurrent connector authority load passes
- **WHEN** scenario ID `branch-authority-isolation` at `scenario_version=1` runs on the declared real connector/storage substrate with its full population and workload
- **THEN** all latency, reconciliation, and zero-unauthorized-effect invariants pass from independently recomputable evidence

#### Scenario: Shaped authority test appears green
- **WHEN** a reduced, mocked, or otherwise non-equivalent run observes no authorization violation
- **THEN** its verdict is `not_run`, never `passed`, and branch-authority release remains blocked

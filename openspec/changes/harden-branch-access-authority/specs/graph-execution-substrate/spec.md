## ADDED Requirements

### Requirement: Branch authorship and authority derive from the authenticated subject
The system SHALL derive branch authorship and every branch authority decision from the request-local, credential-validated subject. It MUST NOT use an environment-derived fallback or caller-supplied `actor`, `author`, `owner`, or `force` value as authority. Branch creation and composite build surfaces SHALL persist the authenticated subject as author and SHALL fail closed when a required authenticated subject is absent.

#### Scenario: Caller attempts to choose another author
- **WHEN** an authenticated caller creates or builds a branch while supplying a different `author`
- **THEN** the stored author is server-bound to the authenticated subject rather than the caller-supplied identity

#### Scenario: Environment identity exists without an authenticated subject
- **WHEN** a private-branch read or branch mutation has no credential-validated subject but the process environment names the branch author
- **THEN** the environment value grants no authority and the operation fails closed

#### Scenario: Authenticated author accesses their branch
- **WHEN** the credential-validated subject equals the stored branch author
- **THEN** author-only reads and writes remain available subject to their other existing gates

### Requirement: Exact-ID branch reads preserve not-found equivalence
The system SHALL apply one shared branch-read authority helper to `get_branch`, `describe_branch`, `validate_branch`, `fork_tree`, and exact-branch node search before constructing branch-derived output. A foreign private branch and a nonexistent branch MUST return the byte-identical JSON envelope `{"error": "Branch '<id>' not found."}` with no existence, author, visibility, structure, validation, lineage, or projection metadata.

#### Scenario: Non-owner describes a private branch by exact ID
- **WHEN** an authenticated subject requests `describe_branch` for another author's private branch
- **THEN** the response is byte-identical to describing a nonexistent branch with that requested ID

#### Scenario: Non-owner validates a private branch by exact ID
- **WHEN** an authenticated subject requests validation or exact-branch node search for another author's private branch
- **THEN** the response contains only the canonical not-found envelope

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
The system SHALL require the credential-validated subject to equal the stored branch author before `add_node`, `connect_nodes`, `set_entry_point`, `add_state_field`, `update_node`, `patch_nodes`, `approve_source_code`, `patch_branch`, or `delete_branch` changes state. Batch, empty-selection, and exact-ID forms MUST NOT bypass this gate. Caller-supplied `force` SHALL apply only to an already-authorized commit-conflict path and MUST NOT relax or alter an authority denial.

#### Scenario: Non-author mutation is denied
- **WHEN** a caller attempts any branch mutation against a branch authored by another subject
- **THEN** the operation is denied before state changes and the branch remains byte-equivalent to its pre-call state

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

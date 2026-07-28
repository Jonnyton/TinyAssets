## ADDED Requirements

### Requirement: Retired Loop Labels Are Migrated Without Losing Repository Work

The repository SHALL remove the 28 product-loop label definitions:
`auto-bug`, `auto-change`, `auto-checker-dispatched`,
`auto-checker-failed`, `auto-fix-already-fixed`, `auto-fix-attempted`,
`auto-fix-auth-expired`, `auto-fix-auth-missing`, `auto-fix-blocked`,
`auto-fix-branch-push-blocked`, `auto-fix-claude-subscription-missing`,
`auto-fix-codex-subscription-missing`, `auto-fix-exhausted`,
`auto-fix-pr-blocked`, `auto-fix-provider-exhausted`,
`auto-fix-retries-1`, `auto-fix-retries-2`, `auto-fix-retries-3`,
`auto-fix-retries-4`, `auto-fix-retries-5`, `auto-fix-reviewed`,
`auto-fix-stale-gate`, `auto-fix-superseded`, `auto-fix-writer-failed`,
`community-loop-red`, `loop-consent`, `priority:loop-discipline`, and
`ready_for_checker`.

Before mutation, an idempotent dry-run/apply migrator SHALL disable/remove every
retired-label producer, including the community-loop watch successor cutover,
cancel or drain queued/in-progress producer runs, and record that quiescence.
It SHALL then paginate every label definition and every open/closed issue/PR
association to exhaustion into a digest-bound receipt. Apply SHALL remove
retired labels from open items without closing them, rewriting their bodies,
or removing unrelated labels; publish one repository-wide retirement notice
linked to the receipt; and delete the label definitions only after item
migration succeeds. Closed item bodies remain historical and their former
associations remain recoverable from the receipt.

The migration SHALL preserve generic coordination vocabulary including
`daemon-request`, `request:*`, `payment:*`, `gate-required`, `checker:*`,
`writer:*`, `writer-pool:*`, `needs-human`, `priority:primitive-*`,
`patch_request`, `merge-effector`, and `secure-merge`. `patch_request` SHALL
remain non-routing generic filing/effect trace vocabulary and SHALL NOT imply a
writer, checker, daemon, merge, or effect authority. After cutover, no active
workflow, script, website fallback, runtime, or agent skill may consume a
retired label.

#### Scenario: Dry run changes no repository state

- **WHEN** the label migrator runs in dry-run mode
- **THEN** it emits the complete deterministic definition/item plan and receipt digest
- **AND** it does not edit an issue, pull request, label, notice, or repository file

#### Scenario: Open work remains open

- **WHEN** apply processes an open issue or pull request bearing one or more retired labels
- **THEN** it removes only those retired labels and preserves the item's state, title, body, comments, and unrelated labels
- **AND** the receipt records the before/after label sets and item identity

#### Scenario: Label producers are quiesced before apply

- **WHEN** a workflow, script, runtime, site fallback, or agent route can still create or consume a retired label, or one of its runs is queued/in-progress
- **THEN** apply stops before item or definition mutation
- **AND** the receipt does not claim a stable final inventory

#### Scenario: Association inventory paginates to exhaustion

- **WHEN** dry-run inventories retired-label associations
- **THEN** it follows every page for open/closed issues and pull requests and records pagination completion
- **AND** a partial page set cannot authorize definition deletion

#### Scenario: Definitions leave only after migration

- **WHEN** every affected open item is migrated and the repository-wide notice is recorded idempotently
- **THEN** apply deletes all 28 retired label definitions
- **AND** a partial item/notice failure leaves remaining definitions intact for safe retry

#### Scenario: Generic labels survive

- **WHEN** a labelled item also carries generic request, gate, checker, writer, payment, primitive-priority, or merge vocabulary
- **THEN** those generic labels remain unchanged
- **AND** no retired label is renamed into a compatibility alias

### Requirement: Standing Workflow Auto-Merge Enrollments Are Revoked Without Overwriting Explicit Choices

A pre-deletion migrator SHALL run before
`.github/workflows/auto-enroll-merge.yml` is deleted. Before inventory or PR
mutation, it SHALL persist a digest-bound write-ahead receipt and idempotency
apply key, disable the live workflow through GitHub Actions, verify its
disabled state, cancel or drain every queued/in-progress run, and record that
quiescence evidence. Failure to disable or drain SHALL stop apply.

After quiescence, it SHALL snapshot every open auto-enrolled pull request's
number, node id, exact head SHA, state, base/head repositories, draft flag, and
full `autoMergeRequest` tuple (enabled actor/time, merge method, commit
headline/body, and author email) plus attribution evidence into that receipt.
Attribution SHALL require the exact same-repository, non-draft, `main`-target
eligibility tuple, exact raw GraphQL actor tuple
`Bot/github-actions/MDM6Qm90NDE4OTgyODI=`, and historical repository/Actions
evidence at `enabledAt` tying the enrollment to this workflow. That evidence
SHALL include the reviewed default-branch workflow blob, exact run/job/step
window, and bounded run-log proof of the PR, repository, enrollment command,
and successful enrollment line; current-source uniqueness alone is
insufficient. A PR head that advanced after enrollment SHALL remain separately
bound in the current migration tuple and SHALL NOT erase otherwise exact
historical enrollment evidence. If any otherwise eligible candidate run's log
cannot be read or verified, the receipt SHALL bind a typed uncertainty to that
captured run and preserve the enrollment as ambiguous; a failed read SHALL
never be treated as evidence that the competing candidate was absent.

The inventory reader SHALL expose structured repository reads rather than
caller-supplied GitHub CLI arguments. REST reads SHALL explicitly select GET;
the GraphQL reader SHALL accept only the reviewed query and exact plain
repository variables. Every read SHALL pin the public `github.com` host rather
than inherit an ambient CLI host. Array-valued REST connections SHALL follow
the exact GitHub `Link` header chain, validate every next URL remains on the
same API origin/repository/endpoint/query scope, and bind per-page request,
response, count, next-request chain, and terminal `rel="next"`-absence evidence
into the receipt. Observed counts SHALL NOT be copied into a fictitious server
total.

Offline receipt verification SHALL verify schema, normalization, bindings, and
digest integrity only; it SHALL report that external GitHub evidence was not
re-verified. The offline plan importer SHALL NOT mint attributed auto-merge
evidence. Attribution-bearing receipts SHALL originate from the live read-only
collector, and any future mutation authority SHALL freshly re-fetch and compare
the exact external source/run/job/step/log evidence.

Before each disable, apply SHALL atomically persist the per-PR intent and
planned tuple, then re-read that tuple. GitHub's disable mutation has no
expected-head CAS, so any changed tuple SHALL be skipped for a fresh plan.
Apply SHALL disable only attributed enrollment, post-read the result, and
persist its per-PR outcome before advancing. On restart under the same apply
key, it SHALL reconcile already-disabled planned tuples as completed rather
than fail or reissue authority, and retry only a still-matching recorded
intent.

Explicit user/maintainer enrollment SHALL remain unchanged. Ambiguous
provenance SHALL be held for host review, not guessed. After all per-PR
outcomes, apply SHALL perform and persist a full fresh open-PR rescan.
Workflow-file deletion SHALL require a complete receipt, zero attributed open
enrollments, zero ambiguity, zero queued/in-progress workflow runs, and the
workflow still disabled.

#### Scenario: Dry run inventories durable merge instructions

- **WHEN** the migrator runs in dry-run mode
- **THEN** it emits the deterministic workflow-quiescence and open-enrollment plan plus receipt digest with no repository mutation
- **AND** it distinguishes attributed, explicit, and ambiguous enrollment

#### Scenario: Read-only inventory cannot smuggle mutation arguments

- **WHEN** the migrator reads repository REST or GraphQL state
- **THEN** it constructs only explicit GET REST requests or the one reviewed GraphQL query with exact plain repository variables
- **AND** compact field flags, file-backed query values, cross-repository endpoints, and arbitrary argument vectors are unavailable

#### Scenario: Array pagination records its terminal oracle

- **WHEN** the migrator inventories an array-valued GitHub REST connection
- **THEN** it follows every validated `rel="next"` URL and receipts each page plus the first terminal response without `rel="next"`
- **AND** missing, malformed, looping, cross-scope, or over-bound Link chains fail closed without claiming a server total

#### Scenario: Offline verification is integrity-only

- **WHEN** a stored retirement receipt is verified without live GitHub reads
- **THEN** the result reports valid internal integrity and external evidence not re-verified
- **AND** an offline imported auto-merge inventory cannot mint attributed evidence

#### Scenario: Workflow is quiesced before enrollment mutation

- **WHEN** apply begins under a new idempotency key
- **THEN** it durably records intent, disables and verifies the live workflow, and cancels or drains queued/in-progress runs before snapshotting enrollments
- **AND** failure or uncertainty stops apply without disabling an auto-merge enrollment

#### Scenario: Workflow enrollment is disabled against the exact tuple

- **WHEN** apply has persisted per-PR intent and re-reads an attributed enrollment whose state/head/eligibility/full-auto-merge tuple matches the receipt plan
- **THEN** it disables auto-merge and durably records the post-read result
- **AND** the pull request, branch, labels, reviews, content, and explicit merge primitive remain unchanged

#### Scenario: Explicit or ambiguous enrollment is preserved

- **WHEN** an enrollment was enabled by a user/maintainer or attribution is not conclusive
- **THEN** apply leaves it unchanged
- **AND** ambiguous provenance blocks workflow deletion pending host review

#### Scenario: Concurrent PR change fails closed

- **WHEN** a planned pull request's head SHA, state, repository tuple, draft flag, or full auto-merge tuple changes before mutation
- **THEN** apply skips mutation and records the changed tuple for a fresh plan
- **AND** it does not infer that a new enrollment belongs to the retired workflow

#### Scenario: Restart reconciles an already-disabled planned enrollment

- **WHEN** apply restarts after GitHub disabled an attributed enrollment but before its post-read outcome was persisted
- **THEN** the same idempotency key and write-ahead intent reconcile the now-absent enrollment as completed
- **AND** no new merge, enrollment, branch, or effect authority is issued

#### Scenario: Final rescan gates workflow deletion

- **WHEN** every planned per-PR outcome has been persisted
- **THEN** apply freshly rescans every open pull request and records the final workflow/run/enrollment state
- **AND** the workflow file cannot be deleted unless the receipt is complete, the workflow is disabled and drained, and attributed plus ambiguous open-enrollment counts are zero

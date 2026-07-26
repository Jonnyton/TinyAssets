## ADDED Requirements

### Requirement: Retired Loop Labels Are Migrated Without Losing Repository Work

The repository SHALL remove the 27 product-loop label definitions:
`auto-bug`, `auto-change`, `auto-checker-dispatched`,
`auto-checker-failed`, `auto-fix-already-fixed`, `auto-fix-attempted`,
`auto-fix-auth-expired`, `auto-fix-auth-missing`, `auto-fix-blocked`,
`auto-fix-branch-push-blocked`, `auto-fix-claude-subscription-missing`,
`auto-fix-codex-subscription-missing`, `auto-fix-exhausted`,
`auto-fix-pr-blocked`, `auto-fix-provider-exhausted`,
`auto-fix-retries-1`, `auto-fix-retries-2`, `auto-fix-retries-3`,
`auto-fix-retries-4`, `auto-fix-retries-5`, `auto-fix-reviewed`,
`auto-fix-stale-gate`, `auto-fix-superseded`, `auto-fix-writer-failed`,
`community-loop-red`, `loop-consent`, and `priority:loop-discipline`.

Before mutation, an idempotent dry-run/apply migrator SHALL snapshot each
definition and every open or closed issue/PR association into a digest-bound
receipt. Apply SHALL remove retired labels from open items without closing
them, rewriting their bodies, or removing unrelated labels; publish one
repository-wide retirement notice linked to the receipt; and delete the label
definitions only after item migration succeeds. Closed item bodies remain
historical and their former associations remain recoverable from the receipt.

The migration SHALL preserve generic coordination vocabulary including
`daemon-request`, `request:*`, `payment:*`, `gate-required`, `checker:*`,
`writer:*`, `writer-pool:*`, `needs-human`, `priority:primitive-*`,
`merge-effector`, and `secure-merge`. After cutover, no active workflow,
script, website fallback, runtime, or agent skill may consume a retired label.

#### Scenario: Dry run changes no repository state

- **WHEN** the label migrator runs in dry-run mode
- **THEN** it emits the complete deterministic definition/item plan and receipt digest
- **AND** it does not edit an issue, pull request, label, notice, or repository file

#### Scenario: Open work remains open

- **WHEN** apply processes an open issue or pull request bearing one or more retired labels
- **THEN** it removes only those retired labels and preserves the item's state, title, body, comments, and unrelated labels
- **AND** the receipt records the before/after label sets and item identity

#### Scenario: Definitions leave only after migration

- **WHEN** every affected open item is migrated and the repository-wide notice is recorded idempotently
- **THEN** apply deletes all 27 retired label definitions
- **AND** a partial item/notice failure leaves remaining definitions intact for safe retry

#### Scenario: Generic labels survive

- **WHEN** a labelled item also carries generic request, gate, checker, writer, payment, primitive-priority, or merge vocabulary
- **THEN** those generic labels remain unchanged
- **AND** no retired label is renamed into a compatibility alias

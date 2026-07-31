## ADDED Requirements

### Requirement: Drain workers use bounded lane-local worktree inspection

`worktree_status.py --provider <needle>` SHALL apply its existing
case-insensitive slug, branch, or path match before constructing per-worktree
status. Nonmatching worktrees MUST NOT incur per-entry git probes. The filtered
records and ordering MUST equal the matching subset that the full inventory
would produce from the same snapshot.

A controller-launched worker SHALL run the diagnostic with its exact drain
identity and a 15-second cap. A timeout MUST NOT bypass exact claim, collision,
OpenSpec, or provider-context checks and MUST NOT grant authority to create,
switch, or edit another lane. The unfiltered command remains available as the
global session/operator diagnostic. An empty scoped result MUST be treated only
as diagnostic output; it MUST NOT prove that a lane is clean, grant edit
authority, or replace independent verification of the exact prepared worktree
and STATUS claim.

#### Scenario: Provider filter excludes historical lanes before probing

- **WHEN** the git inventory contains one worktree matching the provider needle
  and many nonmatching historical worktrees
- **THEN** only the matching entry is passed to per-worktree status construction
- **AND** the rendered or JSON result equals that entry's row from a full
  inventory snapshot

#### Scenario: Scoped diagnostic times out

- **WHEN** the exact-identity-scoped diagnostic exceeds 15 seconds
- **THEN** the worker records the timeout and continues only in its clean exact
  lane
- **AND** all exact claim, collision, OpenSpec, and provider-context gates still
  apply

#### Scenario: Provider filter matches no worktree

- **WHEN** the exact-identity-scoped diagnostic returns no rows
- **THEN** the worker treats the result only as an inventory observation
- **AND** it does not edit until the exact prepared worktree and STATUS claim
  are independently established and verified

### Requirement: Foldback continuation owns one fresh delivery PR

The drain's one-PR limit SHALL apply per disposable worker attempt. When a
worker resumes a `PARTIAL` result whose implementation PR is already merged,
that earlier PR MUST NOT consume the new worker's PR budget. The worker SHALL
restack onto current main, exclude merged implementation content, create at
most one fresh foldback PR for remaining coordination changes, and cite the
fresh foldback PR in `PARTIAL` or `MERGED`. It MUST NOT repeat the prior
implementation PR as its new terminal receipt.

#### Scenario: Merged implementation needs foldback

- **WHEN** the persisted prior result is `PARTIAL` for a verified merged
  implementation PR and current main retains the exact claim
- **THEN** the replacement worker is instructed to create one new foldback PR
- **AND** its terminal result cites that foldback PR rather than the
  implementation PR

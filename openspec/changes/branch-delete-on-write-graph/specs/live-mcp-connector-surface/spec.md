# Live MCP connector surface

## ADDED Requirements

### Requirement: An owner can delete their own branch through write_graph

`write_graph target=branch` SHALL accept `operation=delete` with `branch_id` on
both the universe surface and the served build surface, as an operation under the
existing `write_graph` handle and not as a new advertised tool. The operation SHALL
delete only a branch authored by the caller; for any other branch, including a
public one, it SHALL answer with the same not-found envelope a private read gives.
A public branch is a shape others copy or remix into their own universe and runs
nothing for anyone else, so it SHALL delete like any other. It SHALL refuse with
`branch_has_dependents`, naming each dependent it found, when any of these
readers still references the branch: an active automation (any universe), an
active webhook, an active schedule or event subscription, a canonical goal
binding (default, personal or legacy) on any of the branch's versions, another
branch of the same author — by current definition or by an active published
snapshot — that invokes it through `invoke_branch_spec` or
`invoke_branch_version_spec`, or a universe whose soul declares it as its loop
branch. A foreign snapshot that invoked the branch while it was public SHALL NOT
count: it was cut off when the branch went private and is not the owner's to
edit. Version ids SHALL be read uncapped. The branch's own patch snapshots in `branch_versions` SHALL NOT
count as a dependency. The tool text on both surfaces SHALL name the operation
and the refusal.

#### Scenario: An own private branch nothing depends on is deleted

- **WHEN** the author calls `write_graph target=branch operation=delete branch_id=<own private branch>`
- **THEN** the result is `{"branch_def_id": ..., "status": "deleted"}`
- **AND** `read_graph target=branches` no longer lists it

#### Scenario: A branch that was patched still deletes

- **WHEN** the author has patched the branch (which minted version snapshots) and then calls delete
- **THEN** it is deleted

#### Scenario: A public branch deletes like any other

- **WHEN** the author calls delete on their public branch that nothing of theirs depends on
- **THEN** it is deleted

#### Scenario: Dependents are named, not broken

- **WHEN** any listed reader references the branch
- **THEN** delete answers `branch_has_dependents` with the ids under `automations`, `webhooks`, `schedules`, `subscriptions`, `goals`, `branches`, `universes`
- **AND** nothing is deleted

#### Scenario: A non-author cannot probe

- **WHEN** a caller who is not the author calls delete on a public branch
- **THEN** the result is the not-found envelope

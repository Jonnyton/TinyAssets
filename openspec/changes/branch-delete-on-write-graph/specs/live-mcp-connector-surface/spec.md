# Live MCP connector surface

## ADDED Requirements

### Requirement: An owner can delete their own branch through write_graph

`write_graph target=branch` SHALL accept `operation=delete` with `branch_id` on
both the universe surface and the served build surface, as an operation under the
existing `write_graph` handle and not as a new advertised tool. The operation SHALL
delete only a branch authored by the caller; for any other branch, including a
public one, it SHALL answer with the same not-found envelope a private read gives.
It SHALL refuse a public branch with `branch_is_public`, and SHALL refuse a branch
that an automation, a canonical goal binding, or one of the caller's other
branches still depends on with `branch_has_dependents`, naming every dependent.
Internal patch snapshots in `branch_versions` SHALL NOT count as a dependency. The
tool text on both surfaces SHALL name the operation and both refusals.

#### Scenario: An own private branch nothing depends on is deleted

- **WHEN** the author calls `write_graph target=branch operation=delete branch_id=<own private branch>`
- **THEN** the result is `{"branch_def_id": ..., "status": "deleted"}`
- **AND** `read_graph target=branches` no longer lists it

#### Scenario: A branch that was patched still deletes

- **WHEN** the author has patched the branch (which minted version snapshots) and then calls delete
- **THEN** it is deleted

#### Scenario: A public branch is refused, and the advertised remediation works

- **WHEN** the author calls delete on their public branch
- **THEN** the result is `branch_is_public`
- **AND** after `patch set_visibility private`, delete succeeds

#### Scenario: Dependents are named, not broken

- **WHEN** an active automation is bound to the branch, or a goal's canonical binding points at one of its versions, or another of the author's branches invokes it
- **THEN** delete answers `branch_has_dependents` with the automation ids, goal ids and branch ids
- **AND** nothing is deleted

#### Scenario: A non-author cannot probe

- **WHEN** a caller who is not the author calls delete on a public branch
- **THEN** the result is the not-found envelope, not `branch_is_public`

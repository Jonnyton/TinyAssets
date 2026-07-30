## ADDED Requirements

### Requirement: OpenSpec Drain Hosts Are Consoleless On Windows

The development coordination runtime SHALL start the sign-in tray host and all
provider subprocesses without creating a visible Windows console, so closing an
unrelated terminal cannot terminate the tray or active drain.

#### Scenario: Scheduled tray starts after sign-in

- **WHEN** the current-user scheduled task starts the drain tray
- **THEN** no command or PowerShell console is displayed
- **AND** the scheduled host remains alive while the tray process is alive

#### Scenario: Provider CLI resolves through a command shim

- **WHEN** a Windows worker launches a provider CLI whose executable is a
  `.CMD` shim
- **THEN** the launcher creates the subprocess with no console window
- **AND** stdout and stderr remain captured for the attempt artifact

### Requirement: Drain Workers Can Deliver From Linked Worktrees

The development coordination runtime SHALL resolve and grant a write-capable
Codex worker access to its assigned linked worktree's Git common directory,
SHALL use an explicit Git-metadata-capable write mode, SHALL direct the worker
to publish with repository-local `git` and `gh` commands, and MUST preserve the
existing worktree, branch, claim, review, CI, and finite-budget safety
boundaries. Read-only peers MUST remain read-only.

#### Scenario: Codex worker receives a linked worktree

- **WHEN** write mode launches Codex from a linked worktree
- **THEN** the launcher resolves that worktree's absolute Git common directory
- **AND** passes it as an additional writable directory
- **AND** selects the explicit write sandbox mode required to stage and commit

#### Scenario: Read-only worker is launched

- **WHEN** the peer launcher runs in read-only mode
- **THEN** it does not add Git metadata as a writable directory

#### Scenario: Verified work is ready to publish

- **WHEN** a drain worker has completed its acceptance, tests, and required
  review
- **THEN** it uses shell `git` and `gh` from the assigned worktree for
  commit, push, and pull-request delivery

### Requirement: Delivery Failure Is Distinct From Durable Work Blocking

The OpenSpec drain supervisor SHALL reserve `BLOCKED` for durable task, host,
dependency, review, or policy gates and SHALL treat failure to stage, commit,
push, or create a pull request as a retryable `FAILED` delivery result. A
delivery failure MUST preserve the admitted target and worktree so the next
fresh worker resumes it under the existing finite failure budget.

#### Scenario: Git metadata cannot be written

- **WHEN** a worker has verified local work but staging or committing fails
- **THEN** it returns `FAILED` for the admitted target
- **AND** the supervisor preserves the admission for the next worker
- **AND** it does not add the target to the recent-blocked set

#### Scenario: Pull-request publication is unavailable

- **WHEN** commit or push succeeds but the supported pull-request publication
  route fails
- **THEN** the worker returns `FAILED` for the admitted target
- **AND** a fresh worker resumes delivery immediately within the finite budget

#### Scenario: Work requires a host-only test subject

- **WHEN** the remaining acceptance contract requires an unavailable host
  action or external test identity
- **THEN** the worker returns `BLOCKED` with the durable reason
- **AND** the supervisor may select different work after its blocked interval

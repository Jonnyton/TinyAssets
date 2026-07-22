## ADDED Requirements

### Requirement: Enumerate every supported local lane shape

The stranded-lane detector SHALL inspect the union of registered Git worktrees
and supported sibling or scratch clone locations, de-duplicated by resolved
path.

#### Scenario: Standalone scratch clone is not a registered worktree

- **GIVEN** a Git clone under `.codex-scratch-*` that is absent from `git
  worktree list --porcelain`
- **WHEN** the detector runs from the primary repository
- **THEN** the clone is still inspected and can be named in the result

### Requirement: Fail on incomplete publication

The detector SHALL exit 2 and report `STRANDED` when a readable lane has one or
more commits in `origin/main..HEAD` and either its current branch is not pushed
to `origin` or no pull request exists for that branch in any state.

#### Scenario: Ahead commit has no remote branch

- **GIVEN** a checkout with one commit ahead of `origin/main`
- **AND** its current branch is absent from the origin heads
- **WHEN** the detector runs
- **THEN** it exits 2 and names the path, branch, head, ahead count, and missing
  remote branch

#### Scenario: Historical audit base is explicit

- **GIVEN** a shallow scratch clone contains historical base commit `2c1f63cb`
  but no `origin/main` tracking ref
- **WHEN** the detector runs with `--base-ref 2c1f63cb`
- **THEN** it computes the ahead count without fetching or changing the clone

#### Scenario: Ahead commit is fully published

- **GIVEN** a checkout with one commit ahead of `origin/main`
- **AND** its current branch exists on origin
- **AND** a pull request exists for that branch
- **WHEN** the detector runs
- **THEN** the lane is not reported as stranded and the command exits 0 when no
  other stranded or unknown lanes exist

### Requirement: Unknown lanes fail visibly

The detector SHALL report an unreadable or indeterminate supported checkout as
`UNKNOWN` and exit 2 without modifying the checkout, Git configuration, or any
remote state.

#### Scenario: Git rejects sandbox-owned checkout ownership

- **GIVEN** Git returns a dubious-ownership error for a discovered checkout
- **WHEN** the detector attempts to inspect it
- **THEN** the output names the path and error class, exits 2, and does not add a
  safe-directory exception

### Requirement: Detector remains read-only and narrowly scoped

The detector SHALL limit its operations to filesystem discovery and read-only
Git/GitHub queries.

#### Scenario: Detector identifies a strand

- **WHEN** a stranded lane is reported
- **THEN** no file, branch, remote, pull request, worktree, or Git configuration
  is created, changed, pushed, cleaned, or deleted

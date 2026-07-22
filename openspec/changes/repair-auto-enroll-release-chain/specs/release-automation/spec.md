# Release automation

## ADDED Requirements

### Requirement: Release-relevant main commits converge to production without merge events

The repository SHALL periodically compare the latest release-relevant commit on `main` with successful production deploy ancestry. When no successful production deploy contains that commit, automation SHALL dispatch the canonical image-build workflow without depending on a push or pull-request event emitted by the merging token.

#### Scenario: An Actions-token merge emits no workflow runs

- **GIVEN** an auto-merged commit on `main` changes a release-relevant path
- **AND** the merge produces no push-triggered workflow run
- **WHEN** scheduled release reconciliation runs
- **THEN** it SHALL detect that no successful production deploy contains the commit
- **AND** it SHALL dispatch `build-image.yml` on `main`.

### Requirement: Enrolled behind branches are updated automatically

The repository SHALL periodically inspect open pull requests targeting `main`. A pull request that is non-draft, enrolled for auto-merge, and reported `BEHIND` SHALL have its head branch updated so strict branch protection can rerun checks and merge it when green.

#### Scenario: A green enrolled PR falls behind main

- **GIVEN** an open, non-draft pull request targeting `main`
- **AND** it is enrolled for auto-merge
- **AND** GitHub reports its merge state as `BEHIND`
- **WHEN** scheduled branch reconciliation runs
- **THEN** automation SHALL request an update of that pull request branch.

#### Scenario: A PR is not eligible for branch reconciliation

- **GIVEN** a pull request that is draft, not enrolled, closed, or not `BEHIND`
- **WHEN** scheduled branch reconciliation runs
- **THEN** automation SHALL NOT request a branch update for it.

### Requirement: Strict protection remains enabled

Repairing the update loop SHALL NOT require disabling strict required-status-check freshness, and SHALL NOT introduce a long-lived PAT or GitHub App private key for merge enrollment.

#### Scenario: Repair preserves the gate

- **GIVEN** branch protection requires current branches
- **WHEN** the automation repairs an enrolled PR that has fallen behind
- **THEN** it SHALL update the branch and allow required checks to rerun rather than weaken protection.

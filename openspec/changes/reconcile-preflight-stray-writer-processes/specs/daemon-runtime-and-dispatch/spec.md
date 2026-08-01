## ADDED Requirements

### Requirement: Deploy Preflight Confirms Exact Container Ownership Before Stray-Writer Refusal

The production deploy fence SHALL reconcile preliminary writer-process
candidates against one fresh PID snapshot from the exact container identities
already inspected by preflight before classifying any candidate as an unowned
stray writer. It MUST ignore a candidate only when that PID no longer exists or
the fresh snapshot proves the captured exact container generation owns it. It
MUST keep every still-live candidate whose exact-container ownership is absent
or unproved, and MUST fail before host mutation when any such candidate
remains. Refusal MUST expose only the existing fixed process-risk class and
MUST NOT publish process, command-line, environment, mount, receipt, or
identity details.

#### Scenario: Container spawns a process between ownership snapshots

- **WHEN** the preliminary process scan finds a live candidate that was absent
  from the first Docker PID snapshot
- **AND** one fresh snapshot proves that an exact container identity captured
  by preflight now owns that PID
- **THEN** preflight does not classify that candidate as a stray writer
- **AND** every other queue, receipt, unit, fleet, and process proof remains
  required before mutation

#### Scenario: Live host writer remains unowned

- **WHEN** a preliminary candidate still exists and no captured exact container
  identity owns its PID in the fresh snapshot
- **THEN** preflight fails before host mutation with the fixed stray-process
  risk class
- **AND** no candidate detail is published

#### Scenario: Candidate exits before confirmation

- **WHEN** a preliminary candidate PID no longer exists at confirmation time
- **THEN** it is not treated as a live stray writer
- **AND** later process and queue proofs remain mandatory

#### Scenario: Container identity cannot prove ownership

- **WHEN** fresh Docker PID lookup for a captured identity fails, returns no
  ownership, or a same-name replacement exists
- **THEN** a still-live preliminary candidate is not excused by that container
- **AND** preflight fails before mutation if the candidate remains unowned

#### Scenario: Bounded candidate churn retains one genuine survivor

- **WHEN** the maximum bounded preliminary candidate set contains exited PIDs,
  newly container-owned PIDs, and one still-live unowned PID
- **THEN** confirmation takes one fresh exact-container PID snapshot
- **AND** it returns only the genuine unowned survivor for fail-closed refusal

## ADDED Requirements

### Requirement: Deploy Preflight Confirms Exact Container Ownership Before Stray-Writer Refusal

The production deploy fence SHALL use captured nonempty exact container IDs for
both its initial process-exclusion snapshot and one fresh confirmation snapshot
before classifying a preliminary candidate as an unowned stray writer. Those
IDs MUST cover the inspected expected fleet, extra volume consumers, and
admitted recovery sidecars; mutable names MUST NOT establish ownership. A
per-identity Docker PID lookup MUST contribute ownership only when it succeeds
with a complete well-formed header and PID rows. Nonzero, timed-out, malformed,
missing-header, or partial output MUST contribute zero trusted PIDs and MUST
NOT expose raw errors. Each candidate MUST bind its PID to the Linux process
generation captured during the scan. The fence MUST ignore a candidate only
when it exited, or when the fresh exact-ID snapshot owns its PID and a recheck
proves the process generation is unchanged. It MUST keep a live candidate when
ownership is absent or unproved, the generation is unreadable, or the PID was
reused, and MUST fail before host mutation when any such candidate remains. It
MUST refuse a 101st risk candidate rather than truncate the bounded 100-item
inventory. Refusal MUST expose only fixed process-risk or overflow classes and
MUST NOT publish process, command-line, environment, mount, receipt, identity,
or raw Docker-error details.

#### Scenario: Container spawns a process between ownership snapshots

- **WHEN** the preliminary process scan finds a live candidate that was absent
  from the first Docker PID snapshot
- **AND** one fresh complete snapshot proves that a captured exact container ID
  now owns that PID
- **AND** the process-generation recheck equals the scanned generation
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

- **WHEN** Docker PID lookup for a captured identity fails, times out, has a
  missing header, is malformed or partial, or returns no ownership
- **THEN** a still-live preliminary candidate is not excused by that container
- **AND** no raw Docker failure or output is published
- **AND** preflight fails before mutation if the candidate remains unowned

#### Scenario: Same-name replacement precedes the initial snapshot

- **WHEN** a captured exact container is replaced under the same mutable name
  between inspection and the initial process-exclusion snapshot
- **THEN** only the captured nonempty exact ID is queried for ownership
- **AND** the replacement PID remains eligible for preliminary risk detection

#### Scenario: Numeric PID is reused after Docker ownership snapshot

- **WHEN** Docker reports a candidate PID as owned by a captured exact container
- **AND** the scanned process exits and another process reuses that numeric PID
  before confirmation classifies it
- **THEN** the changed or unreadable process generation prevents ownership from
  being trusted
- **AND** the live candidate remains fail-closed before mutation

#### Scenario: Bounded candidate churn retains one genuine survivor

- **WHEN** exactly 100 preliminary candidates contain exited PIDs, newly
  same-generation container-owned PIDs, and one still-live unowned PID
- **THEN** confirmation takes one fresh exact-container PID snapshot
- **AND** it returns only the genuine unowned survivor for fail-closed refusal

#### Scenario: Candidate inventory exceeds the bounded cap

- **WHEN** process scanning encounters a 101st risk candidate
- **THEN** it fails before mutation with a fixed overflow class
- **AND** it does not silently truncate or publish any candidate detail

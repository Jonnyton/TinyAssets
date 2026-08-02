## ADDED Requirements

### Requirement: Windows release lifecycle verification has an independent total deadline
The desktop release workflow SHALL execute the exact unsigned Windows installer lifecycle beneath a non-PowerShell parent supervisor whose total deadline is independent of all waits and cleanup performed by the lifecycle child. The supervisor deadline MUST expire before the GitHub job timeout begins cancellation, and the job timeout MUST remain as defense in depth rather than the primary lifecycle bound.

#### Scenario: Lifecycle child hangs inside a phase or cleanup path
- **WHEN** the Windows lifecycle child does not exit before the supervisor's total deadline
- **THEN** the supervisor reports a non-zero timeout verdict without waiting for the GitHub job timeout
- **AND** cleanup of the child tree is itself bounded

#### Scenario: Lifecycle completes normally
- **WHEN** install, packaged health probe, same-version repair, and content-preserving uninstall all complete within the total deadline
- **THEN** the supervisor returns the lifecycle child's successful verdict
- **AND** the workflow continues to later signing gates without weakening any artifact or identity check

### Requirement: Caught Windows lifecycle failures retain phase diagnostics
The lifecycle child SHALL report each phase name and root process identity before waiting, and the outer supervisor SHALL capture child stdout and stderr outside the workflow output handles and replay a fixed byte-capped snapshot before returning its verdict. The supervisor MUST report the cap and observed byte count when either stream is truncated. An escaped or continuously writing descendant MUST NOT retain the workflow step's output handles or extend replay beyond the bounded margin, and supervisor timeout evidence MUST name the configured total deadline.

#### Scenario: Supervisor catches a synthetic hung child
- **WHEN** a Windows regression child emits a phase marker, writes continuously, and then exceeds the total deadline
- **THEN** the supervisor's returned output contains the child marker and the total-timeout verdict
- **AND** the output contains truthful truncation evidence and remains below the configured replay bound
- **AND** the regression completes within a bounded wall-clock interval

#### Scenario: Child fails before the total deadline
- **WHEN** the lifecycle child exits non-zero after emitting diagnostic output
- **THEN** the supervisor replays stdout and stderr and returns a non-zero child-failure verdict

### Requirement: Lifecycle recovery does not overstate desktop release readiness
The bounded unsigned Windows lifecycle gate SHALL remain supporting CI evidence only. It MUST NOT be represented as signed publication, cross-platform clean-machine acceptance, the under-five-minute Tier-2 cohort proof, or post-release organic-use evidence.

#### Scenario: Unsigned lifecycle gate passes
- **WHEN** the supervised unsigned Windows lifecycle completes successfully
- **THEN** release state may record that exact CI artifact verification passed
- **AND** signed publication and clean-machine acceptance remain independently gated

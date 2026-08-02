## MODIFIED Requirements

### Requirement: Caught Windows lifecycle failures retain phase diagnostics
The lifecycle child SHALL report each phase name and root process identity before waiting, and the outer supervisor SHALL capture child stdout and stderr in private files that are not workflow output handles and replay a fixed byte-capped snapshot before returning its verdict. The supervisor MUST report the cap and observed byte count when either stream is truncated. An escaped or continuously writing descendant MUST NOT retain the workflow step's output handles, extend replay beyond the bounded margin, or make supervisor completion depend on descendant EOF; supervisor timeout evidence MUST name the configured total deadline.

#### Scenario: Supervisor catches a synthetic hung child
- **WHEN** a Windows regression child emits a phase marker, writes continuously, and then exceeds the total deadline
- **THEN** the supervisor's returned output contains the child marker and the total-timeout verdict
- **AND** the output contains truthful truncation evidence and remains below the configured replay bound
- **AND** the regression completes within a bounded wall-clock interval

#### Scenario: Lifecycle parent exits while a descendant retains inherited handles
- **WHEN** the PowerShell lifecycle parent exits after starting a descendant that retains inherited stdout and stderr handles
- **THEN** the supervisor returns the lifecycle verdict within its bounded margin without waiting for descendant EOF
- **AND** replay uses the fixed capture horizon observed at verdict time
- **AND** the descendant holds no GitHub workflow output handle

#### Scenario: Child fails before the total deadline
- **WHEN** the lifecycle child exits non-zero after emitting diagnostic output
- **THEN** the supervisor replays stdout and stderr and returns a non-zero child-failure verdict

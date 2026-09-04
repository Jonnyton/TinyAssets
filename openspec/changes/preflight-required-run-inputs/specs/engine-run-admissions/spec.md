## ADDED Requirements

### Requirement: Unresolved required inputs are refused before run admission
The engine SHALL preflight the exact authorized Branch target before creating or
admitting a run, and SHALL refuse a submission when any declared node input is not
supplied, defaulted, or guaranteed by an earlier node.

#### Scenario: Invalid initial state creates no activity
- **WHEN** a caller submits a valid authorized Branch target with one or more unresolved required inputs
- **THEN** the engine returns `failure_class=missing_required_inputs` without a run id and creates no run row, queue item, admission or billing record, provider call, or effect

#### Scenario: Supplied and defaulted inputs admit normally
- **WHEN** every required initial input is present in `inputs_json` or has a declared schema default
- **THEN** the existing run admission and execution path proceeds unchanged

#### Scenario: Authorization precedes contract disclosure
- **WHEN** a caller is not authorized to run or read a private Branch target
- **THEN** the existing authority-safe not-found or refusal result is returned without disclosing missing keys or schema guidance

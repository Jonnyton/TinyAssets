## ADDED Requirements

### Requirement: Background branch provider calls use distinct assigned authority
Every daemon-owned queued branch provider launch MUST use operation `background_branch_run`, MUST select only the task universe's current assigned serving provider, and MUST use a separate provider-work binding whose roles and spend ceilings are bounded by the pinned branch and background attempt. The interactive `converse`/`writer` binding SHALL NOT authorize this operation.

#### Scenario: Interactive grant only
- **WHEN** a universe has a valid `converse`/`writer` serving grant but no valid background branch binding and attempt
- **THEN** queued background execution is held before credential or provider access

#### Scenario: Cross-universe or cross-provider substitution
- **WHEN** a task, assignment, provider binding, custody reference, or supplied policy identifies another universe or provider
- **THEN** the launch is rejected with no ambient or fallback provider attempt

### Requirement: Background spend is reserved before launch
The authority path MUST durably reserve attempt, invocation, token, and cost budget before provider launch, MUST reuse the same attempt budget on retry, and MUST always remove a temporary credential snapshot in `finally`.

#### Scenario: Retry after pre-launch failure
- **WHEN** a launch fails before crossing the provider boundary and the same task retries
- **THEN** the existing attempt budget is reused rather than minting another full budget

#### Scenario: Credential rotates before launch
- **WHEN** custody or assignment rotates before the launch fence is armed
- **THEN** authorization fails closed and no stale or ambient credential launches

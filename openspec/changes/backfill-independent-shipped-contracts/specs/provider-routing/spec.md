## ADDED Requirements

### Requirement: The provider call bridge retries only transient full-chain exhaustion
The shared provider call bridge SHALL retry `AllProvidersExhaustedError` up to three total router attempts with exponential waits bounded from two through eight seconds. It SHALL NOT retry unrelated exceptions. After failure or when no router exists, it SHALL return the caller-supplied fallback response when present and otherwise re-raise the original unrelated error, or raise `AllProvidersExhaustedError` for exhaustion or a missing router, rather than synthesize empty prose.

#### Scenario: Transient exhaustion clears
- **WHEN** the first router attempt raises `AllProvidersExhaustedError` and the second succeeds
- **THEN** the bridge returns the successful provider text after two attempts

#### Scenario: Three exhaustion attempts use the explicit fallback
- **WHEN** all three router attempts raise `AllProvidersExhaustedError` and `fallback_response` is supplied
- **THEN** the bridge returns that fallback response

#### Scenario: Exhaustion without fallback fails loudly
- **WHEN** all router attempts exhaust and no fallback response is supplied
- **THEN** the final `AllProvidersExhaustedError` is raised

#### Scenario: Unrelated exception is not retried
- **WHEN** the router raises an exception other than `AllProvidersExhaustedError`
- **THEN** the bridge performs one router attempt and then returns the supplied fallback or re-raises that exception

#### Scenario: No router preserves fallback semantics
- **WHEN** no router is installed
- **THEN** the bridge returns a supplied fallback immediately or raises `AllProvidersExhaustedError` when no fallback exists

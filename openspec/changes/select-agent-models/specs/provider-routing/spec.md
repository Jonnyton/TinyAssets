## ADDED Requirements

### Requirement: Automatic interactive-agent selection respects owner priorities
Automatic interactive-agent routing SHALL prefer eligible owner-connected subscription or local sources over OpenRouter, then order suitable OpenRouter models using fresh ranking evidence; explicit owner choices and accepted fallback order SHALL override automatic ranking.

#### Scenario: Multiple connected sources
- **WHEN** automatic mode has an eligible subscription/local source and OpenRouter
- **THEN** it starts with the subscription/local source without borrowing any ambient host credential

#### Scenario: OpenRouter only
- **WHEN** automatic mode has only OpenRouter
- **THEN** it selects the best-ranked eligible model and maintains ordered compatible alternatives, without embedding model-release names in platform code

### Requirement: Fallback preserves spend and inference authority
Every interactive fallback attempt SHALL revalidate current owner authority, capability and cost constraints; free onboarding SHALL NOT authorize paid fallback.

#### Scenario: Revoked candidate
- **WHEN** an accepted fallback's grant is revoked before invocation
- **THEN** no inference uses that grant and no broader credential is substituted

#### Scenario: Free model withdrawn
- **WHEN** a free-only choice becomes unavailable or paid
- **THEN** the runtime uses another authorized free compatible candidate or waits without charging for a paid replacement

### Requirement: Capacity fallback preserves completed work
The runtime SHALL distinguish model-local capacity from proven shared account limits, honor retry information and preserve completed tool results without replaying effects.

#### Scenario: Account allowance exhausted
- **WHEN** a typed refusal identifies exhaustion shared by all models on an account
- **THEN** the runtime skips those sibling models and tries an authorized independent source or shows a waiting state

#### Scenario: Ambiguous tool completion
- **WHEN** an inference fails after a tool might have executed without a durable result
- **THEN** fallback does not replay that action as a fresh turn

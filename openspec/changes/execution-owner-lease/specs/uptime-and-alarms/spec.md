## ADDED Requirements

### Requirement: A Deploy Hands Over Owners Per Command Center Or Touches Frontends Only, And Measures Both
A deploy that changes only frontend modules SHALL replace frontends blue-green. Old frontends SHALL keep their open streams until those streams end, and the deploy SHALL NOT touch any owner. A deploy that changes owner code SHALL move each command center to the new owner only when that command center is idle, and SHALL NOT cut running work except by explicit operator force. Each deploy SHALL report failed requests, interrupted executions, and how long any old owner lingered.

#### Scenario: A frontend-only deploy interrupts nothing
- **WHEN** a merge changes only frontend modules while a long turn runs
- **THEN** the turn keeps running in its owner, and the deploy reports zero failed requests and zero interrupted executions

#### Scenario: An owner deploy waits per command center, not for the slowest turn
- **WHEN** an owner deploy runs while one command center has a long turn and others are idle
- **THEN** the idle ones move at once, the busy one moves when its turn finishes, and the report shows zero interrupted executions

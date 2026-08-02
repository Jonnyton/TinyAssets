## ADDED Requirements

### Requirement: Terminal Receipt Separates Cleanup From Forward And Rollback Truth

Terminal publication SHALL preserve the original forward and rollback
observations while separately recording whether deploy cleanup restored the
boot posture or safely re-fenced the fleet. It SHALL derive running image
identity only from a container whose inspected running state is true.

#### Scenario: Post-forward cleanup safely fences the fleet

- **WHEN** the forward deploy and its canary succeed, rollback is truthfully
  `not_needed`, and cleanup cannot prove restored boot posture but does prove
  the fleet authoritatively restart-fenced
- **THEN** the terminal receipt preserves the successful forward and
  not-needed rollback tuple
- **AND** records cleanup mutation, `cleanup_restored=false`, and
  `cleanup_safely_fenced=true`
- **AND** classifies the terminal outcome as `failed_without_rollback` with a
  failed applicable canary instead of rejecting a contradictory synthesized
  rollback tuple or reporting the stopped container as running

#### Scenario: Cleanup proof is contradictory or incomplete

- **WHEN** cleanup is simultaneously recorded restored and safely fenced, a
  safe fence lacks a cleanup mutation marker, or a mutated production deploy
  has neither exact restoration nor safe-fence proof
- **THEN** terminal receipt construction fails closed and the workflow remains
  red without replacing the prior atomic receipt

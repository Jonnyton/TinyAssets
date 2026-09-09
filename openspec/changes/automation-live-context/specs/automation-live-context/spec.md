# ADDED Requirements

## Requirement: Resolve opt-in inputs at execution time
The scheduler SHALL resolve an exact top-level `{"$automation_context":"v1"}` input against the persisted automation owner's universe after the current authority check and before graph admission. Inputs without the marker SHALL retain existing behavior.

### Scenario: A founder signal arrives between runs
- WHEN a founder conversation row is recorded after one run
- THEN the next run SHALL receive the latest stored row with its provenance, alongside current brain content and the preceding terminal run's output.

## Requirement: Preserve scope and evidence
The resolver SHALL reject foreign, missing, nonterminal or mismatched prior-run references, reject universe and file escapes, preserve failure evidence, and label all recovered content as evidence without granting authority. Prior snapshots SHALL NOT recursively accumulate. Missing source stores SHALL be explicit; corrupt stores and excessive input size SHALL fail visibly. A limited conversation window SHALL expose its history gap.

### Scenario: A recorded approval is replayed
- WHEN conversation data contains approval text
- THEN the snapshot SHALL preserve it as historical evidence without treating it as a new authorization.

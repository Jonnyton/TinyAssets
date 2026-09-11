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


### Requirement: recover committed progress after a failed wake
The context MUST expose last_completed_run separately from previous_run. The former MUST be scoped to this automation and universe and preserve non-input output. Missing, foreign, or inconsistent committed run records MUST refuse recovery. The immediate failed result MUST remain visible for diagnosis.

### Requirement: deterministic artifact completion
The optional progress helper MUST retain earlier entries without mutation, reject completed work IDs, reject identical content under renamed IDs, and reject corrupted checkpoints. It MUST NOT claim shared ownership or exactly-once external effects.

## ADDED Requirements

### Requirement: Executable soul-loop declaration and target authority advance together
The system SHALL treat the normalized loop branch in governed `soul.md` as executable configuration bound to the pinned soul version/content digest. As built, `UniverseSoul.loop_branch_def_id` is rendered/read from the `Loop branch` declaration and `PROGRAM.md` is only a legacy fallback; this change makes that existing declaration authoritative rather than inventing a second loop field. Universe creation through `seed_okf_bundle` or a governed edit through `apply_soul_edit` MUST prepare, authorize, and commit a matching `BackgroundBranchBinding`, or a narrow carry-forward when the normalized target is unchanged, before publishing a runnable loop generation. A changed target MUST require fresh authenticated target authorization or an existing binding that explicitly delegates that exact target. These binding clauses MUST remain dark until universe-creation ownership, store ownership, and live-activation prerequisites pass.

#### Scenario: Unchanged target carries only narrow scope
- **WHEN** an authorized governed edit changes soul content while preserving the normalized loop branch
- **THEN** the system may bind the new pinned soul digest to the same exact target scope
- **AND** it does not inherit any broader rights of the principal or learning source

#### Scenario: Changed target requires target authorization
- **WHEN** a governed edit names a different loop branch without fresh authority or an exact delegated target
- **THEN** the edit cannot publish a runnable loop generation

### Requirement: Cross-store soul transitions recover by exact digest
The system SHALL coordinate the existing compare-and-swap soul edit/snapshot with loop-binding prepare/commit/revoke state. After a crash, recovery MUST compare the current pinned soul digest and normalized target with the prepared candidate: an exact candidate match commits it, an exact old-state match aborts it, and any third state quarantines the loop. Execution MUST accept only the active binding whose soul digest and target exactly match current pinned state.

#### Scenario: Crash after soul write converges
- **WHEN** the soul file and snapshot are written but the candidate binding was not committed before a crash
- **THEN** recovery commits that exact candidate if its digest and target match
- **AND** no second binding generation is invented

#### Scenario: Third state fails closed
- **WHEN** recovery finds a soul digest or normalized loop target matching neither the prepared candidate nor the old committed state
- **THEN** the loop enters `reauthorization_required` and no legacy or prior binding is used

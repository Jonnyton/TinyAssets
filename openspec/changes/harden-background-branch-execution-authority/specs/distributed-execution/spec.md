## ADDED Requirements

### Requirement: Distributed workers require independent target and execution authority
The distributed execution path SHALL treat queue/admission reservation, `BackgroundBranchAttempt`, B2 execution grant, provider-work authority, provider-attempt receipt, and payment/effect authority as separate domains. Before resolving a branch or creating a run, a worker MUST claim the exact target attempt for the physical universe, task/source generation, and worker audience. It MUST additionally satisfy each other domain that applies to the operation. No receipt, verdict, signature, identifier, lease, or serialized envelope from one domain may mint or substitute for another. Target-attempt enforcement MUST remain dark until both this capability's B2 owner and background-target live-activation prerequisites pass.

#### Scenario: B2 grant cannot replace target authority
- **WHEN** a worker has a valid B2 execution grant but the background target attempt is missing, revoked, or bound to another physical universe
- **THEN** branch execution is refused before branch resolution or run creation

#### Scenario: Target authority cannot replace B2
- **WHEN** a worker has a valid current background target attempt but distributed execution requires B2 and no valid B2 grant exists
- **THEN** distributed execution remains pending or held without treating the target attempt as B2 authority

#### Scenario: Cross-domain references remain non-authorizing
- **WHEN** audit records link target, B2, and provider receipt IDs/digests
- **THEN** each authority service still validates its own current record and generation independently

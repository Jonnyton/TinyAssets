## ADDED Requirements

### Requirement: Goal Branch protocols are ordered metadata, not an executor
The system SHALL let an authenticated Goal author or the literal `host` actor replace a Goal's `branch_protocol` through `goals action=define_protocol`, persist the protocol as an ordered list of metadata step objects, and expose it through `goals action=get` and `goals action=get_protocol`. Each step MUST reference an existing Branch bound to that Goal; the system SHALL coerce a truthy `order` to an integer, substitute the one-based input position when `order` is omitted or otherwise falsy (including an explicitly supplied numeric zero), sort steps by the resulting order, and default `step_id`, `status`, artifact-label lists, `source_label`, `required_rung_key`, `required_verdict`, `rollback_policy`, and `next_step_conditions` when absent. The first step whose normalized status is not `completed`, `skipped`, or `superseded` SHALL be reported as `current_protocol_step`. Protocol fields SHALL remain descriptive metadata: this surface SHALL NOT execute a referenced Branch, enforce prerequisites or verdicts, advance step state, or perform rollback.

#### Scenario: Defining a protocol normalizes and orders bound Branch steps
- **WHEN** the Goal author submits a JSON list whose step objects reference Branches bound to that Goal and contain valid truthy integer-coercible `order` values
- **THEN** the system persists the normalized steps in ascending `order`, supplies missing metadata defaults, and reports the first non-terminal step as current

#### Scenario: Explicit zero order follows the falsy default path
- **WHEN** a protocol step after the first input position supplies numeric `order=0`
- **THEN** the current normalizer replaces zero with that step's input position before sorting rather than preserving zero as an explicit order

#### Scenario: Invalid or unbound protocol steps are rejected
- **WHEN** a protocol is not a JSON list, contains a non-object step, omits `branch_def_id`, references a missing or differently bound Branch, or supplies an order that cannot be converted to an integer
- **THEN** the system rejects the replacement and does not persist that invalid protocol

#### Scenario: Protocol reads expose the same stored metadata
- **WHEN** a caller reads a Goal with `goals action=get` or reads its protocol with `goals action=get_protocol`
- **THEN** the response includes the stored ordered protocol and the same first non-terminal `current_protocol_step`, or an empty protocol and no current step when none is defined

#### Scenario: Protocol metadata does not execute or roll back work
- **WHEN** a stored step carries `required_rung_key`, `required_verdict`, `rollback_policy`, or `next_step_conditions`
- **THEN** defining or reading the protocol only round-trips those values and does not run a Branch, test the condition, advance status, or perform rollback

### Requirement: Common-node discovery compares exact node identifiers
The system SHALL implement `goals action=common_nodes` as exact, case-sensitive `node_id` equality over viewer-visible Branch definitions, counting a repeated identifier at most once per Branch and returning only identifiers meeting `min_branches` (coerced to at least one), ordered by descending Branch occurrence and capped by `limit` (coerced to at least one). The default `scope=this_goal` MUST require `goal_id` and restrict aggregation to Branches bound to that Goal; `scope=all` SHALL aggregate across every visible Branch, including unbound Branches, and include the distinct non-empty Goal IDs where each node occurred. Display names, descriptions, prompt text, and semantic similarity SHALL NOT merge different node IDs.

#### Scenario: Goal-scoped discovery finds an exact repeated node ID
- **WHEN** two viewer-visible Branches bound to the requested Goal each contain a node with the same non-empty `node_id` and the threshold is two
- **THEN** common-node discovery returns one entry for that identifier with occurrence count two and both Branch IDs

#### Scenario: Repetition inside one Branch counts once
- **WHEN** a single Branch contains more than one node record with the same `node_id`
- **THEN** that Branch contributes exactly one occurrence for the identifier

#### Scenario: Similar nodes with different IDs remain separate
- **WHEN** Branches contain nodes with similar names, descriptions, or prompts but different `node_id` values
- **THEN** common-node discovery does not combine those nodes into one entry

#### Scenario: Cross-Goal discovery includes visible unbound Branches
- **WHEN** a caller selects `scope=all`
- **THEN** the system aggregates exact node IDs across all viewer-visible Branches, counts unbound Branches, and lists only the non-empty Goal IDs associated with each returned node

### Requirement: Archive consultation uses a fixed server-side parent heuristic
The system SHALL implement `goals action=archive_consultation` with the fixed server-side parent score `0.4 * quality + 0.4 * outcome + 0.2 * diversity` over viewer-visible Branches bound to the requested Goal. Quality MUST be the Branch `avg_quality_score` clamped to `[0,1]`; outcome MUST be the highest active, non-orphaned gate-rung index normalized by the Goal ladder's maximum index (or zero when no positive maximum exists); diversity SHALL be recomputed greedily against already selected candidates from tokens drawn from Branch identity, author, tags, and node IDs/display names. A non-empty query SHALL filter candidates to those sharing at least one normalized token before ranking. This ranking SHALL remain fixed platform logic and SHALL NOT dispatch the Goal's selector Branch.

#### Scenario: Quality and outcome jointly rank parent candidates
- **WHEN** archive consultation runs for a Goal whose visible Branches have quality scores and active gate claims
- **THEN** the response ranks candidates greedily by the fixed quality, outcome, and diversity weights and includes the component scores, parent score, selection basis, and matching outcome-leaderboard entries

#### Scenario: Query filtering precedes parent ranking
- **WHEN** archive consultation receives a non-empty query
- **THEN** only candidates whose normalized feature tokens overlap the query tokens enter the ranking pool

#### Scenario: Archive consultation does not use the Goal selector
- **WHEN** a Goal has a custom selector Branch and archive consultation is invoked
- **THEN** the consultation still uses the fixed server-side `0.4/0.4/0.2` heuristic and does not dispatch that selector

### Requirement: Outcome-gate ladders are flag-gated Goal metadata with scoped definition authority
The system SHALL expose the `gates` action surface only while `GATES_ENABLED` is enabled; otherwise every gates action MUST return `status=not_available` without dispatching its handler. `gates action=define_ladder` SHALL replace a Goal's entire ordered rung list only when each rung is an object with a non-empty, unique `rung_key`, and SHALL authorize the replacement only for the Goal author or an actor holding the `define_gate_ladder` grant. The literal actor name `host` SHALL NOT confer ladder-definition authority by itself. Ladder replacement SHALL preserve existing claim rows so claims for removed rungs become orphaned rather than deleted. `gates action=get_ladder` and `goals action=get` SHALL expose the stored ladder, including an empty list when undefined.

#### Scenario: Disabled gates reject the surface before action dispatch
- **WHEN** any gates action is invoked while `GATES_ENABLED` is disabled
- **THEN** the system returns `status=not_available` and identifies the disabled flag

#### Scenario: Goal author replaces a valid ladder
- **WHEN** the Goal author submits a JSON list of rung objects with distinct non-empty `rung_key` values
- **THEN** the system replaces the previous ladder and returns the newly stored ordered rung list

#### Scenario: Explicit ladder grant authorizes a non-author
- **WHEN** a non-author holding the `define_gate_ladder` grant submits a valid ladder
- **THEN** the system accepts the replacement under the same validation rules as an author request

#### Scenario: Bare host identity has no ladder override
- **WHEN** an actor named `host` is neither the Goal author nor a holder of the `define_gate_ladder` grant
- **THEN** the system rejects the ladder replacement and leaves the stored ladder unchanged

#### Scenario: Ladder replacement preserves orphaned claim history
- **WHEN** a valid replacement ladder removes a rung that already has claim rows
- **THEN** the system retains those claim rows and subsequent claim listing tags them as orphaned instead of deleting them

### Requirement: Gate claims support claim, retract, and visibility-aware listing lifecycle
The system SHALL let an authorized gates writer self-report that a Goal-bound Branch reached a rung by persisting one claim row per `(branch_def_id, rung_key)`, provided the rung exists in the Branch's current Goal ladder and `evidence_url` is an HTTP(S) URL with a host or a non-empty TinyAssets run-evidence handle. Reclaiming the same Branch and rung MUST retain the claim ID while refreshing evidence, claimant, timestamp, and any prior retraction; an active claim whose Branch has moved to another Goal SHALL be rejected until it is retracted. `claim_from_branch_run` MUST accept only a completed run, read its case-sensitive `recommended_rung_claim`, and resolve claim evidence in caller override, Branch output, then `workflow:run:<run_id>` order. Retraction MUST require a non-empty reason and authorize only the recorded claimant, the Goal author, or an actor holding the `retract_gate_claim` grant; no actor, including a host, SHALL gain implicit retraction authority from its name or deployment role. Claim storage SHALL record evidence references supplied by the caller but SHALL NOT itself fetch, evaluate, or verify their contents.

#### Scenario: Claiming a ladder rung persists a self-report
- **WHEN** an authorized writer claims an existing rung for a Branch currently bound to the ladder's Goal with an accepted evidence reference
- **THEN** the system persists the claim with the Branch, Goal, rung, evidence reference, claimant, and claim timestamp and returns `status=claimed`

#### Scenario: Reclaim updates the existing claim row
- **WHEN** the same Branch and rung are claimed again without an unresolved cross-Goal rebind
- **THEN** the system preserves the existing claim ID, updates the supplied claim fields and timestamp, and clears any previous retraction

#### Scenario: A completed run recommendation becomes a claim
- **WHEN** `claim_from_branch_run` receives a completed run whose result recommends the exact current rung key and no explicit evidence override
- **THEN** the system claims that rung using Branch output evidence when present, otherwise the opaque `workflow:run:<run_id>` evidence handle

#### Scenario: An unfinished run cannot claim a rung
- **WHEN** `claim_from_branch_run` receives a run that is missing or not completed
- **THEN** it rejects the request without creating or refreshing a claim

#### Scenario: Active cross-Goal rebind requires retraction first
- **WHEN** an active claim exists for a Branch and rung under one Goal but the Branch is now bound to a different Goal
- **THEN** the system rejects the claim with `error=branch_rebound` until the earlier claim is retracted

#### Scenario: Claimant or Goal author retracts with a reason
- **WHEN** the recorded claimant or Goal author requests retraction with a non-empty reason
- **THEN** the system soft-deletes the claim by recording its retraction time and reason while retaining the row

#### Scenario: Repeated retraction is idempotent
- **WHEN** an authorized actor retracts a claim that is already retracted
- **THEN** the system returns `status=already_retracted` without replacing its original retraction timestamp or reason

#### Scenario: Explicit retraction grant authorizes another actor
- **WHEN** an actor holding the `retract_gate_claim` grant requests retraction with a non-empty reason
- **THEN** the system retracts the claim even when that actor is neither claimant nor Goal author

#### Scenario: Bare host identity has no retraction override
- **WHEN** an actor named or configured as a host is neither the claimant, the Goal author, nor a holder of the `retract_gate_claim` grant
- **THEN** the system rejects the retraction and leaves the claim active

#### Scenario: Claim listing uses exactly one filter and hides retractions by default
- **WHEN** a caller lists claims with exactly one of `branch_def_id` or `goal_id`
- **THEN** the system returns viewer-visible matching claims newest first, excludes retracted claims unless `include_retracted=true`, tags claims whose rung is absent from the current ladder as `orphaned`, and caps the requested limit at 500

### Requirement: The outcome leaderboard deterministically ranks active ladder progress
The system SHALL rank each Branch under a Goal by its highest active claim whose `rung_key` still exists in the current ladder, using the ladder's zero-based order as the score and the earliest claim timestamp as the tie-breaker between Branches at the same highest rung. `gates action=leaderboard` and `goals action=leaderboard metric=outcome` MUST use this deterministic ranking and SHALL NOT dispatch a selector Branch. A Goal with no ladder or no qualifying claims SHALL return an empty ranking. The `gates action=leaderboard` presentation boundary SHALL remove private Branch entries for viewers who do not own them; the current `goals ... metric=outcome` alias does not reapply that presentation filter.

#### Scenario: Higher active rung ranks first
- **WHEN** two Branches have non-retracted claims on different current ladder rungs
- **THEN** the Branch whose highest claim has the larger ladder index ranks first

#### Scenario: Earliest claim breaks an equal-rung tie
- **WHEN** two visible Branches have the same highest current rung
- **THEN** the Branch with the earlier claim timestamp ranks first

#### Scenario: Retracted and orphaned claims do not rank
- **WHEN** a claim is retracted or its rung no longer appears in the Goal's current ladder
- **THEN** that claim does not contribute to the Branch's outcome-leaderboard position

#### Scenario: Outcome ranking bypasses the selector
- **WHEN** a Goal has a custom selector Branch and either outcome-leaderboard surface is invoked
- **THEN** the system computes the result from current ladder order and active claims without dispatching the selector

### Requirement: Gate bonus attachment is paid-market-gated and node-only
The system SHALL make gate-bonus attachment available only while both `GATES_ENABLED` and `TINYASSETS_PAID_MARKET=on` are enabled. `gates action=stake_bonus` MUST target an existing, active, currently unstaked claim, require a positive integer `bonus_stake` and non-empty `node_id`, and accept only `attachment_scope=node`; `attachment_scope=branch` and every other scope SHALL be rejected. Only the recorded claim owner or configured host identity SHALL be allowed to attach a bonus, and the immutable bonus staker recorded on the claim SHALL remain the claim owner even when the host initiates attachment. The stored `bonus_refund_after` timestamp SHALL be attachment metadata only; this surface SHALL NOT schedule or execute automatic expiry processing. Monetary release, refund, treasury allocation, and settlement behavior remain owned by the paid-market capability.

#### Scenario: Eligible node attachment records bonus metadata
- **WHEN** the claim owner or configured host submits a positive integer stake and non-empty node ID for an active unstaked claim while both flags are enabled
- **THEN** the system records a node-scoped bonus, immutable claim-owner staker identity, node ID, and refund-after timestamp on the claim

#### Scenario: Paid-market flag disables bonus attachment
- **WHEN** `stake_bonus` is invoked while gates are enabled but `TINYASSETS_PAID_MARKET` is not `on`
- **THEN** the system returns `status=not_available` without attaching a bonus

#### Scenario: Branch attachment is not implemented
- **WHEN** `stake_bonus` is invoked with `attachment_scope=branch`
- **THEN** the system rejects the request and records no bonus attachment

#### Scenario: Refund-after metadata does not trigger expiry
- **WHEN** a node-scoped bonus has a stored `bonus_refund_after` timestamp
- **THEN** the gate attachment surface retains the timestamp as metadata and does not automatically unstake, refund, release, or otherwise settle the bonus when that time passes

### Requirement: Gate bonus resolution is single-winner but has current stranded states
The gate surface SHALL allow only the immutable recorded staker to unstake an active bonus and SHALL allow the Goal owner, configured host, or an actor holding `retract_gate_claim` to release it with caller-supplied verdict `pass`, `fail`, or `skip` plus a non-empty `node_last_claimer`. It MUST clear the claim's active stake with a compare-and-swap transition before applying the paid-market settlement, so concurrent unstake or release attempts cannot settle the same stake twice. A pass SHALL delegate payout to the node's last claimer through the paid-market ledger, while fail or skip SHALL delegate refund to the immutable staker. The handler SHALL NOT invoke an evaluator to establish the supplied verdict. As built, a retracted staked claim rejects both unstake and release, and no automatic refund-after worker resolves that stranded attachment.

#### Scenario: Concurrent resolution has one winner
- **WHEN** two callers race to unstake or release the same active bonus
- **THEN** exactly one compare-and-swap clears and settles the stake and the other observes that no active bonus remains

#### Scenario: Passing release delegates payout to the node claimer
- **WHEN** an authorized releaser supplies verdict `pass` and a node last-claimer for an active bonus
- **THEN** the gate surface clears the attachment and delegates paid-market release to that node claimer under the ledger's settlement policy

#### Scenario: Failing or skipped release refunds the immutable staker
- **WHEN** an authorized releaser supplies verdict `fail` or `skip` and the required node last-claimer field
- **THEN** the gate surface clears the attachment and delegates refund to the immutable recorded staker even though the node last-claimer value is unused for that refund

#### Scenario: Retracted staked claims can remain stranded
- **WHEN** a claim is retracted while it still carries an active bonus
- **THEN** current unstake and release handlers reject resolution and no refund-after worker automatically clears or settles the attachment

## MODIFIED Requirements

### Requirement: The Goal leaderboard is synthesized by a user-bound selector branch
The system SHALL use a user-buildable selector Branch, rather than a fixed platform weighting formula (DESIGN-008), for the quality-leaderboard and parent-recommendation surfaces and for canonical refresh that consumes their top quality candidate. This selector contract SHALL NOT apply to `goals action=leaderboard` metrics (`run_count`, `forks`, `outcome`, or `gate_events`), the deterministic gates outcome leaderboard, or fixed archive consultation. `goals action=set_selector` SHALL bind a published branch version as the Goal's selector and SHALL be permitted only for the Goal author or an actor holding the selector-bind capability. An empty `branch_version_id` SHALL unbind and fall back to the platform default selector. The bound selector Branch SHALL be pure: a Branch that carries node effects or invokes child Branches SHALL be rejected so a selector cannot cause side effects while ranking.

#### Scenario: Author binds a selector branch
- **WHEN** the Goal author invokes `goals action=set_selector` with a valid selector `branch_version_id`
- **THEN** the Goal records that selector and future quality-leaderboard synthesis dispatches it to rank candidates

#### Scenario: Non-author without capability is rejected
- **WHEN** an actor who is neither the Goal author nor holder of the selector-bind capability invokes `set_selector`
- **THEN** the call is rejected and the selector binding is unchanged

#### Scenario: A selector branch with effects is rejected
- **WHEN** `set_selector` is called with a Branch that carries node effects or invokes a child Branch
- **THEN** the call is rejected with a structured effects error and no selector is bound

#### Scenario: Empty branch_version_id unbinds to the default selector
- **WHEN** `set_selector` is called with an empty `branch_version_id`
- **THEN** the Goal's selector is unbound and quality-leaderboard calls fall back to the platform default selector

#### Scenario: Non-quality Goal rankings bypass the selector
- **WHEN** a caller requests a `goals action=leaderboard` metric, the outcome-gate leaderboard, or archive consultation
- **THEN** the system uses that surface's deterministic or fixed server-side ranking and does not dispatch the Goal's selector Branch

## As-Built Limitations

- Verified 2026-07-22 on the reconciliation worktree with `python -m pytest -q tests/test_outcome_gate_claims.py::test_retract_by_host_allowed tests/test_outcome_gate_claims.py::test_define_ladder_host_override`: both tests fail because they expect an actor merely named `host` to override ladder and retraction authorization. Current handlers instead require Goal author or `define_gate_ladder` for ladder replacement, and claimant, Goal author, or `retract_gate_claim` for retraction. These are stale-test observations, not normative host powers.
- Goal protocol prerequisite, verdict, transition, and rollback fields are persisted metadata only; there is no protocol executor or rollback interpreter.
- Archive consultation is fixed server-side ranking, not a selector-driven or user-buildable ranking surface.
- Unlike `gates action=leaderboard`, `goals action=leaderboard metric=outcome` currently returns the shared outcome ranking without reapplying viewer-based private-Branch filtering.
- Bonus attachment supports nodes only. Branch attachment is rejected, and `bonus_refund_after` has no automatic expiry worker on this surface.

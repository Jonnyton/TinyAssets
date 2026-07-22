## ADDED Requirements

### Requirement: Soul guidance is a bounded advisory input to deterministic dispatch
The dispatcher SHALL apply soul guidance only after the ordinary pending-status, enabled-tier, required-LLM-type, and preferred-request-type filters, and SHALL use it only to reject work explicitly directed to another bound daemon or to add a non-negative capped affinity term to the existing deterministic queue score. `soul_guided_dispatch_read` MUST remain read-only: it derives affinity from token overlap with the active daemon's domain claims and soul plus the importance of at most three open mini-brain hints, but it neither claims nor mutates a task. This shipped path does not ask a model to choose among souls or candidates and does not persist a soul-choice receipt.

#### Scenario: default configuration leaves soul guidance inert
- **WHEN** selection runs with the default empty `active_daemon_id` and zero `soul_affinity_coefficient`
- **THEN** every otherwise eligible task receives a zero soul adjustment, a task's `directed_daemon_id` is not enforced without an active daemon binding, and ordinary deterministic queue policy decides the winner

#### Scenario: a bound daemon enforces requester direction
- **WHEN** `active_daemon_id` is non-empty and an otherwise eligible task has a different non-empty `directed_daemon_id`
- **THEN** soul guidance marks that task ineligible before scoring it, while an undirected task or a task directed to the active daemon remains eligible

#### Scenario: affinity is advisory and bounded
- **WHEN** a bound daemon has domain-claim, soul-token, or open mini-brain matches for an eligible task and the configured coefficient is positive
- **THEN** the dispatcher adds `min(max(0, coefficient) * raw_affinity, max(0, term_cap))` to the ordinary score and does not let the affinity term bypass any ordinary eligibility filter

#### Scenario: unavailable soul or brain data fails open
- **WHEN** active-daemon lookup fails, or the optional mini-brain hint read fails
- **THEN** the dispatcher logs the advisory-read failure and retains ordinary task eligibility, using zero adjustment when the daemon itself is unavailable and any remaining soul or claim evidence when only brain hints are unavailable

#### Scenario: selection produces no model choice receipt
- **WHEN** soul-guided selection chooses a task
- **THEN** the result is still the deterministic top `BranchTask` from the in-memory score ordering, with no model invocation, autonomous soul choice, or persisted soul-selection receipt

### Requirement: Generic work targets persist records and expose guarded helper transitions
The generic work-target layer SHALL persist a `WorkTarget` record keyed by `target_id` with title, home link, role, publish stage, lifecycle, intent, tags, artifact/note/target/timeline/lineage references, selection reason, metadata, timestamps, and producer origin. It MUST support load, replace, lookup, and upsert through the daemon storage server with JSON fallback; active-only selection with an optional role filter; create, provisional-create, role reclassification, publish commit, discard, and review/execution artifact helpers. The exported role, publish-stage, lifecycle, and origin literals are conventions used by these helpers, not validated enums: `from_dict`, `create_target`, and producer origin stamping currently permit arbitrary strings to persist. The JSON fallback path SHALL NOT be represented as sharing the branch-task queue's file-locking guarantee; its read/replace/upsert operations are not protected by that queue lock.

#### Scenario: a generic target round-trips through storage
- **WHEN** a caller creates or upserts a target and later loads or looks it up by `target_id`
- **THEN** the record fields and references round-trip through the daemon storage server, or through `work_targets.json` when that server operation raises, and the upsert refreshes `updated_at`

#### Scenario: selectable registry reads exclude non-active records
- **WHEN** `list_selectable_targets` reads records with active and non-active lifecycle values and an optional role filter
- **THEN** it returns only records whose lifecycle string is exactly `active` and, when supplied, whose role string exactly matches the requested role

#### Scenario: helper transitions guard publish state
- **WHEN** a notes target is reclassified as publishable and then committed
- **THEN** reclassification first sets `publish_stage` to `provisional`, commit changes it to `committed`, and reclassification back to notes resets it to `none` and can emit a reconciliation note

#### Scenario: enum-like fields remain permissive
- **WHEN** stored input or a helper caller supplies an unrecognized role, publish-stage, lifecycle, or origin string
- **THEN** the generic record layer persists that string rather than rejecting it as outside a closed enum, although built-in filters and transitions only recognize their named constants

#### Scenario: discard is delayed and recoverable
- **WHEN** a target is marked for discard at review cycle N
- **THEN** it remains `marked_for_discard` until at least 20 review cycles have elapsed, after which finalization sets it to `discarded`, writes an archival JSON copy, and records a 30-day recoverability deadline instead of deleting the registry row

#### Scenario: review and execution artifacts are durable but not a complete public snapshot
- **WHEN** a review stage or execution handoff writes its payload
- **THEN** the helper stores a uniquely named JSON artifact under `artifacts/reviews` or an execution-ID-named JSON artifact under `artifacts/executions`, while the current read tools expose `work_targets.json` and `status.json` separately and do not provide one complete public snapshot joining targets, hard priorities, review artifacts, and execution artifacts

### Requirement: Fantasy foundation review gates authorial work on current hard priorities
The fantasy-domain universe graph SHALL enter `foundation_priority_review` before authorial selection, finalize eligible delayed discards, synchronize source-synthesis priorities, collect soft conflicts, and persist a foundation review artifact. It MUST treat only active records with `hard_block=true` as blockers and currently creates such blockers for fantasy source-upload synthesis; this review topology is fantasy-specific and is not a generic daemon-engine review protocol.

#### Scenario: an unsynthesized source upload hard-blocks authorial work
- **WHEN** synchronized source state yields one or more active hard priorities
- **THEN** foundation review selects the first hard priority's target, sets intent to `synthesize source upload`, routes `current_task` and `task_queue` to `worldbuild`, reports stage `foundation`, and records the priorities and synthesis signals in a review artifact

#### Scenario: soft conflicts remain visible without blocking
- **WHEN** undismissed notes categorized as `concern` or `error` exist but no active hard priority exists
- **THEN** foundation review includes them as soft conflicts, reports stage `authorial`, leaves the selected target and current task empty, and allows the graph to continue to authorial review

#### Scenario: clearly wrong remains soft at the foundation gate
- **WHEN** a collected concern or error carries `clearly_wrong=true` but has no corresponding active hard-priority record
- **THEN** foundation review reports the flag in `soft_conflicts` and does not promote it into a hard blocker

#### Scenario: foundation review finalizes eligible discards
- **WHEN** a target has remained marked for discard for the configured 20-cycle delay when foundation review runs
- **THEN** the review finalizes that target, includes its ID in `finalized_discards`, and persists the result in the foundation review artifact

#### Scenario: missing universe context cannot produce a foundation snapshot
- **WHEN** foundation review receives neither `_universe_path` nor `universe_path`
- **THEN** it returns an authorial-stage no-op with empty soft conflicts and a diagnostic trace, without writing the normal review artifact

### Requirement: Fantasy authorial review ranks producer candidates and hands one target to execution
The fantasy-domain authorial path SHALL materialize and rank work-target candidates, choose at most one selected target plus at most two alternates, persist an authorial review artifact, and pass the selected target and intent to `dispatch_execution`. With the producer interface enabled by default, it MUST run registered producers in registration order, stamp every emitted target with the producer's origin, skip and log a failing producer, and merge duplicate `target_id` values last-write-wins; the shipped fantasy registration order is `seed`, `fantasy_authorial`, then `user_request`. This selection and execution topology, including book/chapter/scene scope inference, is fantasy-only rather than a generic engine scheduler.

#### Scenario: producer candidates are merged before ranking
- **WHEN** the producer interface is enabled for an authorial review cycle
- **THEN** the phase runs all registered producers, merges their emitted targets by `target_id` with the later producer winning, and passes that merged list as the complete `candidate_override` to authorial ranking

#### Scenario: producer failure does not abort the cycle
- **WHEN** one registered producer raises while a later producer emits a target
- **THEN** the failure is logged, the later producer still runs, and its origin-stamped target remains available for ranking

#### Scenario: producer overrides can retain paused or discarded candidates
- **WHEN** any registered producer emits a target whose lifecycle is `paused`, `discarded`, or another non-active string
- **THEN** merge and `candidate_override` ranking do not universally filter it out, so it can survive into the ranked candidate set with a lower lifecycle score and can be selected if higher-ranked alternatives do not displace it

#### Scenario: a pending request is materialized but not guaranteed selection
- **WHEN** the user-request producer reads a valid `requests.json` entry with `status=pending`
- **THEN** it idempotently upserts an active notes target keyed from the request ID, marks the request `seen` with timestamp and target reference, and includes the target among the cycle's candidates without guaranteeing that it becomes the selected target

#### Scenario: deterministic authorial heuristics select one target
- **WHEN** authorial review receives ranked candidates
- **THEN** it prefers the first notes target for explicit `reflect` or `worldbuild`, otherwise preserves a previously selected target when present, otherwise takes the top-ranked candidate; it derives intent from the workflow hint or target intent and records no more than two remaining candidate IDs as alternates

#### Scenario: no candidate yields idle
- **WHEN** authorial ranking returns no candidates
- **THEN** review selects no target, persists the authorial review artifact, and hands off `current_task=idle` with an `idle` task queue

#### Scenario: execution routing honors request type before heuristics
- **WHEN** `dispatch_execution` receives a selected target and intent
- **THEN** it maps request types `scene_direction` and `revision` to `run_book` and `canon_change` and `branch_proposal` to `worldbuild` before considering intent keywords, then falls back to `reflect`, worldbuild/reconcile/synthesis/compare intent, notes-role worldbuild, or publishable `run_book`, with missing target and intent yielding `idle`

#### Scenario: execution handoff persists fantasy scope and review linkage
- **WHEN** execution routing determines the concrete task
- **THEN** it creates a unique execution ID, infers the fantasy book/chapter/scene-or-notes scope from the selected target, writes an execution artifact containing the selected target, intent, task, scope, prior review reference, and alternates, and returns the corresponding legacy task queue

# Scheduled monitoring shape review — September 19, 2026

Independent Claude Fable alias, subscription peer, session 64340; terminal exit 0
after 223 seconds. Prepared proposal/design plus red-first tests were reviewed;
this is a shape verdict, not exact-head implementation approval.

## Disposition

The four basic adaptations are implemented: explicit producer-owned Actions
outputs; positive recognition of the existing no-home projection; separate
measured-red and receiptless history fixtures; explicit unavailable automatic
recovery warning. The safe policy is that every unknown/skipped previous
observation breaks the chain; receipts older than 30 minutes are unproven.

One reviewer factual statement is contradicted by the exact-attempt Jobs API:
the September 19 Layer-2 job concluded success despite its tolerated exit 13.
Its specific failure did not contaminate that run's workflow conclusion. The
whole-workflow history bug remains real for unrelated job/infra failures.
See the dated diagnosis for the read-only command and result.

The requested cleanup of old false incidents requires fresh incident evidence
and coordinator/incident-owner disposition. No issue was closed or host-only
ask invented; see the existing scheduled-uptime concern. Required coverage
stays open, so automatic recovery is explicitly unavailable for now.

## Retained peer output (unaltered)

I'll read the proposal, design, delta spec, and the scoped source and test locations, then reason to a verdict without dispatching anything or editing files.

Review complete. I read the proposal, design, delta spec, tasks, the workflow's combine and alarm-sink steps, the Layer-2 job, the revert script's error and fetch paths, both test diffs, and the diagnosis. No agents dispatched, no files edited.

**Answer to the bounded question.** Explicit unknown plus an exact-attempt measured-red step receipt does preserve actionable outage detection without inventing coverage: every measured handshake, tool, executor, wiki, or transport failure stays red, unknown never reaches the threshold or REST, and the sentinel-step receipt is a real Actions primitive that the current whole-conclusion check lacks. The shape is right. Four gaps need closing before build, because as written the workflow cannot actually consume the typed reason, one existing test contradicts the new one, an empty status payload would downgrade to unknown, and recovery becomes unreachable in production without the design saying so.

**Required adaptations**

- **DISAGREE_EVIDENCE: the producer-to-workflow channel for `observation` does not exist.** The script's `main` returns only the exit code (`scripts/revert_loop_canary.py:404-409`), and the revert step records only that code (`.github/workflows/uptime-canary.yml:188`). Both new tests pin exit 5 for `probe_failed` and for `legacy_evidence_unavailable`. So the typed reason lives on an exception the workflow never sees, and design §1 forbids parsing the human text. Build: have the script print one machine-readable line to stdout on failure, in the style of the wiki canary's GHA format, for example `revert_observation=unknown` and `revert_reason=legacy_evidence_unavailable`. The revert step copies those keys into the step outputs, and the combine or classifier reads the key. Nonzero exit with the line absent is red.

- **DISAGREE_CONCERN: absent evidence must be positively recognized, not inferred from a missing key.** The branch slated to become unknown is "payload has no evidence block" (`scripts/revert_loop_canary.py:302-308`). A broken, renamed, or empty `get_status` returning `{}` hits the same branch and would now read as unknown, which is a regression from today's red. Build: classify `legacy_evidence_unavailable` only when the payload carries a field the confined canary projection always includes (the diagnosis names deploy identity and executor liveness; pick one stable key and assert it). Anything unrecognized stays `probe_failed`. The "read failed" caveat branch stays red because the daemon observed its own read failing. The design should list which branches map to which reason.

- **DISAGREE_EVIDENCE: the existing threshold test and the new red-first test cannot both pass.** The harness models prior red as a bare failed conclusion (`tests/test_uptime_canary_workflow.py:69-71`). The existing test asserts `issues.create` with that stub (`:151-160`); the new test asserts no `issues.create` with the same stub (`:188-191`). Build in the same slice: split the stub into a workflow-failure-only shape and a measured-red shape that returns `run_attempt`, `head_branch`, `path`, plus a `listJobsForWorkflowRunAttempt` stub carrying the named sentinel step with conclusion failure. Move the existing test to the measured-red shape, and add negative cases for a skipped sentinel, wrong attempt, non-main branch, and an API throw.

- **DISAGREE_CONCERN: green becomes unreachable in production, and the design does not say so.** The diagnosis shows revert exits 5 on every scheduled run today, so after this change every tick is unknown unless another probe is red. With literal green as the only recovery path, any incident opened by a real outage stays open after recovery, a later outage takes the escalation path instead of first-alarm, and any incident opened during the false-red era never auto-closes. This is the truthful outcome and I agree with not manufacturing coverage, but it must be an explicit decision: state it in the design risks, add a host-action row to close any open false incident with a comment, and have the scheduled summary say recovery is unreachable while revert coverage is unknown.

**Nonblocking hardening**

- **AGREE with the sentinel receipt; pin its mechanics.** Combine must stop exiting nonzero (`uptime-canary.yml:337`) so the sentinel is the only failing step, with no `continue-on-error` and no `if: always()`, and a versioned unique name. Reader logic: failure means prior red, success means not red, anything else means unproven.
- **Define "eligible" precisely.** The concurrency group with no cancel (`uptime-canary.yml:39-41`) makes the previous completed run the true previous run. Decide whether a deploy-triggered run whose probe job was skipped is ineligible and stepped over within the bounded page, or breaks the chain. I recommend ineligible since it produced no observation, but either is safe if a test pins it.
- **Layer-2 comment is stale.** The job claims the harness exits SKIP 14 on the hosted runner (`uptime-canary.yml:341-343`), but the Sept 19 run exited 13 and failed the job, which is exactly how a Layer-2 failure polluted the whole conclusion. Put the prerequisite check in the workflow so the harness is never invoked on the hosted runner, and keep the user-directed path untouched. AGREE this stays within PLAN: no LLM, no universe, no tenant grant.
- **Later option, not this slice:** incident-scoped recovery, where closing requires green on the probes that opened the incident, would restore auto-close without manufacturing revert coverage.

VERDICT: ADAPT

Checked: the running dispatch is this review's own output slot, and the vanished entries belong to other lanes. My brief forbids dispatching, editing files, or opening worktrees, so there is nothing further I may advance here. The verdict above stands.

VERDICT: ADAPT



# Loop Outcome Rubric v0

Status: proposal
Owner: Workflow community patch loop
Pairs with: `docs/milestones/auto-ship-canary-v0.md` (PR #198, merged a3e6ec4)

## 1. Purpose

The substrate is now reliably running community-loop investigations end-to-end
(post-#205 claim grace + #196 dispatcher pickup + #201 request_text plumbing).
The next bottleneck is not "can the loop run" but **how does the system know a
loop variant is better and safe enough to promote?**

Without an explicit outcome rubric:
- the loop's own coding_packet labels (`status`, `release_posture`,
  `candidate_decision`, `automation_claim_status`) drift across branch versions
  and contradict each other (BUG-051);
- auto-ship eligibility (PR #198) cannot enforce consistent gates;
- promotion of a variant from canary to canonical has no shared definition;
- silent-failure modes (auto-shipped patch passes shallow gates but is wrong)
  have no canary that fires before Mark notices.

This rubric is the substrate-level vocabulary that subsequent loop content,
release gates, and observability surfaces all reference. Loop content
authoring (Mark's lane) writes prompts that emit fields conformant to this
rubric. Substrate (Codex's + Cowork's lane) enforces the rubric in
`auto_ship_packet_v0`, `live_observation_gate`, and `get_status` surfaces.

## 2. Evidence classes

Every loop-outcome assertion must be backed by one of these evidence classes.
Each class names what *kind* of fact is being claimed:

| Class | Semantics | Concrete examples |
|---|---|---|
| `trigger` | A request was filed and accepted by the intake surface. | `wiki.file_bug` returned `bug_id` + `trigger_attempt_id`. |
| `claim` | A daemon/worker took ownership of the work item. | `BranchTask.claimed_by` non-empty. |
| `parent-run` | The parent loop branch run terminated. | `extensions.get_run(parent_run_id).status in {completed, failed, interrupted}`. |
| `child-run` | A child branch run was spawned by the parent. | parent state contains `selected_child_run_id`; child's `get_run` returns the same id. |
| `child-output` | The child run produced typed outputs that the parent received. | parent state contains `attached_child_evidence_handle`; payload fields like `child_candidate_patch_packet` are non-empty. |
| `release` | The release gate produced a structured verdict. | `release_gate_result in {APPROVE_AUTO_SHIP, HOLD, SEND_BACK, OBSERVE, REJECT, ATTACH_REQUIRED, CHILD_REVIEW_READY}`. |
| `observation` | A live-observation gate confirmed real-world effect. | `observation_gate_result=OBSERVE` with `commit_sha` reachable in repo, or matching effect on the targeted surface. |
| `rollback` | A previously-shipped patch was reverted. | `rollback_handle` resolved to a real revert PR or commit. |

A KEEP/auto-ship verdict requires evidence in at least: `trigger` + `claim` +
`parent-run` + (`child-run` AND `child-output`) + `release` + path to
`observation`.

## 3. Outcome labels

Loop runs and shipped patches both terminate in one of these labels. The
label MUST be derivable from the evidence classes; no label is allowed to be
asserted without backing evidence.

| Label | Semantics | Required evidence |
|---|---|---|
| `failed` | Run terminated with an error or exception. | `parent-run` with non-empty `error`. |
| `interrupted` | Run was reaped by supervisor/operator before terminal. | `parent-run.status=interrupted`. |
| `blocked` | Run terminated cleanly but explicitly refused to make a decision. | `parent-run.status=completed` + release_gate_result=ATTACH_REQUIRED or REJECT. |
| `review_ready` | Run produced a candidate packet but explicitly requires human review. | `parent-run` + `release` with `release_gate_result=CHILD_REVIEW_READY` or `HOLD`. |
| `keep` | Run produced a candidate packet judged ship-ready by the loop's own gates. | All of: `parent-run` + `child-run` + `child-output` + `release.release_gate_result in {APPROVE, APPROVE_AUTO_SHIP}`. |
| `shipped` | A KEEP packet was actually merged or committed. | `keep` + `release.commit_sha` OR `release.pr_url` resolves on the repo, OR `live_observation_gate_result=OBSERVE`. |
| `observed_healthy` | A shipped patch was observed in production for ≥ N hours with no rollback signal. | `shipped` + `observation` with timestamp delta ≥ threshold + no `rollback` evidence in window. |
| `rolled_back` | A shipped patch was reverted. | `rollback` with handle resolving to revert PR/commit. |

## 4. Promotion criteria (canonical branch advancement)

A loop variant (e.g. `change_loop_v1_auto_keep_canary`) may be promoted to
canonical (replacing or augmenting `change_loop_v1`) only when:

```
N >= 5 successful terminal runs labeled `shipped` or `observed_healthy`
AND no run in window labeled `rolled_back`
AND no `claim` evidence missing for any `parent-run` with `keep` decision
AND no `release` evidence labeled `keep` without backing `child-output` evidence
AND human review of the rubric-conformance happened at least once in window
```

The "no overclaim" rule is critical: a release labeled `keep` MUST have
backing `child-output` evidence. A run that asserts KEEP without typed child
outputs in parent state is an overclaim and forbidden from promotion math.

## 5. KEEP criteria (per-run)

A single loop run earns the `keep` label only when ALL of these are true:

```
child-run.status=completed
child-output evidence present (non-empty attached_child_evidence_handle +
                                child_candidate_patch_packet present)
release.score >= 9.0  (or branch-defined threshold)
release.evidence_bundle_complete=true
release.release_gate_result in {APPROVE, APPROVE_AUTO_SHIP}
no field in parent state contradicts another (rubric-conformance check)
```

The last bullet is the BUG-051 antidote: a run cannot be KEEP if its
`automation_claim_status` says `child_invoked_with_handle` while its
`reason_for_downgrade` says `cannot attach/invoke the child packet`. The
rubric-conformance check is a structural validator on the packet, not a
human judgment.

## 6. Auto-ship criteria (per-PR-#198 envelope)

A KEEP-labeled run MAY auto-ship only when ALL of these are true (this is the
intersection with PR #198's safety envelope):

```
label == keep
ship_class in {docs_canary, metadata_canary, test_fixture_canary}
changed_paths subset of allowed_paths from PR #198 §6.2
rollback_handle present and resolvable
ci_status=passed at the moment of merge attempt
no `rolled_back` event in last 24h on the same loop variant
no `failed` event in last 1h on the same loop variant (cooldown)
```

Auto-ship combines KEEP semantics (this rubric) with shipper enforcement
(PR #198). Neither is sufficient alone.

## 7. Anti-patterns (rubric forbids)

| Anti-pattern | Why it's forbidden |
|---|---|
| Inferring run success from `extensions.list_runs` only. | `list_runs` may show `status=completed` for runs that hit `recursion_limit_applied` and forced through without producing real outputs. Always require backing `child-output` evidence. |
| Treating `dispatcher_request_id` as `run_id`. | They differ — `dispatcher_request_id` is the queued BranchTask id; `run_id` is the durable run instance. Conflating them breaks evidence traceability. |
| Cached stale `tools/list`. | (FEAT-005) Connector wrappers cache catalog descriptions; a missing field in the cached schema does not mean the field is missing on the server. Always reconcile with `get_status.tool_schema_versions` (when shipped). |
| Asserting `keep` from a run with `__system__: recursion_limit_applied`. | Recursion-limit termination produces empty output dicts even when status=completed. Fails the "evidence_bundle_complete" rubric requirement. |
| Promoting a branch from a single successful run. | Single-run promotion masks intermittent silent failures. Promotion math requires N successful terminal runs in a window. |
| Asserting `shipped` without a resolvable `commit_sha`/`pr_url`. | A patch that "merged" but has no resolvable repo handle was not actually shipped — possibly a logging artifact or stale state. |

## 8. Surface contracts

Each rubric concept maps to a concrete surface for observation:

| Concept | Surface |
|---|---|
| Outcome label | `extensions.get_run(run_id).label` (new field, or computed from existing fields per §3) |
| Evidence bundle | Required fields enumerated in §2; structural validator runs at `release_safety_gate`. |
| Promotion math | Aggregation surfaces in `get_status.loop_health[<branch_def_id>]` (new field). |
| Auto-ship eligibility | `auto_ship_packet_v0` validates rubric §6 before any repo write (PR #198 spec). |
| Anti-pattern detection | Validator hooks at coding_dispatch + review_release_gate that reject packets violating §7. |

## 9. Failure handling

If a packet violates rubric §5 or §7:
- Release gate forces `release_gate_result=HOLD` or `SEND_BACK`.
- `manual_review_required=true`.
- Activity log emits `[rubric_violation] run_id=<id> rule=<rule> field=<field>`.
- The loop variant's `get_status.loop_health.rubric_violations_24h` increments.

If a shipped patch produces a `rolled_back` event:
- Loop variant cooldown for 24h (auto-ship suppressed).
- Activity log emits `[shipped_rollback] run_id=<id> commit_sha=<sha> rollback_handle=<handle>`.
- The 5-successful-run promotion counter resets for that variant.

## 10. Implementation phases

### Phase 0 — design only (this doc)
Land this rubric as the shared vocabulary.

### Phase 1 — structural validator
Implement a pure-Python validator that takes a coding_packet/release_packet
and asserts §5 + §7 rules. Emits `rubric_violation` records but does not yet
block release.

### Phase 2 — gate enforcement
Wire the validator into `release_safety_gate` so violating packets force
HOLD. This is when overclaim becomes impossible.

### Phase 3 — promotion math surface
Add `get_status.loop_health[<branch_def_id>]` aggregating per-window
counts of {failed, interrupted, blocked, review_ready, keep, shipped,
observed_healthy, rolled_back}. Operators can read promotion-eligibility
without inspecting individual runs.

### Phase 4 — auto-ship integration
`auto_ship_packet_v0` (PR #198) calls the rubric validator + checks §6
before any repo write.

## 11. Acceptance test

The rubric is "live" when:
- A run that hits `recursion_limit_applied` with empty output is labeled
  `failed` or `interrupted`, NOT `keep`.
- A run that asserts `automation_claim_status=child_invoked_with_handle` AND
  `reason_for_downgrade=BUG-045 cannot invoke` triggers a
  `rubric_violation` log line.
- `get_status.loop_health[fd5c66b1d87d]` returns counts mapped to outcome
  labels for the last 24h.
- Auto-ship attempts on a non-conforming packet are refused before any repo
  write.

## 12. Why this matters for the larger mission

The user's standing direction is "24/7 uptime + self-evolution of the loop".
We've solved:
- 24/7 uptime: substrate alive, daemon claims and runs reliably.
- Self-evolution of the loop: runs produce candidate packets.

The rubric closes the gap between "produces packets" and "improves itself
safely". Without it, auto-ship is unsafe (silent failures could compound)
and promotion is undefined (no shared metric for "this variant is better").
With it, auto-ship has clear guards, promotion is observable, and the loop
can identify its own rubric violations and route them to itself for
investigation.

## Source

Captured from dev-partner chat (ChatGPT gpt-5) with the Workflow MCP
connector installed, on 2026-05-02. The chatbot was asked the second-order
question: "what's the highest-likelihood + highest-blast-radius silent-
failure class once auto-ship lands?". Answer: there isn't one specific
silent-failure class to design for — the meta-failure is the absence of a
shared scoring rubric. Build the rubric first; specific failure modes
become detectable rubric-conformance violations rather than mystery silent
incidents.

Conversation: https://chatgpt.com/c/69f64b8d-fa04-83e8-b4d3-bb6e95b16475

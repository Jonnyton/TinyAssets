# Auto-ship rollback primitive v0

Status: proposal
Owner: Workflow community patch loop (Slice C of option-2 lane)
Pairs with:
- `docs/milestones/auto-ship-canary-v0.md` (PR #198 §5.2 + §10 Phase 4)
- `docs/specs/loop-outcome-rubric-v0.md` (rubric §2 `rollback` evidence class)
- `workflow.auto_ship_ledger` (PR #226 — Slice A — schema this primitive
  reads from + writes to)
- `get_status.auto_ship_health` (Codex's Slice B WIP — surfaces the same
  `observation_status` this primitive reacts to)

## 1. Purpose

Once the auto-ship lane begins opening real PRs (Phase 2) and merging them
(Phase 3), the loop must be able to detect when a shipped patch is causing
harm — and revert it cleanly without operator intervention. The rollback
primitive is what closes that loop. It is the LAST safety net beneath the
validator (Slice A's safety envelope) and the observation gate (Slice B).

Without it:
- a regressed canary stays merged until a human notices and reverts;
- the ledger has no record that a rollback decision was made or executed,
  so the loop cannot learn from rollback patterns;
- observation_gate_result transitions to `REGRESSED` are advisory rather
  than actionable, and Mark (loop content) has no substrate to reference
  in a "what should happen when observation says regressed" prompt.

This spec defines the primitive's **interface**, **decision rules**, and
**evidence contract**. Implementation lands in a follow-on PR after PR
#226 (Slice A) and Slice B (`auto_ship_health`) merge.

## 2. Module shape

New module: `workflow.auto_ship_rollback`. Mirrored at
`packaging/claude-plugin/plugins/workflow-universe-server/runtime/workflow/auto_ship_rollback.py`.

Public API (small, additive — no changes to Slice A's surface):

```
def assess_rollback_candidates(
    universe_path: Path,
    *,
    now: datetime | None = None,
) -> list[RollbackCandidate]:
    """Read every ledger row whose ship_status is in {opened, merged}
    and observation_status is REGRESSED, and return one RollbackCandidate
    per row that has not already been rolled back.

    Pure read of the ledger — no IO except read_attempts(). No mutation."""

def propose_rollback(
    universe_path: Path,
    ship_attempt_id: str,
    *,
    reason: str = "",
    now: datetime | None = None,
) -> RollbackProposal:
    """Build a structured rollback proposal for one attempt:
       - revert target = the original commit_sha
       - revert evidence = the original rollback_handle (set by Slice A)
       - revert packet shape = a synthetic ship_request that, when fed to
         validate_ship_request, would PASS the envelope as ship_class=
         'rollback_canary'.

    The proposal is returned, NOT acted on. v0 is dry-run only — Phase 4
    wires the actual `gh pr create` behind a feature flag."""

def record_rollback_decision(
    universe_path: Path,
    ship_attempt_id: str,
    *,
    decision: str,         # "approved" | "deferred" | "skipped"
    reason: str = "",
    rollback_pr_number: int | None = None,
    rollback_pr_url: str = "",
    now: datetime | None = None,
) -> ShipAttempt:
    """Mutate the ledger row for ship_attempt_id:
       - sets ship_status='rolled_back' if decision=='approved' AND
         rollback_pr_number is set,
       - leaves ship_status untouched otherwise (deferred/skipped only
         annotate observation_status_at + error_message).

    Records the decision so future iterations of the loop can reference
    a rolled-back attempt without re-deciding."""
```

Three dataclasses live here too:

```
@dataclass
class RollbackCandidate:
    ship_attempt_id: str
    pr_url: str                  # the original PR being reverted
    commit_sha: str              # the original commit
    rollback_handle: str         # Slice A populated this
    observation_status: str      # always "regressed" in candidates
    observation_status_at: str
    days_since_merge: float

@dataclass
class RollbackProposal:
    ship_attempt_id: str
    target_commit_sha: str
    target_pr_url: str
    rollback_packet: dict        # same shape as a Phase 1 ship_request
    suggested_branch: str        # e.g. "auto-ship-rollback/<ship_attempt_id>"
    suggested_pr_title: str
    suggested_pr_body: str
    rollback_handle: str         # carried from original attempt
```

Why three functions, not one:
- assessment is the read-only "what should we revert" surface, used by
  `get_status.auto_ship_health.rollback_recommendations` (Slice B
  reads this via the ledger directly — but assess_rollback_candidates
  is the canonical implementation other callers can use too);
- proposal is the deterministic build step — same input always
  produces the same RollbackProposal, so it can be unit-tested;
- recording is the mutation point — the only place ledger writes
  happen on the rollback path.

## 3. Decision rules (when to recommend rollback)

A ledger row qualifies as a rollback candidate iff ALL hold:

1. `ship_status in {opened, merged}` (so we don't try to roll back a
   blocked or already-rolled-back row);
2. `observation_status == "regressed"` (the observation gate has flipped
   the verdict from observing/healthy to regressed);
3. no other row exists with `request_id == this.request_id` and
   `ship_status == "rolled_back"` (don't roll back the same request
   twice — that would race with whatever the prior rollback PR is doing);
4. `rollback_handle` is non-empty (Slice A's validator REQUIRES this on
   passed packets, so this should always hold, but the rollback path
   defends against missing data anyway);
5. `commit_sha` is non-empty for `merged` rows (PR-opened-but-not-merged
   rollbacks revert by closing the PR, not by `git revert`).

When zero candidates qualify, the function returns `[]` — no surprise
errors, no warnings.

## 4. Rollback packet shape

The rollback proposal's `rollback_packet` field is a dict shaped exactly
like the input to `validate_ship_request`. It must pass the envelope as
ship_class=`rollback_canary` (a NEW ship class to be added to
`auto_ship.ALLOWED_SHIP_CLASSES` in the same Slice C PR). Required
fields the proposal must populate:

| Field | Value |
|---|---|
| `release_gate_result` | `"APPROVE_AUTO_SHIP"` (rollbacks are pre-approved by the rubric) |
| `ship_class` | `"rollback_canary"` |
| `child_keep_reject_decision` | `"KEEP"` |
| `child_score` | `9.0` (rubric §5 floor; rollbacks are by definition keep-worthy) |
| `risk_level` | `"low"` (revert PRs are mechanically simple) |
| `blocked_execution_record` | `{}` |
| `stable_evidence_handle` | the original attempt's `stable_evidence_handle` |
| `automation_claim_status` | `"direct_packet_with_handle"` |
| `rollback_plan` | `f"revert:{target_commit_sha}"` |
| `coding_packet.status` | `"AUTO_SHIP_READY"` |
| `changed_paths` | the original attempt's `changed_paths_json` decoded — same paths get reverted |
| `diff` | the unified-diff of `git revert <commit_sha>` (computed by Phase 4 wire-up) |

In v0 (dry-run) the diff is not computed; the proposal's `diff` field is
empty and `validate_ship_request` is run against the rest of the packet
to confirm everything else is well-formed. Phase 4 fills the diff
field, opens the PR, and writes the rollback PR number back to the
ledger via `record_rollback_decision`.

## 5. Evidence contract

Every rollback decision (approved, deferred, or skipped) records to the
ledger via `update_attempt`:

| Field | Approved | Deferred | Skipped |
|---|---|---|---|
| `ship_status` | `rolled_back` | unchanged | unchanged |
| `observation_status_at` | now | now | now |
| `error_class` | `""` | `"rollback_deferred"` | `"rollback_skipped"` |
| `error_message` | reason text | reason text | reason text |
| `rollback_handle` | unchanged (set by Slice A) | unchanged | unchanged |
| `rollback_pr_number` | rollback PR # (Phase 4b) | `""` | `""` |
| `rollback_pr_url` | rollback PR URL (Phase 4b) | `""` | `""` |

Schema notes (updated per Codex's PR #227 review on 2026-05-03; addressed
in commit `8b75e90`):

- The Slice A `MUTABLE_FIELDS` set already includes `observation_status`,
  `observation_status_at`, `error_class`, `error_message`, and
  `ship_status` — so the rollback decision-class fields above are
  writable by `record_rollback_decision` without further schema change
  for the dry-run/Phase-4a path.
- `rollback_pr_number` and `rollback_pr_url` were ADDED to the ledger
  schema in commit `8b75e90` (PR #227 schema-fix) so Phase 4b can store
  the rollback PR identity in structured form rather than parsing prose.
  Both fields are in `MUTABLE_FIELDS`. Default empty string when no
  rollback PR has been issued. `get_status.auto_ship_health.rollback_recommendations`
  surfaces them directly so chatbots and operators can locate the
  rollback PR without parsing prose (Codex's review preference).
- Forward-compat: `ShipAttempt.from_dict` ignores unknown keys, so old
  JSONL rows written before the schema addition still hydrate cleanly
  with the new fields defaulting to empty string.

Slice C is therefore an additive consumer of Slice A's surface plus the
two structured rollback-PR-identity fields added in PR #227.

## 6. Phase split

| Phase | Lands when | What it adds |
|---|---|---|
| Phase 4a (this Slice C) | Post Slice B merge | `assess_rollback_candidates` + `propose_rollback` + `record_rollback_decision` (dry-run); new ship_class `rollback_canary` in `auto_ship.ALLOWED_SHIP_CLASSES`; tests covering decision rules + packet shape + ledger write contract. |
| Phase 4b | Post first live `observation_status=regressed` event in production | wire `gh pr create` into `propose_rollback` behind a feature flag, emitting the actual revert PR; `record_rollback_decision(approved=True, rollback_pr_number=...)` writes the PR number into the ledger row. |
| Phase 4c | Post Phase 4b + observation window tuning | auto-merge of rollback PRs in narrow canary classes (mirrors Phase 3 of the original ship lane). |

Phase 4a is what this spec covers. 4b and 4c are gated on production
evidence and explicit host approval.

## 7. Test surfaces

Test file: `tests/test_auto_ship_rollback.py`. Coverage outline:

- `assess_rollback_candidates`
  - empty ledger → `[]`
  - row with `ship_status="opened"` + `observation_status="observing"` → not a candidate
  - row with `ship_status="merged"` + `observation_status="regressed"` → IS a candidate
  - row with `ship_status="merged"` + `observation_status="regressed"` BUT another row with same `request_id` already `rolled_back` → not a candidate (idempotence)
  - row with `ship_status="blocked"` → not a candidate
  - mixed-state ledger with 5 rows → returns the right subset, sorted by oldest first

- `propose_rollback`
  - happy path: builds packet that PASSES `validate_ship_request` with `ship_class="rollback_canary"`
  - missing original commit_sha → raises ValueError (defensive — should never happen for merged rows)
  - missing rollback_handle → raises ValueError
  - suggested branch name follows convention
  - PR title and body include `ship_attempt_id` and `target_commit_sha`
  - deterministic: same input twice produces equal RollbackProposal

- `record_rollback_decision`
  - approved + rollback_pr_number → ship_status flips to `rolled_back`
  - deferred → ship_status untouched, error_class set
  - skipped → ship_status untouched, error_class set
  - missing ship_attempt_id → KeyError (consistent with Slice A's `update_attempt`)
  - approved without rollback_pr_number → ValueError

- `auto_ship.ALLOWED_SHIP_CLASSES`
  - regression pin: `rollback_canary` is in the allowlist after Phase 4a

## 8. Open questions for host / Codex

These are intentionally NOT decided here — they're Slice C-time conversations:

- **Q1**: Should rollback PRs be subject to the same path allowlist
  (`docs/autoship-canaries/**` etc.) as forward ship attempts? Argument
  for: defense in depth. Argument against: a regressed
  `docs/autoship-canaries/foo.md` ship needs to be revertable, and if the
  forward attempt was allowed, the revert should be too. Default v0:
  inherit the original attempt's `changed_paths` and run the validator
  on the rollback packet — no separate path allowlist.
- **Q2**: Should `observation_status=regressed` set by the observation
  gate ALSO trigger a paged alert independent of rollback? Argument for:
  rollback may legitimately defer (e.g. operator wants to look first);
  silent regression with no human notification is bad. Default v0: no —
  rollback recommendation surfacing through `get_status.auto_ship_health`
  is the alert; paging is post-MVP.
- **Q3**: What is the right cadence for the observation poller (the
  thing that flips `observation_status` from `observing` → `healthy` /
  `regressed`)? Codex's Slice B will include a sketch; Slice C's Phase
  4b will wire to whatever Slice B picks. Default v0: 24h observation
  window per Phase 4 spec, polled hourly by a workflow_dispatch.

## 9. Acceptance criteria for Slice C Phase 4a

The Slice C PR is acceptable when:

```
1. workflow/auto_ship_rollback.py module exists (mirrored to packaging
   plugin path).
2. assess_rollback_candidates returns the right rows for the test
   matrix in §7.
3. propose_rollback's output rollback_packet, when fed to
   validate_ship_request, returns validation_result="passed" and
   would_open_pr=True.
4. record_rollback_decision mutates the ledger correctly for all
   three decision values.
5. auto_ship.ALLOWED_SHIP_CLASSES contains "rollback_canary".
6. All tests in tests/test_auto_ship_rollback.py pass.
7. No code path in this PR opens a PR or runs git commands — Phase 4a
   is dry-run only.
```

Stretch: a paired update to `docs/milestones/auto-ship-canary-v0.md`
§10 noting Slice C Phase 4a landed and what it adds.

## 10. Why this is the right next thing after Slice B

Three reasons:

1. **The validator + ledger + observation surface are write-and-read
   without a closing action.** Slice A records decisions; Slice B
   surfaces them; without Slice C the loop can SEE that a patch
   regressed and DO NOTHING about it. That's worse than not having
   observation at all — it builds operator-trained learned-helplessness.

2. **Rollback is rare but mandatory.** Even in v0 with `docs_canary`
   only, a bad markdown commit (broken table, malformed link, wrong
   timestamp) needs a clean revert path. Operator-driven manual reverts
   work but burn a turn each time and don't feed the ledger.

3. **It unblocks Phase 4 of the milestone.** Per `docs/milestones/auto-
   ship-canary-v0.md` §10 Phase 4, "auto-merge for narrow canary
   classes after one successful PR-open round" is the milestone's
   stretch acceptance. Auto-merge without rollback is unsafe; rollback
   without auto-merge is wasted complexity. They land together in 4c.

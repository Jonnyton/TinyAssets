# Paid-market live-price source-context review

- **Date/environment:** 2026-07-22 PT / 2026-07-23 UTC, Windows worktree `codex/paid-market-track-e-wave2-spec`
- **Reviewer:** Claude Sonnet, foreground-only and read-only
- **Source lane:** draft research PR #1574, `codex/compute-market-frontier-research`
- **Target:** `paid-market-live-price-discovery` plus its composition with `paid-market-track-e-wave-2-transport`
- **Final verdict:** **APPROVE**

## Scope

The gate re-read the PR #1574 compute/LLM/task/fabrication market report, its
prior Claude ADAPT review, the current TinyAssets market/identity/receipt/
execution owners, and the complete target deltas. It also re-checked the
high-risk legal source claims used by the capacity-forward design.

The first source-context review returned `NEEDS_CHANGES` with three blockers:

1. bare `§18.6` references were ambiguous between the integrated architecture
   and distributed-execution exec plan;
2. the forward requirements incorporated physical-delivery restrictions but
   omitted the CFTC facts-and-circumstances test and a specialist legal gate;
3. generic requester acceptance could override machine-gated bounty/task
   verdicts, reintroducing the subjective griefing surface PR #1574 deferred.

It also found two provenance overclaims: the no-maintainer-compute rule was
presented as landed PLAN despite PR #1574 still being open, and private-payload
language did not explicitly preserve the unresolved platform-storage decision.

## Corrections approved

- Every chain-settlement citation now names
  `docs/design-notes/2026-04-18-full-platform-architecture.md` §18.6; S14/B36
  separately names the distributed-execution exec plan.
- Forward activation now requires jurisdiction-specific specialist analysis of
  the CFTC/SEC facts-and-circumstances forward-contract exclusion and applicable
  commodities, derivatives, securities, consumer, money-transmission,
  sanctions, and export-control rules. Physical delivery/collateral/no
  secondary transfer is explicitly not a safe harbor.
- The May 2025 BIS AI-training statement is represented as narrower
  transaction/end-user/end-use and knowledge-based EAR triggers, not a blanket
  AI-training ban or automated classification oracle.
- Machine-gate-only bounties and standing-goal tasks accept from the first
  positive immutable domain verdict; requester subjective veto is forbidden.
  Disputes may challenge evidence, authority, or gate execution and invoke a
  deterministic rerun/higher-tier evaluator, not replace the verdict.
- Human/inspection review exists only for separately reviewed domains that
  declare it, such as fabrication inspection or training checkpoint review.
- The no-maintainer-compute/BYOC constraint is attributed to live STATUS #1582
  and pending PLAN ratification in open PR #1574.
- PR #1574's Commons-first host-resident payload posture is identified as a
  research assumption; this change stores only opaque commitments and bounded
  market/evidence facts while the STATUS private-storage host decision remains
  authoritative.

## Source and validation evidence

- Re-checked primary CFTC/SEC interpretation:
  `https://www.cftc.gov/LawRegulation/FederalRegister/finalrules/2015-11946.html`
- Re-checked BIS policy statement:
  `https://www.bis.gov/media/documents/ai-policy-statement-training-ai-models-may-13-2025`
- `openspec validate paid-market-live-price-discovery --strict` — valid
- `openspec validate paid-market-track-e-wave-2-transport --strict` — valid
- `openspec validate --all --strict` — 36 passed, 0 failed
- `git diff --check` — clean
- Live-price delta — 16 requirement headings, 51 scenarios
- Wave 2 delta — 14 requirement headings, 77 scenarios
- Review was foreground-only and read-only; no background dispatch, edit,
  commit, push, or PR mutation occurred.
- `tests/test_uptime_canary_layer2.py` was not run.

The final re-review found no remaining source-fidelity blocker, new owner
collision, contradictory lifecycle edge, or accidental legal claim.

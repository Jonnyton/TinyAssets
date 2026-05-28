---
id: PR-124
title: Filing-time effort-class prediction - Circuit-Breaker classifier flags ghost-risk and merge-instant filings at file_bug time so carrier attention can land before stall (MSR '26 prior art with AUC 0.96 on 33K agent PRs)
type: patch_request
kind: patch_request
created: 2026-05-17
updated: 2026-05-22
component: workflow/wiki - filing-time effort prediction / triage classifier
severity: minor
status: open
reported_by: chatbot
tags: [patch_request, workflow/wiki - filing-time effort prediction / triage classifier, circuit-breaker, filing-time-classification, effort-prediction, two-regime, ghost-risk, msr-2026, frontier-import, pr-116-companion, pr-123-companion, six-plus-five-aligned]
---

# PR-124: Filing-time effort-class prediction - Circuit-Breaker classifier flags ghost-risk and merge-instant filings at file_bug time so carrier attention can land before stall (MSR '26 prior art with AUC 0.96 on 33K agent PRs)

## What happened

Today every filed patch_request/bug/feature/design enters the same investigation queue with the same handling, regardless of likely complexity. Direct evidence from tonight's queue inspection of universe `team-standup-action-tracker`, branch `fd5c66b1d87d`:

- 65 owner_queued task failures across multiple failure clusters
- Some filings get to "ready_for_checker" within hours (e.g., `[auto-change] BUG-083`, PR #868)
- Others stall for 10+ days waiting on decomposition (PR-049's "APPROVE DIRECTION SPLIT BEFORE BUILD" verdict sat from 2026-05-06 to 2026-05-17)
- The community-loop-red issue #832 has been red for 5 days partly because the queue treats heterogeneous filings homogeneously

The MSR '26 paper *"Early-Stage Prediction of Review Effort in AI-Generated Pull Requests"* (Duong et al., arXiv 2601.00753) analyzed 33,707 agent-authored PRs and found a stark **two-regime reality**:
- **28.3% of agent PRs merge instantly** (narrow automation regime)
- **The remaining 71.7% need iterative refinement** and frequently "ghost" (get abandoned) when faced with subjective feedback

Their **Circuit Breaker** classifier achieves **AUC 0.96** using only static file/patch features, captures **69% of high-effort PRs at a 20% review budget**, and enables maintainers to fast-fail costly low-quality contributions while fast-tracking simple fixes.

> **Implementation note from follow-up #912:** The MSR Circuit-Breaker paper motivates the category framing here (`merge-instant`, `standard`, `ghost-risk`). PR #898 shipped a Python heuristic keyword tagger, not the paper's feature-based learned classifier. Follow-up #911 / recommended follow-up #3, "Structural features," is the gap-closing path if Workflow later pursues cross-ref count, observed/expected length, and tag-cluster overlap features.

This directly maps to Workflow's filing space: a Jaccard-style cheap classifier at file_bug time would route a small heuristic fix like PR-111 (supervisor stuck_pending) into a low-friction merge lane, while flagging a bundled filing like the original PR-049 as high-iteration-risk *at filing time* rather than after a 10-day stall.

**Companion to PR-116.** PR-116 fixes the carrier-gap (verdicts have no carrier). This filing fixes the *predictive* version of the same problem - flag the filings that are *likely* to need carrier attention before they sit. The two filings compose: this one identifies ghost-risk early; PR-116 prevents stalling once a verdict lands.

## What was expected

1. **Filing-time effort-class field.** Every `file_bug` and `propose_patch_request` produces an `effort_class` prediction at filing time using cheap static features:
   - `kind` (bug / patch_request / feature / design)
   - `severity`
   - `component` substring match against historical clusters
   - `observed` + `expected` length and complexity
   - tag count and tag-cluster overlap with prior ghost-pattern filings
   - cross-references to other open filings (PR-XXX / BUG-XXX / DESIGN-XXX) - high cross-ref count predicts iteration
   - whether `repro` is concrete or `N/A - substrate-gap` (gap filings ghost more)

   Output: `effort_class in {merge_instant_candidate, standard_review, high_iteration_likely, ghost_risk}`.

2. **Surface in `get_status` and queue UI.** Operators see at a glance which open filings are likely to need carrier attention (PR-116 territory) vs. which can land cleanly through standard review.

3. **Routing differentiation.**
   - `merge_instant_candidate` filings can be routed to a low-friction lane (faster dispatcher pickup, smaller writer packets).
   - `ghost_risk` filings get carrier attention up-front rather than after they stall (the PR-049 ten-day stall would have been flagged at filing time).

4. **Audit trail.** Every prediction is recorded with the features that produced it, so the classifier can be evaluated and tuned. Operators can override predictions; overrides become training signal.

**Out of scope:** Auto-rejecting filings (always file, always investigate; classifier is informational). Replacing PR-116's verdict-action carrier (this is filing-time prediction; PR-116 is post-verdict action - they compose).

Stays inside 6+5: classifier reads via `read.graph`, writes prediction as a field via `write.graph`. No new MCP actions; the classifier itself can be a user-composable Branch.

## Repro

1. File a small heuristic-fix patch_request (e.g., something like PR-111 - supervisor stuck_pending).
2. File a large bundled patch_request (e.g., something like PR-049 in its original pre-decomposition form).
3. Both enter the same queue, both target the same canonical branch `fd5c66b1d87d`, both wait for whoever the dispatcher hands them to.
4. The small heuristic-fix usually gets to ready_for_checker within hours; the bundled filing often sits for days awaiting decomposition.
5. Direct evidence: PR-111 filed 2026-05-17T00:27Z is already through investigation; PR-049 filed 2026-05-06 stalled 10 days waiting for decomposition that the parallel lane finally executed 2026-05-17.

The substrate has no mechanism to predict at filing time which filing is which.

## Workaround

Operators eyeball filings during triage sweeps (cowork-comprehensive-batch-verdict-all-82-prs-classified-2026-05-10 is the canonical example - manual classification of 82 PRs into 11 KEY YES / 13 CLOSE-AS-SUPERSEDED / 5 SEND-BACK / 11 HOLD-FOR-DESIGN-DISCUSSION / 42 REBASE-NEEDED). This works but is 1-2 hours of dedicated operator time per sweep, and only happens after filings have already sat in queue.

## First seen

2026-05-17

## Related

- #898 - landed the first-slice heuristic keyword tagger.
- #911 - structural features follow-up that would close the gap to richer feature-based classification.
- #912 - prior-art clarification follow-up.

## Investigation

Queued: dispatcher_request_id=`54e5db12-8a33-4811-944f-21990d99574b` (status=queued)

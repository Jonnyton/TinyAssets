---
title: Canonical Goal-Completion Probe - Researcher Paper To Publication
date: 2026-05-08
author: codex-wiki-design
status: proposed
request_id: WIKI-DESIGN
github_issue: 482
wiki_source: pages/design-proposals/design-004-canonical-goal-completion-probe-researcher-paper-to-publicat.md
scope: design-only; no runtime code in this branch
builds_on:
  - PLAN.md#evaluation
  - PLAN.md#multi-user-evolutionary-design
  - docs/specs/2026-04-19-handoffs-real-world-pipeline.md
  - prototype/workflow-catalog-v0/catalog/branches/research-paper-pipeline.yaml
  - prototype/workflow-catalog-v0/catalog/branches/research-paper-submission.yaml
---

# Canonical Goal-Completion Probe - Researcher Paper To Publication

## 1. Recommendation Summary

Accept the request as a project-design proposal for a canonical
goal-completion probe, not as runtime implementation work.

The smallest useful change is to define one Workflow-native Acceptance
Scenario Pack: a multi-month academic researcher drive from paper idea to
public outcome evidence. The probe should measure whether Workflow can keep a
real user moving through the full ladder:

```text
topic -> hypothesis -> method -> draft -> peer feedback -> submission
      -> acceptance/preprint -> publication -> citations or other uptake
```

This fits the accepted PLAN.md direction for Evaluation: reusable long-horizon
scenario packs that combine user simulation, rubric checks, MCP/API or browser
evidence, and artifact capture into `EvalResult` evidence. It also fits the
Multi-User Evolutionary Design section: real-world outcome gates are the truth
signal for a Goal, and research papers already have an explicit gate ladder.

Do not add a new platform primitive for this probe. The probe composes existing
and already-designed surfaces: Goals, Branches, Evaluators, handoffs,
real-world outcomes, connector receipts, public wiki rubrics, and user-surface
chatbot verification.

## 2. Request Classification

**Kind:** project design.

**Smallest useful project change:** a proposed design note under
`docs/design-notes/proposed/` that names the canonical probe, its evidence
contract, its non-goals, and its future build gates.

**Runtime code:** none in this branch. The issue asks for an architectural
proposal; implementing storage, connector, or evaluation changes before the
design clears review would violate the minimal-primitives and
community-build-over-platform-build scoping rules.

## 3. Why This Probe

Workflow's thesis is not "produce a plausible artifact in one chat." It is
"bind a daemon network to a real goal and let it drive." A researcher moving
from early paper idea to publication is a useful canonical stress test because
it exercises the hard parts together:

- long duration: days to months, with idle time and resumed context;
- external validators: peers, preprint servers, journals, DOI/citation systems;
- private/public split: draft and author identity stay owner-local, while the
  reusable workflow concept can be public commons material;
- artifact chain integrity: every later claim depends on earlier evidence;
- user vocabulary: the chatbot must speak like a research assistant, not expose
  engine terms unless the user asks for them;
- outcome truth: success is external progression, not internal completion.

This should become the empirical bar for "goal completion" because a system
that only completes toy tasks will fail the probe visibly: it loses context,
fabricates progress, cannot route handoffs, cannot prove external outcomes, or
cannot keep private material out of the commons.

## 4. Scenario Pack Contract

The probe should be represented as an Acceptance Scenario Pack, not a bespoke
benchmark harness. A future implementation should define a portable scenario
record with these fields:

```yaml
id: canonical-research-paper-to-publication
goal_slug: research-paper
duration_class: multi_month
capability_tiers:
  - browser_only
  - local_app
hosts:
  required_launch_hosts:
    - claude.ai
    - chatgpt
privacy_posture:
  public:
    - branch concept
    - reusable rubrics
    - outcome gate definitions
    - verified public receipts
  owner_local:
    - draft text before publication
    - author identity
    - reviewer feedback unless user publishes it
    - raw private data
gate_ladder:
  - topic_scoped
  - hypothesis_selected
  - method_plan_reviewed
  - draft_complete
  - peer_feedback_integrated
  - preprint_or_journal_submitted
  - externally_accepted
  - published_or_publicly_indexed
  - uptake_observed
evidence_outputs:
  - transcript_refs
  - artifact_refs
  - evaluator_results
  - connector_receipts
  - outcome_events
  - user_attestations
```

The pack should be executable in slices. A single CI run cannot wait months for
journal acceptance, but the scenario can still be canonical if it supports
checkpointed evidence:

1. **Synthetic fast path** for development: mocked external validators and
   fixture receipts prove the orchestration shape.
2. **Live short path** for release gates: real chatbot conversation, local or
   staged handoffs where safe, and user-visible artifact capture.
3. **Live long path** for empirical proof: a real or rights-cleared paper drive
   accumulates outcome events over time.

Only the long path can prove the full product claim. The fast and short paths
are regression gates, not substitutes for external outcome evidence.

## 5. Pass And Fail Semantics

The probe should report progress as a ladder, not a binary pass/fail. Each gate
records:

- `state`: `not_started`, `in_progress`, `blocked`, `attested`, or `verified`;
- `evidence_ref`: transcript, artifact, receipt, URL, or outcome-event ID;
- `verified_at`: freshness stamp for the latest check;
- `verifier`: deterministic check, independent reader, user attestation, or
  external source;
- `privacy_class`: public commons evidence or owner-local evidence.

Canonical failure modes:

- chatbot claims submission, acceptance, publication, or citation without a
  receipt or attestation;
- chatbot leaks owner-local draft or identity into a public branch concept;
- branch concept cannot be remixed without private instance data;
- evaluator says prose/methods are ready while evidence contradicts the claim;
- handoff status changes are not reflected in the Goal's gate ladder;
- the same user cannot resume after a long idle gap and recover context;
- browser-only and local-app users get materially different Goal semantics.

The top-line score should be the highest verified gate plus a confidence label,
not a single percentage. For example: `verified: preprint accepted; attested:
journal submitted; unknown: citations`.

## 6. Composition Over New Primitives

This proposal should not create a `complete_research_paper_goal` action, a
research-specific evaluator kind, or a publication-only workflow API. The
platform already has or has designs for the necessary primitives:

- **Goal / Branch binding** from PLAN.md Multi-User Evolutionary Design;
- **Evaluator evidence** from PLAN.md Evaluation and existing evaluator
  protocol direction;
- **Handoff tracking** from the real-world pipeline spec;
- **Research-paper branch concepts** in the catalog prototype;
- **Community-authored rubrics** from prior methods and methodological-parity
  design notes.

If the scenario cannot be composed from those parts, the failure should be
logged as the smallest missing primitive. The probe's job is to expose such
gaps with evidence, not to pre-author a pile of research-specific platform
features.

## 7. Relationship To Existing Research-Paper Material

The prototype catalog already has two relevant branch definitions:

- `research-paper-pipeline`: topic and prior work to hypotheses, method
  scaffold, and citation bundle.
- `research-paper-submission`: draft finalization through peer-review prep,
  arXiv moderation, and optional journal submission.

The canonical probe should stitch those into one Goal-level scenario rather
than pick one as the blessed workflow. PLAN.md says many Branches can bind to
one Goal; diverse research-paper workflows are a feature. The probe should
therefore define the outcome ladder and evidence contract, then allow multiple
Branches to compete or collaborate against it.

The real-world handoff spec already gives the right substrate for submission
and publication evidence. This probe should consume those receipts and outcome
events. It should not redefine the handoff pipeline.

## 8. Future Build Gates

A future implementation branch should not be considered done until it provides:

1. A scenario-pack schema and fixture for
   `canonical-research-paper-to-publication`.
2. A focused test proving checkpointed gate progression from draft through at
   least submitted/accepted fixture receipts.
3. A privacy test proving owner-local draft/identity fields are not written to
   public scenario evidence.
4. A rendered chatbot-surface verification transcript through a live Workflow
   connector for at least the setup and resume path.
5. A post-fix or post-launch watch item for real-user clean-use evidence if no
   real long-path run exists yet.

The implementation should be blocked on opposite-family review because the
request came through the community design loop and future code would affect the
evaluation/outcome contract.

## 9. Open Questions

- What exact public fixture can stand in for a paper without copyright,
  authorship, or reviewer-confidentiality risk?
- Which external outcome should count as the first live long-path proof:
  preprint acceptance, DOI registration, journal acceptance, or indexed
  publication?
- How should the system represent a gate that is user-attested today but later
  externally verified?
- Where should long-path scenario evidence live so it is durable but does not
  become a fourth living source of truth?
- The request title mentions the "6+5 framing"; this branch found no current
  repo definition for that phrase. Before accepting this as canonical wording,
  a reviewer should either link the source framing or replace it with the
  explicit gate-ladder contract above.

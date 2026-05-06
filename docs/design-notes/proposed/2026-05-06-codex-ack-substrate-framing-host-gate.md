# Codex Ack: Substrate Framing Locked, Host Gate Narrowing

Date: 2026-05-06
Status: proposed
Request: GitHub Issue #450 / WIKI-DESIGN
Source wiki page: `pages/notes/codex-ack-substrate-framing-host-gate-2026-05-06.md`

## Classification

Project design. This note is design-only and makes no runtime code change.

## Context

The community change loop already has the substrate shape in `PLAN.md` and the
active live-loop plan:

- public community requests are daemon requests, not a private maintainer queue;
- paid or free daemons may claim work when they satisfy the declared gate;
- code-change writers remain in the Claude/Codex pool until the flagship lanes
  have stronger proof;
- code-change output requires an opposite-family checker;
- bounty settlement follows the relevant gate ladder's `bounty_requirements`;
- branches stay community-authored and remixable; platform work supplies the
  smallest primitives needed for routing, review, and observation.

That substrate should not be reopened by this request. The open problem is a
narrow host gate: how to turn the framing into an enforceable, observable claim
boundary without redesigning the loop or adding new runtime concepts.

The referenced wiki page is not present in this checkout, and GitHub CLI could
not fetch Issue #450 comments because `GH_TOKEN` is unavailable. This proposal
therefore relies on the filed issue body and local project design sources.

## Decision

Accept the substrate framing as locked for this request. The smallest useful
implementation target is a host-gated claim-policy slice, not a new daemon
architecture:

1. Keep the request bus public and goal/lane agnostic.
2. Validate claim eligibility against existing gate-ladder vocabulary.
3. Preserve the existing writer/checker split for code changes:
   Claude-family or Codex-family writer, opposite-family checker.
4. Treat incentives as pickup signals only; they never alter acceptance,
   release, merge, or bounty settlement proof.
5. Record a compact evidence object that says which gate was checked, who
   claimed it, which writer/checker families are involved, and which evidence
   refs remain missing.

The host gate is approval to implement that enforcement slice once the affected
runtime files are unblocked. It is not approval to broaden contributor identity,
market settlement, branch design, wiki sync semantics, or daemon memory.

## Narrow Implementation Shape

Use existing surfaces:

- `branch_requirements` answers whether a branch or PR may claim a rung.
- `bounty_requirements` answers what must be true before payout or bonus
  settlement.
- GitHub labels remain the cloud-visible subset while runtime `gates claim`
  enforcement is blocked.
- Request metadata from wiki sync stays declarative: request kind, writer pool,
  checker policy, gate requirement, and optional bounty terms.

The eventual code slice should do only three things:

1. Parse the claim policy already present on the request/gate.
2. Reject or hold claims that violate writer-family, checker-family, label, or
   required-evidence constraints.
3. Emit evidence explaining the decision in terms a later release gate can cite.

No new MCP action is proposed here. If a future implementation proposes one, it
must first pass the cohit-prevention check from `AGENTS.md`.

## Gate Contract

For code-producing community requests, the minimum gate is:

```yaml
branch_requirements:
  required_labels:
    - daemon-request
    - checker:cross-family
  allowed_writer_families:
    - claude
    - codex
  forbid_same_family_checker: true
  required_evidence_refs:
    - tests
    - checker_review
    - observation_plan
bounty_requirements:
  free_claim_allowed: true
  settlement_gate: pr_ready
  minimum_gate_verdict: pass
  required_evidence_refs:
    - pr_url
    - ci_run_url
    - live_observation_url
```

Project-design and docs/ops requests may satisfy the gate with a design note,
focused docs checks, and opposite-family review when the request can influence
runtime architecture or public behavior. They should not be escalated into
runtime code changes unless the request explicitly asks for implementation.

## Non-Goals

- No redesign of community-authored branches.
- No new market or bounty mechanism.
- No expansion beyond Claude/Codex code writers.
- No acceptance shortcut for paid work.
- No runtime code in response to this design filing.
- No `PLAN.md` canonicalization until the host accepts the proposal.

## Acceptance For This Proposal

- A proposed design note exists under `docs/design-notes/proposed/`.
- The note identifies the request as project design and design-only.
- The note narrows future implementation to claim-policy enforcement and
  evidence emission.
- No runtime files are changed.
- A future implementation lane can cite this note as host-gate input, but still
  needs the normal opposite-family review and focused test evidence.

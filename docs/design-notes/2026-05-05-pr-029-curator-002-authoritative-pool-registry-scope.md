# PR-029 / CURATOR-002 AuthoritativePoolRegistry Scope

Status: scoping artifact; not accepted architecture.
Date: 2026-05-05
Source: GitHub Issue #328 / wiki path `pages/design-proposals/design-003-pr-029-proposed-curator-002-authoritativepoolregistry-typed-.md`
Request kind: project-design

## Request

Issue #328 names a proposed `AuthoritativePoolRegistry`: a typed registry of
trusted per-platform source pools for a universal branch's `candidate_search`
and `legal_classification` stages.

The referenced wiki page is not present in this checkout under
`pages/design-proposals/`, `knowledge/pages/`, or a local wiki mirror. GitHub
Issue #328 also contains only the sync metadata, not the proposal body. This
note therefore preserves the smallest reviewable project response without
reconstructing the community proposal from its title.

## Classification

This is a project-design request, not a bug or patch. The smallest useful
project change is a scoping record that defines the acceptance bar and prevents
premature platform code.

## Current Design Fit

The title points at a real platform concern: search and legal classification
must be able to tell users which source pools were considered, which were
trusted, and why a source was eligible or rejected.

The proposed shape is not yet dev-dispatchable as platform runtime work:

- A hardcoded "authoritative" registry is likely policy, not a primitive. Under
  `PLAN.md` scoping rules, platform code should provide typed evidence,
  provenance, and rejection reasons; community-maintained rubrics can decide
  which pools are trusted for a domain.
- Per-platform source pools risk becoming a frozen platform taxonomy. The
  community-build path is stronger if the registry entries are public commons
  artifacts with typed attestations rather than source lists embedded in
  runtime code.
- Legal classification is high-risk. A registry can support classification, but
  it must not be presented as legal advice or as a blanket rights guarantee.
- The proposal references universal-branch stages (`candidate_search` and
  `legal_classification`) that are not established as canonical PLAN.md module
  names. Any implementation needs to map them onto existing branch, retrieval,
  evaluation, provenance, and wiki surfaces first.

## Minimal Acceptable Next Step

Before code ships, the design should be rewritten as a typed data contract:

- `SourcePool`: stable id, domain/platform label, maintained-by, URL/source
  pattern, license/terms evidence fields, freshness timestamp, confidence, and
  moderation status.
- `SourcePoolDecision`: source id, pool id, stage, decision
  (`eligible`, `rejected`, `needs_review`), reason code, evidence links, and
  classifier/version metadata.
- A community-maintained registry location in the public commons, not a
  hardcoded runtime allowlist.
- A runtime read path that treats registry records as evidence inputs and emits
  decisions in branch/run artifacts.

That contract can then be reviewed against existing primitives:

- Retrieval and memory routing for candidate discovery.
- Evaluation primitives for legal/rights classification.
- Wiki/commons storage for community-maintained registry records.
- Provenance and source-inspection actions for user-visible evidence.

## Gates

Do not implement platform runtime code for CURATOR-002 until all are true:

1. The missing wiki proposal body is available or the author supplies an
   equivalent design summary.
2. An opposite-family checker reviews the typed data contract, because the
   issue declares `checker:cross-family`.
3. The design clears PLAN.md scoping rules as a primitive rather than a
   convenience or frozen policy bundle.
4. Legal-classification wording is reviewed so outputs are evidence-backed
   classifications, not legal guarantees.
5. A focused test plan exists for source-pool parsing, stale/withdrawn pool
   handling, decision provenance, and user-visible rejection reasons.

## Recommendation

Keep PR-029 / CURATOR-002 in project-design scoping. Do not add
`AuthoritativePoolRegistry` as a hardcoded runtime registry yet. The safe
primitive is the typed evidence and decision contract; the trusted pool contents
should evolve through the public commons and be consumed by runtime stages as
data.

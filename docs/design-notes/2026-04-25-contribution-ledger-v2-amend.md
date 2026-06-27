---
status: active
---

# Contribution Ledger v2 Amend — Anonymous-Author Asymmetry

**Date:** 2026-04-25
**Author:** navigator
**Status:** v2 amend to `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (#48). Pin a deliberate asymmetry between `execute_step` and `design_used` emit-sites that surfaced from the implementation pair-read.
**Scope:** §1.4 design clarification ONLY. No schema change, no behavioral change in implementation (the implementation already encodes this asymmetry correctly per `runs.py:1254` and `runs.py:428`). This amend documents what the implementation already does and pins it as the design contract going forward.
**Builds on:** impl-pair-read #78 (`docs/audits/2026-04-25-impl-71-72-75-vs-48-convergence.md`) cross-check 5 — anonymous-author skip widening. This amend lifts cross-check 5's prose into the design source so future implementers reading #48 see the contract, not just the implementation reading it back.

---

## 1. The amend (insertion into #48 §1.4)

Add a new subsection §1.4.1 after the existing §1.4 emit-site description, BEFORE §1.5 (caused_regression). Suggested wording:

---

### §1.4.1 — Anonymous-author asymmetry between event types

The `actor_id` field has different semantic interpretations across event types when the actor identity is anonymous or empty. **Different event types apply different filtering rules at emit time.**

**Rule:**

| Event type | Anonymous emission policy |
|---|---|
| `execute_step` | **MAY emit with `actor_id="anonymous"`.** The daemon-host attribution captures who-ran-the-step; if the daemon was unauthenticated, "anonymous" is a real-actor record (the unauthenticated daemon-host). Sybil scoring scales distribution; the row is auditable, just deweighted at calc time. |
| `design_used` | **SHOULD NOT emit with `actor_id="anonymous"` OR empty.** The designer field comes from `NodeDefinition.author` at authoring time. If the author was unauthenticated when authoring, no real designer exists to credit later. Emitting would create a synthetic-actor ledger row that no real actor can ever claim and that gets aggregated into a synthetic actor's share of the bounty pool. **Worse than dropping.** |
| `code_committed` | **SHOULD NOT emit with `actor_id="anonymous"` OR empty.** Same reasoning as `design_used` — PR authorship without a real GitHub handle linkage is synthetic-actor pollution. The handle in tags (per #55) preserves the trace; the contribution event waits for the actor link. |
| `feedback_provided` | **SHOULD NOT emit with `actor_id="anonymous"` OR empty.** Same reasoning. Anti-spam invariant (no cite, no credit) already gates emission; anonymous-author skip is a second filter. |
| `caused_regression` | **MUST attribute proportionally to merge actors with positive share.** If the original merge had no positively-credited actors (e.g., all anonymous via `execute_step` only), no `caused_regression` events are emitted; the rollback is recorded in `branch_versions.status='rolled_back'` but no actor bears the negative weight. |

**Why the asymmetry:**

1. **Daemon-host vs. designer semantics differ.** `execute_step` records "the daemon host that ran a step." Even an unauthenticated daemon-host is a real entity for ops/audit purposes (which machine, which process, when). `design_used` records "the actor who authored the artifact." An unauthenticated designer is not a real recoverable actor — there's no path from "anonymous" back to a person who can claim credit later.

2. **Sybil resistance forward-compat (per attribution-layer-specs §5).** Anonymous bindings are exactly the sybil-vulnerable surface for credit-bearing event types. Pre-filtering at emit time is cheaper than filtering at calc time, and prevents sybil-pool inflation in the ledger itself.

3. **Orphan-row prevention.** A `design_used` event with `actor_id="anonymous"` is an orphan: no future "claim my credits" flow can ever attach it to a real actor. The ledger should not accumulate orphans by default.

**Implementation reference:** the asymmetry is already correctly encoded in the production implementation:
- `tinyassets/runs.py:428` — `execute_step` emit: `actor_id=row["actor"] or "anonymous"` (allows anonymous).
- `tinyassets/runs.py:1254` — `design_used` emit: `if not node_def_id or not author or author == "anonymous": return` (skips anonymous).

This amend documents the existing implementation's correct asymmetry as the canonical design contract. Future emit-sites for `code_committed`, `feedback_provided`, and `caused_regression` should follow the SHOULD NOT rule for those event types.

---

## 2. What this amend does NOT cover

- **No schema change.** The asymmetry is enforced at emit-time logic in the application layer; no DB-level constraint required.
- **No retroactive cleanup.** Any `design_used` events that already exist with `actor_id="anonymous"` (none expected per implementation discipline at #75) would need a separate cleanup script. Not anticipated.
- **No `link_actor_id_to_github` retroactive backfill design.** When an actor opts in to GitHub linkage (per #55 §5), retroactive linking of historical `actor_id="anonymous"` events to their now-known identity is a separate primitive. Out of scope for this amend.
- **No tier/team scope handling.** When `actor_id` is a tier-binding or team-binding (per #47 §6 Q1/Q2 punted), authorization rules differ. Out of scope; tier-membership lookup primitive ships separately.

---

## 3. References

- Source #48: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` §1.4 (this amend slots in as §1.4.1).
- Origin pair-read: `docs/audits/2026-04-25-impl-71-72-75-vs-48-convergence.md` cross-check 5 (anonymous-author skip widening).
- Sibling implementation reference: `tinyassets/runs.py:1254` (design_used skip) + `:428` (execute_step allow).
- Composition with sybil resistance: `docs/design-notes/2026-04-25-attribution-layer-specs.md` §5 (sybil sketches A/B/C).
- Composition with #55 PR bridge: `docs/design-notes/2026-04-25-external-pr-bridge-proposal.md` §5 (handle linkage opt-in primitive).

---

## 4. Recommended integration path

This amend is structured as a **standalone insertion document** rather than an inline rewrite of #48. Two reasons:

1. **Diff lineage preservation** — #48's original commit (`287790c`) stays unchanged; this amend is the typed delta. Future readers can see exactly what changed and why.
2. **Reviewer convenience** — host or future navigator can ratify this amend as a standalone doc; if approved, fold into #48 as §1.4.1 verbatim.

Once ratified, integration into #48 is mechanical: insert the §1.4.1 content (the rule table + Why subsections + implementation reference) as a new subsection, update #48's table of contents if any, and bump #48's modification date with a footnote pointing here.

If the amend is large enough to warrant #48 v2 as a full rewrite (rather than a targeted addition), this content is the v2's first section.

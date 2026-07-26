## Context

The canonicality argument is settled and does not get re-litigated here. Its
decisions (D1–D6 of the archived `brain-okf-canonical-store` amendment) were
reviewed by Codex (`ADAPT`, six adaptations folded), approved by the host on
2026-07-25, and recorded in `PLAN.md` — Brain Module "Canonical store" carries
the source-of-truth, redaction-ordering, build-boundary, and backup positions;
Design Decisions carries the per-domain store scoping and the user-designable
brain-organization rule; Open Tensions records Postgres-vs-file as
resolved-by-scoping.

This change starts one step later: **what has to be true in the code** before
`openspec/specs/brain-canonical-store/` may exist.

Current live state, verified against the tree 2026-07-25: no `tinyassets/brain/`
package; no bundle write path, outbox, or entry-state machine; no `assemble(lens)`.
What ships is `tinyassets/wiki/okf_export.py` — a curated one-way export with the
`OKF_VERSION = "0.1"` pin and a narrow generated-bundle conformance report,
as-built in `openspec/specs/knowledge-retrieval-and-memory/spec.md`.

## Goals / Non-Goals

**Goals:**
- Give the brain-store build a single owner, an honest task list, and a delta that
  syncs when — and only when — behavior exists.
- Reuse the shipped projection mechanics instead of rebuilding them in a second
  place with a second set of bugs.
- Keep the substrate expressive enough that a user-designed brain organization is
  a configuration of it, not a fork of it.

**Non-Goals:**
- Re-deciding canonicality, redaction ordering, the build boundary, or backup
  shape. Those are PLAN truth now.
- Starting the build. The Codex 6 pre-build gates still apply.
- Migrating wiki content. Slice-1 reads in place through the shim.

## Decisions

**A1 — The delta travels with the build, not with the amendment.**
`openspec/specs/` is as-built truth, so the change that *ships* the behavior is
the change that syncs it. The amendment archived with `--skip-specs`.
Alternatives: *sync on the amendment's archive* — rejected; it asserts unbuilt
requirements as built, and a read of `openspec/specs/` would report a canonical
store that does not exist. Cross-family gate: Codex returned `REFUTED: no` on the
claim that the sync must not happen yet.

**A2 — The read path is the gap; the projection rules are settled.**
Slice-1 needs an *in-place* reader over the existing wiki. The exporter's
wikilink conversion, `index.md`/`log.md` handling, and exclusion rules are the
same rules the reader needs — factor them out rather than reimplementing.
Alternatives: *export-then-read* — rejected; it makes a copy the slice-1 read
path depends on, which contradicts "no content migration" and adds a staleness
window.

**A3 — `drafts/` membership must be declared for the write path explicitly.**
The exporter excludes `drafts/` from generated bundles. That settles export, not
canon membership. The write path declares its own rule in 2.2; inheriting the
export rule silently would decide a design question by accident.

**A4 — The bundle reader/writer abstracts organization, not just OKF.**
PLAN makes OKF the *default* brain organization and user-designed organizations
first-class remixable commons patterns. The substrate therefore treats "OKF" as
one organization implementation behind the reader/writer seam. Alternatives:
*hardcode OKF* — rejected; it would make every user-designed organization a fork
of the engine, which Scoping Rule 1's corollary explicitly rules out.

## Risks / Trade-offs

- **Partial projection** (entry in the index, not yet in the bundle) → outbox +
  pending→durable states + crash recovery; the bundle is authoritative on
  reconcile.
- **Latency vs durability** → async projection off the write path; durability
  acked from the outbox, not the file fsync.
- **`log.md` as a hot file** under multi-writer load → it is generated human
  history; the transactional journal is separate operational state.
- **Git-snapshot race** capturing half-projected state → atomic bundle
  generations / write-lock coordination at snapshot time.
- **Redaction staleness** → the operational index must stop serving FIRST, then
  the bundle body is deleted, then the index rebuilds; secrets-class tombstones
  omit recoverable content hashes.
- **OKF is v0.1 Draft** → depend only on its stable core; the `okf_version` pin
  plus the composable steward absorb minor bumps; a major bump is a deliberate
  reviewed migration.
- **File-per-entry scale** (1,183+ wiki pages) → the build stays gated on size
  caps, consolidation policy, and load proof. "Just files" is not scale evidence.
- **Partial sync** → if only some of 2.1–2.4 lands, 3.1 syncs only the satisfied
  requirements. A half-synced capability that claims the whole contract is the
  same drift this change exists to avoid.

## Migration Plan

No data migration and no runtime change in this change itself. Slice-1 reads the
existing wiki in place through the A2 shim; later slices add the commit protocol,
index rebuild, and steward behind the Codex gates. **Rollback:** retire this
change; nothing runtime depends on it.

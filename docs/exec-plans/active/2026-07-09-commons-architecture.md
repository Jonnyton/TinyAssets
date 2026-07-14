# Commons Architecture — Substrate, Scopes, Lenses, Federation (2026-07-09)

**Status:** Binding design note. The design law applied to the commons itself: the commons cannot be a platform feature.

## 1. Substrate: three primitives only
- **Artifacts**: content-addressed, typed manifests (MIME/schema per boundary §12) + license + provenance.
- **Links**: remix lineage, references, built-on relations.
- **Claims**: gate evidence attached to artifacts.
The commons is this graph — nothing more. (Web analogy: pages + links; search built on top by anyone.)

## 2. Lenses — discovery is commons-built, never a platform monopoly
Indexes, rankings, taxonomies, curated collections ("best harness shapes for researchers") are themselves commons artifacts: authored, attributed, remixable, earnable, and CONTESTABLE — a rival lens is always one fork away. The platform ships a minimal default lens as a commons artifact like any other. Rationale: platform-owned discovery is a rebuilt gatekeeper and rots (the Thingiverse failure mode).

## 3. One substrate, three scopes — the universe's brain IS a private commons
The same graph model at three visibility scopes: **private** (a universe's memory/designs), **group** (team/company shared graph — the fourth door's home), **commons** (public). Publishing = scope promotion with a license attached, never an export. Remix semantics identical at every scope. Consequence: designing your universe and contributing to the commons are one gesture.

## 4. Federation — connect all existing commons (via the boundary layer)
Connectors wrap external commons (ClawHub, HuggingFace, Printables, GitHub, OpenSCAD libs, Hacker Fab, ...) as **read-through references**: external artifacts enter the graph with provenance=external(origin) + license terms.
- **HARD RULE — reference, never ingest.** No wholesale copying (legal + freshness). Cache per source terms; always attribute origin.
- Licensing gates USE, not REFERENCE: unregistered-license externals are discoverable/discussable, not trainable/fabbable (fail-closed unchanged).
- **External attribution accrual (acquisition mechanic):** remixes of external artifacts record lineage across the boundary; attribution earnings ACCRUE IN ESCROW for the external creator, claimable on verified proof of origin-account control ("your Printables design earned $X here — claim it"). Unclaimed accruals expire after a declared window (default 24 months) to the treasury; window and destination are published policy, not fine print.

## 5. Collaboration — fork-first, upstream-optional
Permissionless fork/remix with preserved lineage is the default. Upstreaming = proposals against an artifact accepted by its maintainer (OpenSpec-shaped change semantics), fundable via goal bounties, verified by gates. Maintainership is authorship, transferable. No approval step exists for forking — only for merging upstream.

## 6. What Opus must NOT build
A platform-owned taxonomy; a single blessed ranking; an ingestion pipeline that copies external commons; a publish flow that exports rather than re-scopes. Each violates §1–4.

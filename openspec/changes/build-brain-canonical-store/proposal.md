## Why

`brain-okf-canonical-store` was a **design amendment**: it argued the canonicality
inversion, took a Codex `ADAPT` review, folded the six adaptations, and waited on
a host decision. That decision landed 2026-07-25 and is now recorded in
`PLAN.md` (Brain Module "Canonical store"; Design Decisions; Open Tensions
resolved-by-scoping). The amendment is finished and archived.

What the amendment never owned is the **build**. Its own §5 heading said so —
"Future build (gated — NOT in this change)" — which is precisely why that change
could never reach completion and why its terminal note prescribed relocating §5
to a successor. This is that successor: the change that owns building the brain's
canonical store and syncing `brain-canonical-store` into `openspec/specs/` once
the behavior is real.

The delta specs travel with this change rather than being synced by the
amendment, because `openspec/specs/<capability>/spec.md` is **as-built** truth
(AGENTS.md §Spec-driven development). There is no `tinyassets/brain/` package, no
bundle write path, no commit protocol, and no outbox anywhere in `tinyassets/`;
syncing the delta on the amendment's archive would have asserted requirements the
system does not satisfy. Cross-family gate 2026-07-25: Codex (read-only) was
asked to refute that reasoning and returned `REFUTED: no`, recommending exactly
this relocation.

## What Changes

- Own the three previously-unowned §5 build items: the OKF **read-path**
  compatibility shim for slice-1 `assemble(lens)`, the **write commit protocol**,
  and **substrate conformance validation** plus the `[composable]` upstream-watch
  steward.
- Carry the `brain-canonical-store` delta (relocated from the archived amendment,
  including all six Codex adaptations) as the live target contract, and sync it
  into `openspec/specs/` only when the corresponding behavior ships. The
  relocation was verbatim apart from one 2026-07-25 correction: the
  source-of-truth and OKF-conformance requirements are now scoped to the commons
  and the default organization instead of asserting OKF for every brain, which
  removes a live contradiction against A4 and tasks.md 4.5.
- Reuse rather than rebuild what already landed. `tinyassets/wiki/okf_export.py`
  ships the four projection mechanics as a one-way **export** — `_convert_wikilinks`,
  `_write_index` (root `index.md` frontmatter is `okf_version` and nothing else),
  `_write_log`, and `_EXCLUDED_ROOTS = {"drafts", "raw", "daemon-wiki"}` — plus the
  `OKF_VERSION = "0.1"` pin and a narrow `_conformance_report`. That is as-built in
  `openspec/specs/knowledge-retrieval-and-memory/spec.md`, whose own wording is
  careful that it is not canonical-store authority. The gap is the in-place
  **reader**, not the projection rules.
- Keep the pre-build gates. This change does not itself authorize the build to
  start; it gives the build a home, an owner, and an honest task list.

## Capabilities

### New Capabilities

- `brain-canonical-store`: the canonical knowledge representation and durability
  contract **for the commons and for the default brain organization** — the OKF
  bundle as source of truth, the SQLite/FTS/vector store as a rebuildable
  operational index, write-through durability under an explicit commit protocol,
  the OKF frontmatter + reserved-file conformance mapping for Tiny's typed
  entries, and the auto-sync-to-OKF obligation. These requirements bind the OKF
  organization, **not every brain**: `PLAN.md` Design Decisions make OKF the
  default rather than a mandate, and A4 below keeps the reader/writer seam
  organization-neutral so a user-designed non-OKF organization is expressible on
  the same substrate (open seam — tasks.md 4.5).

### Modified Capabilities

<!-- No existing capability's requirements change. `knowledge-retrieval-and-memory`
     already spec's the shipped one-way exporter as-built and is not amended here;
     if the read-path shim ends up reusing exporter internals, that reuse is an
     implementation detail, not a requirement change. -->

## Impact

- **Architecture authority:** none pending. `PLAN.md` already carries the
  host-approved source-of-truth, redaction-ordering, build-boundary, and backup
  decisions (host-approved 2026-07-25), marked architecture-only.
- **Future code:** the unbuilt `tinyassets/brain/` package — bundle reader/writer,
  index-rebuild command, write-through projection, conformance validation, and
  the composable steward. No runtime file is touched by this change itself.
- **Spec sync:** `openspec/specs/brain-canonical-store/` does not exist and MUST
  NOT be created until the behavior it describes is built. A dependent lane that
  needs a stable path today cites this change, not that spec.
- **Dependent lanes:** the archived amendment's "Dependent-lane contract" still
  holds and moves here — in particular, no lane may rely on an `assemble(lens)`
  runtime, which remains unbuilt.
- **Gates:** the Codex 6 pre-build gates, cross-provider review, and the
  user-designable-brain-organization constraint (OKF is the default organization,
  not a mandate — `PLAN.md` Design Decisions) all apply before implementation.

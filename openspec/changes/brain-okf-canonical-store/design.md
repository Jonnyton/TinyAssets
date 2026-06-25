## Context

The TINY brain spec (`docs/specs/2026-06-10-tiny-first-principles-spec.md` §5) was ratified 2026-06-10 with the store line: *"SQLite canonical (entries + FTS + vectors); wiki becomes a RENDERING of document-type entries."* The same section adopted OpenClaw's mechanics — the index-is-disposable invariant and `chunk identity = hash(source:lines:content:model_version)` — which presume **markdown is the source of truth and SQLite is the rebuildable index**, the inverse of "SQLite canonical." §5 has been internally inconsistent since ratification.

On 2026-06-12 Google published **OKF v0.1** (`github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md`): a directory of markdown + YAML-frontmatter files, one file per concept, cross-links as an untyped relationship graph, reserved `index.md`/`log.md`; only `type` is required; consumers MUST tolerate unknown types/keys and broken links; extensibility is free `type` values + arbitrary additional frontmatter keys (no profile registry); versioned `<major>.<minor>` with backward-compatible minor bumps; bundle root MAY declare `okf_version`. Host directive 2026-06-24: OKF is the brain's format foundation and the brain must auto-sync as the standard evolves.

Current live state: the brain write path is **unbuilt** and gated behind the Codex 6 pre-build gates (`docs/audits/2026-06-10-tiny-first-principles-codex-review.md`); the designated first slice is a read-only `assemble(lens)` projection over the existing markdown wiki. So the canonicality decision can be corrected before any code locks it in.

## Goals / Non-Goals

**Goals:**
- Make the OKF bundle the canonical source of truth and the SQLite/FTS/vector store a rebuildable operational index (resolve the §5 inconsistency in favor of the model the spec already half-adopted).
- Preserve concurrent multi-writer serving (the one real argument for SQLite-canonical) via a write-through model.
- Map Tiny's typed entries onto OKF as a conformant consumer/producer with zero special-casing.
- Make durability, federation, and no-lock-in fall out of the bundle (git snapshot = the store; export = the bundle).
- Define an auto-sync obligation to the OKF standard as a composable steward.

**Non-Goals:**
- Unblocking or performing the brain build (still gated; this is a design amendment).
- Migrating the 1,183-page wiki now (slice-1 reads it in place as the bundle).
- Building the `workflow/brain/` package, the index-rebuild command, or the steward in this change.
- Inventing an OKF "profile" mechanism (OKF has none; we use its native extensibility).

## Decisions

**D1 — OKF bundle canonical; SQLite is the rebuildable operational index.**
Rationale: host directive; completes the OpenClaw model the spec already cited (source #5); strengthens durability (the git snapshot becomes the store, not a backup-of-a-DB — retiring the rebuild-mandate backup gap) and no-lock-in (wholesale OKF export is the native form).
Alternatives: *keep SQLite-canonical* — rejected (contradicts the directive + the adopted index-is-disposable invariant; makes export and federation secondary). *Dual-canonical* — rejected (ambiguous source of truth; reconciliation undefined).

**D2 — Write-through: operational layer serves writes, bundle is the durability boundary.**
A write is applied transactionally to the operational index (concurrency + candidate gate) and projected to the bundle; durability is defined as "present in the bundle." Rationale: preserves SQLite's concurrency answer to research gap #4 (WAL single-writer, p95<200ms) while moving source-of-truth to the bundle.
Alternatives: *bundle-only writes* — rejected (file-level concurrency is weak at a public multi-writer endpoint). *SQLite-durable + periodic export* — rejected (that is the status quo; export becomes a stale backup, not the canonical form).

**D3 — Typed fields ride as additional frontmatter keys; no formal profile.**
`type` is the only required field; `goal_id`/`universe_id`/`visibility`/`lifecycle`/`ttl_class`/`supersedes`/`evidence_refs` are additional keys OKF consumers preserve. Tiny's conventions are contributed upstream by community PR. Rationale: OKF's stated extensibility model; keeps Tiny bundles readable by any OKF tool.
Alternatives: *OKF profile/extension registry* — rejected (OKF specifies none; would be inventing non-standard machinery).

**D4 — Auto-sync is a composable steward, not platform code.**
A forkable steward holds a vigil on the OKF spec repo (§6.2 change-control treats vendors/standards as upstream assets), pins `okf_version`, and absorbs minor bumps. Rationale: build-boundary law #4 — conformance-tracking is composable; only the bundle store + assemble + caps are `[substrate]`.
Alternatives: *platform-coded conformance/sync* — rejected (drift from law #4).

**D5 — Amend the narrative spec in the same change.**
Edit §5 store bullet + §5h, §11.2 (redaction order), §13 (build-boundary wording), §14 (migration/backup) so the ratified narrative and this capability never diverge. Rationale: the §5 inconsistency is exactly the drift OpenSpec exists to prevent.

## Risks / Trade-offs

- **SQLite single-writer / latency SLO (research gap #4)** → unchanged by this decision; the operational layer still owns concurrency. Bundle projection can be async/batched off the write path. Mitigation tracked in the future build slice, not here.
- **Bundle/index divergence on partial write-through failure** → bundle is authoritative; the index reconciles on rebuild; `log.md` is the journal of record.
- **Redaction in a never-delete git store** → existing §11.2 pipeline (tombstone + index purge + snapshot scrub; filter-repo + force-push + rotate for secrets). OKF-canonical makes this *cleaner* — redaction deletes from the actual source of truth, and "index rebuild becomes the compliance feature" stays literally true.
- **OKF is v0.1 Draft and may change** → we depend only on its stable core (markdown + frontmatter + non-empty `type` + reserved files); `okf_version` pin + steward absorb minor bumps; a major bump is a deliberate, reviewed migration.
- **File-per-entry scale** (1,183+ entries today, growing) → bounded by the §5 size-pressure caps + consolidation; OKF "just files" scales like git, which the wiki already does.

## Migration Plan

Design amendment only — **no data migration, no runtime change**. The narrative-spec edits land with this change. Slice-1 (gated, future) reads the existing wiki in place as the canonical bundle; later slices build the write-through projection + index-rebuild + steward behind the Codex gates. **Rollback:** revert the spec edits; nothing runtime depends on this change yet.

## Open Questions

- Bundle topology: one physical bundle per universe with the commons as a union *view*, or a physical commons bundle? (Defer to build slice; §5 says per-universe brains + commons = union.)
- Does `log.md` subsume the DREAMS.md consolidation diary, or are they distinct reserved/conventional files?
- Render-time coexistence of Tiny's typed relations (`supersedes`, `evidence_refs`, goal-graph edges) with OKF's untyped body cross-links.
- `okf_version` pin cadence + who owns the steward's escalation thresholds (org-chart routed).
- **Codex review verdict** on this amendment — required before it gates any build (research-derived → opposite-provider review).

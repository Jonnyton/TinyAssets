## Why

Two June legacy documents preserve conflicting design provenance: the TINY
first-principles narrative describes SQLite as canonical, while its research
companion records OpenClaw's markdown-source-of-truth/rebuildable-index model.
Neither file is current authority: PLAN owns architecture and this active
OpenSpec change owns the in-flight behavioral target. On 2026-06-12 Google
published **Open Knowledge Format (OKF) v0.1**, a vendor-neutral version of the
markdown-canonical model. Host directive 2026-06-24: adopt OKF as the brain's
format and auto-sync as the standard evolves. The change is cheap now — the
brain write path is unbuilt and gated — and expensive once a SQLite-canonical
write path ships.

## What Changes

- **Canonicality inversion (the core decision):** the canonical source of truth becomes an **OKF bundle** — a directory of markdown + YAML-frontmatter files, one file per entry, cross-links forming the graph, reserved `index.md` + `log.md`. The SQLite entry store + FTS + vectors becomes a **fully rebuildable operational index** over the bundle (disposable by design; one-command rebuild). *(The earlier SQLite-canonical wording survives only as legacy provenance.)*
- **Write-through durability under a commit protocol:** a write lands transactionally in the operational layer (concurrency + candidate gate) and projects to the bundle under an explicit commit protocol (idempotency key, pending→durable states, atomic temp+rename, outbox ordering, crash recovery); an entry is durable only once it is in the bundle. Write-through **re-houses, not resolves**, the public-concurrency hazards of research-impl Gap #4. The bundle is the unit of nightly git-snapshot durability, cross-universe federation (the commons = union of public goal-addressed bundle entries), and wholesale self-host/fork export ("format not platform" = real no-lock-in).
- **OKF conformance mapping:** Tiny's typed/scoped/lifecycled entry fields (`goal_id`, `universe_id`, `visibility`, `lifecycle`, `ttl_class`, `supersedes`, `evidence_refs`) ride as **additional frontmatter keys** — explicitly OKF-conformant (only `type` is required; consumers MUST tolerate unknown types and preserve unknown keys). Reserved-file/section mapping: `index.md` ↔ progressive-disclosure manifest; `log.md` ↔ bi-temporal lineage + consolidation diary; `# Citations` / `references/` ↔ citation-required promotion; broken cross-links ↔ not-yet-written candidate knowledge; concept-ID-as-path ↔ entry addressing.
- **Auto-sync to the standard:** a forkable steward holds a vigil on the OKF spec repo (`okf_version` pin); backward-compatible minor bumps are absorbed; Tiny's conventions are contributed upstream via community PR (OKF has **no** formal profile mechanism — extensibility is free `type` + additional keys + GitHub governance). This steward is `[composable]` (a forkable default branch), never platform code.
- **Slice-1 needs no content migration, but a compatibility shim:** the first build slice (read-only `assemble(lens)` over the existing wiki) reads it through an OKF compatibility shim (lossless `[[wikilink]]`→Markdown-link projection, root-`index.md`→`okf_version`-only, `log.md` normalization) — the wiki is *not* OKF-conformant as-is. No content is migrated.
- Treat the two legacy June documents as provenance only. Before this target
  can gate implementation or sync, fold the host-approved architectural
  source-of-truth decision into PLAN; the OpenSpec delta remains the sole
  behavioral target owner.

## Capabilities

### New Capabilities
- `brain-canonical-store`: The brain's canonical knowledge representation and durability contract — the OKF bundle as source of truth, the SQLite/FTS/vector store as a rebuildable operational index, write-through durability, the OKF frontmatter + reserved-file conformance mapping for Tiny's typed entries, and the auto-sync-to-OKF obligation.

### Modified Capabilities
<!-- openspec/specs/ has no existing capability covering the brain store; the active `mcp-five-handle-surface` change is the user-facing tool surface and is unaffected. No existing OpenSpec capability requirements change. -->

## Impact

- **Architecture authority:** PLAN must receive the host-approved store decision
  before implementation or spec sync. The TINY narrative and research
  companion are conflicting provenance inputs, not files this change amends or
  treats as canonical.
- **Future code (gated — NOT in this change):** the unbuilt `tinyassets/brain/` package — bundle reader/writer, index-rebuild command, write-through projection, conformance + auto-sync steward. The slice-1 read-only `assemble(lens)` path is unchanged.
- **Durability target:** the nightly git snapshot is the canonical bundle rather
  than a secondary backup of an authoritative database.
- **Gates:** this is an in-flight behavioral proposal and does not unblock
  build. It stays under the Codex 6 pre-build gates, cross-provider review, and
  host-approved PLAN foldback; OKF-as-foundation is research-derived.
- **Target principles:** no-lock-in (wholesale OKF export is the native form),
  commons (federation is bundle-union), and redaction (block the operational
  index, delete from the bundle, then rebuild).

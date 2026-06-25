# Codex review — brain-okf-canonical-store (OKF-canonical brain store)

- **Date:** 2026-06-24
- **Reviewer:** Codex (opposite-provider gate, AGENTS.md cross-provider review)
- **Initial author:** Claude (Opus 4.8) session
- **Under review:** OpenSpec change `brain-okf-canonical-store`; amendment to `docs/specs/2026-06-10-tiny-first-principles-spec.md` §5/§5h/§11.2/§13/§14
- **PR:** #1369 (draft)

## Verdict: ADAPT

Direction approved; **build-gating BLOCKED** until the 6 required adaptations land in the spec delta. Per AGENTS.md, ADAPT gates build/push/live-rollout/acceptance — not the design landing itself.

## Summary

OKF-canonical is directionally sound, but the amendment overclaimed on two points: that write-through *solves* public concurrency (research-impl Gap #4), and that the existing wiki is already an OKF bundle. The §5-vs-companion inconsistency is a real cross-artifact mismatch but was overstated as a purely internal §5 contradiction.

## Source re-check (OKF v0.1)

Core claims match upstream `okf/SPEC.md`. Discrepancies found:
- Unknown-key preservation is **SHOULD**, not MUST.
- Broken links are valid, but OKF does not label them "candidate knowledge" (could be typos/stale links).
- The current wiki is **not** OKF-conformant as-is: the root `index.md` scaffold writes `title/type/updated` frontmatter (OKF permits only `okf_version` at root `index.md`); the wiki uses `[[wikilinks]]` (OKF uses standard Markdown links).

## Context re-check

- **§5 inconsistency:** mostly true as a spec+companion mismatch (old §5 "SQLite canonical" vs the research companion's adopted OpenClaw "markdown source-of-truth + rebuildable SQLite index"); **overstated** as purely internal, since disposable FTS/vectors can be consistent with SQLite-canonical.
- **Gap #4 NOT resolved:** write-through re-houses concurrency behind a SQLite front door but adds hazards (partial projection, `log.md` write contention, bundle/index divergence, git-snapshot races) absent an explicit commit protocol.

## Risks (verbatim)

- Accepted write visible in SQLite but failing before bundle projection violates "durable only once in bundle."
- If the API waits for bundle projection, file write + log append + fsync/snapshot coordination may break p95 <200ms.
- `log.md` as "journal of record" = a single hot file under public multi-writer load.
- Git snapshots can capture half-projected bundle state without write-lock/atomic-generation coordination.
- "Slice-1 reads existing wiki in place as the canonical bundle" is false without a compatibility layer (wikilinks, non-conformant index/log).
- Redaction source-first can leave stale content served from FTS/vector/SQLite until rebuild completes.
- Tombstone `content-hash` is unsafe for secrets if it is a plain hash of leaked material.

## Required adaptations (gate build)

1. **OKF compatibility/conformance task before build** — root `index.md` carries only `okf_version`; `log.md` uses OKF date structure; standard Markdown links OR a documented lossless wikilink→markdown projection; a rule for whether `drafts/` are bundle concepts or operational staging outside the bundle.
2. **Replace "write-through resolves Gap #4" with a concrete commit protocol** — idempotency key; pending/durable states; atomic temp-file+rename; file locking; SQLite transaction/outbox ordering; crash recovery; rebuild reconciliation.
3. **Split `log.md` semantics** — OKF human update-history may be generated/appended; the transactional journal cannot rely on a single prose markdown file under concurrent writes.
4. **Build-boundary** — bundle store, index, AND conformance VALIDATION are `[substrate]`; only the upstream OKF-watch / migration-proposal steward is `[composable]`.
5. **Tighten redaction** — synchronously block reads / tombstone the operational index BEFORE content can keep serving; purge vectors/FTS/raw copies/rollups; secrets → filter-repo/force-push/rotate AND omit plain content hashes in tombstones.
6. **Reword the inconsistency rationale** — "cross-artifact mismatch with the adopted OpenClaw precedent," not an internal §5 contradiction.

## Disposition

All 6 adaptations folded into the OpenSpec change (`proposal.md`/`design.md`/`specs/brain-canonical-store/spec.md`/`tasks.md`) and the ratified-spec §5/§11.2/§13 wording in the same commit as this artifact. PR #1369 remains **draft** pending host merge key; build remains gated under the Codex 6 pre-build gates.

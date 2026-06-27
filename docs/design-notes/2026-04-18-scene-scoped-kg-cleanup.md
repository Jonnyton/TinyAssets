---
status: active
---

# Scene-scoped KG cleanup — `seeded_scene` schema expansion

**Date:** 2026-04-18
**Author:** navigator
**Status:** Follow-up scoping note. Enables full Fix E per `docs/concerns/2026-04-16-synthesis-skip-echoes.md`.
**Relates to:** Task #17 Fix E (post-synthesis drift-KG cleanup), STATUS.md "Synthesis race RC-1".

---

## 1. The gap

`FactWithContext.seeded_scene` (tinyassets/knowledge/models.py:129) records which scene-draft seeded a fact. The `facts` table mirrors it as a column (tinyassets/knowledge/knowledge_graph.py:160). This lets Fix E target exactly the drift-authored facts: `DELETE FROM facts WHERE seeded_scene LIKE '%-B*-C*-S*_chunk_*'`.

**The `entities` and `edges` tables have no such column.** Schema at `knowledge_graph.py:116-139` shows `entities(entity_id, entity_type, access_tier, public/hidden/secret_description, aliases)` and `edges(source, target, relation_type, access_tier, temporal_scope, pov_characters, weight, valid_from/to_chapter)`. No provenance, no scene-seeding field.

Consequence: **Fix E as currently scoped can only clean facts, not entities or edges.** In the echoes_of_the_cosmos contamination (53 facts / 43 entities / 60 edges from drift), Fix E removes 53, leaves 103 drift-created nodes and relationships. That is the "facts-only subset" the lead flagged.

## 2. What full scene-scoped cleanup needs

Three schema additions, symmetric with `facts.seeded_scene`:

1. `entities.seeded_scene TEXT NOT NULL DEFAULT ''`
2. `edges.seeded_scene TEXT NOT NULL DEFAULT ''`
3. Matching fields on `GraphEntity` and `GraphEdge` TypedDicts (`models.py:157-180`).

Plus wiring: entity/edge extraction paths need to thread the scene context the way fact extraction does today (see `entity_extraction.py:160` where `seeded_scene=scene_id` is already passed when building `FactWithContext`; entity/edge constructors currently drop the same context on the floor).

## 3. ROI framing

Worth doing — but sequenced, not bundled with #17.

**Earns its keep because:**
- Drift contamination is not a one-time echoes bug. Any race between canon upload and run_book will produce the same asymmetric contamination. Scene-scoped cleanup is the durable guard; Fix E without it is half a mitigation.
- The same field enables other features on the shortlist: per-scene retraction when evaluator reverts, branch-scoped forking (copy KG rows seeded after fork point), provenance audit when canon and drift disagree.
- Schema cost is low: additive columns with defaults, backfillable by setting `''` on pre-existing rows (treats them as "canon/unknown origin", conservative default — they don't get deleted by Fix E).

**Cost estimate:**
- Schema migration: ~30 lines in `_ensure_schema` (ALTER TABLE … ADD COLUMN, idempotent like the Stage-2a scope columns at `knowledge_graph.py:174+`).
- Dataclass/TypedDict updates: ~10 lines.
- Extraction thread-through: ~40 lines across `entity_extraction.py` and whichever path writes edges (audit needed).
- Tests: ~60 lines covering migration idempotence, threading, and full-scope Fix E cleanup.
- Total: ~140 lines + tests. Half a dev-day.

## 4. Sequencing recommendation

1. Land #17 Fix A+C+E (facts-only) as planned. That ships the immediate race fix and removes the worst contamination.
2. Wipe+re-ingest echoes_of_the_cosmos KG (Q2 host-decided).
3. File a follow-up exec plan for this expansion after #17 is stable (~1 week monitoring). Do it before Fix E gets load-bearing elsewhere, so the one-shot cleanup grows into the full form rather than being replaced.
4. Update Fix E cleanup helper to sweep entities + edges once the schema lands — small delta on top of existing facts sweep.

Do **not** fold into #17. #17 already carries A+C+E revert-and-expand scope; piling a schema migration on top widens the blast radius.

## 5. Open question for dev/host

Does the entity/edge extraction path have obvious seams to thread scene context, or does the current pipeline batch extraction at a level higher than per-scene? If batched, Fix E-full requires scene awareness to be introduced — not just plumbed. That would push the cost up. Recommend dev audit `entity_extraction.py` and whatever writes edges (check `knowledge_graph.py` entity/edge upsert paths) before committing to the half-day estimate.

---

## 6. Sources

- Concern: `docs/concerns/2026-04-16-synthesis-skip-echoes.md` (Fix E scope line 105, phase-list line 125).
- Schema: `tinyassets/knowledge/knowledge_graph.py:116-163` (entities/edges/facts DDL), `:174+` (Stage-2a additive-migration pattern).
- Model: `tinyassets/knowledge/models.py:129` (`FactWithContext.seeded_scene`), `:157-180` (GraphEntity/GraphEdge — no seeded_scene).
- Extraction: `tinyassets/knowledge/entity_extraction.py:160` (fact-level threading).

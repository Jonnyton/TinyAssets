# Schema-Migration Follow-Ups Audit

**Date:** 2026-04-19
**Author:** navigator
**Trigger:** Mission 26 bonus finding — storage schema migrated 04-17 → 04-19. New universes write `knowledge.db::facts` + `knowledge.db::entities`; legacy universes still read `story.db::extracted_facts` + `story.db::character_states`. Fix E's cleanup path was written for the new schema and orphans the old (per `domains/fantasy_daemon/phases/drift_cleanup.py`'s explicit "scope: facts-only on knowledge.db" docstring).

**Lens:** identify *other* code paths that may have the same shape — code that was updated for the new schema but leaves the legacy schema in an inconsistent or stale state. Dev #49 handles the acute Fix E symptom; this audit asks "is the same gap latent elsewhere?"

**Method:** Walked all `tinyassets/`, `domains/`, `fantasy_daemon/` modules referencing `story.db` and/or `knowledge.db`. Cross-referenced against the Fix E commit (`05ce779`) + the dual-source pattern at `tinyassets/universe_server.py:2797-2890` (`_query_world_db`).

---

## 1. Headline — three classes of migration gap

The 04-17 → 04-19 migration is more accurately described as *bifurcation*: `story.db` was the original world-state store; `knowledge.db` was added as the KG-pipeline store. Both still exist, both are being written to, neither was deleted or fully migrated to the other. This means:

- **Class 1 — read-side bridges that work correctly.** Code that knows about both DBs and probes them in priority order. Works as designed; no follow-up needed.
- **Class 2 — write-side asymmetries that are acute today.** Code that writes to one DB but should also touch the other. Fix E is the only known instance; dev #49 closes it.
- **Class 3 — write-side asymmetries that are latent.** Code that writes to (or cleans) one DB but the corresponding mutation in the other DB hasn't been audited. **This is the audit's primary finding surface.**

---

## 2. Inventory — every code path touching story.db OR knowledge.db

| Code path | Touches | Operation | Class | Notes |
|---|---|---|---|---|
| `tinyassets/universe_server.py:2797-2890` `_query_world_db` | both | READ (probe-priority) | 1 | Dual-source bridge; explicitly tries `story.db::extracted_facts` first, falls back to `knowledge.db::facts`. Same shape for `characters`. **Working as designed.** |
| `tinyassets/universe_server.py:1345` | story.db | READ (path construction) | 1 | `db_path = udir / "story.db"` for individual universe. Standard read access. |
| `tinyassets/memory/archival.py:131` | knowledge.db | READ (path construction) | 1 | `kg_path = str(Path(db_path).parent / "knowledge.db")` — derives KG path from world-state db path. Read-side only. |
| `tinyassets/memory/manager.py:294,330` | (state-shape) | READ (state field `extracted_facts`) | 1 | Reads the state.extracted_facts field passed in by the commit pipeline; not direct DB access. |
| `tinyassets/evaluation/structural.py:723,780,923,1009` | (state-shape) | READ (state field `extracted_facts`) | 1 | Same — state-shape consumer, not direct DB. |
| `domains/fantasy_daemon/phases/drift_cleanup.py` | knowledge.db | DELETE | **3** | **Fix E. Scope explicitly facts-only on knowledge.db. Does NOT touch story.db::extracted_facts, story.db::character_states, or story.db::promises.** Dev #49 in flight. |
| `domains/fantasy_daemon/phases/orient.py:36` | story.db | path-policy comment | 1 | Comment about default path removal; no operation. |
| `domains/fantasy_daemon/phases/world_state_db.py:4` | story.db | (module — full impl) | 1 | World-state DB module. Full WRITE pipeline for `story.db` tables. **Does NOT also write to knowledge.db** — KG pipeline owns that side. |
| `domains/fantasy_daemon/phases/_paths.py:21,30,46,55` | both | path resolution | 1 | Helpers — `world_state_db_path()` returns story.db path; `knowledge_db_path()` returns knowledge.db path. No operations, just path policy. |
| `domains/fantasy_daemon/state/universe_state.py:113,116` | both | typed-state field declarations | 1 | TypedDict fields documenting the two DB paths. No operations. |
| `fantasy_daemon/api.py:1221-1238` | story.db | READ (file existence + path return) | 1 | `_resolve_story_db_path()` — fallback path when daemon isn't running. No write. |
| `fantasy_daemon/__main__.py:543-560` | story.db | path resolution + INIT | 1 | DaemonController init sets `_db_path` to `<universe>/story.db` for the world-state pipeline. Init only. |
| `fantasy_daemon/__main__.py:720-726, 910` | knowledge.db | path resolution + state-injection | 1 | Wires `_kg_path` for the KG pipeline. No direct write. |
| `fantasy_daemon/__main__.py:2013` | story.db | CLI help string | 1 | Argparse help text. Cosmetic. |

**Total Class 3 entries (latent migration gaps): 1.** That's Fix E itself, which dev #49 is closing.

---

## 3. Latent gap analysis — does Fix E's pattern exist elsewhere?

Fix E's gap is a **single-direction cleanup**: a mutation pipeline that *deletes* records in one DB but doesn't propagate the deletion to the corresponding records in the other DB. To find latent instances, the audit asks: *what other mutation operations should propagate across both DBs but might not?*

### 3.1 Other DELETE operations

The only DELETE operation against either DB I can identify in canonical code is Fix E's `cleanup_drift_kg`. There is no other "scrub all rows matching pattern X" path. **No latent DELETE-side gaps.**

### 3.2 INSERT/WRITE asymmetries

The two DBs have *complementary* write pipelines by design — the commit pipeline writes story.db tables (extracted_facts, character_states, promises) and the KG pipeline writes knowledge.db tables (entities, facts, edges, communities). Both run on every accepted scene. **No write asymmetry — they're meant to be parallel.**

The risk would be: a commit succeeds and writes to story.db but the KG pipeline fails or is skipped, leaving knowledge.db without the corresponding rows. That's a *runtime consistency* bug shape, not a *migration gap* shape — they're different failure modes. Worth flagging separately, but not the question this audit is answering.

### 3.3 SCHEMA-EVOLUTION gaps

When `knowledge.db` was added (04-17 era per Mission 26's bonus finding), did any code that previously read story.db for a given query type get switched to read knowledge.db without a fallback? Per the `_query_world_db` priority-list pattern at `universe_server.py:2820-2832`, the dual-source bridge is correct — story.db is tried first (richest data; sporemarch has 282 rows there), knowledge.db is the fallback. **Read side correctly handles both.**

### 3.4 The Fix E shape generalized

Fix E's docstring is explicit:
> *Scope: facts-only. Only `facts` carries `seeded_scene` in the current schema; entities and edges have no scene attribution. We intentionally do NOT sweep orphan entities…*

The intentional limitation is that the schema doesn't carry the metadata needed to do scene-scoped cleanup on entities/edges. That's a **schema-expansion ask** (add `seeded_scene` columns to entities + edges), tracked in the Fix E commit message as deferred to "task #10" — recommend confirming this is in the dispatch queue or restating it as a current task.

**Crucially, the Fix E gap that Mission 26 surfaced is a different shape:** Fix E *also* doesn't sweep `story.db::extracted_facts` or `story.db::character_states`. Both of those tables DO carry scene attribution (they're written keyed to scene_ids). The omission is a *cross-DB scope gap*, not a schema-expansion gap. **Dev #49 is the right closure.**

### 3.5 Are there other operations like Fix E waiting to be added?

Hypothetically, future cleanup operations would have the same shape — "wipe drift rows for a scene_id pattern" — and they should be designed against both DBs from the start, not just one. Recommend a small architectural rule (proposable for PLAN.md if accepted): *cleanup operations against scene-attributed data must scope across all DBs that hold scene-attributed rows*. This generalizes Fix E + #49's lesson.

---

## 4. Dev #49 sufficiency check

Dev's task #49 is "Fix E DB-derivative cleanup" — the acute symptom Mission 26 surfaced. Two questions for sufficiency:

1. **Does #49 sweep all three story.db tables (extracted_facts, character_states, promises)?** Mission 26 evidence: 80+ orphan extracted_facts rows + 9 residual character_states rows. The promises table wasn't probed in Mission 26 — recommend dev verify it as part of #49 scope. If dev's spec only covers extracted_facts + character_states, ask them to add promises.

2. **Does #49 also handle the NER-quality #B3 case?** The character_states orphans Mission 26 found include NER garbage ("If Kael", "For", "Manual", "Oxygen") — these will be deleted along with real-character orphans because they share the same scene_id keying. **#49 should incidentally clean up #B3 evidence.** Worth a one-line check post-#49 landing: re-run Mission 26 Probe B Branch B, confirm character_states is clean of both orphan-real-characters AND NER garbage tied to drift scene_ids.

Recommend nav surface both checks to dev before #49 commit.

---

## 5. The migration-test gap (the meta-finding)

The 04-17 → 04-19 schema bifurcation does not appear to have shipped with a **migration-completeness test** — a test that asserts every operation that mutates one DB also has a corresponding code path for the other DB (or explicitly opts out with a documented reason).

If such a test had existed at 04-17, Fix E's cross-DB scope gap would have been caught at `05ce779` commit time, not three days later via Mission 26 user-sim probe.

**Recommendation: a single light-weight invariant test.** Per CLAUDE_LEAD_OPS.md's "Code Before Agents" standing rule (mechanical hooks > agent re-checks), this is exactly the pattern that should become a hook:

```python
# tests/test_schema_dual_source_invariant.py
def test_cleanup_operations_scope_across_dbs():
    """Every DELETE/UPDATE against story.db has a documented counterpart
    against knowledge.db (or explicit opt-out comment)."""
    # Walk all `cur.execute("DELETE FROM ...)` and similar across canonical
    # tree; assert each is paired with a sibling op against the other DB,
    # OR carries an `# noqa: dual-source-asymmetric` marker with reason.
```

**Cost:** ~2-3 hours dev work. Sequenced as a small follow-up after #49 lands. Catches future Fix-E-shape regressions without needing a user-sim mission to find them. Aligns with the host's "Code Before Agents" standing rule.

---

## 6. Recommended follow-up actions

**For dev (queueable now, conditional on #49 in flight):**
- **Verify #49 scope covers all 3 story.db tables** (extracted_facts, character_states, promises). One-line confirmation in the dispatch ack.
- **Post-#49 verification mission:** re-run Mission 26 Probe B Branch B; confirm character_states clean of drift-keyed rows AND NER garbage. Single-prompt user-sim mission, ~5 minutes.
- **NEW: schema-dual-source invariant test** (~2-3 hours, post-#49). Mechanical hook per "Code Before Agents." Catches future Fix-E-shape regressions.
- **NEW: confirm Fix E follow-up (entity/edge `seeded_scene` schema expansion) is in the dispatch queue.** Per Fix E commit message, deferred to "task #10" — verify that task exists or restate.

**For nav (this turn — already done):**
- This audit identifies the single Class-3 gap (Fix E itself) and confirms no other latent migration gaps in the canonical tree. **Reassuring finding:** the migration is more contained than Mission 26's bonus comment suggested. Dev #49 + the proposed invariant test fully close the audit's surface.

**For host (no immediate action):**
- Architectural-rule proposal for next PLAN.md.draft revision: *"Cleanup operations against scene-attributed data must scope across all DBs that hold scene-attributed rows."* Small commitment; generalizes Fix E lesson.

---

## 7. Summary

- **Single Class-3 latent migration gap found: Fix E itself.** Dev #49 in flight closes it.
- **No other latent gaps in canonical tree.** Read-side dual-source bridge (`_query_world_db`) is correctly designed; write-side pipelines are complementary by design (no asymmetry); no other DELETE operations exist beyond Fix E.
- **Two sufficiency checks recommended for #49** (story.db scope coverage + NER garbage incidental cleanup).
- **One mechanical-hook follow-up proposed** (schema-dual-source invariant test, ~2-3 hours, aligns with "Code Before Agents" rule).
- **One PLAN.md.draft amendment proposed** (cleanup operations cross-DB-scope rule).
- **Audit conclusion:** the migration is more contained than Mission 26's framing suggested. Mission 26 found *one* concrete instance of the gap, and that instance is the same one dev is closing. The system is in better shape than the headline finding implied.

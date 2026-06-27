# Author -> Daemon Rename: Phase 0 Audit

Companion to `docs/exec-plans/active/2026-04-15-author-to-daemon-rename.md`.
Phase 0 deliverable per plan §1.5 ("Audit list") and §4 Phase 0.

Date: 2026-04-17. Owner: dev.

---

## 1. `author_id` site classification (plan §1.5)

**Total live occurrences:** 97 across 12 live files (grep `\bauthor_id\b`, Python only, excluding `fantasy_author_original/` and `packaging/claude-plugin/.../runtime/` which are mirror copies).

**Classification result: every live `author_id` site is agent-runtime. Zero content-authorship sites. Zero ambiguous sites.**

### Agent-runtime (-> rename to `daemon_id` in Phase 2/3)

| File | Occurrences | Role |
|---|---|---|
| `tinyassets/author_server.py` | 25 | Table `author_definitions.author_id` PK, FK on `branch_definitions`, `goals`; `_author_id_for()` generator; `get_author()` lookup; runtime capacity assignment. Pure agent-runtime. |
| `fantasy_author/api.py` | 7 | REST surface: `POST /authors/{author_id}/run`, `GET /v1/authors/{author_id}`, body param `author_id`, `parent_author_id`. Exposes agent-runtime identity to clients. |
| `tests/test_author_server_api.py` | 4 | Exercises the same REST surface; `preferred_author_id`, `parent_author_id`. Agent-runtime. |
| `tinyassets/context/guardrails.py` | 1 | Docstring only: scope metadata field name. Agent-runtime (scope describes running daemon). |
| `tinyassets/context/compaction.py` | 1 | Docstring only: same. Agent-runtime. |
| `tinyassets/memory/tools.py` | 1 | Historical comment about Stage 2b collapsing `author_id` into `user_id`. Agent-runtime. |

### Content-authorship (-> keep `author_id`, add `author_kind` in Phase 3)

**None.** Grep of the live tree confirms:
- No `CREATE TABLE` for scenes / prose / chunks that carry an `author_id` column.
- No `.sql` artefacts reference `author_id` / `author_kind`.
- No scene-level row writer writes an `author_id` value.

Implication: the `author_kind` discriminator in Phase 3 (§1.5 schema shape) **has no current rows to backfill**. Add column + default value; leave migration idempotent; no DML required for existing data.

### Ambiguous

**None.**

### Excluded (by plan §2, not counted above)

- `fantasy_author_original/` — legacy package tree, scheduled for outright deletion in Phase 1 per host §9-B.
- `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/` — build-time mirror of `tinyassets/`, regenerated during packaging; renames land transitively once source is renamed.
- `docs/` historical specs + design notes — exclusion list §2.
- Git commit `author` field — exclusion list §2.

---

## 2. `fantasy_author_original/` live-import confirmation (plan §4 Phase 0)

- `from fantasy_author_original` / `import fantasy_author_original` — **zero matches** in the live tree.
- Only surviving reference is `scripts/resync_packages.py`, which uses the directory as a path literal (`ORIG = Path('.') / 'fantasy_author_original'`) to re-sync `tinyassets/` and `domains/fantasy_author/` with rewritten imports.

**Action required at Phase 1:** delete `scripts/resync_packages.py` alongside `fantasy_author_original/`. Host has already confirmed delete-with-no-safety-net in §9-B.

**Verdict: safe to delete in Phase 1. No runtime imports to fix.**

---

## 3. External-consumer identifier audit (plan §4 Phase 0)

Packaging surfaces checked:

| Surface | `author` occurrences | Semantics | Rename action |
|---|---|---|---|
| `packaging/mcpb/manifest.json` | `"author": { "name": "Jonathan Farnsworth" }` (L8) + marketing copy "autonomous Author daemons writing novels" (L7) | Package-metadata publisher field + user-visible brand copy. | Metadata `author` **stays** (publisher field, exclusion §2). Marketing copy "Author daemons" -> **Phase 4 brand pass**. |
| `packaging/registry/server.json` | `"description": ... "autonomous Author daemons ..."` (L5) | User-visible brand copy. | **Phase 4 brand pass.** No identifier rename. |
| `packaging/claude-plugin/.../plugin.json` | `"author": { "name": "..." }` (L5) | Package-metadata publisher. | **Stays** (exclusion §2). |

**Verdict: no external client consumes agent-runtime `author` identifiers today. Rename before distribution goes live is still the cheaper ordering.** One Phase 4 marketing-copy sweep covers "Author daemons" -> "Daemons" brand edits.

---

## 4. Compat flag (plan §4 Phase 0)

- Added `tinyassets/_rename_compat.py` with `rename_compat_enabled()` reading `TINYASSETS_AUTHOR_RENAME_COMPAT` (default on).
- Consumers wired in Phases 1-2 (shim `__init__.py` re-exports + module-level `Author = Daemon` aliases).
- Flag flips off + file deleted in Phase 5.

---

## 5. Scope freeze

Starting 2026-04-17 (Phase 0 land), any new `author_id` / `Author` / `author_server` additions between here and Phase 5 merge must use the new names (or be a documented content-authorship site, per plan §4 Phase 0).

---

## 6. Open blockers for Phase 1

1. **Host Q1** — out-of-band `fantasy_author/api.py` + `pyproject.toml` fastapi edits still uncommitted in tree. Phase 1 renames `fantasy_author/` wholesale; these local edits will move with the package but must be either committed or reverted before Phase 1 begins.
2. **Host Q2** — `echoes_of_the_cosmos` KG wipe vs preserve. Independent of rename, but if wipe happens it should land before Phase 3's schema migration for cleaner ID-prefix rewrites.

Neither blocks Phase 0 landing. Both block Phase 1 start.

# Author → Daemon Mass-Rename — Execution Plan

**Status:** Planner exec-plan, host §9 answers applied 2026-04-15. Promotion-ready; dev-2 (or fresh claim) implements.
**Related:** STATUS.md Work row "Author → Daemon mass-rename". Planner memory `project_terminology_daemon.md`, `project_daemon_product_voice.md`. Host greenlight 2026-04-15 with scope-expansion to user-facing brand.
**Scope:** Two concurrent shifts:
1. **Internal rename** — `daemon` replaces `author` as the agent identifier throughout code/tests/DB. Disciplined symbol shape: `daemon`, `daemon_id`, etc.
2. **User-facing brand pass** — UX copy leans *hard* into daemon vocabulary. Verbs matter: "summon a daemon," "bind a daemon to a universe." The host's viral-hook direction; see §"Brand voice" under Phase 4.

**Critical distinction retained:** humans can author content too (including human-assisted prose). `author_id` does NOT collapse into `daemon_id`. The agent-runtime concept becomes `daemon_id`; the content-authorship concept keeps `author_id` with a new discriminator — see §1.5.

## Goal

Two goals, in priority order:

1. **Ship "summon the daemon" as the user-facing brand** before external-user traffic arrives. Packaging is set "weeks not months" for distribution; UX copy is the highest-priority surface and the viral hook. Phase 4 is the brand pass, not a cleanup.
2. **Eliminate the agent-vs-authorship concept collision.** "Author" today silently covers both (a) the daemon-that-runs-work and (b) the human-or-daemon-that-authored-prose. Disentangle: `daemon_id` owns the agent runtime; `author_id` + `author_kind` discriminator owns content authorship with human-or-daemon resolution.

## 1. Rename glossary

The canonical mapping. Dev treats this as authoritative. Ambiguous cases land in §2.

| Old | New | Notes |
|---|---|---|
| `author` (free word) | `daemon` | Only when referent is the agent. See §2 for non-agent meanings. |
| `Author` (class/type) | `Daemon` | e.g. `class Author` → `class Daemon`. |
| `author_id` (agent-runtime column, field, variable) | `daemon_id` | DB migration; backfill existing rows. **Content-authorship `author_id` fields DO NOT rename — see §1.5.** |
| `author_definitions` (table — represents daemons) | `daemon_definitions` | DB migration. |
| `author_votes` (table — represents daemon forks/approval) | `daemon_votes` | DB migration. |
| `parent_author_id`, `child_author_id` (daemon lineage) | `parent_daemon_id`, `child_daemon_id` | DB migration. |
| `preferred_author_id` (user's preferred daemon) | `preferred_daemon_id` | DB migration. |
| `"author::..."` (slug prefix) | `"daemon::..."` | ID string prefix. Requires backfill OR accept-both strategy — see §4. |
| `_author_id_for` (function) | `_daemon_id_for` | |
| `ensure_default_author` | `ensure_default_daemon` | |
| `register_author` / `list_authors` / `get_author` | `register_daemon` / `list_daemons` / `get_daemon` | Public API rename — see §5 for back-compat alias window. |
| `author_server.py` (module) | `daemon_server.py` | Module-level rename; updates ~300 imports across repo. |
| `author_server_db_path` / `initialize_author_server` | `daemon_server_db_path` / `initialize_daemon_server` | |
| `fantasy_author/` (package) | `fantasy_daemon/` | Full package rename. ~2366 Python files reference the path in some form; most via `from fantasy_author.X import Y`. |
| `domains/fantasy_author/` | `domains/fantasy_daemon/` | Domain-specific sub-package. |
| `fantasy_author_original/` | **DELETE** | Per explorer scout (see §2), this is a legacy snapshot; confirm before delete. |
| `fantasy_author.pyw` / `tinyassets.pyw` | `fantasy_daemon.pyw` | Windows launcher. |
| `AUTHOR_*` env vars (if any) | `DAEMON_*` | Check `.env.example` if exists. |
| Error messages, docstrings, log strings saying "author" | "daemon" | User-visible strings FIRST priority (weeks-to-launch). |
| `docs/specs/**/*author*` (file names, TOC) | Leave historical specs; update *active* docs only. | Specs are historical record; renaming them rewrites history. |

## 1.5. Content-authorship disambiguation (host §9-A answer)

Humans can author content too, including human-assisted prose. The `author_id` field on content-authorship sites (scene records, prose chunks, claims attached to drafts) identifies **who wrote the content** — a human user or a daemon. This is distinct from `daemon_id`, which identifies **which agent-runtime is currently executing**.

### Option comparison

| Option | Shape | Pros | Cons |
|---|---|---|---|
| **1. `author_id` + `author_kind` discriminator** | `author_id TEXT, author_kind TEXT IN ('human','daemon')` on content rows | Single lookup column; clear discriminator; extensible to new kinds (system, co-author). Matches the `visibility` pattern (`goals.visibility`). | Requires downstream callers to always read the discriminator; wrong resolution silently credits a daemon as human or vice-versa. |
| **2. Mutually-exclusive `human_author_id` + `daemon_id` fields** | Two columns, exactly one non-NULL per row | Zero ambiguity in reads — you query the column you want. | Schema enforces XOR via CHECK constraint; every write site has to decide which column to set; adding a third "kind" (e.g. co-authored by both) requires another column. |
| **3. Generic `author_id` + separate `authors` registry table** | `author_id` stays a string; `authors(author_id, kind, display_name, ...)` resolves it | Most normalized; co-authorship extensible via join table; decouples attribution from runtime identity entirely. | Every read needs a join for basic attribution; slowest option; overkill today. |

### Pick: Option 1

**Option 1. `author_id` + `author_kind` discriminator.** Confidence: high.

Reasoning:
- Option 1 matches the idiom the codebase already uses (e.g. `goals.visibility` as a string discriminator). New readers see one column + one discriminator and understand the model.
- Option 2 looks cleaner for reads but has a fatal shape problem: human-daemon co-authorship is a plausible near-term shape (a daemon drafts, a human edits the draft — whose attribution wins?). Option 2 forces a binary choice at write time; Option 1 accommodates by adding `"co_authored"` to the discriminator later, with no schema change.
- Option 3 normalizes further but pays a join cost on every content read. The `authors` registry data lives naturally in `daemon_definitions` (for daemons) and `users` (for humans, once that table exists) — so Option 3 would be building a third registry to federate two that already exist. Unnecessary today.

### Schema shape

For any content-authorship site (starting with scenes; audit for others in Phase 0):

```sql
ALTER TABLE scenes ADD COLUMN author_kind TEXT NOT NULL DEFAULT 'daemon';
-- `author_id` keeps its existing shape and its values.
-- Resolution: if author_kind='human', author_id resolves against user registry.
--             if author_kind='daemon', author_id resolves against daemon_definitions.
```

Existing rows backfill `author_kind='daemon'` — consistent with current state where the daemon writes all prose. Future human-authored rows set `author_kind='human'`.

### Why this doesn't collapse `author_id` into `daemon_id`

The agent-runtime side (`author_definitions` table, `register_author` function, `preferred_author_id` setting) IS renamed wholesale to `daemon_*`. The content-authorship side (`author_id` column on scenes + similar) stays `author_id` and gains `author_kind`. The two concepts had been sharing a name; they don't share one any more.

### Audit list (Phase 0 deliverable)

Dev enumerates every `author_id` site in the codebase and classifies each as either:
- **Agent-runtime:** rename to `daemon_id`. (E.g. `goals.author`, `branch_definitions.author`, `preferred_author_id`.)
- **Content-authorship:** keep `author_id`, add `author_kind` discriminator. (E.g. scene records, if any.)
- **Ambiguous:** escalate to planner/host. Default to content-authorship on ambiguity (the safer classification — the data stays human-interpretable).

## 2. What does NOT get renamed (exclusion list)

- **Git commit author field** (`git log --author=`, `git commit --author=`). This is a git primitive, not the agent concept. Never touch.
- **Content-authorship fields on scenes / prose / claims.** `author_id` stays on content rows, paired with new `author_kind` discriminator (§1.5). Only the agent-runtime meaning gets renamed to `daemon`.
- **Historical specs and design notes** (`docs/specs/*.md`, `docs/design-notes/*.md` already landed). These are a record of what was decided when; renaming them is rewriting history. Dev edits only ACTIVE docs (`PLAN.md`, `AGENTS.md`, `STATUS.md`, live `docs/exec-plans/`, live `docs/specs/` for unfinished phases).
- **External package names** consumed from upstream libraries that happen to use "author." None known today; if found, leave alone.
- **Third-party SDK / API field names** (e.g. if any MCP tool response schema has an `author` field consumed by external clients). **Check each tool response shape in Phase 2.**

**`fantasy_author_original/` is NOT in the exclusion list — host confirmed DELETE in §9 answers.** See Phase 1 steps.

## 3. Rename surface scope (concrete counts)

From repo grep at 2026-04-15 (all excluding `__pycache__`):

- Total Python files with at least one match on `author|Author|author_id|author_server`: **1,189**.
- Python files mentioning `fantasy_author`: **2,366** (includes every import; most drive-by).
- Python files mentioning `author_server`: **299**.
- Python files with `\bAuthor\b` (class/type casing): **500**.
- SQLite tables affected (confirmed): **3** (`author_definitions`, `author_votes`, plus `author_id` column appears on at least `branch_definitions` and `goals` as FK).
- Test files affected: **all major test suites** (`test_author_server_api.py` is explicit; plus `test_branches.py`, `test_branch_definitions_db.py`, `test_community_branches_phase*`, etc).
- Documentation: ~30 docs files mention the term in content.
- Module root surfaces: `tinyassets/author_server.py` (2600+ lines), `fantasy_author/` package (32 files), `domains/fantasy_author/` (subpackage), `fantasy_author_original/` (legacy).

**This is a 1000+ file diff.** Treat it as a landing risk commensurate with a full phase shift, not a cleanup commit.

## 4. Phased landing strategy

Ship in 5 phases. Each phase is independently mergeable and leaves the repo in a working state. No phase is abandonable mid-way.

### Phase 0 — Preflight (1 commit, ~0.5 day)

**Goal:** establish the move is safe and remove blockers.

- **Classify every `author_id` site** into agent-runtime (→ rename `daemon_id`) vs content-authorship (→ keep `author_id`, add `author_kind` in Phase 3) vs ambiguous (→ escalate). Produce a short audit list committed to the plan thread. This is §1.5's audit deliverable; dev owns it.
- Confirm `fantasy_author_original/` has zero live imports. Grep: `from fantasy_author_original` + `import fantasy_author_original`. If zero: proceed. If non-zero: fix the imports first (they shouldn't exist). **Host-confirmed delete; no safety net.**
- Confirm no external consumer depends on current user-visible identifiers. Packaging surfaces (`packaging/mcpb/manifest.json`, `packaging/registry/server.json`, `packaging/claude-plugin/.../plugin.json`) — check if any string field names or IDs say "author" and are consumed by clients. Per planner memory + STATUS direction, packaging is weeks from user traffic; renaming before distribution goes live is the cheaper order.
- Add `TINYASSETS_AUTHOR_RENAME_COMPAT` flag (default `on`) — re-exports old names from new modules during the transition. Flag flips to `off` in Phase 5. Keeps third-party scripts / user tooling from breaking mid-rename.
- Freeze the rename scope. Any `author_id` / `Author` / `author_server` additions between Phase 0 and Phase 5 merge must use the new names (or be a documented content-authorship site).

### Phase 1 — Module + package rename (1-2 commits, ~1 day)

**Goal:** physical file moves. No API changes yet.

- `fantasy_author/` → `fantasy_daemon/` (full `git mv` of the package tree).
- `domains/fantasy_author/` → `domains/fantasy_daemon/` (full move).
- `tinyassets/author_server.py` → `tinyassets/daemon_server.py`.
- `fantasy_author/__init__.py` gets a back-compat shim: `from fantasy_daemon import *` (enabled by `TINYASSETS_AUTHOR_RENAME_COMPAT`). Same for `tinyassets/author_server.py` → shim to `workflow.daemon_server`.
- **Delete `fantasy_author_original/` outright** (host-confirmed §9-B, zero safety net). Include the `rm -rf` in this phase's commit. Phase 0 already confirmed zero live imports; no rollback planned.
- Rename `fantasy_author.pyw` → `fantasy_daemon.pyw`.
- Run `pytest` — should pass because shims re-export. Run `ruff check` — should pass.
- **Test gate:** the full suite runs green with shims in place.

### Phase 2 — Identifier rename inside new modules (3-5 commits, ~2 days)

**Goal:** rename classes / functions / variables WITHIN the renamed modules. Old identifier names get aliased at module level for back-compat.

- `class Author` → `class Daemon`; add `Author = Daemon` alias guarded by flag.
- Function renames (`register_author` → `register_daemon`, etc). Each gets an alias.
- Internal variable/argument renames (e.g. `author_id: str` → `daemon_id: str` in function signatures). This is the big boring find-replace. Recommend: one commit per subsystem (daemon_server, branches, memory, retrieval, runtime).
- Update all call sites WITHIN the repo to use new names. The flag-gated alias covers any missed site.
- **Test gate:** full suite green at each sub-commit. Ruff green.
- **Trap:** `author_id` appears as a column name in SQL strings. Leave column SQL alone in this phase — DB rename is Phase 3. But the Python variable holding the column value gets renamed to `daemon_id`. The SQL reads/writes look awkward temporarily (`daemon_id = row["author_id"]`) — that's fine; fixed in Phase 3.

### Phase 3 — Database schema rename (1-2 commits, ~1-1.5 days)

**Goal:** rename DB tables, columns, and ID-prefix strings. Migration is the critical path.

- ALTER TABLE: `author_definitions` → `daemon_definitions`; `author_votes` → `daemon_votes`.
- ALTER COLUMN: `author_id`, `parent_author_id`, `child_author_id`, `preferred_author_id` → `daemon_*` **on agent-runtime tables only** (per the Phase 0 audit from §1.5). SQLite doesn't support ALTER COLUMN; use the standard "create new table, INSERT SELECT, drop old, rename" pattern. Keep the migration idempotent.
- **Content-authorship tables (scenes, prose chunks, etc.):** `author_id` column KEEPS ITS NAME. Add `author_kind TEXT NOT NULL DEFAULT 'daemon'` column. Backfill all existing rows to `author_kind='daemon'` (current state). Future human-authored rows set `'human'`. Per §1.5.
- ID string prefix migration: existing rows have IDs of shape `"author::slug::hash"`. Decision point:
  - **Option A — backfill in-place:** UPDATE all ID values, changing `author::` prefix to `daemon::`. Breaks any external reference to the old ID. Cheaper long-term.
  - **Option B — accept-both:** new IDs get `daemon::` prefix; old IDs stay. Add a tolerant match helper `_normalize_daemon_id(raw)` that strips either prefix. More complex, never-ending compat tax.
  - **Recommendation: Option A.** External IDs are not distributed (no public API using them yet). Backfill once, clean forever. Ship it in the same migration as the schema ALTER.
- Update SQL strings in Python to reference new column names.
- **Test gate:** full suite green. Fresh-DB test creates new schema; upgrade test verifies migration from old schema.

### Phase 4 — User-facing BRAND PASS (2-3 commits, ~1.5 days)

**Goal:** this is NOT a find-replace cleanup. This is the viral-hook phase. Host direction (2026-04-15): "the daemon terminology is something we want to lean into for the user experience as it is the nerdy kind of thing that could go viral, summoning the daemon."

Copy is evocative, not sanitized. Internal symbols stay disciplined (`daemon`, `daemon_id`); external-facing copy uses richer vocabulary that maps back unambiguously.

### Brand voice

**Verbs that should appear in user-visible copy:**
- **summon** — "Summon a daemon," "Summoning the market-analysis daemon…" (not "create," "start")
- **bind** — "Bind this daemon to your research universe" (not "configure," "set up")
- **roam** — "Daemons roam the universe's canon for relevant facts" (not "query," "retrieve")
- **return** — "The daemon returns with its findings" (not "completes," "finishes")
- **dismiss** — "Dismiss the daemon" (not "stop," "kill")
- **entrust** — "Entrust the daemon with a task" (not "assign," "give")

**Noun patterns:**
- "your daemon" > "the daemon instance"
- "a universe" > "a workspace"
- "canon" > "knowledge base" (within the brand; keep "knowledge base" for technical docs where precise)
- "soul" > "configuration" (for soul-files)
- "summoning" > "initialization"

**Tone:** nerdy, slightly mythic, self-aware. The vocabulary is load-bearing on the viral hook; the user should feel like they're doing something a little occult and a little powerful.

**Lines that translate well:**
- Before: "Create a new author and assign it to a universe."
- After: "Summon a new daemon and bind it to a universe."

- Before: "Author registered successfully."
- After: "The daemon has been summoned."

- Before: "No authors available. Configure one to start."
- After: "No daemons summoned yet. Summon your first daemon to begin."

- Before: "Failed to start author process."
- After: "The summoning failed. (Check that the universe exists and try again.)"

### Scope (files + surfaces)

**MCP tool descriptions** (visible inside Claude.ai and other MCP clients — HIGHEST priority):
- `tinyassets/universe_server.py` — every tool's description string, parameter descriptions, example response copy.
- `tinyassets/daemon_server.py` — same.
- `packaging/mcpb/manifest.json` — bundle description, tool descriptions visible in install UI.
- `packaging/claude-plugin/.claude-plugin/marketplace.json` — plugin marketplace copy.
- `packaging/claude-plugin/plugins/tinyassets-universe-server/.claude-plugin/plugin.json` — plugin description.
- `packaging/registry/server.json` — MCP Registry listing copy (desc, title if needed).

**User-facing docs (external entry points):**
- `README.md` — top-level project pitch. This is where "summoning daemons" lives in the first paragraph.
- `INDEX.md` — repo map; brand matters for the first-time reader.
- `packaging/PACKAGING_MAP.md`, `packaging/INDEX.md`, `packaging/mcpb/README.md`, `packaging/claude-plugin/README.md` — install/setup narrative.
- `docs/mcpb_packaging.md`, `docs/distribution_validation.md` — adjacent to install copy.
- Any onboarding / setup text the user encounters on first launch (check `packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/bootstrap.py` for first-launch messages).

**User-facing error messages:**
- Every `raise ValueError(...)` / `raise RuntimeError(...)` inside `tinyassets/universe_server.py` and `tinyassets/daemon_server.py` that can surface to an MCP client.
- Any MCP tool response `message` / `error` / `note` strings.
- Log strings that show up in MCP client-visible surfaces (daemon_overview, status responses).

**Internal docs (voice-adjusted, not brand-rewritten):**
- `AGENTS.md`, `PLAN.md`, `STATUS.md` active sections — use "daemon" consistently but these are internal; no "summoning" mysticism required. Precise technical voice stays.
- `LAUNCH_PROMPT.md`, `CLAUDE.md`, `CLAUDE_LEAD_OPS.md` — agent-facing; "daemon" vocabulary fine, brand voice optional.
- `.claude/agents/*.md` — agent definitions; "daemon" replaces "author" where relevant.
- **Historical specs** (`docs/specs/*.md`, `docs/design-notes/*.md` already landed): unchanged. Historical record.

**Marketing-adjacent copy (future viral push):**
- No landing page or announcement text exists in the repo today (checked). If a `docs/launch/` or `marketing/` directory appears before Phase 4 lands, escalate to host for brand-voice review.
- A single launch-tweet / announcement draft file would help lock the voice for consistency; recommend host drafts this and drops a reference in `docs/launch/` if they want it in-repo.

**MCP tool response FIELD names** (schema-breaking):
- Check each tool response in `tinyassets/universe_server.py` for fields literally named `author` (vs `author_id`).
- Rename to `daemon_id` and document the break. No distribution yet = no external consumers to break.

### Test gate

- Docstring tests pass (if any assert on tool-description content, update the assertions).
- Example-output fixtures pass.
- **Manual smoke test:** install the packaged bundle into Claude.ai, invoke a tool, read the response. Does the copy feel "summoning a daemon," or "configuring an author"? If the latter, Phase 4 isn't done.

### Phase 5 — Remove shims + flag flip (1 commit, ~0.5 day)

**Goal:** finalize. Delete compat shims, remove the flag.

- Delete `fantasy_author/__init__.py` shim file + `tinyassets/author_server.py` shim.
- Remove `Author = Daemon` aliases from classes.
- Remove `_normalize_daemon_id` if Phase 3 chose Option A.
- Flip `TINYASSETS_AUTHOR_RENAME_COMPAT` to default `off`, document in release notes.
- Delete the flag entirely after one release cycle passes.
- Final `ruff check` + `pytest` — the repo should have zero "author" references outside the §2 exclusion list, content-authorship sites (§1.5), and historical docs.
- Grep the repo for stragglers: `grep -rn "author" --include="*.py" | grep -v "# git-author-ok" | grep -v "author_kind\|author_id"` → review hits, fix any. (Content-authorship `author_id`/`author_kind` is expected and kept.)

### Landing cadence

- Phases 0-5 ship as separate commits, ideally separate PRs or at least reviewable chunks.
- Between any two phases, the repo compiles, tests pass, ruff passes, daemon runs.
- Rollback at any phase: revert the phase's commits. Shim design means partial-state isn't user-visible.

## 5. Risk assessment

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Missed call site breaks production daemon | Medium | High | Shim-based back-compat in Phases 1-4; Phase 5 is the only "no shim" moment and comes after full test pass. |
| DB migration fails on live universes with populated data | Medium | High | Migration is idempotent + transactional. Backup `.author_server.db` before running (trivial file copy). Test on a fixture DB with real data shape first. |
| Phase 2 find-replace hits false positives (SQL strings, git author fields, prose content) | High | Low-medium | Do find-replace subsystem-by-subsystem, NOT repo-wide. Each subsystem commit gets a reviewer pass specifically for false positives. Exclusion list §2 documents what to leave. |
| Historical docs start contradicting active code | Certain | Low | Expected and accepted. Historical specs are records; they describe what WAS decided. Active docs (PLAN.md, AGENTS.md, STATUS.md) are the truth going forward. |
| External tooling (user scripts, MCP clients) breaks on tool-response field rename | Low | Medium | No distribution yet. Document breaking change in release notes; no back-compat commitment pre-launch. |
| Merge conflicts with in-flight work (Path A visibility, queue_cancel, packaging Option 1) | High | Medium | **Sequence matters.** Land active in-flight Work rows FIRST; this rename merges AFTER them. Rename is the last-mover because 1000-file diffs lose every conflict. |
| `author_id` as SQL column colliding with `daemon_id` mid-migration | Medium | Medium | Phase 2 and Phase 3 are intentionally separated: Python identifiers first, DB columns second. Mid-phase code has awkward `daemon_id = row["author_id"]` reads; that's temporary and tested. |
| Regression in tests that relied on identifier names in assertions (`assert x.author_id == ...`) | High | Low | Tests get updated in each phase along with the code they test. Run suite after every subsystem commit. |

## 6. Sequencing against other in-flight work

Per current STATUS.md Work rows (2026-04-15 snapshot):

- `#56 Path A — Branch visibility column` (dev-2) → land FIRST. Touches `tinyassets/author_server.py` schema. This rename consumes its schema change cleanly.
- `Phase E queue_cancel graph interrupt` (dev) → land FIRST or IN PARALLEL on non-overlapping files. Check collision before starting.
- `Packaging Option 1` (dev-2, pending) → land IN PARALLEL. Packaging touches `packaging/` + `scripts/` + build config, not the rename surface. Low collision.
- `Memory-scope Stage 2` (blocked:host) → land AFTER the rename if possible. The tiered scope design introduces `user_id`, `goal_id`, etc — it'd be nice if `author_id`→`daemon_id` had already happened so Stage 2 doesn't have to cite both names.

**Recommended order:** Path A → this rename → Memory-scope Stage 2. Packaging Option 1 runs independent of all three.

## 7. Success criteria

- Zero Python files contain `author|Author|author_id|author_server` outside §2 exclusions (git author field, historical docs, document-authorship fields for scenes).
- Zero DB tables or columns contain "author" in their names.
- Zero user-visible strings (tool docstrings, error messages, MCP response field docs) contain "author" in the agent sense.
- Full test suite green. Ruff green. Daemon starts, connects via MCP, writes to SQLite.
- Release notes contain a clear "Breaking: `Author`→`Daemon` rename" section.
- `TINYASSETS_AUTHOR_RENAME_COMPAT` flag removed from the codebase.

## 8. Effort estimate

**Total: ~7-8 dev days** (revised from 6-7 after §9-A/C scope expansion). Phase breakdown:
- Phase 0: 0.5-1 day (scouting + author_id audit classification + flag add).
- Phase 1: 1 day (package moves + shims + `fantasy_author_original` delete).
- Phase 2: 2 days (identifier rename, per-subsystem commits; agent-runtime sites only).
- Phase 3: 1.5 days (DB migration: agent-runtime ALTER + content-authorship ADD `author_kind` + ID prefix backfill).
- Phase 4: **1.5 days** (brand pass, up from 1 day; iterative smoke test in Claude.ai before declaring done).
- Phase 5: 0.5 day (shim deletion + flag flip).

Sequential by design — no phase parallelizable except Phase 2 subsystems within a single dev. Two devs on this would save maybe 1 day total, not worth the coordination cost.

## 9. Host-answered (2026-04-15)

### 9.A Scene `author_id` disambiguation — ANSWERED

**Humans can author content too, including human-assisted work.** Do NOT collapse `author_id` into `daemon_id`. Handle with `author_id` + `author_kind: 'human' | 'daemon'` discriminator (Option 1 of three considered; tradeoffs in §1.5). Content-authorship sites keep the `author_id` column; agent-runtime sites rename to `daemon_id`. Dev's Phase 0 audit classifies each site.

### 9.B `fantasy_author_original/` deletion — ANSWERED

**Delete. No safety net required.** Folded into Phase 1. Phase 0 verifies zero live imports before the delete commit runs; if any import exists, that's a bug to fix first (not a reason to retain the dir).

### 9.C User-facing labels — ANSWERED + SCOPE EXPANSION

**Labels change AND user copy leans into daemon vocabulary as a viral hook.** Phase 4 is a BRAND pass, not a cleanup. "Summon the daemon" as the core verbal shape; internal symbols stay disciplined, external copy is evocative. Full scope + voice guide in Phase 4 above.

Escalations:
- If `docs/launch/` or marketing-adjacent copy appears before Phase 4 lands, loop back to host for brand review.
- UI string for the fantasy domain: "Fantasy Authoring" (the activity the user performs, still using "authoring" in its literal sense) is distinct from the module name `fantasy_daemon` (the daemon-of-fantasy-work). Confirm with host during Phase 4 if ambiguity surfaces.

## 9.2 Still open (lower-priority)

1. **`TINYASSETS_AUTHOR_RENAME_COMPAT` flag removal timeline**: delete in the same release as Phase 5, or keep one release for grace? Recommend: same release, no distribution yet = no external scripts to grandfather.
2. **ID-prefix backfill (Phase 3 Option A vs B)**: confirm Option A (backfill once) is acceptable. If any user has IDs stashed in external tools, Option B is safer; if not, Option A is cleaner.
3. **`author_kind` values enum boundary**: start with `'human' | 'daemon'`. Third value candidates: `'system'` (for automated ingest that's neither human nor a registered daemon), `'co_authored'` (human+daemon). Recommend: start with the two, add as concrete need surfaces.

## 10. PLAN.md alignment

- **§Daemon-Driven** (PLAN.md L120): core principle. The rename makes the code match the principle.
- **§Multiplayer Daemon Platform** (L102): "Daemons are public, forkable, summonable agent identities defined by soul files." Current code says "Author" in exactly the places this sentence says "Daemon." The code-docs mismatch breaks reader trust; the rename closes it.
- No principle conflict. Every other PLAN.md section is unaffected.

Promotes to dev-2 (or claimer) after host resolves §9 Qs 1-5.

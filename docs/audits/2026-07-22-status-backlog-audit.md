<!--
Provenance: carried verbatim from `output/s2-gate/status-backlog-audit.md` (lane report,
2026-07-21 13:11). The lane produced this report but never opened a PR, so it
existed only on disk. Body below is the report unmodified; only this
comment was added.
-->

Audit complete across all 19 rows. Every verdict below rests on first-hand code/git evidence I reproduced.

# STATUS.md Work-table audit — 19 rows

**Headline: 9 of 19 rows (47%) are landed or inverted.** The five caught today were not bad luck — they were the visible part. Independently, my community-pool finding converged exactly with the earlier lane's reasoning (`ecad62f2`), which is corroboration rather than coincidence.

## INVERTED — traps ranked first (would cause harm if built)

**1. `#24 Arc C` — env-var deprecation aliases** (line 44)
`1ae48ef` (2026-04-29, **ancestor of main**) is literally *"refactor: remove author rename compatibility shims"*. `tinyassets/_rename_compat.py` does not exist. `tinyassets/storage/__init__.py:270` reads only canonical `TINYASSETS_WIKI_PATH`.
**Harm:** re-introduces shims deleted on purpose 83 days ago, violating the active no-shims-ever directive. Its `Depends: #25` points at an already-merged row, so the dependency gate that should have blocked it is itself dead.

**2. Phase 6 — `.workflow.db`** (line 45)
Landed `20047d1d` (2026-05-01, ancestor of main); `db_path()` lives at `tinyassets/storage/__init__.py:355`. **The row's target filename is itself superseded** — `DB_FILENAME = ".tinyassets.db"` (`storage/__init__.py:46`) since rename `89edf995` (2026-06-26).
**Harm:** building it as written renames the DB *to* `.workflow.db` — the exact filename whose missing migration link silently stranded every universe booted 2026-05-01..06-26 (`a9334190`). The row doesn't just describe stale work; it prescribes re-creating the data-loss bug.

**3. `TINYASSETS_REPO_ROOT` community-pool** (line 50)
`goal_pool.py:117` does `Path(env).expanduser().resolve()` — non-strict, cannot raise. Both catch sites (`universe.py:3365`, `:3471`) only catch `RuntimeError`, so `repo_root_not_resolvable` is unreachable while the env var is set. **Proven empirically** in a scratch script outside the repo:
```
A PASS: repo_root_path returned ...\ta-does-not-exist-xyz\community-pool (NO RuntimeError)
B PASS: write_pool_post created ...\goal_pool\g1\bt_...yaml (exists=True); dir was auto-made
```
**Harm:** *both* prescribed fixes are wrong. "mkdir scaffold" is already performed by `write_pool_post`'s `mkdir(parents=True, exist_ok=True)`; "drop the env" would actually *change* behavior by falling back to git-detect.

**4–5. Windows backup.sh path fix / Clean-clone MCP config mismatch** (lines 47, 48)
Neither failure reproduces: **53 passed, 2 skipped**. The 2 skips are `shellcheck not installed` (`test_backup_script.py:105,114`) — not a Windows path bug, not a config mismatch.
**Harm:** an agent "fixing" a passing test edits working code to chase a phantom, and the real defect (vacuity) stays masked.

## LANDED — delete, commit named

| Row | Commit | Evidence |
|---|---|---|
| **in-node enqueue ADAPT** (38) | `6d0e6898` 2026-06-02 (#1221), ancestor of main | All three asks at `graph_compiler.py:1418-1600`; docstring names them "(Fix 1)"/"(Fix 2)"/"(Fix 3)". 20 tests pass. |
| **`#23` Arc B phase 2** (42) | `c967272` 2026-04-29, ancestor of main | Marked `host-review` for **83 days** on already-merged code. |
| **`#25` Arc B phase 3** (43) | `1ae48ef` 2026-04-29, ancestor of main | Files cell names 3 paths that don't exist on disk. |
| **`run_branch resume_from`** (46) | `b7300bb7` 2026-05-01 | `runs.py:591-722`, 5 failure classes implemented. |

Caveat on 38: the flag still ships dark by design (`_node_enqueue_enabled()`, `graph_compiler.py:1337`). The row's *stated prerequisites* are done; "flip the flag" is a separate host decision.

## LIVE — but already built on unmerged branches

This is the second systemic failure: **five completed fix branches from today are invisible to `claim_check.py`.**

- **L4 reducer law** (39) — defect confirmed live: `_dict_merge` still shallow right-biased at `graph_compiler.py:371-375`, plugin mirror identical at `:371`, **no test references it**. Work complete on `origin/fix/l4-reducer-law` (`fccf490b`).
- **Card-matcher** (49) — 7 tests pass; contract genuinely ambiguous (`claude_chat.py:221,518,526,793`). `origin/fix/card-matcher-fallback` (`dcad9a73`) found a **security defect the row never mentions**: the probe could auto-grant *third-party* connectors.
- **Paid-market Track E** (37) — drifted. `assert_drained` (`ledger.py:103`) and `best_execution` (`match.py:61`) already exist; `market.apply_tx` doesn't exist under that name (it's `Ledger.apply`, `ledger.py:84`); Files cell is wrong — migrations 006–008 live in `prototype/full-platform-v0/migrations/`. No `schema_migrations` table exists anywhere. Adapters + renumbering are genuinely unbuilt.

## UNVERIFIABLE — need evidence before anyone builds

| Row | What's checkable | What isn't |
|---|---|---|
| External directory (40) | proof docs exist, all dated 2026-05-02 | canary claim is **80 days stale**; first-user evidence is live-only |
| OpenAI submission (41) | `chatgpt-app-submission.json` + 5 docs, all 2026-05-02 | whether submission occurred is external |
| Mark-branch canonical (51) | `set_canonical` plumbing at `canonical_dispatch.py:165` | live-MCP state |
| BUG-018 (52) | `116a657c` 2026-04-27 "fix BUG-003 + BUG-018 canonical resolution" landed — **likely already moot** | needs one live wiki read to confirm |
| DR drill #3 (53) | workflow exists; untouched since rename | no drill record found |
| ChatGPT re-register (54) | — | OpenAI workspace admin |
| Memory-scope 2c (55) | gate stamped `95b05f1d` 2026-05-01 → 30d elapsed **2026-05-31, 81 days ago** | but `ce5e6d16` (2026-06-30) touched memory-scope ACLs, arguably resetting the clock to 2026-07-30. Someone must state which clock governs. |

## Proposed replacement Work table

Delete 9 rows outright (38, 42, 43, 44, 45, 46, 47, 48, 50). Replace with:

```markdown
| Task | Files | Depends | Status |
|------|-------|---------|--------|
| **Merge queue — 5 completed fix branches (2026-07-21) unmerged + invisible to claim_check**: fix/l4-reducer-law fccf490b; fix/test-surface-repair 54c958a7; fix/card-matcher-fallback dcad9a73 (security: probe auto-granted 3rd-party connectors); fix/repo-root-community-pool ecad62f2; feat/phase6-workflow-db a9334190 (data-loss, universes booted 05-01..06-26) | per-branch | - | host-review |
| **P1 data-loss** — universes booted 2026-05-01..06-26 carry `.workflow.db`, invisible to the migrator; db_path() creates a fresh empty DB. Fix ready on origin/feat/phase6-workflow-db | tinyassets/storage/__init__.py + plugin mirror | merge queue | host-review |
| Paid-market Track E Wave 2 — adapters + migration renumber + schema_migrations table. NOTE: assert_drained (ledger.py:103) + best_execution (match.py:61) EXIST; `market.apply_tx` is `Ledger.apply` (ledger.py:84); migrations are in prototype/full-platform-v0/migrations/ | prototype/full-platform-v0/migrations/, tinyassets/paid_market/ | - | pending |
| In-node enqueue flag flip — containment LANDED 6d0e6898; ships dark by design (graph_compiler.py:1337). Enable = host call | TINYASSETS_NODE_ENQUEUE_ENABLED | - | host-decision |
| RFC 9728 discovery non-conformant — resource https://tinyassets.io/mcp requires /.well-known/oauth-protected-resource/mcp; code mounts /mcp/.well-known/... (wellknown.py:125, middleware.py:113). Codex-reported, code confirmed, live 404 UNVERIFIED | tinyassets/auth/wellknown.py, middleware.py | - | pending |
| Vector retrieval scope filter skipped when tag_query is None (router.py:323-329) — Codex-reported cross-universe leak; code shape confirmed, diagnostic NOT reproduced by me | tinyassets/retrieval/router.py, tests/ | - | pending |
| External directory acceptance — canary evidence 80d stale (2026-05-02); needs fresh probe + first-user evidence | packaging/registry/server.json, docs/ops/mcp-* | - | host-action |
| OpenAI app submission — artifacts on disk dated 2026-05-02; submission status external | chatgpt-app-submission.json, docs/ops/openai-app-submission-* | clean ChatGPT proof | host-action |
| BUG-018 trailing-hyphen — likely MOOT: 116a657c (2026-04-27) fixed BUG-003+BUG-018 canonical resolution. Needs one live wiki read to close | wiki | - | host-decision |
| Memory-scope Stage 2c — 30d gate stamped 95b05f1d (2026-05-01) elapsed 81d ago, BUT ce5e6d16 (2026-06-30) touched memory-scope ACLs. Which clock governs? | - | host call on clock | host-decision |
| Mark-branch canonical decision (Task #33 phase 0) | live MCP `goals action=propose/bind/set_canonical` | host | host-decision |
| Fire DR drill #3 via workflow_dispatch — no drill record found | `.github/workflows/dr-drill.yml` | - | host or lead-with-PAT |
| Host-action: re-register `TinyAssets DEV` ChatGPT connector as workspace admin | OpenAI workspace admin | - | host-action |
```

**Structural recommendation (beyond the table):** two mechanisms failed here. Rows carry a *filed* date but no *verified* date (the Concerns section requires `[filed: verified:]`; the Work table doesn't), and `claim_check.py` reads only STATUS.md, so five branches of finished work were invisible. Extending the Concern date-stamp convention to Work rows, and teaching `claim_check.py` to cross-reference unmerged branches, would have caught most of today's five.

---

`VERDICT: audit complete — 5 inverted, 4 landed, 3 live-but-already-built, 7 unverifiable.`

**What I built:** nothing. Per the brief this was an audit; deliverable is this report plus the proposed table above. I did **not** edit STATUS.md, AGENTS.md, PLAN.md, or REFLECTION.md. No commits, no pushes, no branch switches. `git status --porcelain` is empty — the tree is unmodified.

**Verbatim RED:** none — I wrote no tests. **Mutations:** none — I asserted nothing security-related that needed mutation-proving. The one empirical probe I ran (`repo_root_path` / `write_pool_post`) was written and executed in `%TEMP%`, outside the repo, and deleted afterward; its output is quoted verbatim above.

**Exact commands + counts:**
- `pytest tests/test_node_enqueue_verb.py tests/test_node_enqueue_concurrency.py` → **20 passed**
- `pytest tests/test_backup_script.py tests/test_mcp_server.py` → **53 passed, 2 skipped** (both skips: `shellcheck not installed`)
- `pytest tests/test_claude_chat_inline_dismiss.py` → **7 passed**
- `ruff check --target-version py311 .` → **166 errors, all pre-existing baseline debt** (tree unmodified by me; I neither fixed nor suppressed any)

**Found but NOT fixed:**
1. The P1 `.workflow.db` data-loss fix (`a9334190`) is **not on main** — it sits on `origin/feat/phase6-workflow-db`. Live universes booted 2026-05-01..06-26 remain exposed.
2. Four other completed fix branches are unmerged and invisible to `claim_check.py`.
3. Codex's two most serious findings (RFC 9728 discovery path; vector-retrieval scope bypass) — I confirmed the **code shape** at `wellknown.py:125` / `middleware.py:113` and `router.py:323-329`, but I did **not** reproduce Codex's live 404 or its cross-universe leak diagnostic. Treat as pending, not confirmed.

**Cross-family gate — honest status:** I dispatched Codex twice and **neither run adjudicated my claims**. Run 1 returned `VERDICT: reject` ("no review target") because an audit produces no diff. Run 2 returned `VERDICT: adapt` but audited the OpenSpec baseline specs instead of my 8 numbered items — useful independent signal (items 1–2 above), but *not* verification of this audit. My verdicts therefore rest on my own first-hand, reproducible code and git evidence, not on a passed cross-family gate. I'd rather say that plainly than let an unrelated `adapt` read as endorsement.

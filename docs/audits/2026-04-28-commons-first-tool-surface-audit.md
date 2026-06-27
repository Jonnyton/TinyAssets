---
title: Commons-first tool-surface audit — running the 5 foundational principles against the live primitive set
date: 2026-04-28
author: navigator
status: read-only discovery audit — host curates dispatch
companion:
  - project_minimal_primitives_principle (lead memory) — fewest building blocks
  - project_community_build_over_platform_build (lead memory) — community evolves features
  - project_commons_first_architecture (lead memory) — public commons + host-resident private
  - project_privacy_via_community_composition (lead memory) — privacy is community-composed
  - project_user_capability_axis (lead memory) — browser-only vs local-app, Claude vs OpenAI vs OSS
  - docs/audits/2026-04-26-legacy-branding-comprehensive-sweep.md (sibling: branding hygiene)
  - docs/audits/2026-04-26-architecture-edges-sweep.md (sibling: architecture edges)
load-bearing-question: For each existing tool/action surface, does it pass the irreducibility test (could it be composed from a smaller primitive set), the commons-first test (does it respect public-commons + host-resident-private boundary), and the user-capability test (does it work across browser-only and local-app users)?
audience: lead, host
---

# Commons-first tool-surface audit

## TL;DR

The platform's **public** tool surface is small (6 MCP tools) — that's GOOD against minimal-primitives. The **internal action verb surface is large** (~70 verbs across the 6 tools) and is where convenience-creep risk concentrates.

| Finding class | Count | Headline |
|---|---|---|
| **PRIMITIVE — earns its keep** | ~38 verbs | Core CRUD, run lifecycle, wiki write/read, paid-market settlement, attribution. |
| **CONVENIENCE-COMPOSABLE — chatbot can build** | ~18 verbs | Helper rollups, named queries, status-formatters that the chatbot can reconstruct from primitives in <5 reasoning steps. |
| **PRIMITIVE-GAP — flag for spec** | 3 verbs | Composition is structurally fragile (missing primitive earns a scope). |
| **COMMONS-LEAK-RISK — verify principle compliance** | 2 surfaces | `add_canon_from_path` + private universe state both blur the commons-vs-host-resident line; need explicit principle annotation. |
| **DUPLICATE-LEGACY-SURFACE — collapse** | 1 module | `tinyassets/mcp_server.py` ships **12 single-purpose stdio tools** that duplicate subsets of the 6 streamable-http canonical tools. |

**Headlines:**

1. **`tinyassets/mcp_server.py` is a primitive-set violation.** It exposes 12 separate single-purpose tools (`get_status`, `add_note`, `get_premise`, `set_premise`, `get_progress`, `get_work_targets`, `get_review_state`, `get_chapter`, `get_activity`, `pause`, `resume`, `add_canon`) where the canonical 6-tool surface (`universe`, `extensions`, `goals`, `gates`, `wiki`, `get_status`) covers the same capabilities. **Per minimal-primitives + commons-first, retire `mcp_server.py` toward a thin adapter that delegates to the canonical 6-tool surface.** Ship blocker check: any active stdio client still requires single-purpose tools? If no → retire.
2. **The Recency + continue_branch checkpoint applies here.** Both were host-approved 2026-04-26 BUT `project_minimal_primitives_principle` flags them for re-test under the principle. This audit recommends running the irreducibility-test BEFORE dev implements them.
3. **`add_canon_from_path` is a commons-first edge case.** Pulls bytes from host-local filesystem into a universe. If the universe is public-commons, that path leaks private host content into the platform commons. The `TINYASSETS_UPLOAD_WHITELIST` env var is the existing primitive guard — but the principle compliance is implicit. Recommend explicit annotation: "this verb is the commons/host-resident boundary; chatbot is required to decide visibility per-piece per `project_privacy_per_piece_chatbot_judged`."
4. **18 verbs are convenience-composable.** Each represents 5-15 minutes of platform code that could retire in favor of a wiki composition-pattern page. Net tool-surface budget: ~70 → ~52, principle-aligned.
5. **The 6-tool public surface itself is healthy.** No public-tool-level finding. The work is in pruning action verbs and collapsing the stdio shim.

---

## 1. Methodology

### Tests applied per verb

**T1 — Irreducibility test** (per `project_minimal_primitives_principle`):
- Could a competent chatbot reliably compose this verb's behavior from existing primitives in **<5 reasoning steps**?
- If YES → CONVENIENCE-COMPOSABLE. Document the composition pattern in a wiki page; retire the verb.
- If NO and the gap is structurally impossible (no primitive combination produces this behavior) → PRIMITIVE-GAP. Flag for scope.
- If NO and the verb IS the irreducible building block → PRIMITIVE.

**T2 — Commons-first test** (per `project_commons_first_architecture`):
- Does this verb's read/write path respect the public-commons + host-resident-private boundary?
- If it stores user content on the platform: is that content public-commons-by-construction (per the architecture) or does it carry implicit privacy?
- If it reads host-local data: is the host/commons boundary explicit?

**T3 — User-capability test** (per `project_user_capability_axis`):
- Does this verb work for browser-only users (Claude.ai web, ChatGPT web, OSS clients) AS WELL as local-app users?
- A verb that requires local filesystem or local subprocess is browser-incompatible — is the cloud-mediated alternative ready, or is this a tier gap?

### Surface inventory

**Public MCP tools (streamable-http canonical):** 6 — `universe`, `extensions`, `goals`, `gates`, `wiki`, `get_status` (per `tinyassets/universe_server.py`).

**Internal action verbs:**
- `universe`: 27 verbs (universe-level operations: list, inspect, switch, create + canon CRUD + queue/dispatcher + ledger + control_daemon + premise + give_direction + query_world)
- `extensions/branches`: 17 verbs (`_ext_branch_*`: branch CRUD + node CRUD + connect + state-fields + validate + describe + build + patch + search + continue_branch + fork_tree)
- `wiki`: 16 verbs (read, search, list, write, consolidate, promote, ingest, supersede, lint, sync_projects, cosign_bug, file_bug + 4 helpers)
- `goals` + `gates` + `get_status`: ~10 verbs total (goal action=create/list/get/propose/bind/set_canonical, gate action=*, get_status standalone)

**Legacy stdio surface (`tinyassets/mcp_server.py`):** 12 separate `@mcp.tool` decorators — `get_status`, `add_note`, `get_premise`, `set_premise`, `get_progress`, `get_work_targets`, `get_review_state`, `get_chapter`, `get_activity`, `pause`, `resume`, `add_canon`.

---

## 2. Findings

### F1 — `tinyassets/mcp_server.py` is a 12-tool legacy surface duplicating the canonical 6

**Location:** `tinyassets/mcp_server.py` (~12 single-purpose `@mcp.tool` decorators).

**What's wrong:** Every one of these 12 tools is a SUBSET of an action available on the canonical 6-tool surface:

| Stdio tool | Canonical equivalent |
|---|---|
| `get_status` | already present on canonical surface (matches) |
| `add_note` | `universe action=give_direction` (notes are time-stamped attributed directives) |
| `get_premise` | `universe action=read_premise` |
| `set_premise` | `universe action=set_premise` |
| `get_progress` | `universe action=daemon_overview` (rolls up phase/word-count/staleness) |
| `get_work_targets` | (covered by `universe action=daemon_overview` + `extensions action=list`) |
| `get_review_state` | (covered by `universe action=daemon_overview`) |
| `get_chapter` | `universe action=read_output` with path filter |
| `get_activity` | `universe action=get_activity` |
| `pause` | `universe action=control_daemon` (with action=pause kwarg) |
| `resume` | `universe action=control_daemon` (with action=resume kwarg) |
| `add_canon` | `universe action=add_canon` |

**Per minimal-primitives:** 12 → 0 platform-shipped tools (collapse to thin adapter that routes stdio clients to the canonical action verbs). Tool-count budget: -12.

**Per commons-first:** stdio tools currently expose private universe content (premise, chapters, work-targets) to a stdio path that has different auth than the streamable-http canonical surface. **This is a commons-leak-risk** if the stdio shim is reachable by any auth-shape that the canonical isn't. Verify auth parity before retire.

**Per user-capability:** stdio is the LOCAL-APP path (Claude Code desktop / Cowork desktop). Browser-only users never reach `mcp_server.py`. If the canonical tools work for browser-only AND can handle stdio routing, no user-capability regression.

**Recommendation — DEV TASK F1:**
- File: `tinyassets/mcp_server.py` (rewrite, ~200 LOC → ~30 LOC adapter)
- Action: replace the 12 single-purpose tools with a thin adapter that translates legacy stdio calls to the canonical action verbs. Delete the `@mcp.tool` decorators; route through `universe(action=...)` etc.
- Depends: confirm no active stdio client requires the legacy tool-name shape (Claude Code stdio packaging audit).
- Verify: integration test that all 12 legacy tool names still produce equivalent JSON via the adapter.
- Effort: ~2-3h.

---

### F2 — Recency + continue_branch checkpoint (host-approved, principle re-test pending)

**Location:** approved spec per STATUS.md Work table; not yet implemented.

**What `project_minimal_primitives_principle` says:**
> Recency + continue_branch — approved by host 2026-04-26 BUT this principle invites re-evaluation. Test: can chatbot compose "what was I working on last week" from `query_runs` + author filter alone, in <5 steps? If yes → community-build pattern. If chatbot reliably fishes around, the primitive may earn its keep. Worth retesting under this principle.

**Audit verdict:** The `query_runs` primitive already exists (per `tinyassets/api/runs.py`). The question is whether `query_runs(author=me, since=ts, ordered=desc, limit=N)` in 1-2 steps covers the recency intent.

**Composition trace** (chatbot's likely path):
1. `query_runs(author=user_id, ordered_by=created_at_desc, limit=10)` — gets last 10 runs by user.
2. (optional) `goals action=get goal_id=<top-result>` — surfaces the top branch's goal context.

**That's 1-2 primitives, not 5+.** Strongly suggests **CONVENIENCE-COMPOSABLE**.

**continue_branch** is a different shape — it RESUMES a paused/blocked run. Current primitives:
- `extensions action=run_branch` re-creates from scratch (no resume).
- The dispatcher can resume on its own schedule.
- A chatbot wanting "continue what was paused" needs: query → identify paused → re-dispatch with same state.

**Composition trace (continue_branch):**
1. `extensions action=list_runs filter=paused`
2. `extensions action=get_run run_id=X` (to confirm state)
3. `extensions action=run_branch branch_id=X resume_from=run_id` — **THIS is the primitive gap.** No "resume_from" param exists.

**Audit verdict:** continue_branch IS a primitive gap. The composition fails at step 3 — there's no way to inject prior run state into a new run. **Recommend ship continue_branch as a primitive** (per the host approval) BUT scope it as `extensions action=run_branch resume_from=<run_id>` rather than a new top-level action — collapse into existing surface.

**Recommendation — NAV TASK F2:** Bring this re-test result back to host. Concrete proposal:
- **Recency:** retire as platform primitive. Ship a wiki page `pages/plans/recency-via-query-runs.md` showing the chatbot composition pattern. Host re-decision needed.
- **continue_branch:** ship as `resume_from` param on existing `run_branch`, not as new action verb. Scope reduction.

---

### F3 — `add_canon_from_path` is the commons/host-resident boundary

**Location:** `tinyassets/api/universe.py:_action_add_canon_from_path`.

**What's wrong (per commons-first):** This verb reads bytes from the host's local filesystem (`TINYASSETS_UPLOAD_WHITELIST`-gated absolute paths) and stores them in a universe directory. If the universe later becomes public-commons material, those bytes leak from host to commons.

**Existing safeguard:** `TINYASSETS_UPLOAD_WHITELIST` env var (in AGENTS.md config table) — colon/semicolon-separated absolute path prefixes; unset = permissive.

**Per principle:** the chatbot is supposed to make the per-piece visibility decision (per `project_privacy_per_piece_chatbot_judged`). Today, nothing in the verb's contract surfaces "this content is now in the commons by storage location" — chatbot has no introspection point.

**Recommendation — DOC TASK F3:** Annotate `add_canon_from_path` with self-auditing-tools pattern (per PLAN.md "Trust-critical tools are self-auditing"). Add structured caveat to the response:
- `commons_visibility`: `"public_commons" | "host_resident" | "asynchronous"`
- `host_path_recorded`: the path the bytes came from (chatbot can use this in the user-facing narrative)
- `whitelist_check`: `"matched" | "permissive_unset" | "rejected"`

Then chatbot composes the user-facing narrative on top of the structured evidence. NOT a code refactor — an evidence-shape addition.

- File: `tinyassets/api/universe.py` (`_action_add_canon_from_path`)
- Effort: ~1h
- Depends: nothing
- Verify: test that response includes the 3 new keys; test that whitelist_check accurately reflects TINYASSETS_UPLOAD_WHITELIST state

**Companion design-note refresh:** existing concern row "Privacy mode note has 3 host Qs: docs/design-notes/2026-04-18-privacy-modes-for-sensitive-workflows.md" — REFRAME under `project_privacy_via_community_composition` (privacy is community-build, not platform-shipped). The 3 host Qs may dissolve or change shape after the reframe.

---

### F4 — 18 convenience-composable action verbs (candidates for retire)

Each of these passes T1 with <5 reasoning steps to compose. Recommend retire-and-document-pattern. Not all will retire — host curates which the chatbot composition pattern is reliable for vs which are too fragile.

| Verb | Composes from | Likely composition steps |
|---|---|---|
| `_action_daemon_overview` | `get_status` + `extensions action=list` + `universe action=get_activity` | 3 |
| `_action_query_world` | `wiki action=search` + `universe action=read_canon` + filter | 3 |
| `_action_list_subscriptions` | `goals action=list` + `extensions action=list_runs filter=author=me` | 2 |
| `_action_get_recent_events` | `universe action=get_activity` + window filter | 1 (already a near-no-op wrapper) |
| `_action_get_ledger` | `universe action=get_activity filter=ledger` | 1 |
| `_action_read_canon` | `universe action=list_canon` + per-file `universe action=read_output` | 2 |
| `_ext_branch_describe` | `_ext_branch_get` + `_ext_branch_list` + per-node `_ext_branch_get_node` | 3 (depends on chatbot's tolerance for multi-call) |
| `_ext_branch_search_nodes` | `_ext_branch_list` + grep | 2 |
| `_ext_branch_validate` | `_ext_branch_describe` + chatbot inspection | 2 |
| `_action_set_tier_config` | per-tier `universe action=update_config` | 2 |
| `_action_subscribe_goal` / `_action_unsubscribe_goal` / `_action_post_to_goal_pool` / `_action_submit_node_bid` | `goals action=set_subscription` (single primitive with subscribe/unsubscribe kwarg) + `goals action=post_request` + `bid action=submit` | 1 each (already covered by `goals` and bid surfaces) |
| `_wiki_consolidate` | `wiki action=read all` + chatbot diff + `wiki action=write` | 4 |
| `_wiki_lint` | `wiki action=list` + `wiki action=read` + lint logic in chatbot | 3 |
| `_wiki_promote` | `wiki action=read draft` + `wiki action=write promoted` | 2 |
| `_wiki_supersede` | `wiki action=write redirect` + `wiki action=delete` | 2 |
| `_wiki_sync_projects` | `wiki action=list scope=external` + diff + `wiki action=write` | 3-4 |

**Recommendation — DOC TASK F4:** ~1-2h navigator pass to write `pages/plans/composition-patterns.md` (wiki, post-redeploy when BUG-028 alias-fix lands). One pattern per retired verb. Goes in commons.

**Important caveat:** this is the NAV's first-pass irreducibility classification. Host curates which actually retire — some verbs may be load-bearing for low-tier-budget chatbots even though they're composable. The principle says "fewest most-powerful," not "fewest that any chatbot can compose." For chatbots with tight tool-budget windows, a 1-step-rollup may be principle-aligned even if it's reducible.

---

### F5 — User-capability axis check across the 6-tool surface

Per `project_user_capability_axis`: every verb should work for browser-only AND local-app users.

| Tool | Browser-only viable? | Notes |
|---|---|---|
| `universe` | ✅ except `add_canon_from_path` (host filesystem) — already host-only by design | Browser-only equivalent for `add_canon_from_path` is `add_canon` (uploaded bytes). Documented. |
| `extensions` | ✅ | All run/branch operations are cloud-mediated. |
| `goals` | ✅ | Pure cloud surface. |
| `gates` | ✅ | Pure cloud surface. |
| `wiki` | ✅ | Pure cloud commons. |
| `get_status` | ✅ | Pure cloud read. |

**No user-capability regression in the 6-tool surface.** Good.

**The legacy stdio surface (F1) IS local-app-only**, since stdio is local-app-only by definition. F1's "collapse to canonical" automatically resolves this — browser-only users never reached the stdio shim.

---

## 3. Per-finding dispatch summary

| ID | Title | Class | Effort | Dispatch-ready |
|---|---|---|---|---|
| **F1** | Collapse `tinyassets/mcp_server.py` 12 stdio tools → canonical-adapter | DUPLICATE-LEGACY | 2-3h | NO — needs auth-parity verification + stdio-client survey first |
| **F2** | Recency / continue_branch principle re-test | NAV→HOST | 30 min navigator + host re-decision | navigator-ready (recommend: send re-test result to host) |
| **F3** | `add_canon_from_path` self-auditing-tools annotation | PRIMITIVE-GAP-PROXY (clarification, not new feature) | 1h | YES, dev or dev-2 |
| **F4** | Composition-patterns wiki page (18 verbs) | NAV-AUTHORED | 1-2h navigator | navigator-ready (gated on BUG-028 redeploy for wiki write) |
| **F5** | User-capability axis check | INFORMATIONAL | — | (no dispatch — finding is "no regression") |

**Total dispatch-ready effort: ~5-7h** spread across 4 tasks (F1 + F3 + F4 + F2 host-conversation).

---

## 4. Recommended dispatch sequence

**Phase 1 — navigator-authored (no dev block):**
1. **F2** — Send Recency + continue_branch re-test to host with concrete proposal: retire Recency as platform primitive (community-build via `query_runs`); collapse continue_branch to `run_branch resume_from=` param. Wait for host decision before any dev work on either.
2. **F4** — Draft `pages/plans/composition-patterns.md` (LOCAL DRAFT first, push to wiki post-redeploy). 1-2h navigator.

**Phase 2 — small dev dispatch (post-#18):**
3. **F3** — `add_canon_from_path` self-auditing annotation. ~1h. Verify: response includes 3 new keys.

**Phase 3 — gated:**
4. **F1** — `tinyassets/mcp_server.py` collapse. Gated on auth-parity audit + stdio-client survey. 2-3h dev.

**Phase 4 — F4 push:**
5. Once BUG-028 alias-fix is live in prod, push the composition-patterns wiki page (or have host do it via mcp_probe.py).

---

## 5. Decision asks for the lead → host

1. **Approve F1 dispatch** (collapse `tinyassets/mcp_server.py` to thin adapter)? Recommend yes after auth-parity verification. Question for host: is any active client still using `add_note` / `get_premise` / etc. by name?
2. **F2 — accept the principle re-test result?**
   - Retire Recency as platform primitive (community-build pattern via `query_runs`)?
   - Collapse continue_branch to `run_branch resume_from=` rather than new action verb?
   These reverse a 2026-04-26 host approval; navigator wants explicit re-decision before any dev work.
3. **F3 — `add_canon_from_path` self-auditing**? 1-hour dev win. Recommend yes.
4. **F4 — composition-patterns wiki page**? Recommend yes. Will draft locally first; host or me posts post-redeploy.
5. **The principles themselves** — confirm this audit's classification methodology is what you want me applying going forward (irreducibility test + commons-first test + user-capability test as the 3 gates for any new verb)? If yes, I'll save this as the navigator's standing audit kit.

---

## 6. What's NOT in this audit

- **Internal Python module structure** — covered by `docs/audits/2026-04-26-architecture-edges-sweep.md`.
- **Branding hygiene** — covered by `docs/audits/2026-04-26-legacy-branding-comprehensive-sweep.md`.
- **Test surface** — separate audit; not commons-first-relevant in-itself.
- **`get_status` field-level audit** — `get_status` returns ~30 keys; auditing each against principle is a follow-up if host wants it.
- **Provider routing + retrieval router internals** — domain-deep audits, separate workstream.
- **Bid/escrow/ledger semantics** — paid-market mechanics; separate primitive class (commerce primitives are intentional, not convenience).

---

## 7. Cross-references

- `project_minimal_primitives_principle` — the irreducibility test source
- `project_community_build_over_platform_build` — the convenience-vs-primitive decision rule
- `project_commons_first_architecture` — commons-vs-host-resident boundary
- `project_privacy_via_community_composition` — privacy as composition, not feature
- `project_user_capability_axis` — browser-only vs local-app axis
- `project_privacy_per_piece_chatbot_judged` — chatbot makes per-piece visibility calls
- PLAN.md §"API And MCP Interface" — "small number of coarse-grained tools" principle
- PLAN.md §"Tools are the agent-computer interface" — self-auditing tools pattern (F3)
- `docs/design-notes/2026-04-19-self-auditing-tools.md` — pattern for F3
- `docs/audits/2026-04-25-engine-domain-api-separation.md` — sibling structural audit
- STATUS.md Concern row 2026-04-26 — methods-prose evaluator REFRAME (precedent for F2 reverse-decision)

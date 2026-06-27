---
status: research
---

# Mark's `change_loop_v1` — Platform-Gap Mapping

**Date:** 2026-04-26
**Author:** navigator
**Source:** Host paste of Mark's status report (2026-04-26).
**Companion task:** #15.

---

## 1. Goal

Mark (daemon-author persona) shipped 3 valid branches + 2 unpromoted wiki drafts toward a community-change-loop v1, then catalogued **12 platform primitives** that are missing for the loop to run live. This memo classifies each gap into one of four buckets and recommends 1-2 to scope as next platform-work after uptime fixes ship.

**Buckets:**
- **A — ALREADY-LANDED:** primitive exists; Mark just needs to wire it.
- **B — IN-FLIGHT:** current session or recent landings; near-ready.
- **C — NOT-BUILT, blocking Mark:** worth scoping next.
- **D — NOT-BUILT, lower priority:** Mark can work around or defer.

---

## 2. Mapping table

| # | Gap | Bucket | Evidence |
|---|-----|--------|----------|
| 1 | Automatic file/request trigger (wiki `file_bug` auto-starts `change_loop_v1`) | **A — LANDED** | `tinyassets/bug_investigation.py:_maybe_enqueue_investigation` + `tinyassets/dispatcher.py` (env var `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID`); landed via `d06a6d7` skeleton + `79a3c28` substrate + `218d9ec`/`c686b48` Task #46 fix-ups. Mark needs to: (a) wait for cloud daemon redeploy, then (b) ask host to set `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID=fd5c66b1d87d` (his `change_loop_v1`). |
| 2 | Canonical branch lookup ("what's the best branch for this Goal?") | **B — IN-FLIGHT (blocked on redeploy)** | `goals action=set_canonical` exists at `universe_server.py:10751`. `goals action=resolve_canonical` design landed `03361ef` Task #59, MCP wrapper pending impl. `canonical_bindings` table + reader cutover landed Tasks #61/#63/#64. Live `set_canonical` 404s on tinyassets.io/mcp until cloud daemon redeploys (per STATUS Concern). |
| 3 | Sub-branch invocation (nodes invoke other branches with typed outputs) | **A — LANDED** | Phase A items 1-5 complete. Audit trace in `docs/audits/2026-04-25-sub-branch-invocation-audit.md`. Phase A item 5 close-out `a12e284` (Task #76c) shipped: two-pool concurrent-runs model (`_parent_pool` for depth=0, `_child_pool` for depth≥1, env-tunable via `TINYASSETS_CHILD_POOL_SIZE`), runtime invocation-depth threading via `_invocation_depth` kwarg, MAX_INVOKE_BRANCH_DEPTH=5. Tests at `tests/test_sub_branch_invocation.py` + `_integration.py`. **Mark's loop should compose this directly.** |
| 4 | True conditional gate routing (text → routes) | **A — LANDED** | `bdb088f` "bundle: #20 conditional_edges fixes + ..." + `c1d8b8b` "Tier 1 routing contract fix" both shipped. Conditional-edge plumbing live in `tinyassets/branches.py`, `branch_versions.py`, `catalog/serializer.py`, `daemon_server.py`, `graph_compiler.py`. BUG-019/021/022 closed by Tier 1 fix (router-returns-target-name → LangGraph wants path_map key inversion). Named-checkpoint decision-routing contract design at `e90a640` Task #58 (extends but doesn't replace conditional edges). |
| 5 | Standalone reusable gate branches (`gate_investigation_v1`, `gate_review_v1`, etc.) | **A — LANDED, Mark needs to build them** | This isn't a missing primitive — it's a **missing content asset**. Standalone branches that act as gate evaluators are just sub-branches that emit a verdict-shaped output. With #3 (sub-branch invocation) live, Mark builds these as ordinary branches via `extensions action=build_branch`. He may want a convention for "verdict node output shape" — see Recommendation R3 below. |
| 6 | Simulated user testing branch | **D — Mark can build** | Same shape as #5. Build a branch that takes a user-intent + chatbot-style transcript output and runs evaluator nodes. No new platform primitive required; this is Mark composing sub-branches with `node_evaluator` nodes (already in fantasy_daemon eval/). Cross-domain: science-domain testing branches would compose differently but use same primitives. |
| 7 | Live observation watcher (scheduled) | **A — LANDED** | `tinyassets/scheduler.py` (804 lines) + `_SCHEDULER_ACTIONS` MCP surface at `universe_server.py` lines 8245-8418. Scheduler DOW bug fix in `3c15cf9`. Mark schedules `change_loop_v1` runs via `extensions action=schedule_branch` (per design-notes/exec-plans). The "observation" semantics is Mark's content (what the scheduled run does); the scheduler primitive is live. |
| 8 | Patch landing detector | **D — out of platform scope** | This is a *git-event watcher*: did a PR land that closes the BUG? That requires a GitHub-side watcher feeding the dispatcher. Not a Workflow primitive — it's an integration. Closest thing in the platform is the `outcomes` action surface (`tinyassets/outcomes/`, `_OUTCOME_ACTIONS`); a host-runnable script could poll `gh pr list --search "fixes BUG-NNN"` and emit `record_outcome(branch_id, kind="patch_landed")`. Mark can build this script himself; not load-bearing for change-loop v1 testing. |
| 9 | Rollback / auto-heal integration | **B — design-only, not impl** | Surgical rollback design at `b64dd0f` Task #57 (268 lines, atomic-set + bisect-on-canary). Implementation pending — referenced as "Phase D in roadmap 9b28834, E11 from v1 vision." Auto-heal exists separately at `.github/workflows/p0-outage-triage.yml` (uptime-only, not branch-rollback). For Mark's loop: design is vetted but no code to compose against. **Highest-value scoping candidate per §3 R1.** |
| 10 | Evidence ledger / re-entry automation | **B — design-substrate landed** | Contribution events table (Task #71, `098cf15`) + emit-site wiring (Tasks #72/#75, `a608a03`/`fea677d`) + bounty-calc query template (Task #82, `373df03`) form the evidence-ledger substrate. `attribution/` package live. Re-entry semantics ("if BUG re-opens, re-run the change-loop on the same Goal") is one wiki query + scheduler trigger away. Mark needs the substrate to be wired through, not new primitives. |
| 11 | Community promotion system (best known branch → canonical) | **B — design-only, blocked on Task #82** | Bounty-pool dispatch primitive design (`docs/design-notes/2026-04-25-bounty-pool-dispatch-primitive.md`, navigator-vetted PASS this session) + variant canonicals schema (`a0e98d1` Task #47) form the substrate. `goals action=set_canonical` exists for the promotion act itself. Missing: the "best known branch" RANKING — needs outcome events to accumulate + bounty-calc to read. **Implementation chain is Task #82 → bounty-pool dispatch impl → ranking query.** |
| 12 | Private hardened gates | **D — defer** | Per `project_privacy_per_piece_chatbot_judged` memory: visibility is per-piece, chatbot-judged, not a node boolean. "Private hardened gate" framing imports a config-flag mental model that the platform explicitly rejected. The actual mechanism is: gate branch lives in private universe; `extensions action=run_branch` from public universe references a private branch_def_id; ACLs on universes (per `tinyassets/memory/scoping.py` ACL fixture, Stage 2b.3) enforce the privacy boundary. Mark doesn't need a new primitive; he needs a recipe doc on "how to author a private gate." Lower priority. |

---

## 3. Bucket summary

- **A — ALREADY-LANDED (5):** #1 file_bug auto-trigger, #3 sub-branch invocation, #4 conditional edges, #5 reusable gate branches (Mark's content), #7 scheduler.
- **B — IN-FLIGHT or near-ready (4):** #2 canonical lookup (blocked on redeploy), #9 rollback (design-only), #10 evidence ledger (substrate landing), #11 community promotion (blocked on Task #82).
- **C — NOT-BUILT, blocking Mark:** **none.** Every gap that blocks Mark right now is either a redeploy-blocked-thing or a "Mark builds this content" thing.
- **D — NOT-BUILT, lower priority (3):** #6 simulated user testing branch (Mark builds), #8 patch landing detector (out of scope), #12 private hardened gates (recipe needed, not primitive).

**The most important bucket is empty.** Mark is not blocked on missing platform primitives — he's blocked on (a) cloud daemon redeploy, (b) Task #82 substrate land, (c) his own content authoring.

---

## 4. Recommendations (1-2 to scope after uptime fixes)

### R1 (top recommendation): Surgical rollback implementation (#9)

**Why:** This is the only design-only-no-code item that directly enables a real change-loop. Without rollback impl, every patch the loop produces requires manual "did this break anything?" verification. With it, the loop self-validates: patch lands → canary observes → rollback if regression → retry.

**Scope:** Implement `b64dd0f` Task #57 design (atomic-set + bisect-on-canary). Estimate from design doc: ~3 dev-days. Files: new `tinyassets/rollback.py` + integration into `runs.py` + MCP wrapper at `universe_server.py` + tests.

**Sequence:** Wait for redeploy + Task #82 land first (both queued). Then dispatch.

**3-layer chain payoff (System → Chatbot → User):** chatbot can promise users "a regression in this branch will auto-revert" — that's a credibility upgrade for the entire change-loop pitch.

### R2 (second recommendation): Standalone gate-branch convention doc

**Why:** Gap #5 isn't a platform primitive — it's a content/convention gap. Multiple users (Mark, future contributors) will build gate branches. Without a convention, every gate emits a different verdict shape, and the conditional-edge router can't generalize.

**Scope:** ~half-day navigator-authored doc:
- `docs/conventions/gate-branch-shape.md` — verdict-node output schema
  (`{verdict: "pass"|"fail"|"abstain", evidence: [...], suggested_action: str}`).
- Worked example: `change_loop_v1`'s gate nodes annotated as conformant.
- Cross-link from `docs/conventions.md` (already exists per AGENTS.md).
- This is convention work, not code work. Dev not required.

**3-layer chain payoff:** chatbots authoring gate branches converge on the same shape — conditional-edge router stays simple, chatbot output narration becomes consistent across gate types.

### R3 (deferred, after R1 + R2): Wire the loop end-to-end

Once R1 + R2 land + cloud daemon redeploys + Task #82 ships:
- Bind `change_loop_v1` to a `bug_investigation` Goal via `goals action=bind`.
- `set_canonical` on the binding.
- Set `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID` in droplet env.
- File a test BUG via `wiki action=file_bug`.
- Watch the dispatcher pick up the request, invoke `change_loop_v1`, output a patch packet.

That's the "live loop" milestone. No new platform work; pure wiring.

---

## 5. Mark's two unpromoted wiki drafts

Per task brief: `drafts/notes/community-change-loop-v1-builder-notes.md` + `drafts/notes/community-change-loop-v1-piece-map.md` exist on the live wiki but are unpromoted. Per `feedback_wiki_bugs_vet_before_implement` (which generalizes to any user-authored wiki content): these need vet before promote.

**Vet plan (separate, navigator-internal, ~30min when slate clears):**
1. Pull both drafts via `mcp__wiki__wiki_read` (their slugs from cursor).
2. Cross-check for: (a) accuracy against current platform state per this mapping, (b) alignment with PLAN.md principles, (c) no stale references to retired primitives, (d) no malicious-design-disguised-as-fix patterns.
3. If clean: `wiki_promote` to `pages/notes/`. If issues: comment back to Mark via wiki page or surface-to-lead for direct contact.

**Not promoting now.** Defer until current scoping work + uptime fixes settle. Surface separately when ready.

---

## 6. What this mapping does NOT do

- Does not propose any new task IDs. Recommendations R1/R2 surface to lead for task-creation if accepted.
- Does not promote Mark's drafts. Vet step deferred (§5).
- Does not assess whether `change_loop_v1` (Mark's actual branch, branch_def_id `fd5c66b1d87d`) is well-designed. That's a separate `describe_branch` + author-vet exercise; navigator can do it once redeploy lands.
- Does not address Mark's specific scaffolded-but-not-real items individually (intake_router, gates, observation, etc.) — those are content within `change_loop_v1`, not platform primitives. They become real when the platform primitives in §2 are wired together.

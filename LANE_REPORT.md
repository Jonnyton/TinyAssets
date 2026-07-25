# Lane report — o5-retire-inventory

Branch `claude/o5-retire-inventory`. Tree analysed: `92d730bc` (`origin/main` = `d8ef3dea`;
the 1-commit delta is STATUS.md-only and affects no finding). No runtime code changed; no `.py`
touched, so ruff was not required.

---

> **SUPERSEDED BY THE REWORK SECTION BELOW.** The Scope 1 block that follows is the **v1**
> report. An opposite-provider review returned **reject** on it; its "6 wire callers" headline and
> "176 Python bindings" labelling are wrong. Read §*Rework (v2)* for the corrected figures. The v1
> text is kept verbatim so the correction is auditable.

## Scope 1 — retire-legacy-live-mcp-tools tasks 2.1–2.3: DONE *(v1 — superseded)*

Artifact: **`docs/ops/2026-07-25-legacy-mcp-tool-caller-inventory.md`** (new).
Tasks 2.1, 2.2, 2.3 checked off in `openspec/changes/retire-legacy-live-mcp-tools/tasks.md`,
each with an inline evidence summary.

**Premise verified:** `universe_server.py` registers 13 tools — 7 canonical + the 6 hidden
(`_DEPRECATED_TOOL_NAMES`, line 1030), dropped from `tools/list` by `_DeprecatedToolVisibility`
(line 1983) but still dispatchable via `on_call_tool`.

### Inventory summary — counts per caller class

| Caller class | Count | Breaks on unregistration? | Decision |
|---|---|---|---|
| `tests/` direct import (`from …universe_server import <legacy>`) | 57 bindings / 26 files | No | Preserve |
| `tests/` module-attr call (`us.<legacy>(…)`) | 119 bindings / 41 files | No | Preserve |
| **Production runtime Python callers (`tinyassets/` non-test)** | **0** | — | none exist |
| Canonical→legacy delegation edges inside `universe_server.py` | **0** | — | none exist |
| `scripts/` Python-API callers | 0 | — | none exist |
| `fantasy_daemon/universe_server.py` (`import *`) | 1 | No | Preserve |
| **Wire callers (MCP tool-name dispatch)** | **6 sites / 3 files** | **Yes** | **Migrate** |
| Retired-tool metadata residue (conway panel JSON, market.py labels) | 8 refs / 2 files | No | Fix strings (task 4.5) |
| Excluded false positives (website snapshot data, packaged mirror, logger names, hint prose) | — | No | Do not "fix" |

**Union: 176 Python bindings across 67 files — every one under `tests/`.**

### Key findings

1. **2.3-A — zero production-runtime Python callers, zero canonical→legacy delegation.** Both
   surfaces delegate independently to the same `tinyassets/api/*` impls. This confirms task 4.1's
   default: remove the 6 registrations, keep the 6 `def`s. Deleting the wrapper bodies would break
   67 test files for no benefit.
2. **2.3-B (blocker) — `wiki action=list` has no canonical replacement.** `read_page` only ever
   emits `read`/`search`/`since`. Two live scripts depend on it, including
   `scripts/navigator_wiki_sweep.py`, which defaults to **`https://tinyassets.io/mcp`** and drives
   the navigator's standing 30-min sweep cadence. Retirement must first extend `read_page` or
   retire the cadence with host sign-off.
3. **2.2-A — open PR #1467 would restore the retired `directory_server.py`.** It carries
   `modified +30/-3` against a file `origin/main` deleted in `60f7f9f1` (#1718). Must be rebased
   before merge — violates tasks 2.2 and 4.4 otherwise.
4. **Action-reachability gap:** the 6 legacy tools are `action=` passthroughs exposing **187**
   dispatchable actions; the canonical 7 are narrow target routers reaching **18**. **169 orphaned**
   (`gates` = 20 of 20 — no canonical handle routes to it at all). Not 169 regressions — much of it
   is deliberate surface reduction — but it makes retirement a ~90% action-surface cut, not a
   rename. Two live STATUS.md rows already depend on orphaned actions (`goals action=bind/set_canonical`;
   `wiki action=promote`).
5. **2.3-C — precedent exists.** `scripts/last_activity_canary.py` already made this exact
   migration (`universe action=inspect` → `read_graph target="graph"`) and documents that every
   shape assertion stayed unchanged. The two `mcp_probe.py` universe sites can follow it verbatim today.
6. **The public canary cannot see the hidden six** — it reads `tools/list`, which the middleware
   already filters. A green `--assert-handles` run is not retirement evidence; hence task 3.1's
   "listing middleware bypassed" requirement.

**2.1 ownership:** of the nine PRs, 5 CLOSED; **4 OPEN and all edit `universe_server.py`** —
#1493 `a4115dd3`, #1467 `5fb6d16a`, #1466 `4427d012`, #1465 `8eef71b8`. They are dependency edges
for the implementation lane. `claim_check.py --check-files` on this lane's write-set: **CLEAR**.
**2.2 boundary:** #1561 (`1a5d45af`) confirmed 3 files, stdio-only; `tinyassets/mcp_server.py`'s
tool surface is disjoint from the six, so it is structurally unaffected.

Scoped honestly in §7 of the artifact: this is repository-internal only and does **not** satisfy
task 1.3 (external hidden-name call telemetry). No live probe was run.

---

## Rework (v2) — after opposite-provider review returned `reject`

Artifact reworked in place: **`docs/ops/2026-07-25-legacy-mcp-tool-caller-inventory.md`** (v2).
Verdict source: `…/scratchpad/verdict-retire-inventory.md`. **Every count in the verdict was
re-derived independently before folding; all reproduced exactly.**

### What the review refuted

1. **"6 wire callers" — refuted.** v1 missed an entire caller class: **38 legacy wire invocation
   sites across 8 website JS/TS/Svelte/mjs files**. v1's six rows also mixed unlike things (4 real
   wire calls, 1 panel metadata, 1 response-label residue v1 itself called "not dispatch calls").
2. **"176 Python bindings … all under `tests/`" — mislabelled.** 176 is a **reference** count
   (57 imports + 119 module-attr references), not a caller count. The row headed "module-attr
   call" contains **17 non-call introspection** references. And "all under `tests/`" omits the
   **non-test** `import *` at `fantasy_daemon/universe_server.py:2`.
3. **`wiki action=list` caller scope — undercounted.** v1 said "2 live scripts"; the real set is
   5 wire sites plus the public playground.
4. **Additional missed classes** — packaged plugin skills instructing `universe` calls, the plugin
   boot path, `bids/README.md`, and playground UI copy.
5. **Limits section understated its blind spots** — it implied the static repo inventory was
   complete when it covered only Python.

### What I re-verified myself (independent AST + language-aware scan)

| Figure | v1 claim | Re-derived | Status |
|---|---|---|---|
| Python explicit imports | 57 / 26 files | **57 / 26** | reproduces |
| Python module-attr references | 119 / 41 files, labelled "call" | **119 / 41**, of which **102 calls + 17 introspection** | arithmetic right, **label wrong** |
| Reference union (57+119) | "176 bindings" | **176 references** across **67** files | **mislabelled** |
| Actual Python call expressions | not reported | **376 across 62 files** (274 imported-name + 102 attr) | **missing from v1** |
| Non-test Python binding | mentioned separately | `fantasy_daemon/universe_server.py:2` `import *` | **checkoff phrase unqualified** |
| Website wire sites | **0 reported** | **38 across 8 files** — `wiki` 7, `goals` 9, `universe` 5, `community_change_context` 2, `extensions` 15 | **missed** |
| Total literal wire sites | 6 | **42 across 10 files** (+1 dynamic, +1 registration-level test) | **refuted** |
| `wiki action=list` dependents | 2 scripts | **5 wire sites + public playground** | **undercounted** |
| Open-PR state (#1493/#1467/#1466/#1465/#1561) | pinned shas | re-queried 2026-07-25, **all unchanged** | confirmed |

Mechanism confirmed, not assumed: `live.ts:103` → `rpc('tools/call')`; `playground.ts:132`;
`snapshot-mcp.mjs:210` (official MCP SDK). `fetchLive`/`fetchVitals` are imported and invoked by
11 rendered page components across the two trees; `snapshot-mcp.mjs:25` hardcodes
`https://tinyassets.io/mcp`. Both trees are deployable (`deploy-site.yml` / `deploy-site-react.yml`,
both `workflow_dispatch`-only, sharing the `pages` concurrency group) and their headers
**contradict each other** about which is live — so both are counted; `deploy-site.yml` is the
documented rollback path.

### Two findings v2 adds beyond the verdict

- **2.3-D — `extensions action=stream_run` is a second orphaned action with live callers.**
  `read_graph` emits only `list/get/search/inspect/list_runs/get_run/get_branch`; `stream_run`
  exists only in the legacy docstring (`universe_server.py:1413`). Both `live.ts` trees call it
  from `fetchMcpPatchLoopFeed` (`live.ts:836`), reached from the rendered `/loop` page via the
  **default** `source='mcp'` branch.
- **2.3-E — task 4.4's mirror rebuild breaks four packaged slash commands.**
  `runtime/server.py:39-40` boots the mirrored `universe_server`; `premise`/`progress`/`status`/
  `steer` SKILL.md instruct `universe` calls, and three of the actions they name
  (`get_activity`, `give_direction`, the premise verbs) have **no** canonical equivalent.

Also corrected: `callTool('loop', …)` (`live.ts:838`/`841`) is **not** a legacy caller — `loop` is
not among the 13 registered tools at all. Correctly excluded from the 38; now logged in §4e so a
later reader does not re-add it.

### Final counts (v2)

- **Python — unaffected by unregistration:** 57 imports / 26 files; 119 module-attr references /
  41 files (102 calls + 17 introspection); **376 call expressions / 62 files**; 1 non-test
  `import *`. Union of classes A+B = **67 files, all under `tests/`** — the star import is the
  documented exception to "every repository import."
- **Wire — broken by unregistration:** **42 literal sites / 10 files** = 4 Python
  (`navigator_wiki_sweep.py:162`, `mcp_probe.py:139,146,155`) + **38 website / 8 files**; plus
  1 dynamic dispatcher (`Playground.svelte:95`) and 1 registration-level test
  (`test_universe_server_five_handles.py:127`).
- **Of those 42, 9 have no canonical replacement:** `wiki action=list` ×5,
  `community_change_context` ×2, `extensions action=stream_run` ×2. The other **33** are
  straightforward migrations via the `last_activity_canary.py` precedent.
- **Non-dispatch classes:** 3 metadata panels, 3 response labels, **8+ instruction surfaces**
  (4 packaged skills, `bids/README.md:24`, playground copy, `api/universe.py:2540` hint).
- Action-reachability gap unchanged and re-verified: **187 dispatchable actions → 18 canonical-
  reachable → 169 orphaned** (`gates` 20 of 20).

### Task checkoff reconciliation

| Task | Now | Why |
|---|---|---|
| 2.1 | **`[x]` retained, qualified** | Deliverables done; PR state re-queried today. The "resolve **or depend**" half is now real: artifact §11 is stated as **binding preconditions**, and task 4.1 carries the dependency inline. Caveat recorded: raw scan output not retained, `origin/main` stamp decays. |
| 2.2 | **`[x]` retained** | Unrefuted. #1561 `1a5d45af` re-queried (OPEN draft, 3 files, stdio-only); `mcp_server.py` disjoint; `directory_server.py` absent since `60f7f9f1`. |
| 2.3 | **`[ ]` UNCHECKED** | Its contract ("**every** repository import and direct caller … preserve-or-explicitly-migrate decision") is not met: the wire half was wrong by 36 sites and its checkoff asserted three false statements. The Python half is complete and retained; 2.3 re-checks only after the class E/F/G/K migration decisions in §11 are recorded. |

Task 4.1 also gained an inline block note naming the §11 preconditions — that is what makes 2.1's
"depend on the owners" clause actually binding rather than advisory.

**Still not established (unchanged):** task 1.3 external telemetry, live probes, installed-client
and deployed-bundle state, which website tree is actually serving, adjudication of the 169 orphans.
Class G (user-typed playground input) is not statically enumerable at all.

---

## Scope 2 — BUG-018 closure: BLOCKED (false premise — page is not in this repo)

**The BUG-018 page does not exist anywhere in this repository, and the wiki is not repo-managed.**
The edit as specified could not be performed in-worktree. Evidence:

- `git ls-files | grep -i bug-018` → **0 tracked files**; repo-wide `BUG-018` hits are only
  references (`STATUS.md`, `docs/ops/post-redeploy-wiki-migration.md`, `docs/audits/…`).
- **Zero files tracked under `wiki/`**; no `.gitmodules`. The repo's `pages/bugs/` holds a
  different, unrelated series (`bug-093`, `bug-095`).
- `deploy-prod.yml:293` explicitly **strips** `TINYASSETS_WIKI_PATH` so `wiki_path()` falls back to
  the platform default (`data_dir()/wiki`) — i.e. the **production host volume**. The wiki is live
  service data, not source.
- The only local copy is a stale 2026-06-24 snapshot at
  `Projects/Workflow-live-data-snapshot/wiki/…`, outside this lane's worktree.

**Live state confirmed** (read-only `read_page` against the production connector, 2026-07-25):
page `pages/bugs/BUG-018-no-maintainer-notes-field-on-nodes-builder-to-builder-notes-.md`,
`is_draft: false`, `status: open`, `updated: 2026-04-22`, 3807 chars,
`sha256 = 14d56d920a54bfb0f558837b891c0f5383f7e44a68fe92d86543a55c4c42c749`.

**I did not perform the write.** It is a mutation of live production data, outside the lane's
"work only inside this worktree" fence, and it cannot be captured in this lane's commit. The host
decision authorises the content change, so this needs only a go-ahead — not a re-decision.

Ready to run as-is (CAS-guarded; `write_page` exposes `patch` with `expected_sha256`, so the
malformed filename is preserved and the surrounding body is untouched):

```
write_page action=patch
  page="pages/bugs/BUG-018-no-maintainer-notes-field-on-nodes-builder-to-builder-notes-.md"
  expected_sha256="14d56d920a54bfb0f558837b891c0f5383f7e44a68fe92d86543a55c4c42c749"
  old_text="status: open"
  new_text="status: closed (superseded by feature-describe-branch-related-wiki-pages)"
```

then a second `patch` appending the body note (re-read for the new sha first):

```
old_text="## Related\n\n_none yet_"
new_text="## Related\n\nClosed 2026-07-25 per host decision — see docs/ops/post-redeploy-wiki-migration.md §1.8."
```

Two notes for whoever runs it:
- **Keep the filename.** Confirmed deliberate; renaming risks wikilink breakage for zero reader benefit.
- The live body contains pre-existing malformed markup (stray `</observed>`,
  `<parameter name="expected">` residue). Use `patch`, **not** a full-content `write` — a wholesale
  rewrite would likely mangle it further. Unrelated to this closure, but worth a separate cleanup row.

**Follow-up surfaced, not actioned** (outside this lane's claimed write-set): the STATUS.md
`host-decision` row *"BUG-018 canonical filename trailing-hyphen — rename canonical, or `wiki
action=promote` a draft over it?"* is now answered by the 2026-07-25 decision (keep the filename)
and is ready to be deleted. I left STATUS.md untouched to stay inside the collision check I ran.

---

## Fold 2 (v3) — after opposite-provider round 2 returned `adapt`

Verdict source: `…/scratchpad/verdict-retire-inventory.md` §"Round 2" (reviewed v2 at `9bd88a07`,
read-only static analysis + read-only GitHub PR queries). Artifact bumped **v2 → v3** in place.

**Round 2 confirmed v2's substance.** It independently reproduced every headline count — 38 website
sites / 8 files with the per-tool split 7/9/5/2/15; 42 literal wire sites / 10 files; 57 imports /
26 files; 119 references / 41 files = 176; 376 calls / 62 files; 17 non-call references; the
non-test star import — plus the `wiki action=list` no-equivalent analysis, both new blockers, and
all three task-checkoff states. It named four corrections. **Every disputed number below was
re-derived by me before folding, not taken from the verdict.**

### Correction 1 — B2 file count: 4 → **5** (count 17 unchanged)

Re-ran my binding-aware AST pass (module aliases resolved per-file, `Attribute` nodes classified by
whether their `id()` is the `.func` of an enclosing `Call`):

| File | Non-call refs |
|---|---|
| `tests/test_mcp_dispatch_docstring_parity.py` | 11 |
| `tests/test_api_market.py` | 2 |
| `tests/test_goals_discoverability.py` | 2 |
| `tests/test_api_universe.py` | 1 |
| `tests/test_validate_ship_packet_action.py` | 1 |
| **Total** | **17 across 5 files** |

Same run re-emitted `total module-attr refs: 119` / `of which calls: 102`, so classes B/B1 are
unchanged and only the B2 **file** count was wrong. The verdict's 5-file list matches mine exactly.
**Applied:** §4a row `4` → **`5`** plus an inline correction note naming all five files.

### Correction 2 — blocker prose

**2.3-D (`stream_run`).** v2 claimed it "appears in the repository only inside the legacy
`extensions` docstring." I verified this myself and **v2 was false**: `_action_stream_run` at
`tinyassets/api/runs.py:924`; dispatch entry `_RUN_ACTIONS["stream_run"]` at `:1891`; enumerated at
`tinyassets/api/extensions.py:737`; and covered by real tests (`test_branch_runner.py:751,925,963`;
`test_api_runs.py:37,65,96`). Re-ran my canonical-action AST extraction to confirm the blocker
still holds — `read_graph` emits exactly `['get','get_branch','get_run','inspect','list',
'list_runs','search']`, no `stream_run`. **Applied:** 2.3-D reframed as **canonical
unreachability**, with the explicit note that retirement removes the only wire *route* to working,
tested functionality — which makes restoring it a routing decision, not new feature work.

I also swept for the same defect wherever else I had written "docstring-only," since the verdict
named only `stream_run`. Same error found and fixed for `get_node_output`
(`api/evaluation.py:394`, dispatch `:783`), and verified real for `get_activity`
(`api/universe.py:6084`), `give_direction` (`:6088`), `read_premise` (`:6089`), `set_premise`
(`:6090`), `submit_node_bid` (`:6109`). §5 now defines "orphaned" as *unreachable through the
canonical seven*, never *unimplemented*.

**2.3-E (packaged skills) — three sub-corrections, all verified:**

| v2 said | Truth | How I verified |
|---|---|---|
| `get_premise` / `set_premise` | **`read_premise`** / `set_premise` | `premise/SKILL.md:13` reads `action="read_premise"`. `get_premise` is a tool on the *separate* stdio server `tinyassets/mcp_server.py` (artifact §3) — a different server entirely. |
| "**three** of the five actions … no canonical equivalent" | **four** of five | Unique set across the 4 skills = {`read_premise`, `set_premise`, `inspect`, `get_activity`, `give_direction`}. Only `inspect` is emitted by `read_graph` (AST extraction above) ⇒ **4** unreachable. |
| "the moment **4.1** lands" | breaks at **4.4** | The mirror is a checked-in copy carrying its own registrations — `runtime/tinyassets/universe_server.py:1030` still defines `_DEPRECATED_TOOL_NAMES`. `runtime/server.py:39-40` boots **the mirror**, so 4.1 (source-only) leaves the plugin working; the window opens when **4.4** regenerates it. |

**Applied:** 2.3-E retitled to task 4.4, given a per-skill reachability table, and all three defects
recorded inline. Precondition 5 in §11 restated with the 4.4 deadline. This one is a real
sequencing fix, not cosmetic — v2 would have had the migration land against the wrong task.

### Correction 3 — new authorization/action-scope metadata class (**class L / Finding 2.3-F**)

Verified `tinyassets/auth/provider.py:516-618`: five `_extend_scope_rows(..., tool=…)` calls keyed
on `universe` `:516`, `wiki` `:525`, `extensions` `:580`, `gates` `:600`, `goals` `:610`, carrying
`write_actions` / `costly_actions` / `admin_actions` — including the money-write set
(`escrow_lock/release/refund/fund/set_wallet/withdraw`). I then traced **all six**
`require_action_scope` call sites and confirmed each passes a hardcoded legacy tool-name literal.
Five enforcement sites are on bodies canonical handles delegate into; the `gates` site is reached
only from the hidden legacy dispatcher:
`api/universe.py:6235`→`:6151`, `api/wiki.py:2789`→`:2651`, `api/extensions.py:399`→`:248`,
`api/market.py:2595` (`"goals"`), `api/market.py:3936` (`"gates"`), `api/first_contact.py:50`
(`"universe"`).

**Why it matters:** task 4.2 is told to remove "the legacy-name set, and dead registration-only
state." This table *looks* exactly like that and **is not** — it is load-bearing authorization and
availability state. A missing row fails closed; the narrower risk is removing mutating
classifications while leaving actions to default to `read` in resolve-always mode.
**Applied:** new census row L, new §4f / Finding 2.3-F, new §11 precondition 10, and an inline
scope guard on tasks 4.2/4.4 in `tasks.md` requiring them to state whether they preserved or
lockstep-migrated the registry and mirror, gated by a two-part regression. Does **not** change the
42-site count; `community_change_context` has no scope row (fixed single action).

### Checkoff re-validation

Re-checked against the corrected artifact — **no checkoff changes**, and this matches round 2's own
finding 4 ("2.1 may remain checked … 2.2 may remain checked … 2.3 is correctly unchecked"):

| Task | State | Still correct because |
|---|---|---|
| 2.1 | `[x]` | Unaffected by all three corrections. Round 2 independently re-queried #1493/#1467/#1466/#1465 and reproduced OPEN + matching head SHAs. |
| 2.2 | `[x]` | Unaffected. Round 2 reproduced #1561 OPEN draft `1a5d45af`, exactly 3 files, six names disjoint, #1467's `directory_server.py` delta still present. |
| 2.3 | `[ ]` | Still correctly unchecked. None of the three corrections clears a gate — 2.3-F *adds* a blocker, and 2.3-D/E tighten two existing ones. |

`openspec validate retire-legacy-live-mcp-tools --strict` → **valid**. No `.py` touched, so ruff was
not required.

---

## Fold 3 (v4) — after opposite-provider round 3 returned `adapt`

Round 3 left B2 (**17 references / 5 files**), 2.3-D, and 2.3-E unchanged. It corrected Finding
2.3-F's failure mode: `require_action_scope` fails closed when `action_scope_for` returns `None`,
raising `PermissionError` before resolve-always's read exemption. This was reproduced in the local
tree and at production source SHA `0603aae1`. The residual fail-open risk is narrower: removing
only write/costly/admin classifications while leaving mutating actions in the registry defaults
them to `read`, which resolve-always mode permits.

Applied across inventory §4f/§10/§11 and tasks 2.3/3.5/4.2/4.4: the registry is load-bearing
authorization **and availability** state; source enforcement and the packaged mirror must be
preserved or lockstep-migrated; and a regression must prove both missing-metadata denial and
non-read classification for every mutating action. The §4f reachability row now agrees with §5:
`gates` is **not** reached through a canonical handle (20 of 20 gate actions remain orphaned).
Task 2.3 remains unchecked.

LANE_RESULT: done - folded round-3 ADAPT into inventory v4 and task gates: missing action-scope metadata fails closed, classification-only removal is the narrower resolve-always fail-open risk, `gates` has zero canonical routes, and tasks 4.2/4.4 now require lockstep source/mirror migration plus a two-part regression; B2 17/5 and 2.3-D/E remain unchanged.

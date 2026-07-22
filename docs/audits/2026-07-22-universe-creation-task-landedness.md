# `universe-creation`: landedness audit of 35 unchecked tasks

**Date:** 2026-07-22
**Verified against:** `origin/main` @ `144eaba7` (after `git fetch --prune`)
**Change:** `openspec/changes/universe-creation/`
**Scope:** classification only — no open task was implemented in this lane.

## Why this audit exists

`openspec/changes/universe-creation/tasks.md` carried **35 unchecked tasks of 49**, and — unlike
every other change under `openspec/changes/` — **none of them were annotated `GATED`**. Since
OpenSpec became the project standard on 2026-07-19 (AGENTS.md § *Spec-driven development*), agents
are directed to build from `openspec/changes/*/tasks.md`. So all 35 read as open, claimable work.

They were not. **11 are already implemented on `main`**, and **4 assert behavior a later host
directive reversed** — an agent following the process correctly would have rebuilt landed code and
written tests asserting behavior the host explicitly retired.

This is the `stale-backlog-rows-misdirect` failure class (2026-07-21: 5 of 5 dispatched `dev-ready`
rows had false premises), extended on 2026-07-22 to `openspec/changes/*/tasks.md`. The direct
precedent is **PR #1515**, which classified 11 stale tasks in `universe-personification` against the
same relay reshape.

### The change's own header was stale

`tasks.md` opened with an implementation-status note dated **2026-06-30** listing tasks "held for
host live-proof gates": *"2.7–2.8, 2.10, 3.1–3.2, 2.12, and the existing-universe half of 2.9."*

Two of those — **2.7 and 2.8** — have since **landed** (PR #1437 merged 2026-07-15, PR #1462 merged
2026-07-15). The header was written before the branch merged and never updated. A reader trusting it
would have treated live, deployed code as pending.

## Method

Every verdict below was produced by reading code on `origin/main`, not by matching symbol names.
Two rules were applied throughout, both taken from prior incidents in this repo:

1. **Call sites, not function bodies or file names.** A symbol existing is not proof the requirement
   is met; a symbol missing is not proof it is not. This flipped three verdicts (2.8, 2.11, 2.0g).
2. **Ambiguity resolves to OPEN.** A wrongly-checked box silently deletes work. Where a task's first
   clause landed and its second did not, the task stays **unchecked** and the landed half is recorded
   inline rather than being used to justify a checkmark.

## Rollup

| Verdict | Count | Tasks |
|---|---:|---|
| **LANDED** | 11 | 1.0a, 1.0c.1, 2.0, 2.0a, 2.0b, 2.0c, 2.0d, 2.0f, 2.6, 2.7\*, 2.8\* |
| **REVERSED** | 3 | 1.3, 1.12, 1.13 |
| **GATED** | 10 | 1.4, 1.5, 1.15, 1.17, 2.10, 2.12, 3.1, 3.2, 3.3, 4.3 |
| **OPEN** | 11 | 1.0c, 1.0c.2, 1.0d, 1.0e, 1.4a, 1.16, 2.0e, 2.0g, 2.11, 4.1, 4.2 |

11 + 3 + 10 + 11 = **35**. \* Two LANDED tasks carry an annotated caveat rather than a clean
checkmark: **2.7**'s trailing "first-person universe voice" clause is reversed (the implementation
landed; the voice behavior must not be rebuilt), and **2.8** is landed for the authenticated
multi-tenant path only, with the anonymous/dev marker retained by design.

Mechanically verified in the updated file: 25 checked (14 pre-existing + 11 new), 24 unchecked,
3 `[~]` partial, 52 items total — no task added, removed, or renumbered.

**Net effect: 21 of 35 (60%) were not actionable work** — 11 already done, 10 blocked on a host gate.

---

## Per-task classification

### 1. Contract Tests

| Task | Verdict | Evidence | Reason |
|---|---|---|---|
| **1.0a** WorkOS RS auth tests | **LANDED** | `tests/test_workos_provider.py:101,153,159,164,168,173`; `tests/test_predeploy_auth_hardening.py:65` | All three clauses covered: valid token → founder identity (`:101`); invalid/expired/wrong-issuer/bad-signature tokens create no principal (`:153–:173`); anonymous cannot create (`test_anon_universe_write_rejected_in_resolve_always`). |
| **1.0c** MCP write-boundary tests | **OPEN** *(partial)* | `tests/test_multi_tenant_isolation.py:213` | `test_cross_founder_write_denied_and_private_read_isolated` proves the core boundary, but the task enumerates soul, identity, canon, wiki, runtime goals, body, org chart, files, and state as separate surfaces. One cross-founder write test is not that matrix. |
| **1.0c.1** anonymous-permission tests | **LANDED** | `tests/test_anonymous_write_challenge.py` (15 tests, `:144–:259`); `tests/test_predeploy_auth_hardening.py:58,65` | Write/create/batch/chunked all challenged, reads pass intact. The broader "run/costly/admin/ledger/sync" enumeration is one structural gate (`middleware.py:396` classifies by `metadata.effect`), covered by `test_optional_mode_is_resolve_always_for_writes`. Live `ui-test` passed 2026-07-14 (PR #1441). |
| **1.0c.2** universe-visibility tests | **OPEN** *(moved)* | `openspec/changes/universe-visibility/tasks.md:3.1,3.2` | Ownership of the visibility model moved to the separate `universe-visibility` change, whose §1 model decisions (1.1–1.4) are themselves still open. Writing these tests here would fork the model. Cross-referenced, not duplicated. |
| **1.0d** Branch interaction tests | **OPEN** | patch-request surface exists (`tinyassets/api/universe.py:1439`); no test asserts "without gaining write access" | The surface landed; the negative assertion the task actually asks for does not exist. |
| **1.0e** Branch-run tests | **OPEN** | `tinyassets/api/runs.py:90` (`branch_run_requires_universe`) | Universe-as-actor is enforced in code, but no test covers multi-universe same-Branch instancing or remix-into-variant. |
| **1.3** `get_status` idempotent, does **not** first-create | ⛔ **REVERSED** | `tinyassets/api/status.py:689–700` | **AUTO-BIRTH, host decision 2026-07-15** — `get_status` now *does* create and bind a home universe for an authenticated founder with none, explicitly *"supersedes the 2026-07-02 opt-in birth"*. The "does not first-create the soul bundle" requirement is inverted. The idempotency half is covered (`tests/test_first_contact.py:148`). |
| **1.4** descriptive-id → serial-id reset tests | **GATED** | `docs/exec-plans/2026-06-30-founder-identity-allslices-handoff.md:115` | Live-data migration, held for canary + chatbot `ui-test` (AGENTS.md Rule 11/12). |
| **1.4a** universe-index tests | **OPEN** | see 2.11 | Second assertion (learned-name update) is untestable because the behavior is unimplemented. |
| **1.5** replace HTTP create tests | **GATED** | blocked by 3.1 | Cannot assert `POST /v1/universes` does not create while it still creates. |
| **1.12** first-connect: blank seed + **first-person universe voice** | ⛔ **REVERSED** *(in part)* | `tinyassets/universe_server.py:208–211` | Birth/bind half landed (`tests/test_first_contact.py:124,332`). The clause *"the first response speaks in first person as the universe"* was reversed by the 2026-07-02 relay reshape: shipped code says *"You do NOT speak as the universe … RELAY … you are the connector, not the universe."* Writing this test would assert retired behavior. |
| **1.13** first-connect: existing home speaks as that universe | ⛔ **REVERSED** *(in part)* | same as 1.12 | Home resolution landed (`tests/test_first_contact.py:469`); the "speaks as that universe" clause is reversed. |
| **1.15** existing-universe reset tests | **GATED** | same migration as 1.4 | — |
| **1.16** universe-clearing tests | **OPEN** *(partial)* | `tests/test_reset_universes.py:75` | Covers dirs + index + ACL cleared and branch commons preserved. Does **not** assert the two things the task names: `founder_home` bindings cleared, and run metrics / outcome records intact. The implementation supports both (`tinyassets/reset.py:36`, `:51`); the assertions are missing. |
| **1.17** mobile-contract tests | **GATED** | PR **#1438** OPEN (unmerged); no mobile code on `main` | Depends on the deploy that PR #1438 is itself waiting on. |

### 2. Creation Implementation

| Task | Verdict | Evidence | Reason |
|---|---|---|---|
| **2.0** WorkOS AuthKit RS validation | **LANDED** | `tinyassets/auth/workos_provider.py:52,67,103,135,142,153`; `tinyassets/auth/wellknown.py:63,108–140` | PRM (RFC 9728) + AS metadata (RFC 8414) served at root and `/mcp`; issuer + audience validated; `sub` → founder id. Merged in PR **#1437** (2026-07-15), deployed same day. |
| **2.0a** resolve-always auth mode | **LANDED** | `tinyassets/auth/provider.py:703,1118`; `tinyassets/auth/middleware.py:61,380,396,402` | Reads pass anonymously (`metadata.effect == "read"`); write/costly/admin require an authenticated founder scope via the action-scope registry. |
| **2.0b** target-universe ownership for brain writes | **LANDED** | `tinyassets/api/universe.py:132–157`; `tinyassets/api/permissions.py:92–127` | `_universe_acl_error` is the single ACL gate on universe actions, with documented exemptions (`list`, `create_universe`, `_DAEMON_SCOPED_ACTIONS`). |
| **2.0c** anonymous public-read-only on every write surface | **LANDED** | `middleware.py:396–402` plus per-surface ACL call sites: `auto_ship_actions.py:88`, `runs.py:100`, `status.py:893`, `universe.py:147`, `wiki.py:2493` | Verified at call sites across all five surfaces the task enumerates (ledger/auto-ship, wiki, run, universe-brain). Live-proven 2026-07-14 (PR #1441 + `ui-test`). |
| **2.0d** explicit `public_read`, separate from grants | **LANDED** | `tinyassets/api/permissions.py:6–16,59–90`; `tinyassets/daemon_server.py:114` | Module docstring names the conflation-of-ownership-and-visibility bug this replaces. Fails closed on rules-read error. |
| **2.0e** confirmation-gated visibility action | **OPEN** | only `tinyassets/api/branches.py:2523` (`set_visibility` — *branches*, not universes) | No universe-level public↔private action exists, confirmation-gated or otherwise. Coordinate with `universe-visibility`. |
| **2.0f** cross-universe interactions via request/proposal surfaces | **LANDED** | `tinyassets/api/universe.py:1439,1498,1513,1521`; `tinyassets/api/wiki.py:1662,1795`; `tinyassets/universe_server.py:1014,1097` | Patch-request surface + `_BRAIN_WRITE_RELAY_ACTIONS` relay; direct cross-universe writes blocked by 2.0b. |
| **2.0g** Branch-run authority | **OPEN** *(half landed)* | landed: `tinyassets/api/runs.py:90–107,110–125`. **Not** landed: goal binding | Universe-as-runnable-actor is enforced (`branch_run_requires_universe`, actor `universe:<uid>`). The second clause — *"each run is recorded as a goal-bound Branch-use instance"* — is **not** implemented: `goal_id` appears in `runs.py` only at `:1593`/`:1624` as an isolation-tier **diagnostic string**, never as a recorded binding on a run. Checking this box would delete the goal-binding work. |
| **2.6** `soul.edit.md` policy + execution path | **LANDED** | `tinyassets/soul_edit.py`; `tests/test_soul_edit.py`; MCP action at `tinyassets/api/universe.py:5161` | Already cited by the *checked* task 1.8 — the change contradicted itself. Reads the governed list from the policy file; ACL/scope/ledger-gated; versioning + `log.md` append. |
| **2.7** founder home-universe resolution on first contact | **LANDED** ⚠ *reversed tail* | `tinyassets/api/status.py:689–725`, `ensure_founder_home` `:737`; PR **#1462** (merged 2026-07-15) | Resolution + auto-birth + binding are live. ⚠ The trailing clause *"→ first-person universe voice"* is **reversed** by the relay reshape (`universe_server.py:208`). The implementation landed; the voice behavior must not be rebuilt. |
| **2.8** remove root `.active_universe` from MCP default routing | **LANDED** ⚠ *scoped* | `tinyassets/api/helpers.py:88–116`; `tinyassets/api/universe.py:4665–4680,4747–4760` | Removed from the **authenticated multi-tenant** path at all three call sites, each citing this spec by name. ⚠ Deliberately retained for **anonymous / dev single-tenant**: `_default_universe()` (`helpers.py:73`) still reads the marker, and `switch_universe` still writes it for anonymous callers because the tray app watches that file. The cross-founder leak the task targets is closed; the marker still exists by design. |
| **2.10** serial-id universe roots | **GATED** | `scripts/rename_live_data_universes_to_serial_ids.ps1`; handoff `:115` | Live-data migration, separate reviewed step against a snapshot. |
| **2.11** maintain root universe index | **OPEN** *(half landed)* | landed: `tinyassets/daemon_server.py:610` (`ensure_universe_registered`, called on create). **Not** landed: learned-name column | Nothing syncs a learned `identity.md` name into the index `display_name`. `soul_edit.py:203,254` writes the name into `identity.md` frontmatter and stops there. Confirmed by reading the consumer: `_action_list_universes` (`universe.py:1195–1245`) walks the **filesystem**, never queries the `universes` table, and returns no name field at all. |
| **2.12** Android test app | **GATED** | PR **#1438** OPEN | Explicitly conditioned on "after auth/read/confirmed-write surfaces are stable" + deploy. |

### 3. Remove Duplicate Route

> **This section is the headline correction.** The brief that commissioned this audit suggested much
> of the change was already landed. Section 3 is the opposite: the entire BREAKING change at the
> heart of the proposal is **not done**, and the duplicate creation path is still live on `main`.

| Task | Verdict | Evidence | Reason |
|---|---|---|---|
| **3.1** remove/reject `POST /v1/universes` | **GATED** | `fantasy_daemon/api.py:755–810` | The route is **fully live and still creates universes** — `mkdir`, `ensure_universe_soul`, `canon/`, `output/`, `universe.json`. Held for canary + chatbot `ui-test` (AGENTS.md Rule 11/12) as a breaking public-surface removal. |
| **3.2** remove slug-name creation | **GATED** | `fantasy_daemon/api.py:356` (`_slugify`), `:770` | Slug ids are still minted from `name`, the exact semantics the proposal exists to retire. |
| **3.3** preserve non-create HTTP read/list | **GATED** | with 3.1 | Nothing to preserve until the removal runs. |

### 4. Verification

| Task | Verdict | Evidence | Reason |
|---|---|---|---|
| **4.1** run focused test suites | **OPEN** | — | Cannot be complete while 3.1/3.2 are unbuilt (the task names "affected HTTP API tests"). |
| **4.2** MCP create/status smoke test | **OPEN** | — | No recorded run against a temp data dir for this change. |
| **4.3** update docs teaching HTTP create | **GATED** | `docs/historical/ARCHITECTURE_PLAN.md:255`; handoff `:61,:115` | Blocked by 3.1/3.2 — docs cannot stop teaching a route that still works. |

---

## Follow-ups worth a lane (not done here)

1. **2.11 / 1.4a — the universe index has no consumer.** The `universes` table is written on every
   create but `list` never reads it. Either wire the learned name through, or record that the index
   is ownership/registry state and not a name index. Left OPEN rather than checked.
2. **2.0g — goal-bound run recording.** The spec's Branch-use-instance model is half-built.
3. **1.0c.2 / 2.0e — visibility ownership.** Split between this change and `universe-visibility`;
   `universe-visibility` §1 has undecided model questions blocking both.
4. **The stale header.** Fixed in this PR, but the general lesson: an implementation-status note
   pinned to a *branch* goes stale the moment that branch merges.

## Provenance

- Precedent: **PR #1515** (`universe-personification`, 11 tasks classified against the relay reshape).
- Failure class: memory `stale-backlog-rows-misdirect`.
- Reversal sources: `docs/design-notes/2026-07-02-universe-intelligence-relay-architecture.md`
  (relay reshape); `tinyassets/api/status.py:689` (AUTO-BIRTH host decision 2026-07-15).

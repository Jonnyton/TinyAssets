# Cross-family review: a universe needs an owner (PR #4012)

Reviewer: **Codex CLI** (`codex exec` via `scripts/peer_agent.py`), on its own
budget. Author: Claude. Two rounds, both transcripts below UNEDITED, including the
round-1 REJECT that was correct and the round-2 findings I acted on.

Why this file exists: `AGENTS.md` requires cross-family verification to leave a
durable artifact that gates landing, and `output/` is gitignored. The briefs are
included because a review is only as good as what it was asked to attack --
judging the verdicts needs the questions.

| Round | Head | Verdict | Findings |
|---|---|---|---|
| 1 | `8c5213bcbd5f8dad78915a43aa388ec4e2f3b16f` | REJECT | 2 P0, 1 P1, 1 P2 |
| 2 | `bc2f7a803cc2ee423062b57d82622c5930b12392` | REJECT | 0 P0, 1 P1, 2 P2 |

Round 1's two P0s were the boundary being half a boundary (`read_page` and
explicit-id `get_status` reaching an unowned directory whose `public` visibility
row the old backfill had already written) and my case-folded ownership returning a
directory spelling where an authority key was expected. Both verified in the code
before acting; both fixed.

Round 2 confirmed both fixed and found no new P0. Its findings were in the
pre-deploy safety gate, not the boundary: the inventory script was not actually
read-only, and its report implied "safe to deploy" where no heuristic can. Both
fixed. Its remaining `DISAGREE_CONCERN` -- that a heuristic cannot establish
safety -- is deliberately NOT closed by code: the report no longer claims to, and
the live-root run is a host row in `docs/host-actions.md`.

Three rounds is the cap (`AGENTS.md`). A third round was not opened: round 2
returned no P0 and its findings are fixed, and published evidence says a further
round more often finds weaknesses in tests written one round earlier than real
defects.

---

## Round 1 --- brief

```
# Refute this change: "a universe exists because an ownership row says so"

You are reviewing PR #4012 on branch `feat/a-universe-needs-an-owner`, head
`8c5213bcbd5f8dad78915a43aa388ec4e2f3b16f`, in THIS worktree
(`C:\Users\Jonathan\Projects\ta-wt-universe-owner`). It is one commit on top of
`origin/main`. Read it with `git show --stat HEAD` then `git show HEAD -- <path>`.

Your job is to REFUTE, not to agree. This is a cross-user-isolation change on an
authority path (`tinyassets/api/visibility.py` trips the repo's scope guard), so
the bar is: does an unowned directory remain reachable anywhere, and does an
OWNED universe lose anything it could do before?

## What it claims to do

A universe used to be "any directory under the data root whose name is not one
of `lance`/`output`/`runs`/`wiki`". It is now "a directory an ownership row
names": a `universe_acl` grant of any permission, or a `founder_home` binding,
compared case-folded on both sides, with a dotted name never a universe.

Readers routed: `_action_list_universes`, `_action_inspect_universe`,
`_action_switch_universe`, the `available` list both publish on a miss,
`visibility._discover_universe_ids` (which feeds `backfill_universe_visibility`
and the readiness gate), `branches._branch_dependents`, `branches._resolve_udir`,
`helpers._default_universe`, `helpers._designated_public_universe`. New
predicate: `daemon_server.owned_universe_ids` / `owned_universe_id`, plus
`helpers._owned_universe_dir_name` (which returns the DIRECTORY's spelling, not
the row's).

Deliberately NOT routed, with reasons stated in the code:
`daemon_server.sync_universes_from_filesystem` (a path index a self-hoster needs
before anything can grant), and `reset.universe_dirs` (destructive; a cut needs a
positive reason to believe a directory was a universe, and the migration backup
`docs/host-actions.md` protects owns nothing).

## Specific things to attack

1. **A missed reader.** Grep the tree yourself for anything that turns "a
   directory under `data_dir()`" into "a universe" and is not in the routed list.
   `tinyassets/api/status.py::_platform_has_work` was judged out of scope because
   it returns only a boolean — is that right? Is there a read path (wiki, runs,
   converse, get_status, engine MCP, scheduler, automations) that reaches an
   unowned directory's content by id without passing through inspect/switch?
2. **Fail-open on an unreadable store.** `_discover_universe_ids` now returns `[]`
   when the ownership lookup raises, `_available_universe_ids` returns `[]`, the
   listing returns a note, and the direct-id readers raise
   `_OwnershipUnavailable`. Find a path where a raised lookup ends up ACCEPTING a
   directory instead.
3. **An owned universe losing something.** The claim is that nothing a real,
   owned universe could do before is lost. `_default_universe`'s
   `UNIVERSE_SERVER_DEFAULT_UNIVERSE` branch now answers an unowned configured
   name only when `owned_universe_ids(base)` is empty. Construct a real
   deployment where that regresses — in particular the container default and the
   tray/local-single-tenant path, and a founder whose `founder_home` row exists
   but whose ACL grant does not (or vice versa).
4. **The case fold.** `_name_is_owned` folds both sides; `owned_universe_id`
   iterates `sorted(owned)` and returns the first fold match. With two rows
   `U-Mine` and `u-mine` both owned and one directory on disk, which one is
   returned and does any caller open a path that does not exist?
5. **Creation ordering.** Unlike the stale PR #2779 this change does NOT move the
   ownership grant before `udir.mkdir()` in `_action_create_universe`. So there
   is still a window where a directory exists and no row names it. Is that window
   reachable in a way that HARMS anything now that no reader serves an unowned
   directory? Say explicitly whether it must be fixed here or is safe to leave to
   the prune lane.
6. **The tests.** `tests/test_a_universe_needs_an_owner.py` is new (35
   assertions, 1 skipped on Windows). Eight existing test files were changed to
   bind a `founder_home` owner instead of seeding an ACL row, because a universe
   with zero ACL rows is PUBLIC and a grant would flip every public/anonymous
   fixture. Did any of those edits WEAKEN what its file was asserting? Look hard
   at `tests/test_universe_server_isolation.py` (its D0c model) and the forge
   probe in `tests/test_universe_visibility.py`. Note that `tests/conftest.py`'s
   autouse `_emulate_deployed_visibility_backfill` makes an undeclared universe
   resolve `public` everywhere except `test_universe_visibility` — check that this
   does not make any NEW assertion pass for the wrong reason.

## Return contract

Answer with a short verdict block, then findings. Use exactly these labels:

- `AGREE` — the claim holds, with the code citation that convinced you.
- `DISAGREE_EVIDENCE` — it does not hold, with `file:line` and the concrete
  input that breaks it.
- `DISAGREE_CONCERN` — a worry you cannot demonstrate from the code.

Rank findings P0/P1/P2. A P0 is a reachable cross-user read or an owned universe
that stops working. End with one line: `RECEIPT: APPROVE` or `RECEIPT: REJECT`
for head `8c5213bcbd5f8dad78915a43aa388ec4e2f3b16f`.

## HARD CONSTRAINTS ON HOW YOU WORK

- Do NOT dispatch sub-agents. No `scripts/peer_agent.py`, no `claude`/`codex`
  subprocess, no new worktree. You are the reviewer; review it yourself.
- Do NOT run the full suite. No `scripts/ci_required_tests.py`, no
  `pytest -m "not slow"`. At most run `tests/test_a_universe_needs_an_owner.py`
  with `--basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-cdx-own` using
  `C:/Users/Jonathan/Projects/TinyAssets/.venv/Scripts/python.exe`.
- Do NOT modify any tracked file. Read-only review.
- Budget ~12 minutes. Read the diff and the cited files and reason.
```

## Round 1 --- verdict (head `8c5213bc`)

**DISAGREE_EVIDENCE — REJECT.** The ownership boundary is incomplete, and changing an ID to the directory’s spelling can break an owned universe’s writes.

Reviewed head `8c5213bcbd5f8dad78915a43aa388ec4e2f3b16f`. Counterexamples below are code traces. The permitted Windows test run on 2026-09-26 passed: **36 passed, 1 skipped**. No tracked files modified.

1. **P0 — DISAGREE_EVIDENCE: previously public, unowned directories remain readable through `read_page`.**

   Concrete input: `_removed_universes_20260829/wiki/pages/notes/secret.md` exists; the old backfill left `public_read=true`, `visibility_level=public`; neither ownership table names the archive. Another authenticated user calls:
   ```python
   read_page(
       universe_id="_removed_universes_20260829",
       page="pages/notes/secret.md",
   )
   ```
   [universe_server.py:1869](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/universe_server.py:1869) forwards directly to wiki. [wiki.py:2666](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/wiki.py:2666) checks visibility, whose implementation checks public-read/grants/declaration, **not ownership** ([visibility.py:240](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/visibility.py:240)). An unrestricted page therefore returns its content.

   The new discovery filter neither removes nor invalidates the old public declaration. Explicit-id `get_status` has the same omission: directory existence plus visibility at [status.py:1233](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/status.py:1233). This defeats the claimed recovery for archives already exposed before deployment.

2. **P0 — DISAGREE_EVIDENCE: directory casing replaces the authorization ID and breaks owned writes.**

   Concrete Windows deployment: disk directory `U-Mine`; Alice has an admin ACL for `u-mine`, no `founder_home`; configured default is `u-mine`. Alice submits an otherwise-valid omitted-scope `write_graph(target="universe", operation="declare_loop", branch_id="B")`.

   Before this commit, the configured ID remained `u-mine`; Windows opened the directory and the ACL matched. Now [_designated_public_universe](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/helpers.py:208) returns `U-Mine`. [_universe_acl_error](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/universe.py:146) authorizes that spelling, but [universe_access_permission](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/daemon_server.py:5085) uses exact SQL IDs. No grant exists for `U-Mine`, so the write is denied. Visibility backfill does not repair the missing grant.

   Path spelling and authority identity must remain distinct.

3. **P1 — DISAGREE_EVIDENCE: a new preservation assertion passes because of the visibility emulation.**

   [test_a_universe_needs_an_owner.py:539](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tests/test_a_universe_needs_an_owner.py:539) creates directory/registration `u-mine`, grants `U-Mine`, never declares visibility, and expects listing to include `u-mine`.

   Production finds neither an exact grant nor a declared visibility level for `u-mine`, so it withholds the listing. [conftest.py:175](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tests/conftest.py:175) supplies the public visibility that makes this assertion pass. That assertion does not prove production preserves the mixed-case universe.

4. **P2 — DISAGREE_EVIDENCE: `_platform_has_work` is operationally significant despite returning a boolean.**

   Put `[{"lifecycle":"active"}]` in an unowned archive’s `work_targets.json`, with no actual active universe work. [status.py:1067](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/status.py:1067) reports work. With a live coordinator and stale activity, [last_activity_canary.py:306](C:/Users/Jonathan/Projects/ta-wt-universe-owner/scripts/last_activity_canary.py:306) consequently bypasses healthy-idleness handling and reports stale activity. This is a missed universe enumeration, although not itself a content disclosure.

The remaining requested attacks:

- **AGREE — guarded lookup failures:** listing, inspect/switch, and discovery refuse or return nothing when ownership lookup fails ([universe.py:1795](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/universe.py:1795), [visibility.py:403](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/visibility.py:403)). The P0 read bypass above never consults that lookup.
- **AGREE — two matching ownership rows:** `owned_universe_id` checks exact membership **before** sorted folded matches ([daemon_server.py:5041](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/daemon_server.py:5041)). `u-mine` returns `u-mine`; `U-Mine` returns `U-Mine`; `U-MINE` returns `U-Mine`. Its callers do not open the returned row spelling directly.
- **AGREE — ordinary ownership/default preservation:** either ownership table suffices. A same-spelling, existing owned container/tray default survives. I found no separate regression from suppressing an *unowned* configured default.
- **DISAGREE_EVIDENCE — creation-window premise:** visibility is declared public by default before the grant ([universe.py:5737](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/universe.py:5737)). Thus the missed wiki reader can reach the pre-grant directory. **Fix the read boundary here.** Moving the grant before `mkdir` is not independently required; with that boundary fixed, partial-directory cleanup can remain in the prune lane.
- **AGREE — existing fixture edits:** the D0c fixtures retain their public/private declarations and assertions. The forge probe still reaches the visibility gate: its added grant belongs to another actor, and public-read remains enabled. Those edits do not weaken their tested distinction.

RECEIPT: REJECT

---

## Round 2 --- brief

```
# Round 2: refute the fixes to your own round-1 findings

You reviewed head `8c5213bc` of PR #4012 and returned REJECT with two P0s, a P1
and a P2. Head is now `bc2f7a803cc2ee423062b57d82622c5930b12392` in THIS worktree
(`C:\Users\Jonathan\Projects\ta-wt-universe-owner`), two commits on the branch.
Your own verdict is at `output/codex-review-4012.md` — read it first, then
`git show HEAD` for what changed in response.

This is review round 2 of a three-round cap. Your job is to refute, and
specifically to check whether fixing round 1 created round 2's problems.

## What changed, and what I claim

**Your P0 1 (unowned directories readable via `read_page` / explicit-id
`get_status`).** The ownership requirement moved into
`permissions.universe_access_allows` (`tinyassets/api/permissions.py`), which
`visibility_permits` composes as its ceiling and which the wiki, runs,
automations, cloud, auto-ship and status readers call directly. One definition for
sixteen call sites. The duplicate I had briefly put in `visibility_permits` is
removed.

**Your P0 2 (directory casing replacing the authorization id).** Case-folding is
GONE. `daemon_server.owned_universe_id` now requires the directory name and the
row id to be identical. `helpers._owned_universe_dir_name` returns the name it was
given or `""`, and gained a path-traversal guard. A directory restored under a
different case is therefore unowned — hidden, never deleted — and
`scripts/universe_ownership_inventory.py` (new, read-only) exits 1 naming it.

**Your P1.** The mixed-case preservation test that only passed via conftest's
visibility emulation is gone, replaced by its inverse.

**Your P2.** `status._platform_has_work` is routed.

**Your creation-window ruling.** You said moving the grant before `mkdir` was not
independently required once the read boundary was fixed. I moved it anyway,
because once a universe nobody owns grants no capability, the window becomes a
functional hole for the creator's own seeding reads. Rollback now revokes the
grant and reports a revoke failure.

## Attack these specifically

1. **Did putting ownership in the shared gate break a legitimate read?** Trace
   callers of `universe_access_allows` that pass a universe id which may
   legitimately have no ownership row: a fresh install's `default-universe`, the
   container/tray default, a run record's universe, `auto_ship_actions`,
   `cloud_connections`, `interlocutor`, `universe_server.py:2732`. Find one where
   a real user loses something.
2. **Is the gate reachable before the grant exists anywhere?** I moved the create
   grant above `mkdir`, but check `first_contact`, the converse auto-birth route,
   `ensure_founder_home`, and `claim_founder_home`. Is there any path that
   materializes or reads a universe before any ownership row names it?
3. **Exact matching: who else compares a universe id?** I claim path component and
   authority key are now always the same string. Find a place that still
   normalizes, lowercases, or re-spells a universe id on one side only —
   `storage`, `scoped_reset`, `account_deletion`, `engine_mcp_http`,
   `consumer_selection`, `run_file_capture`.
4. **Fail-closed vs fail-silent.** `_universe_is_owned` in permissions.py returns
   False on any exception; `_owned_universe_id` in universe.py RAISES so a by-id
   reader can say "store unavailable" instead of "not found"; the listing returns a
   note; `_discover_universe_ids` returns `[]`. Is that set of behaviours
   inconsistent in a way that misleads a caller, or is there a path where an
   exception ends up ALLOWING something?
5. **The 65 fixture repairs.** Every one binds a `founder_home` row via
   `tests/conftest.py::own_universe` rather than granting an ACL row, because
   `universe_is_private` is "has any ACL rows" and granting would flip public
   fixtures to private. Check a sample (`tests/test_api_status.py`,
   `tests/test_interlocutor_tier.py`, `tests/test_self_auditing_tools.py`,
   `tests/test_get_status_primitive.py`) for an assertion that now passes for a
   different reason than it used to, or a test whose subject I quietly changed.
6. **One narrowed assertion.**
   `test_read_graph_connections_target_lists_own_http_connections_end_to_end` used
   to assert an empty connections list for a graph pinned at `u-not-mine`; it now
   asserts `error == "not_found"`. Is that a weakening?
7. **The inventory script.** It is the pre-deploy safety gate for this whole
   change. Is its universe signal (`soul.md`, `PROGRAM.md`, serial id) sufficient
   to catch a real universe that would go dark on the live root? What would it
   MISS? Also: is it genuinely read-only?
8. **`reset.universe_dirs` left alone.** It keeps a four-name denylist and so
   still `shutil.rmtree`s the migration backup `docs/host-actions.md` protects.
   I judged narrowing it out of scope for a read-only change. Agree or not.

## Return contract

Short verdict block, then findings. Use exactly these labels: `AGREE`,
`DISAGREE_EVIDENCE` (with `file:line` and the concrete input), `DISAGREE_CONCERN`.
Rank P0/P1/P2. A P0 is a reachable cross-user read or an owned universe that stops
working. End with one line: `RECEIPT: APPROVE` or `RECEIPT: REJECT` for head
`bc2f7a803cc2ee423062b57d82622c5930b12392`.

If your round-1 findings are genuinely fixed, say so plainly — "no new findings"
is a useful answer and I would rather have it than a manufactured third round.

## HARD CONSTRAINTS ON HOW YOU WORK

- Do NOT dispatch sub-agents. No `scripts/peer_agent.py`, no `claude`/`codex`
  subprocess, no new worktree. You are the reviewer; review it yourself.
- Do NOT run the full suite. At most
  `tests/test_a_universe_needs_an_owner.py` and
  `tests/test_universe_ownership_inventory.py`, with
  `--basetemp=C:/Users/Jonathan/AppData/Local/Temp/ta-cdx-own2` using
  `C:/Users/Jonathan/Projects/TinyAssets/.venv/Scripts/python.exe`. **Delete that
  basetemp when you are done** — this box has ~15 GB free and a wide run filled
  the disk earlier today, which reported itself as 174 test failures.
- Do NOT modify any tracked file. Read-only review.
- Budget ~15 minutes. Read the diff and the cited files and reason.
```

## Round 2 --- verdict (head `bc2f7a80`)

**DISAGREE_EVIDENCE — REJECT** for head `bc2f7a803cc2ee423062b57d82622c5930b12392`.

The round-1 findings are fixed. I found no new P0. Two narrower findings remain:

1. **P1 — DISAGREE_EVIDENCE: the inventory is not read-only.**

   Concrete input: `--data-dir` names an existing empty directory without `.tinyassets.db`. [universe_ownership_inventory.py:84](C:/Users/Jonathan/Projects/ta-wt-universe-owner/scripts/universe_ownership_inventory.py:84) calls `_connect`, which creates the database and sets WAL mode at [storage/__init__.py:826](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/storage/__init__.py:826). The missing-table exception is swallowed, and the command reports success.

   With a child directory, line 103 additionally calls `owned_universe_id` → `owned_universe_ids` → `initialize_author_server`. On an older existing database, that executes migrations—for example, adding `founder_home.platform_generated` at [daemon_server.py:567](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/daemon_server.py:567).

   The preservation test misses this: [test_universe_ownership_inventory.py:186](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tests/test_universe_ownership_inventory.py:186) initializes the store before its snapshot, populating the process-local initialization cache. Use a genuinely read-only SQLite connection and avoid initialization helpers.

2. **P2 — DISAGREE_EVIDENCE: the narrowed connections assertion loses isolation coverage.**

   Concrete input: `_GRAPH_ID = "u-not-mine"` with no ownership row, at [test_engine_mcp_server.py:1234](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tests/test_engine_mcp_server.py:1234).

   The new expectation is correct for that input, but [cloud_connections.py:128](C:/Users/Jonathan/Projects/ta-wt-universe-owner/tinyassets/api/cloud_connections.py:128) now returns before the connection ledger is queried. Previously, the empty-list assertion exercised the ledger’s universe filtering. A broken filter could now survive this negative case.

   Keep the refusal assertion, and make the original isolation case use a second owned, readable universe with no connection grants.

**P2 — DISAGREE_CONCERN: the inventory heuristic cannot establish “safe to deploy.”** A legacy, nonserial directory containing only `wiki/`, `notes.json`, or persisted work—but neither seed marker—gets classified as expected operational data and does not block deployment ([universe_ownership_inventory.py:56](C:/Users/Jonathan/Projects/ta-wt-universe-owner/scripts/universe_ownership_inventory.py:56), [line 163](C:/Users/Jonathan/Projects/ta-wt-universe-owner/scripts/universe_ownership_inventory.py:163)). I have not established that `paper-notes` has this shape on production. Unknown directories need inspection; absence of these three signals is not evidence that they are disposable operational buckets.

- **AGREE:** The shared gate closes the reported explicit-ID reads. I found no legitimate owned read newly denied among the cited callers.
- **AGREE:** Explicit creation grants before materialization; first contact reserves `founder_home` first; converse resolves that home before authorization.
- **AGREE:** Removing case-folded ownership resolution fixes the earlier authorization-ID substitution. The cited reset, deletion, engine, consumer, and capture paths yielded no new normalization regression.
- **AGREE:** The exception paths examined deny access. Their error reporting varies, but I found no exception-driven allowance.
- **AGREE:** The sampled fixture repairs preserve their visibility/tier assertions. The self-auditing fixtures now explicitly test an existing universe; they no longer cover an empty installation.
- **AGREE:** Leaving destructive reset behavior outside this read-boundary patch is reasonable. Its existing backup-deletion hazard remains; this review does not endorse it.

Verification: Windows, 2026-09-26, requested Python executable and basetemp, `pytest -q tests/test_a_universe_needs_an_owner.py tests/test_universe_ownership_inventory.py`: **63 passed**. No tracked files modified by this review.

Automatic approval review rejected basetemp deletion twice with “blocked by policy.” `C:/Users/Jonathan/AppData/Local/Temp/ta-cdx-own2` therefore remains.

RECEIPT: REJECT

# Cheat-loop runtime residue and next-wave audit

**Date:** 2026-07-27 PDT / 2026-07-28Z  
**Environment:** Windows, clean worktree at exact `origin/main`
`30c962c714d32f4bfff9549925ed165ddc55314c`  
**Mode:** read-only source, ownership, and live GitHub inventory; no production,
workflow, label, issue, PR, or auto-merge mutation  
**OpenSpec:** `openspec/changes/retire-cheat-loop/`

## Outcome

PRs #1812, #1815, and #1818 have removed the site/announcement wave, active
privileged skill/catalog routes, and seven platform-owned loop-team prompt
assets. The change now has 9 checked and 29 unchecked tasks.

There is no immediately claimable verified runtime deletion wave because the
required tests are owned by active L37/L49 authority lanes. The largest shared
runtime dependency remains task 2.1, the filing-only stop-writer, but it must
wait for exact test carve-outs and a deploy/drain proof.

The smallest safe repository-only implementation wave is available now:
restack the existing fail-closed GitHub-state retirement inventory/migrator for
tasks 3.6/3.7. Its tests are colocated under `scripts/`, so it does not collide
with broad `tests/` claims. It MUST expose no live mutator, MUST NOT disable a
workflow or change labels/PR auto-merge state, and MUST leave tasks 3.6/3.7
unchecked until fresh receipt-backed apply evidence exists.

## Landed retirement boundary

- #1812: production/rollback site presentation and automatic announcement
  composition retired; generic explicit outbound primitives preserved.
- #1815: `loop-uptime-maintenance` and every active provider catalog route
  retired; incident evidence moved to historical storage; generic alarms,
  diagnosis, approval, remediation, and user-buildable workflows preserved.
- #1818: core-team manifest and six platform-owned role souls retired; generic
  soul/daemon machinery and user-published role context preserved.

These source waves do not prove runtime/data/live-state retirement.

## Remaining source families

| Tasks | Current residue | Gate / owner |
|---|---|---|
| 1.1, 2.1 | `file_bug` still creates trigger receipts, enqueues `bug_investigation`, writes Investigation sections, and returns trigger/investigation metadata | Exact wiki tests overlap L37/L49; completion also needs filing-only deploy plus old writer/API/worker/plugin drain/fence proof |
| 2.2-2.5 | `bug_investigation.py`, fantasy-daemon special execution/write-back, env/config defaults, receipt store, and persisted rows remain | 2.1 first; #1803 authority reconciliation; locked migration/barrier; ambiguous/unreadable authority remains fenced |
| 2.6 | Hard-coded patch-request claimant/writer/checker classification persists in market/universe/work-target paths and plugin/tests | Active market/universe/test owners; preserve generic pickup incentives, directed-daemon authority, and user-owned soul dispatch |
| 2.8 | Hidden `community_change_context` action/wrapper/action-map and plugin/tests remain after site callers were removed | `retire-legacy-live-mcp-tools` 4.1/4.4 plus active control-station/universe owners |
| 3.1-3.4 | Auto-ship validator, PR opener, ledger, actions, aliases, health/status/config/reset knowledge, tests, and production data remain | `api/status.py` owned by L37; effectors owned by L49; broad tests owned; operator retention proof required |
| 3.5 | Announcement files are absent and `post_x_update.py` is generic; one retired comment remains in `validate_patch.py` | File owned by L49; final immediate-pre-merge run drain remains |
| 3.6-3.7 | Retired labels and workflow-owned auto-merge instructions remain live | Inventory-only migrator is safe; apply requires fresh exhaustive receipts, producer quiescence, attribution, and host review for ambiguity |
| 4.1-4.3 | Community-named watcher/workflow still carries self-heal input, actions/issues write authority, self-dispatch, and retired label | Exact workflow tests overlap L37/L49; disable/cancel/drain live workflow before merge/apply |
| 4.4 | Nine-heading canonical removal manifest remains | All generic guarantees must first move to surviving owners |
| 5.2-5.3 | Source assets are clean; live page/universe, publication provenance/pagination, stored-role, and synthetic fixture proof remain | Live/source review and released test ownership |
| 6.1, 6.3-6.7 | Plugin rebuild, final suites/scans, rendered connector proof, organic-use evidence, exact spec foldback/delete/archive remain | All source/data/live migrations first |

## Next safe repository wave: inventory-only GitHub-state migrator

Existing branch `codex/retire-loop-github-state` contains the reviewed shape.
Replay only its migrator-specific payload onto current main; do not import its
old snapshot parent or stale STATUS stack.

Exact intended write-set:

```text
scripts/retire_cheat_loop_github_state.py
scripts/retire_cheat_loop_github_state_test.py
docs/ops/2026-07-26-cheat-loop-github-state-retirement.md
openspec/changes/retire-cheat-loop/specs/development-coordination-runtime/spec.md
openspec/changes/retire-cheat-loop/tasks.md
docs/audits/2026-07-26-retire-cheat-loop.md
STATUS.md
REFLECTION.md
.agents/worktrees.md (retire lane only)
```

Candidate replay commits:

```text
fa954aad 4b4fcbb5 56fea841 c6192dec 3e0ca66d
cad40646 77cef3bc 1a8943c4 4a4b9efe d40173a2
```

Fresh verification on the existing payload:

- `python scripts/retire_cheat_loop_github_state_test.py`: 45/45 pass.
- `openspec validate retire-cheat-loop --strict`: pass.
- The CLI has no live mutator; apply behavior remains dependency-injected.
- Tasks 3.6/3.7 remain unchecked.

## Highest-impact blocked runtime wave: task 2.1

Exact intended write-set after claims release:

```text
tinyassets/api/wiki.py
packaging/claude-plugin/plugins/tinyassets-universe-server/runtime/tinyassets/api/wiki.py
tests/test_api_wiki.py
tests/test_bug_investigation_wiring.py
tests/test_file_bug_compact_response.py
docs/audits/2026-07-27-retire-cheat-runtime-residue.md
openspec/changes/retire-cheat-loop/tasks.md
STATUS.md
REFLECTION.md
.agents/worktrees.md (retire lane only)
```

Task 2.1 removes only receipt creation, enqueue, Investigation rendering, and
trigger/investigation response fields. It deliberately leaves filing-effort
routing for task 1.1 and retains receipt readers/store/data until task 2.5.
Stopping new legacy state is the hard precondition for the locked 2.5
migration, which then unlocks 2.2/2.3 deletion and background branch authority.

## Fresh live GitHub evidence

Read-only queries on 2026-07-27 PDT / 2026-07-28Z found:

- `community-loop-watch.yml` remains active (workflow id `268723091`).
  Scheduled run `30332819781` failed and opened issue #1828, “Community loop
  watch red”; self-heal run `30332848126` was in progress. Run `25906701411`
  has remained queued since 2026-05-15.
- `auto-enroll-merge.yml` remains active (workflow id `317815472`); recent run
  `30332455384` succeeded.
- 95 PRs were open; 21 had `autoMergeRequest`. All 21 reported
  `app/github-actions`, SQUASH, same-repository/main tuples. Workflow deletion
  alone would leave those durable instructions active.
- All 28 retired label definitions remain live: the 27 exact family labels
  plus `ready_for_checker`. The newly opened issue #1828 invalidates the old
  label receipt, so apply requires a fresh exhaustive inventory.
- `AUTO_FIX_DISABLED=true` remains a live repository variable and belongs to
  later operator config/data retirement.
- Announcement workflow/script source is absent, no announcement workflow is
  registered, and generic `post_x_update.py` has no retired wording.

These counts are volatile inventory, not apply authority.

## Preserved invariants

Retirement MUST preserve:

- Goal/canonical and BranchTask graph composition;
- generic branch execution and completed-run reuse;
- explicit requester pickup incentives and authorized directed-daemon choice;
- user-owned soul dispatch and user-published role context;
- generic KEEP/APPROVE evaluation;
- generic status/liveness and explicit effect/GitHub primitives;
- read-only uptime observation and a separately authorized incident sink.

No trigger receipt, renamed loop, hidden platform team, standing auto-merge, or
workflow-dispatch self-heal may become the successor.

## Coordination decision

1. Land this audit/foldback and release the completed #1818 source paths.
2. Restack the inventory-only GitHub-state migrator as the next repository
   wave; keep live apply inaccessible and tasks 3.6/3.7 unchecked.
3. Ask L37/L49 to land or carve out the exact task-2.1 tests.
4. Then implement/deploy task 2.1 and prove all old receipt writers drained or
   fenced before checking it complete.
5. Do not delete `auto-enroll-merge.yml` while 21 durable instructions remain;
   do not delete/replace the community watcher before its active/queued runs
   are disabled and drained.


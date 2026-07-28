# Cheat-loop runtime residue and next-wave audit

**Date:** 2026-07-27 PDT / 2026-07-28Z  
**Environment:** Windows; original audit at exact `origin/main`
`30c962c714d32f4bfff9549925ed165ddc55314c`; claim/source revalidation
2026-07-28 at main `52475559` and PR #1835 head `1723aa86`
**Mode:** read-only source, ownership, and live GitHub inventory; no production,
workflow, label, issue, PR, or auto-merge mutation  
**OpenSpec:** `openspec/changes/retire-cheat-loop/`

## Outcome

PRs #1812, #1815, and #1818 have removed the site/announcement wave, active
privileged skill/catalog routes, and seven platform-owned loop-team prompt
assets. The change now has 9 checked and 29 unchecked tasks.

Exact branch/index/worktree revalidation proved task 2.1's canonical source,
plugin mirror, and three tests are clear after narrowing the public-read,
personification, and outbound claim boundaries and deleting the landed
control-station row. The repository stop-writer slice is therefore claimable
after PR #1835. A filing-only deploy plus exhaustive old-writer drain/fence
proof still gates task 2.1 completion.

The intermediate repository-only wave landed through PR #1830: a fail-closed
GitHub-state retirement inventory/migrator for tasks 3.6/3.7. PR #1835 closes
its receipt schemas while exposing no live mutator, disabling no workflow, and
changing no labels or PR auto-merge state. Tasks 3.6/3.7 remain unchecked until
fresh receipt-backed apply evidence exists.

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
| 1.1, 2.1 | `file_bug` still creates trigger receipts, enqueues `bug_investigation`, writes Investigation sections, and returns trigger/investigation metadata | Source/mirror/tests are claim-clear; task 2.1 is next after #1835, while completion still needs filing-only deploy plus old writer/API/worker/plugin drain/fence proof |
| 2.2-2.5 | `bug_investigation.py`, fantasy-daemon special execution/write-back, env/config defaults, receipt store, and persisted rows remain | 2.1 first; then #1803's dark authority store/reconciler core; then locked 2.5 migration/barrier; activation/foldback follows migration; ambiguous/unreadable authority remains fenced |
| 2.6 | Hard-coded patch-request claimant/writer/checker classification persists in market/universe/work-target paths and plugin/tests | Active market/universe/test owners; preserve generic pickup incentives, directed-daemon authority, and user-owned soul dispatch |
| 2.8 | Hidden `community_change_context` action/wrapper/action-map and plugin/tests remain after site callers were removed | `retire-legacy-live-mcp-tools` 4.1/4.4 plus active control-station/universe owners |
| 3.1-3.4 | Auto-ship validator, PR opener, ledger, actions, aliases, health/status/config/reset knowledge, tests, and production data remain | `api/status.py` stays with the personification-relay lane; effectors stay with outbound-boundary; operator retention proof required |
| 3.5 | Announcement files are absent and `post_x_update.py` is generic; three retired loop-era docstring references remain in canonical and plugin-mirror `validate_patch.py` | Canonical effector stays with outbound-boundary; plugin rebuild is task 6.1; final immediate-pre-merge run drain remains |
| 3.6-3.7 | Retired labels and workflow-owned auto-merge instructions remain live | Inventory-only migrator is safe; apply requires fresh exhaustive receipts, producer quiescence, attribution, and host review for ambiguity |
| 4.1-4.3 | Community-named watcher/workflow still carries self-heal input, actions/issues write authority, self-dispatch, and retired label | Repository workflow/tests are claim-clear; disable/cancel/drain the live workflow before merge/apply |
| 4.4 | Nine-heading canonical removal manifest remains | All generic guarantees must first move to surviving owners |
| 5.2-5.3 | Source assets are clean; live page/universe, publication provenance/pagination, stored-role, and synthetic fixture proof remain | Live/source review and released test ownership |
| 6.1, 6.3-6.7 | Plugin rebuild, final suites/scans, rendered connector proof, organic-use evidence, exact spec foldback/delete/archive remain | All source/data/live migrations first |

## Landed inventory wave and post-merge hardening

PR #1830 selectively restacked the inventory-only GitHub-state migrator onto
current main and merged as `52475559`. Draft PR #1820 is closed as superseded;
sibling snapshot PR #1819 remains parked under the separate task-5.3 proof
boundary. The historical source branch targeted the unmerged snapshot branch,
so its commit list below remains provenance only and is not replay authority.

The merged wave used this exact write-set:

```text
scripts/retire_cheat_loop_github_state.py
scripts/retire_cheat_loop_github_state_test.py
docs/ops/2026-07-26-cheat-loop-github-state-retirement.md
openspec/changes/retire-cheat-loop/specs/development-coordination-runtime/spec.md
openspec/changes/retire-cheat-loop/tasks.md
docs/audits/2026-07-27-retire-cheat-runtime-residue.md
STATUS.md
REFLECTION.md
.agents/worktrees.md (retire lane only)
```

Source commits for a selective file-level squash (never direct replay):

```text
fa954aad 4b4fcbb5 56fea841 c6192dec 3e0ca66d
cad40646 77cef3bc 1a8943c4 4a4b9efe d40173a2
```

Commit `56fea841` includes a stale `STATUS.md` hunk, and the final documentation
also semantically supersedes an omitted interleaved receipt commit. Restore the
three final new files from `d40173a2`, apply only the final spec/task delta, and
derive current coordination from current main. Do not cherry-pick the list or
import any commit's STATUS/worktree state.

Historical verification on the source payload:

- `python scripts/retire_cheat_loop_github_state_test.py`: 45/45 pass.
- `openspec validate retire-cheat-loop --strict`: pass.
- The CLI has no live mutator; apply behavior remains dependency-injected.
- Tasks 3.6/3.7 remain unchecked.

Merged selective-restack verification:

Freshness update 2026-07-28: the current-main restack landed through PR #1830
as `52475559`. Exact-current Opus 5 review found that an absent `rel="next"`
after a full 100-row response was still an ambiguous truncation oracle, not
completion proof. The follow-up binds the explicit page-size request into the
receipt, rejects a full terminal page during both collection and stored-receipt
validation, retains the canonical request endpoint so offline validation
re-derives the request digest and bound, and raises the focused suite to 53
tests while preserving #1830's closed receipt envelope. It still exposes no
live mutator and does not complete tasks 3.6/3.7 or authorize any GitHub-state
change. Claude Opus 5's exact-current narrow review returned `APPROVE` after
mutation-testing the live/stored terminal guards, request/page-size binding,
request-digest recomputation, oversized-page checks, and encrypted-log guard;
deleting each guard added the intended focused-test failure.

Selective-restack verification on
`codex/restack-retire-loop-github-state-20260727`:

- The initial payload at `fab12790` restored the three files byte-identically
  from `d40173a2`; `f7e9234b` then intentionally changes the script, test, and
  runbook to close re-digested receipt-schema bypasses.
- Only the reviewed final spec/task delta was applied; current-main STATUS,
  worktree, snapshot, website, and prior receipt ancestry were not imported.
- `python scripts/retire_cheat_loop_github_state_test.py`: 46/46 pass after
  adding a receipt-schema regression.
- `python -m py_compile` for the migrator and tests: pass.
- Strict target and all-OpenSpec validation: 60/60 pass. The source restack
  note said 59/59; exact tree comparison proved the merged and reviewed trees
  identical, and a fresh count corrected that historical figure to 60/60.
- CLI subcommands remain exactly `inventory`, `plan`, and `verify`; tasks
  3.6/3.7 remain unchecked and no live apply was invoked.
- Offline verification rejects re-digested receipts with non-dry-run execution,
  unknown top-level authority, connection authority, or unreviewed pagination
  mode; connection/page/terminal envelopes are closed schemas.
- Exact head `d5b31a3f` received independent Codex security/spec and Claude
  Opus 5 approval before PR #1830 merged as `52475559`.

Post-merge receipt-schema hardening on
`codex/post1830-retire-next-20260728`:

- Three new regressions first failed because re-digested label receipts
  accepted unknown definition fields, unknown association fields, and
  non-empty label `planned_actions`.
- Commit `d95cef1d` closed both peer-record key spaces and rejected every
  non-empty label action list while label apply remains unimplemented. Claude
  Opus 5 then required a collector-contract regression before approval.
- Commit `55a932b0` binds the live collector through build and verify, closes
  peer-record scalar types and values, and converts malformed label action
  containers into fail-closed `PlanError` results.
- Opus approved the adaptation and found one non-blocking error-contract gap;
  commit `cf48df9e` rejects every non-empty label action array before item
  normalization, so malformed members return `PlanError` instead of traceback.
- The complete focused suite passes 54/54; Ruff, `py_compile`, `git diff
  --check`, strict target OpenSpec, and all 60 strict OpenSpec validations pass.
- The CLI remains exactly `inventory`, `plan`, and `verify`; no live mutator or
  auto-merge semantic changed, and tasks 3.6/3.7 remain unchecked.

Current-main terminal-oracle integration on 2026-07-28:

- The Opus-approved terminal-page follow-up was restacked after PR #1835
  landed, preserving both the closed nested receipt schemas and request-bound
  full-terminal-page rejection.
- The combined focused suite passes 61/61; Ruff, strict target OpenSpec, and
  all 60 strict OpenSpec validations pass.
- The CLI still exposes no live mutator and tasks 3.6/3.7 remain unchecked.
- Exact-current Opus review returned `ADAPT`: the fail-closed boundary lacked
  an operator recovery note, the Unicode test did not distinguish `[0-9]`
  from `\d`, a full second terminal page was unpinned, and stored request
  endpoints were digest-bound but not repository-scope validated. All four
  adaptations were folded before publication; the focused suite remains 61/61
  with the semantic distinctions pinned as subtests.

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
Stopping new legacy state is the first hard precondition. The required order is
task 2.1, then #1803's dark authority store/reconciler core, then the locked 2.5
migration, then background-authority activation/foldback. Task 2.5 can also
unlock 2.2/2.3 deletion, but it does not unlock the authority core that it
depends on.

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

1. #1818, this audit (#1829), and the inventory-only migrator (#1830) landed;
   #1820 is closed as superseded and snapshot PR #1819 remains parked.
2. Merge PR #1835 with live apply inaccessible and tasks 3.6/3.7 unchecked.
3. Claim the now-clear task 2.1 source/mirror/tests as the next runtime wave.
4. Implement/deploy task 2.1 and prove all old receipt writers drained or
   fenced; then land #1803's dark authority store/reconciler core before the
   locked 2.5 migration; activate/fold back background authority after migration.
5. Do not delete `auto-enroll-merge.yml` while 21 durable instructions remain;
   do not delete/replace the community watcher before its active/queued runs
   are disabled and drained.

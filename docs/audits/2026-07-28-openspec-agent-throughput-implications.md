# OpenSpec and Agent Delivery Throughput: Diagnosis and Recovery System

**Filed:** 2026-07-28
**Initial provider:** Codex (`codex-gpt5-desktop-throughput`)
**Repository base:** `origin/main@2ddd0a646a1d1b2ec156d69b211789c9f24d8f39`
**Local OpenSpec:** 1.4.1
**Review gate:** Claude must re-check the primary sources and current repository
state before implementation. Until that verdict is `approve` or `adapt`, this
report and its OpenSpec change are planning authority only.

## Executive judgment

TinyAssets does not primarily have a slow-agent problem. It has an
**unbounded-arrival and work-in-progress problem**:

- the agents are producing substantial work;
- the system turns vision, audits, review findings, host actions, and future
  programs into active OpenSpec changes and STATUS work;
- new obligations arrive faster than changes archive;
- broad goals keep sessions alive across many contexts instead of ending at a
  small verified delivery boundary.

The result feels like low throughput because the denominator grows faster than
the numerator. From 2026-07-25 through the audit base, `origin/main` gained 100
commits, but 20 active OpenSpec change directories were added while only 5
changes were archived. The current tree has 34 active changes, 1,200 checkbox
tasks, and 834 unchecked tasks. This is high activity with negative backlog
burn-down.

The highest-leverage correction is not another planning layer. It is a small,
enforceable pull system:

1. PLAN/design/audits hold the full vision and future inventory.
2. An OpenSpec change represents one current delivery slice with one intent,
   one owner, one branch/PR, and at most 12 verifiable tasks.
3. Each exact session-specific provider identity owns at most one active
   delivery change; global delivery WIP is reported alongside this local limit,
   and renaming a session to evade the limit is a process violation.
4. New change admission pauses when active WIP exceeds capacity; security/P0
   exceptions must be explicit.
5. Dispatch chooses the smallest unblocked slice that removes a shared
   dependency, and the session ends when that slice is verified and folded
   back.
6. Findings discovered while building go to the idea feed unless they are
   required for the current acceptance contract.

## Source freshness

Primary sources were checked on 2026-07-28:

- [OpenSpec: existing projects](https://openspec.dev/docs/existing-projects)
- [OpenSpec: team workflow](https://openspec.dev/docs/team-workflow)
- [OpenSpec: writing good specs](https://openspec.dev/docs/writing-specs)
- [OpenAI: how OpenAI uses Codex](https://openai.com/business/guides-and-resources/how-openai-uses-codex/)
- [Anthropic: effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)
- [Anthropic: harness design for long-running application development](https://www.anthropic.com/engineering/harness-design-long-running-apps)
- [Kanban University: official guide](https://kanban.university/kanban-guide/)

The repository measurements below were taken in a clean worktree from current
`origin/main`. The original primary checkout was also measured because it is
what long-running desktop sessions can inherit.

## What OpenSpec is designed to do

OpenSpec's brownfield guidance is explicit:

- do not document or convert the whole existing codebase;
- write specs for the small behavior slice about to change;
- treat existing requirements/design documents as exploration context, not as
  material to import wholesale;
- let as-built specs grow as real changes archive;
- one change should have one intent that fits one focused session;
- map one change to one branch, one owner, and one PR containing both the
  artifacts and implementation.

OpenSpec itself does not impose git, WIP, or task-size policy. Those are team
conventions. TinyAssets adopted artifact rigor but did not add the corresponding
admission and WIP controls, so the CLI validates an ever-growing inventory
without distinguishing deliverable work from future target programs.

## What agent guidance says

OpenAI reports that Codex performs best on well-scoped work roughly equivalent
to about an hour of human work or a few hundred lines, with large changes first
planned in Ask mode and then executed as a focused Code task.

Anthropic's first long-running-agent experiments found that a high-level multi-day
prompt leads agents to attempt too much, cross context boundaries mid-feature,
and spend later contexts reconstructing state. Their effective pattern is one
feature at a time, a clean commit, explicit progress artifacts, and
end-to-end verification. Their newer generator/evaluator harness experimented
with per-sprint contracts, but the article's later simplification work removed
sprint decomposition for a stronger model. OpenAI likewise expects useful task
size to grow with model capability. The 12-task ceiling proposed here is
therefore a dated 2026-07-28 calibration to review on 2026-08-11, not an
architectural constant.

Kanban adds the missing system-level constraint: limit WIP to capacity and pull
new work only when a delivery slot opens. Maximizing utilization and starting
more work degrades flow through context switching. Completed work is more
valuable than started work.

## TinyAssets measurements

### OpenSpec inventory

Fresh command: `openspec list --json`.

| Measure | Current |
|---|---:|
| Active change directories | 34 |
| Total checkbox tasks | 1,200 |
| Completed tasks | 366 |
| Unchecked tasks | 834 |
| Median unchecked tasks per change | 16.5 |
| Changes with more than 25 unchecked tasks | 12 |
| Changes with more than 50 total tasks | 6 |
| Changes with more than 20 total tasks | 23 |
| Active changes not mentioned in `STATUS.md` | 12 |

The largest remaining changes are:

| Change | Remaining / total |
|---|---:|
| `distributed-execution` | 90 / 108 |
| `harden-background-branch-execution-authority` | 77 / 77 |
| `data-commons-contribution` | 57 / 57 |
| `complete-plan-gated-platform-targets` | 50 / 58 |
| `demand-side-signals` | 49 / 49 |
| `constrain-set-engine-provider-authority` | 48 / 83 |

Twelve active changes are not on the live board. Those twelve alone contain 300
unchecked tasks, including the 90-task `distributed-execution` program. This
means neither OpenSpec nor STATUS is a complete execution view:

- OpenSpec contains target programs that are not active delivery lanes.
- STATUS contains host actions, monitoring, concerns, programs, and delivery
  lanes together.

### Arrival versus closure

Using the last commit before 2026-07-25 as the comparison base:

| Measure | 2026-07-25 through current main |
|---|---:|
| Commits | 100 |
| Commits touching OpenSpec | 52 |
| Coordination/spec/document-only commits | 65 |
| Commits touching runtime/tests/tooling | 31 |
| Newly added active changes | 20 |
| Newly added archives | 5 |

The full-product audit on 2026-07-25 listed 20 relevant active changes with 507
unchecked tasks. The current inventory has 834 unchecked tasks. The exact
cohorts are not identical, so the difference is not a cycle-time metric, but it
is decisive evidence that task arrival materially exceeded closure while
agents were shipping.

The 65 coordination/spec/document-only count uses the strict classification
"every touched path is a coordination/spec/document path." A Claude recompute
using the broader inverse classification "does not touch runtime/tests/tooling"
found 69. Both preserve the same conclusion; neither is a productivity score.

### Coordination overhead

| Surface | Current evidence |
|---|---:|
| `STATUS.md` | 59 lines but 20,238 bytes against ~4 KiB guidance |
| Registered git worktrees | 374 |
| `.agents/worktrees.md` | 1,399 lines / 100,365 bytes |
| `worktree_status.py` | timed out after 124 seconds in the opening audit |
| Primary checkout | 240 commits behind `origin/main`, heavily dirty |

`worktree_status.py` performs multiple git subprocesses for each registered
worktree. With 374 worktrees, a required orientation command is itself an
expensive operation. The primary checkout's 240-commit lag also means a session
started there pays a reconciliation tax before it can reason about current
work.

The claim system exposed a related design defect: active rows claim
`STATUS.md`, `.agents/worktrees.md`, and `REFLECTION.md` as exclusive files.
That makes any unrelated new lane appear to overlap on the very shared files
used to coordinate lanes.

## Root causes

### 1. “Touch it → spec it” was expanded into “spec the vision”

The project rule is sound when interpreted as “before changing behavior,
backfill the touched capability and add this change's delta.” It becomes
counterproductive when a high-level goal asks an agent to bring the full
platform vision into OpenSpec. That is the exact bulk-conversion pattern
OpenSpec warns against.

### 2. Target-only planning is treated as active delivery

Large target changes are merged to main with 30–108 tasks and remain active.
This preserves design work but makes `openspec list` an unbounded program
inventory instead of a list of current changes. A valid proposal landing is
counted as progress while adding far more implementation obligations than the
PR retires.

### 3. Goals have no terminal slice boundary

“Complete the full platform” is not an agent task. It is a product direction.
The goal stays unfinished by definition, so agents continue through compaction,
reorientation, audits, new sibling proposals, reviews, and foldback. The
session can be productive for days and still never reach a credible terminal
condition.

### 4. Discovery automatically creates execution demand

Audits and reviews are good at finding gaps. The current process often promotes
each gap immediately into STATUS/OpenSpec. This couples better understanding to
a larger active queue. Backlog growth therefore becomes a success side effect.

### 5. WIP is limited by subscriptions, not by delivery capacity

Multiple Claude and Codex sessions can stay busy, but review, integration,
deployment, host action, and live acceptance are narrower bottlenecks. Filling
every model slot maximizes local utilization while work accumulates before
those bottlenecks.

### 6. Coordination artifacts have become work

The 100-commit sample contains much useful implementation, but 65 commits are
coordination/spec/document-only. The worktree registry, claim board, repeated
restacks, exact-head review rounds, and foldback commits are load-bearing, yet
their volume now rivals delivery. This is a signal to reduce lane count and
change size, not add more fleet management.

## Production system to build

### A. A measured OpenSpec flow inspector

Add `scripts/openspec_flow.py` with text and JSON output. It shall:

- enumerate active changes and task progress without mutating them;
- map change names to STATUS rows and provider claims;
- classify complete-but-unarchived, in-flight, queued, untracked, and
  oversized changes;
- report total WIP, unchecked tasks, per-provider active-change count, broad
  collision atoms, and creation/archive flow over a requested git window;
- recommend finish-first candidates by fewest unchecked tasks, then shared
  dependency impact;
- return non-zero in enforcement mode when a newly introduced change violates
  admission policy.

Run audit mode on demand at dispatch/triage time and run admission mode only
when creating or claiming a change. This command is explicitly **not** a fifth
mandatory session-start ritual.

### B. A narrow admission policy

For new changes:

- one intent expressible in one sentence;
- one branch, one owner, one PR;
- at most 12 task checkboxes;
- explicit acceptance and verification;
- no “complete/full platform/vision” umbrella change;
- design/PLAN material is referenced, never bulk-converted;
- no new change while the same exact session-specific provider identity owns
  another active change;
- global delivery WIP is always reported, and minting a new provider suffix to
  evade the limit is a review violation;
- P0/security exceptions require the exception and displaced WIP to be named.

Existing oversized changes are grandfathered for diagnosis, not blessed. They
must be split only when a concrete next slice is ready; do not mechanically
create hundreds of child changes.

The 12-task ceiling counts all task checkboxes, completed or incomplete. It is
the 2026-07-28 v1 calibration and must be reviewed on 2026-08-11 against cycle
time and model capability rather than retained by inertia. Twenty-nine of the
34 audit-basis active changes exceed it today.

### C. Finish-first dispatch

Default selection order:

1. complete-but-unarchived change;
2. smallest unblocked change already in progress;
3. smallest dependency-removal slice for a P0/uptime surface;
4. only then admit a new change.

Host-only and live-acceptance items do not consume an implementation WIP slot.
They remain visible as blockers, but an agent must not keep a coding session
alive waiting for them.

### D. Three flow metrics

Record per-day snapshots, not a permanent task history:

- active delivery WIP;
- archive-to-admission ratio;
- median delivery cycle time;
- unchecked task count is a diagnostic fourth metric, not a productivity
  score.

The first recovery target is not “finish 834 tasks.” It is:

- archive/admit ratio above 1 until WIP is healthy;
- no provider with more than one active change;
- no new umbrella changes;
- `openspec list` becomes a current-delivery view again.

## Immediate operating recommendation

Until the guard lands:

1. Stop the two broad “full platform vision” goals after their current safe
   commit/PR boundary; do not discard their work.
2. Do not ask either session to “finish the whole OpenSpec task list.”
3. Assign each fresh session one named change slice with a terminal PR/archive
   condition.
4. Run a 72-hour admission freeze for non-P0 new change directories.
5. Archive `scoped-wiki-canary-token` after verifying its synced state.
6. Review the 12 OpenSpec changes absent from STATUS; park target-only programs
   outside the active delivery view rather than spawning child tasks.
7. Keep at most four implementation lanes total only if review/integration can
   drain four; otherwise lower the limit.
8. Use one Claude/Codex pair for implementation/review, not two perpetual
   independent full-product programs.

## Adopt / adapt / avoid / defer

| Decision | Implication |
|---|---|
| **Adopt** | OpenSpec's delta-first, one-change/branch/PR loop. |
| **Adopt** | One feature/slice per agent session with a clean commit and evidence. |
| **Adapt** | Add a TinyAssets flow inspector because OpenSpec intentionally does not enforce git or WIP policy. |
| **Adapt** | Use PLAN as vision truth and OpenSpec as current behavioral delta truth. |
| **Avoid** | Bulk-converting the full architecture/vision into active change tasks. |
| **Avoid** | Measuring productivity by tasks created/completed across differently sized changes. |
| **Avoid** | Keeping agents alive through host-action or acceptance blockers. |
| **Defer** | Destructive worktree cleanup; it is host-controlled and needs a separate reviewed sweep. |
| **Watch** | Whether the 12-task ceiling is too high/low after two weeks of cycle-time data. |

## Cross-provider review packet

Claude reviewer must:

1. re-open the OpenSpec, OpenAI, Anthropic, and Kanban primary sources;
2. recompute current `openspec list --json` totals;
3. verify the git-window and worktree measurements;
4. challenge whether the proposed limits create harmful ceremony or hide
   necessary long-horizon work;
5. return `approve`, `adapt`, `defer`, or `reject`;
6. identify the smallest safe implementation if the verdict is `approve` or
   `adapt`.

## Worktree landing packet

- Branch: `codex/openspec-throughput-system`
- Worktree: `C:\Users\Jonathan\Projects\wf-openspec-throughput-system`
- Base: `origin/main@2ddd0a646a1d1b2ec156d69b211789c9f24d8f39`
- PLAN refs: Scoping Rules; Cross-Cutting Context; Harness & Coordination;
  Full-Platform Architecture
- Change: `openspec/changes/restore-openspec-delivery-flow/`
- First slice: read-only flow inventory and admission diagnostics
- Write set: exact `STATUS.md` row
- Verification: focused unit tests, strict OpenSpec validation, skill sync and
  drift checks, clean diff, independent exact-diff review
- Publish route: one PR; sync/archive in the same lane if implementation and
  review complete
- Build gate: blocked until Claude review is `approve` or `adapt`
- Foldback: retire the STATUS row after merge; do not add follow-up rows unless
  evidence from the guard identifies a concrete, independently deliverable
  defect

## Open questions

1. Should target-only future programs remain under `openspec/changes/`, or move
   to design/exec-plan storage until a delivery slice is admitted?
2. Should a later WIP ceiling add a global hard limit? The first implementation
   enforces one per exact session-specific provider identity and reports global
   WIP; suffix-renaming to evade the rule is forbidden.
3. Should shared coordination files be excluded from collision matching, or
   represented as row/section-scoped atoms?
4. Can `worktree_status.py` batch git metadata or offer a cheap session-start
   mode so 374 registered worktrees do not impose a multi-minute tax?

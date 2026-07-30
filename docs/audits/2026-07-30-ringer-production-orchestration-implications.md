# Ringer Production-Orchestration Implications

Date: 2026-07-30  
Initial provider: Codex (`codex-gpt5-desktop`)  
Review gate: mandatory opposite-provider Claude source/context review before
implementation based on these findings  
TinyAssets base: `ef65fdc7f37fb96d7d1be711dda3b34e9de9c0c8`

## Executive Judgment

TinyAssets' low production throughput is mainly an orchestration problem, not
an agent-intelligence problem.

The current drain asks a long-lived session to be scheduler, backlog refiner,
implementer, verifier, reviewer coordinator, release shepherd, and state
memory. That shape makes sessions expensive and non-terminal. It also feeds
newly discovered work directly into the delivery queue, so the list can grow
while useful output lands.

[Ringer](https://github.com/NateBJones-Projects/ringer) demonstrates a better
executor boundary:

- work is expressed as bounded packets;
- workers are disposable;
- each attempt is isolated;
- verification is executed rather than self-attested;
- a failed check supplies bounded retry context;
- attempt outcomes are durable and measurable.

OpenAI's [Symphony specification](https://openai.com/index/open-source-codex-orchestration-symphony/)
adds the missing production-control shape: tickets are durable control-plane
state, dependencies determine what is runnable, each task gets a dedicated
workspace, and a continuous supervisor shepherds work through merge. OpenAI's
[harness-engineering report](https://openai.com/index/harness-engineering/)
reinforces repository-local context, mechanically enforced invariants, and
end-to-end agent ownership through review and CI. Anthropic's
[multi-agent research report](https://www.anthropic.com/engineering/multi-agent-research-system)
is the necessary brake: parallel workers help when work is genuinely
independent, but multi-agent systems consume much more budget and fit
dependency-heavy coding less well.

The production target is therefore:

> Durable control-plane work packets and dependency-aware waves; disposable
> BYOC executors; independent executable evaluation; reviewed PR/receipt
> delivery; phone-chatbot control; separate backlog refinement from delivery.

This is not a new privileged drain service. It is an ordinary user-authored
Branch composition over TinyAssets' existing Branch, Trigger, Goal, Gate, Run,
Evaluator, effect, activation, lease, and receipt primitives. Jonathan's
OpenSpec drain is the first conformance proof. Any user must be able to bind
their repository, accepted spec, BYOC route, evaluation policy, and GitHub
destination while all personal computers are off.

## Canonical Source

| Field | Value |
|---|---|
| Repository | `NateBJones-Projects/ringer` |
| URL | <https://github.com/NateBJones-Projects/ringer> |
| Default branch | `main` |
| Inspected commit | `a1a91b8b384a90dcca379e1cb9ab91405275ac46` |
| Commit date | `2026-07-28T22:48:00Z` |
| Repository pushed | `2026-07-28T22:48:01Z` |
| Primary language | Python |
| GitHub snapshot | 221 stars, 90 forks on 2026-07-30 |
| License | PolyForm Shield 1.0.0 (`LICENSE.md`; GitHub classifies it as “Other”) |

The PolyForm Shield terms include a competitive-use restriction. TinyAssets
may be a competing orchestration platform. Do not vendor, port, translate, or
copy Ringer implementation code. This report adopts independently described
production patterns and maps them onto already-approved TinyAssets primitives.

The inspected repository is primarily Python (905,816 bytes reported by the
GitHub languages endpoint). Its central `ringer.py` is an approximately
11,135-line orchestration program, supplemented by dashboard, engine, registry,
hook, template, and test directories.

## Ringer Module Map

| Ringer area | Observed responsibility | Useful lesson | TinyAssets boundary |
|---|---|---|---|
| Manifest / `TaskSpec` | Key, spec, check, expected files, engine/model, task type, timeout, attempts, access | Make the unit of execution explicit and bounded | Represent as an ordinary versioned work-packet schema in Branch/Run state, not a new top-level primitive |
| Runner | Semaphore-bounded parallel tasks, worker process, verifier, retry | Scheduler owns concurrency; workers do not select their own fan-out | Server authority selects only dependency-ready, non-colliding packets |
| Verifier | Shell exit code plus nonempty expected artifacts | Execute acceptance; never trust “done” summaries | Repo-owned CI/evaluator references; do not accept arbitrary tenant shell on the control plane |
| Baseline mode | Run checks before spending tokens | Prove acceptance is falsifiable and not pre-broken | Admission gate classifies new-behavior assertions versus unchanged invariants |
| Lint | Detect unfailable/silent checks, write collisions, serial fan-out, disappearing work | Reject or warn on structurally wasteful packets before dispatch | OpenSpec/packet admission and graph validation |
| Worktree mode | One isolated worktree per task | Isolation is a prerequisite for safe concurrency | Existing GitHub/worktree spine or cloud ephemeral workspace |
| Retry | Default one retry with raw failure context | Bounded correction can rescue mechanical failures | One same-packet retry, then replan/refine/block; never endless agent loops |
| Eval log | Attempts, model, task type, duration, tokens, raw check result | Route from evidence, especially first-try pass rate | Typed attempt/EvalResult/receipt rows owned by the user's universe |
| Ringside | Live state, histories, failures, artifacts | Supervisors need observable durable state | Existing chatbot handles and user-visible nodes are canonical; a dashboard may be community-built |
| Engine registry | Pluggable CLI/model routes | Separate work policy from executor route | BYOC capability routing first; market routes later |
| Local run store | `~/.ringer/runs` and optional Postgres eval aggregation | State must outlive a worker | TinyAssets cloud universe/control-plane database, never a laptop directory |

## TinyAssets Module Map

| TinyAssets area | Current relevant seam | Ringer/Symphony adaptation |
|---|---|---|
| `openspec/changes/activate-main-universe-spec-drain/` | Approved ordinary private Branch composition, BYOC-first, activation epoch, single-active claim, GitHub effect receipt, phone control | Generalize wording and work-packet contract so repository/spec/drain identity are user-selected inputs; keep Jonathan as first proof |
| `tinyassets/storage/request_admissions.py` | Transactional request/task records, pickable indexes, leases, recovery and quarantine | Durable admission and claim substrate for ready work; extend only through the owning authority change |
| `tinyassets/branch_tasks_v2.py` | Epoch-2 task adapter and queue consumer seam | Execute one server-authoritative claim generation; no alternate local identity |
| `tinyassets/background_branch_authority.py` | Typed background authority/provenance attempts | Bind every attempt to real user, universe, immutable Branch version, provider authority, and effect scope |
| `tinyassets/cloud_worker.py` | Persistent cloud supervisor, heartbeat, restart recovery | Disposable executor host supervised by cloud control plane; worker restart must not duplicate a packet |
| `tinyassets/evaluation/` | `EvalResult`, structural/editorial/process/scenario evaluation | Evaluator is distinct from implementer; verifier references and evidence are immutable inputs |
| `tinyassets/effectors/github_pr.py` and GitHub effectors | External repository effects | Destination-scoped, idempotent PR effect with remote reconciliation and durable receipt |
| `tinyassets/api/runtime_ops.py`, existing canonical handles | Read/control surfaces | Inspect, pause, resume, reprioritize, repair, version, and rollback from a phone chatbot without a new MCP handle |
| `scripts/openspec_flow.py` | Current WIP/admission/finish-first diagnostics | Backlog refinery input and delivery admission evidence; not itself the production scheduler |
| GitHub branch/worktree/PR spine | Durable implementation integration | A PASS is not delivery until commit/diff/PR/evidence is durable and review/CI can shepherd it to merge |

## Root-Cause Diagnosis

### 1. Session-shaped production

The session is currently the durable unit. When it compacts, exits, hits a
limit, waits for review, or meets a host action, production loses momentum.
Durable packet state must instead own the job while sessions become replaceable
attempt executors.

### 2. Refinement and delivery share one queue

The 2026-07-29 inventory found 33 active changes and 833 unchecked tasks, but
only four claimable candidates. Coding harder cannot drain dependency and
policy debt. A refinery must raise claimable pressure; a delivery executor must
consume already-admitted packets. Neither may silently turn every finding into
active work.

### 3. Parallelism is based on available subscriptions

Two or more long sessions maximize model utilization, not landed throughput.
Review, CI, merge, deployment, and acceptance are narrower stages. Parallelism
must be admitted only when dependencies and write sets prove independence and
downstream capacity exists.

### 4. “Done” is too far from an executed evaluator

Agent summaries, task checkbox changes, and local edits are weak evidence.
Executed checks, independent review, CI, remote PR state, merge verification,
OpenSpec foldback, and release receipts are the production outcome.

### 5. Retry and recovery boundaries are implicit

A broad goal survives indefinitely while the agent changes approach. Each work
packet instead needs a timeout, attempt budget, exact retry identity, and a
terminal state. After the one bounded correction attempt, the controller
replans, refines, or blocks with durable evidence.

## Target Production Contract

### Verified production work packet

The minimum packet is a composition record, not a new platform primitive. It
contains:

- stable packet ID and task type;
- user, universe, repository, accepted-spec, and immutable Branch-version
  references;
- exact dependency packet IDs;
- exact write-set or artifact ownership;
- acceptance evaluator/check references and expected evidence;
- provider/executor capability requirements;
- timeout and maximum attempts;
- budget ceiling and authority source;
- GitHub destination/effect reservation;
- current activation epoch, lease generation, attempt state, and blocker;
- terminal evidence handles and next action.

Packet text may be generated, but identity, authority, dependencies, evaluator,
budgets, and effect destination are controller-derived and immutable for an
attempt.

### Baseline/falsifiability gate

Before model spend:

1. validate the packet and its immutable references;
2. check dependency completion and write-set collisions;
3. execute or inspect the declared acceptance baseline in a sandbox;
4. require new-behavior assertions to fail for the intended reason;
5. require unchanged-invariant checks to pass;
6. reject silent, unfailable, missing-artifact, or self-attested checks.

For a multi-tenant cloud system, user-provided arbitrary shell is not trusted
control-plane input. Checks must be repository-owned CI commands in an isolated
workspace, typed TinyAssets evaluators, or sandboxed external tool nodes under
declared policy.

### Dependency-aware work-conserving waves

The supervisor computes READY packets from:

- all dependencies terminal-success;
- no overlap with currently leased write sets;
- required authority/provider route available;
- review/CI/effect capacity below its configured limit;
- activation epoch and immutable version still current.

It fills available slots only with READY packets. A dependency-heavy slice
remains sequential. A broad independent batch may fan out. Parallelism is a
derived scheduling result, never a fixed “run two agents all day” policy.

### Attempt and retry state machine

`pending → leased → executing → evaluating → reviewed → effect_reserved →
published → merged → folded_back → succeeded`

Terminal alternatives are `failed`, `blocked`, `cancelled`, and `superseded`.

A failed evaluation may retry once under the same packet and effect identity
with bounded raw failure context. A second failure exits execution and creates
a refinery/replan input; it does not remain in an agent loop.

### Durable delivery

Successful evaluator output is not discarded. Before releasing an isolated
workspace, the controller must have a durable commit/diff bundle and, for
software delivery, a destination-scoped PR or explicit artifact receipt.
GitHub remains authoritative for checks, review, and merge. Foldback verifies
remote merge before syncing/archiving OpenSpec and retiring the live claim.

### BYOC routing

Routing begins with the user's eligible provider bindings and executor hosts.
The controller records trained model, harness, access route, task type,
reasoning policy, first-try pass, rescued pass, duration, and cost/budget
consumption separately. It may recommend routes from evidence. Automatic
optimization is deferred until enough user-owned observations exist. There is
no maintainer fallback and market compute is not a prerequisite.

### Phone-chatbot control

Existing canonical handles must support:

- “What is running and what is blocked?”
- “Pause after the current irreversible boundary.”
- “Resume with this immutable version.”
- “Prioritize this ready packet.”
- “Show the failed evaluator and retry budget.”
- “Publish/activate this reviewed orchestration version.”
- “Roll back to the previous version.”

The answer is rendered from durable cloud state. No tray process, local
dashboard, PowerShell command, or computer is required.

## Backlog Refinery Versus Delivery Executor

| Refinery | Delivery executor |
|---|---|
| Measures WIP, blockers, stale claims, oversize changes, and arrival/closure | Claims only READY packets |
| Proposes slices, dependency corrections, and acceptance contracts | Implements exactly one admitted packet |
| Can produce a reviewed planning artifact | Produces evaluated code/artifact and durable PR/receipt |
| May increase claimable pressure | Must not invent new scope |
| Never rewrites PLAN authority automatically | Never bypasses review/CI/effect authority |

The refinery's success metric is increased claimable pressure without
unreviewed scope expansion. The executor's success metric is accepted terminal
closure, not token use or tasks touched.

## Metrics

Record daily flow snapshots and per-attempt receipts:

- work arrival and accepted closure rates;
- active delivery WIP;
- READY queue depth (“claimable pressure”);
- blocked fraction, age, and blocker class;
- archive-to-admission ratio;
- median spec-to-verified-PR and PR-to-merge time;
- first-try pass and rescued pass by task type/provider/model/harness;
- retry and human-intervention rates;
- cost or subscription budget per accepted closure;
- write-set/dependency collision rate;
- useful executor utilization versus time waiting for review/CI/effect slots;
- spec-to-task expansion ratio.

Task count is diagnostic, not a productivity score.

## Adopt / Adapt / Avoid / Defer / Watch

### Adopt

- Executed verification and expected artifact checks.
- Baseline acceptance validation before model spend.
- Bounded retry with raw failure context.
- Attempt metrics split by task type and route.
- Visible durable state for every live and orphaned run.

### Adapt

- Ringer manifest → ordinary TinyAssets verified work-packet composition.
- Local semaphore → server-authoritative dependency/write-set wave scheduler.
- Local CLI engine config → user-owned provider/executor capability binding.
- Local Ringside HUD → canonical chatbot control and user-visible nodes.
- Worktree isolation → durable commit/PR before workspace retirement.
- Flat batch fan-out → DAG/authority/capacity-aware READY selection.

### Avoid

- Copying or vendoring PolyForm Shield implementation code.
- Arbitrary shell checks as trusted multi-tenant control-plane input.
- Trusting worker summaries or worker-authored evaluator definitions.
- Deleting successful worktrees before durable delivery exists.
- Unbounded fan-out or parallelizing dependency-heavy code.
- Using premium models for every mechanical attempt.
- Local-only state, health, or control.
- Automatically feeding all discovered work into active delivery.

### Defer

- Market-compute routing until BYOC works end to end.
- Autonomous cost/model optimization until route metrics are trustworthy.
- A separate first-party dashboard; community compositions may build one.
- Multi-repository fan-out until one generic repository/spec path is proven.

### Watch

- Whether one retry is optimal by task type.
- Whether write-set declarations are precise enough for safe waves.
- Whether baseline checks become performative rather than falsifiable.
- Whether refinement raises claimable pressure or merely creates documents.
- Whether review/CI/merge capacity, rather than executor slots, remains the
  dominant bottleneck.

## Smallest Implementation Slice

The first implementation remains inside
`activate-main-universe-spec-drain`; do not create a sibling scheduler.

Amend the change before runtime work to:

1. replace Jonathan-specific behavioral requirements with generic
   user/repository/spec inputs while retaining Jonathan as the acceptance
   fixture;
2. define the verified work-packet schema using existing composition state;
3. add baseline/falsifiability admission;
4. separate refinery proposals from delivery claims;
5. admit a single READY packet under the already-approved epoch-2 activation
   and lease authority;
6. execute one BYOC attempt, one independent evaluator, and at most one bounded
   retry;
7. preserve a durable commit/diff and destination-scoped PR/effect receipt;
8. expose status/pause/resume/reprioritize through existing chatbot handles;
9. prove two-trigger collision safety and cloud-worker restart recovery.

Only after single-packet conformance passes should the next delta add a
two-packet independent wave and §14 load proof. This preserves the final
architecture without making parallelism the first correctness problem.

## Review Questions For Claude

1. Is Ringer characterized accurately at commit
   `a1a91b8b384a90dcca379e1cb9ab91405275ac46`?
2. Does the PolyForm Shield restriction require any stronger avoid language?
3. Does the proposed work packet compose from existing TinyAssets primitives,
   or does it silently introduce a new top-level primitive?
4. Does this collide with current epoch-2 request admission, background
   authority, evaluator, GitHub effect, or distributed-execution owners?
5. Are baseline checks safe and meaningful for a multi-tenant cloud?
6. Is the smallest slice generic enough for ordinary users while remaining
   deliverable?
7. Which findings are overstated, missing, or unsafe?

## Worktree / Pickup Packet

- Branch: `codex/ringer-production-orchestration-20260730`
- Worktree:
  `C:/Users/Jonathan/Projects/wf-ringer-production-orchestration-20260730`
- Base: `ef65fdc7f37fb96d7d1be711dda3b34e9de9c0c8`
- Claim: STATUS row “Implement Ringer-informed generic GitHub→spec production
  orchestration”
- Research artifact:
  `docs/audits/2026-07-30-ringer-production-orchestration-implications.md`
- Required review artifact:
  `docs/audits/2026-07-30-ringer-production-orchestration-claude-review.md`
- OpenSpec owner:
  `openspec/changes/activate-main-universe-spec-drain/`
- Prior evidence:
  `docs/audits/2026-07-28-openspec-agent-throughput-implications.md`,
  `docs/design-notes/2026-07-29-main-account-cloud-spec-drain.md`,
  `docs/audits/2026-07-29-cloud-drain-current-main-prerequisites.md`
- Gate: no runtime implementation, implementation push, or live acceptance
  based on this report until Claude returns APPROVE or ADAPT and every blocking
  adaptation is folded into the durable artifacts.

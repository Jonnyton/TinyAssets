# Run-owned preference DATA bridge — bounded shape question

2026-09-19. Proposal only; do not implement this bridge until disposition.
Storage checkpoint 2ca96c52 review does not approve this semantic change.

## Exact existing seam

- `foreground_run_provider._admit_manifest` computes one aggregate finite
  allowance from original node/default fallback lengths and compiler retry count.
  `_work_invocation_allowance` preserves the existing accepted shared-self ceiling.
- `_authorize_attempt` chooses `policy.preferred`, then freshly checks current
  owned source/model/custody/spend before arming a **run** invocation carrier.
- `call_with_policy_sync` currently makes one guarded call; adding a fallback
  list alone does not create guarded fallback traversal. Compiler policy retry
  invokes that method again after `AllProvidersExhaustedError`.
- `prepare_owned_model_plan` does useful current owned catalogue discovery but
  rereads mutable saved preferences and takes provider/SQL locks. It cannot be
  called under shared worker `prepare`'s author+runs writers or reused unchanged
  for a previously admitted canonical turn.
- `WorkAgentAdapter` pins one selected model for a tool-agent turn; its checks
  reject `agent_model_plan`, and `create_turn` forbids a served plan. The common
  coordinator's served fallback capability is not reusable work authority.
- `WorkflowAgentTurn` already holds when tool effects or uncertain progress make
  whole-node replay unsafe. Preserve it. An empty journal is not proof a native
  delegated agent did nothing.
- `SourceHealth` tracks exact custody generation/digest per owner/universe/source,
  not a timer. Current `AgentModelPlan.order` demotes known sign-in failures in
  Automatic, rather than removing them. Do not erase that knowledge on a retry
  or falsely describe demotion as a shipped blanket exclusion.

## Proposed data and preparation boundary

Store only validated `ModelPreferences` documents (saved and current-or-absent),
observed saved generation and source (`current`/`saved`/`automatic`) inside the
canonical admission's existing captured context. Never persist a provider carrier,
AgentModelPlan, credential or arbitrary callback. Explicit Automatic clears saved
selection for this turn; absent current choice is different. Explicit empty
fallbacks remain empty, never interpreted as permission for automatic defaults.

New admission first checks the key in the current owner/home scope. If absent,
prepare bounded owned catalogue/preference DATA outside all author/runs writers,
using a factored version of existing owned discovery that accepts the captured
preference documents instead of rereading defaults. Reenter the author fence,
recheck key/owner/installation/source and the prepared preference generation,
then reserve the winning context/run. If preparation changed before reservation,
hold before effects; an unadmitted key may retry. A racing loser returns the
already persisted original context, regardless of today's defaults/history.

At dispatch, the common callback reads the same admission/run and verifies
current owner/source using supplied author_conn/runs_conn only. It must not open
connections, take provider/reset locks or do discovery. `bind_provider` after
durable start, outside SQL, constructs the trusted run session and refreshes
advisory catalogue if required **without changing the stored preference choice**.
All actual attempts still need current run-owned authority. Discovery/start
failure never clears the shared durable marker or creates a private relaunch path.

Lock order stays: shared maintenance barrier -> common run guard -> existing
short author/runs fences. Catalogue/provider/network preparation lives outside
those SQL writers; no consumer reset recovery is invoked automatically.

## One effective order for allowance and dispatch

The server builds one finite eligible model-reference order per effective graph
policy from captured user choices and fresh owned catalogue facts. Keep it outside
the immutable Branch snapshot. Node/branch constraints may narrow compatible
candidates but never replace an explicit selected primary. An explicit conflict
refuses. An absent node fallback list is no additional restriction; an explicit
node list intersects user-approved alternatives and never adds one. Preserve
source/member/model/spend constraints and accepted maximum invocation ceiling.

Use this **same** resolved order to compute the existing aggregate allowance and
to select every actual attempted candidate. Budget arithmetic must be finite and
checked before arming; no new per-model authority pool. Existing compiler retry
count remains an upper bound, not a fresh allowance. Do not increase budget merely
because discovery returns more models than can fit accepted authority.

Session-owned evidence of a positively observed failure **within this canonical
turn** persists across compiler retries and graph nodes. A policy retry cannot
reset to that same failed/exhausted attempt merely by rebuilding the order.
Preexisting advisory source-health knowledge keeps its shipped **demotion**
semantics, not a new blanket ban; it may be lost on restart or bounded eviction,
but elapsed time alone never clears it or promotes the source. Explicit user
choices are never silently replaced. A new credential generation is evaluated by
its actual current authority, not elapsed time. Candidate order is data, and
excluding a proven in-turn failure does not grant the next candidate.

Plain template inference advances only at existing typed, positively observed
no-effect capacity boundaries. Authentication is NOT in the existing closed
capacity predicate: preserve truthful hold and future Automatic demotion. A new
within-turn authentication transition would need its own evidence contract and
review, not relabeling as capacity. Missing/ambiguous telemetry,
unreaped native children, unknown exceptions, timeout or possible side effects
hold; do not guess a retry is safe. Every actual candidate arms a fresh run
carrier, and exhausted order raises without starting over on compiler re-entry.

## Material question: tool-agent fallback

The target includes ordinary Automatic users selecting reusable **tool-capable**
agents with their own model/fallback choices. Prompt-only staging may remain dark;
refusing all multi-candidate work agents is not the delivered requirement.

Use the existing coordinator loop and journal, not a new fallback executor:

- `agent_turn_coordinator.py:327-349`, `_next_after_capacity`, already owns the
  exact same-journal frontier: ready/held_transport/held_native_capacity, closed
  capacity evidence, visited/exhaustion and context selection. Its current hard
  `AgentModelPlan` dependency (`:47-49`) and `plan.next_candidate` calls (`:171`,
  `:341`) are the advisory adapter seam. Factor only candidate-order/progress
  access into the injected adapter; keep served behavior unchanged and its
  original plan validation. Work supplies the finite effective DATA order from
  its run session, never puts a served plan into UniverseContext or journal.
- `workflow_agent.py:25-92` pins one selection in constructor/policy and compares
  every launch to it. Permit a staged next DATA candidate only after the shared
  coordinator accepted the closed boundary. `_authorize_attempt` must reserve a
  NEW carrier with the same run receipt/claim and selected candidate, not reuse
  the failed carrier or increase receipt allowance. Provider/model/custody/parent
  binding checks remain in `foreground_run_provider.py:675-832` per attempt.
- One existing work journal persists. `agent_turn_journal.py:431-479` already
  permits fresh rounds after a failed HTTP inference with no tools or a native
  `capacity_no_effects` terminal, under generation CAS and SAME work receipt ID.
  Its `:219-234` validates prior safe frontiers. No new schema, journal root,
  authority kind, request queue or effect replay is needed. Keep work journal
  policy lineage empty; captured preferences remain canonical admission DATA.
- `_history` (`agent_turn_coordinator.py:84-116`) carries completed text-only
  tool outcomes into continuation and skips proven no-effect failed inference.
  Switching model continues *after* these outcomes; it never issues old tools
  again. Prior completed effects do not prohibit this continuation, but forbid
  any outer node/turn replay. Unknown/non-text/in-flight tool progress holds.
- Native transition requires `capacity_boundary.py` exact supported telemetry:
  complete protocol, reaped process and no effects for every actual attempt;
  skipped quota slots must have no native execution proof. Empty journal alone
  never proves a delegated CLI did nothing. HTTP/native transitions can reuse
  existing history rendering only at these same quiescent frontiers.

One concrete adapter-check issue must be addressed in implementation/review:
`_check_agent_authority` (`foreground_run_provider.py:564-672`) requires the
current invocation state launch_started/succeeded (`:637`); a settled failed
carrier must NOT be accepted as continuing authority simply to switch models.
`WorkAgentAdapter.check` also compares context selection to its pinned selection.
Separate a narrow **pre-inference** run/owner/receipt/claim/current engine-admission
check from the existing active-invocation check. It may validate a staged candidate
as DATA for engine discovery but cannot execute tools or call a provider. The
subsequent `infer` reserves/arms the fresh candidate via `_authorize_attempt`,
sets the adapter's current carrier/selection, and its observer uses the unchanged
strict invocation check before recording any started round. Tool dispatch still
uses strict fresh invocation/member checks. Do not expand accepted failed
reservation states globally, or let a staged candidate satisfy a tool fence.
If the reviewer identifies an existing narrower helper, use that exact helper;
otherwise this phase-specific adapter seam needs an explicit acceptance test.

Finite exhaustion belongs to the run session as well as the in-process turn so
compiler re-entry cannot reset it. If the turn exhausted candidates after any
completed tool, `WorkflowAgentTurn.run` remains effect-held; do not create another
journal. No fallback candidate, exhausted budget, revoked source, cancellation,
unknown exception or crash is permission for outer turn replay. A pure zero-effect
all-skipped retry still must not repeat an already excluded finite candidate.

Current closed capacity failures are credit/rate/overload ONLY. Authentication
holds this turn and records/demotes through existing source-health behavior; it
does not enter `_next_after_capacity`. Within-turn auth fallback is an explicit
remaining boundary, not falsely claimed as already supported or silently retried.

## Producer attribution

Existing provider calls accept a request-local response observer; compiler ran
events already support provider/model metadata. Attribution must follow the
actual producing terminal node's response, not the first graph response or
selected/default model. Where several nodes combine the reply or attribution
cannot be proven, use unknown/multi-contributor representation only if already
supported—do not widen the strict single-model execution receipt deceptively.
No model label inferred from the catalogue or preferred policy counts as reported.

## Required tests / release question

- Explicit current/saved/automatic distinctions and empty-fallback preservation;
  mutable defaults/history after same-key admission do not change the captured data.
- Original snapshot/hash unchanged; graph constraints intersect or refuse, never
  override receiver selection; exact effective order drives both budget and calls.
- Current revocation/model/spend refusal before each attempt; no stale preference
  document or cached catalogue grants authority.
- Known sign-in failure/exhaustion does not repeat after compiler re-entry;
  auth holds/demotes rather than masquerading as capacity. No-effect capacity may
  advance in the same journal; uncertain/native/tool effects never replay.
- Shared prepared callback makes no discovery/provider/new-connection calls under
  writer locks; before/after-marker failures obey common dispatch lifecycle.
- Parallel nodes cannot overwrite each other's producer evidence; ambiguous reply
  provenance stays unknown. Legacy non-consumer graph/provider behavior unchanged.
- Work candidate transition retains journal ID/receipt ID, appends a fresh round
  and reservation, carries completed tool outputs exactly once, and never reissues
  completed tools. HTTP/native/quota-skip capacity variants and unknown telemetry
  are covered. Wrong claim/member, stale carrier, pending selection during tool
  dispatch and any attempted served-plan injection refuse.
- A failed carrier cannot pass the active invocation fence; pre-inference scope
  checking cannot authorize a tool or model effect. Revocation between staging
  and fresh arm refuses. Same-key reconnect/crash cannot resurrect this journal.

Request AGREE / DISAGREE_EVIDENCE / DISAGREE_CONCERN with citations and an
APPROVE / ADAPT / BLOCK verdict on the bounded shape, not a full repository audit.

I'll read the frozen note at 2bd644d3 first, then trace the cited coordinator, run provider, journal and capacity predicate at that same checkpoint.

Now tracing the cited seams at the same checkpoint. I'll pull all the cited line ranges in one pass.

Now requesting the retry loop body, the diagnostic construction, the exhaustion filter, the work-selection validator, and the helper grep together.

Four items left, all independent: how the router builds attempt diagnostics and native evidence, the exhaustion filter, the work-selection validator, and the helper grep.

Review complete. Verdict below.

**Scope reviewed.** Frozen checkpoint 2bd644d3, the model-bridge note, and every seam it cites, read via `git show`. No subagents, no Codex, no edits, no tests run.

## Verified claims (AGREE)

- **Coordinator seam is real.** `tinyassets/agent_turn_coordinator.py:47-49` hard-types `AgentModelPlan`; `next_candidate` is called at `:171` and `:341`. For work turns `plan` is `None` because `WorkAgentAdapter.create_turn` refuses one, so `_next_after_capacity` returns `False` at `:329` and no fallback exists today. Factoring candidate-order access into the adapter is the correct minimal seam.
- **Journal frontier supports a same-journal fallback round.** A failed HTTP round maps to `held_transport` (`agent_turn_journal.py:294-295`); the snapshot validator accepts failed no-tool rounds in the completed prefix (`:223-234`); `begin_round` admits a new round from that state (`:454-460`); `_history` skips failed rounds and carries completed text-only tool rounds exactly once (`agent_turn_coordinator.py:92-115`). Non-text or incomplete tools raise and hold.
- **A failed carrier cannot pass the active fence.** The router settles a failed attempt `FAILED` before raising exhausted (`providers/router.py:1190-1191`); the later `CANCELLED_BEFORE_LAUNCH` at `:1442` is a no-op because `settle_carrier` is guarded at `:634`. `_check_agent_authority` requires `launch_started|succeeded` (`foreground_run_provider.py:639`), so the fence refuses.
- **Auth is not capacity.** `_FAILURES` is credit/rate/overload only (`agent_capacity_boundary.py:18-20`); `auth_invalid` attempts carry an auth failure class (`router.py:1274-1278`) so the boundary returns `None`. `AgentModelPlan.order` demotes reconnect sources only in pure Automatic with no current/saved choice (`agent_model_plan.py:50-54`), exactly as the note describes.
- **`prepare_owned_model_plan` does take the admission fence and SQL** (`served_model_plan.py:267-274, 399-404`). It cannot run under the writers.
- **No Codex actual-model telemetry exists.** `reported_model` is set only in `claude_provider.py:840`.

## Smallest adapter change (recommendation)

Do not add a relaxed `check` mode and do not touch `:639`. `WorkAgentAdapter.check` (`workflow_agent.py:43-54`) is the single gate used by `infer` (`:69`), `round_input` (`:98`) and the pre-tool `_check_scope` (`agent_turn_coordinator.py:280`). Instead:

1. Coordinator: replace `self.plan.next_candidate(...)` with `self.adapter.next_candidate(owner, uid, exhaustion)`; the served adapter wraps `AgentModelPlan`, the work adapter serves the finite DATA order. Keep `visited` and `_next_after_capacity` unchanged.
2. Work adapter `infer`: when `context.model_selection` equals the staged next candidate and the current carrier is settled, skip `self.check`, run only a pure identity prelude (universe dir, no served fields, engine actor/graph ids), set `policy["preferred"]` to the candidate, and call `_authorize_attempt`. That method already performs the fresh receipt/claim/run/member/custody/spend recheck under `BEGIN IMMEDIATE` and mints a new carrier on the same receipt and claim (`foreground_run_provider.py:703-816`). `_authorize_attempt` **is** the pre-inference check; no narrower helper exists (`carrier.validate_for_call` is carrier-level only).
3. Then update `self.carrier` and `self.selection`; the strict `check` in `_infer_launch` (`:86`) and `round_input` (`:98`) gate the actual call and the observer. Tool dispatch stays strict and unchanged.

## Minimum pre-build corrections (DISAGREE_CONCERN)

1. **Allowance arithmetic is unstated and will refuse graphs.** For shared-self graphs `_work_invocation_allowance` returns the member ceiling and raises when the computed minimum exceeds it (`foreground_run_provider.py:75-78`). Replacing `1+len(fallback_chain)` with the effective order length (`:470-479`) makes a long Automatic catalogue refuse a previously admissible graph. Specify: Automatic order is truncated deterministically to fit the ceiling; an explicit user list that cannot fit refuses with a reason. The receipt is admitted at first `_call` (`:888`), so the captured preference document must reach the session at construction, not be reread.
2. **Attribution path does not exist yet.** `call_with_policy_sync` returns a fixed `{"attempts": 1}` with no model (`:950-962`); ran events read `provider_meta["model"]` (`graph_compiler.py:1458`), so work runs report an empty model today. The bridge must return the producing carrier's provider and validated model from the completed round, plus the real attempt count, or attribution falls back to the preferred policy, which the note itself forbids. Codex native must report `configured_model` with `reported_model` unknown.
3. **Compiler re-entry creates a new journal; session exhaustion must survive it.** `journal.create` mints a fresh turn every call (`agent_turn_journal.py:387`), and the compiler retries `AllProvidersExhaustedError` three times (`graph_compiler.py:399-420`). Effect-bearing turns are protected by `WorkAgentEffectHeld` (`workflow_agent.py:140-144`), but a zero-effect exhausted turn restarts the order unless exhaustion lives on the session (which persists across retries). Also `order_models` raises `ValueError` when an exhausted connection is absent from the catalogue (`model_policy.py:376-380`); a session-persisted exhaustion tuple fed into a fresh catalogue must filter or catch that, or the run crashes.

## Red-first tests (minimum)

- Settled `FAILED` carrier plus staged candidate: `check()` refuses; `infer()` arms a new carrier with identical receipt and claim ids; mutating `check` to accept `FAILED` must turn the test red.
- Journal: completed text-only tool round, failed inference, new-candidate round; `_history` holds exactly one captured round and no `start_tool` is issued for old requests.
- Session exhaustion across compiler re-entry: candidates A and B exhausted with zero effects, retry attempts C or raises, never A; include the catalogue-without-A case.
- Allowance: order longer than the ceiling truncates for Automatic and refuses for an explicit list; receipt `max_invocations` unchanged by discovery size.
- `auth_invalid` attempt holds with no candidate advance and unchanged demotion.
- After a fallback, `call_with_policy_sync` meta names the producing provider and model; Codex native reports configured model with reported model unknown.

## Optional hardening

- Pre-filter the effective order to `assignment.candidates` with current member authority so a revoked candidate is excluded at order build rather than holding the turn at arm time.
- Arm refusal for a candidate (budget, revocation) should keep holding in this slice; advancing on local refusal is a new boundary and needs its own evidence contract.

VERDICT: ADAPT

The hook lists other sessions' dispatches. My brief forbids edits, dispatch, and re-dispatch, so the only permitted action is reading the finished file. Checking it now.

Checked. The finished file is the earlier storage review of checkpoint 2ca96c52, which returned APPROVE for dark integration of the canonical admission and explicitly did not approve the model-bridge semantics; that is consistent with my ADAPT verdict and changes nothing in it. The running model-bridge review and the four vanished dispatches belong to other sessions, and re-dispatching, dropping, or taking a build lane would violate this brief's hard constraints of no edits, no children, and no dispatch, so there is honestly nothing else to advance here.

VERDICT: ADAPT

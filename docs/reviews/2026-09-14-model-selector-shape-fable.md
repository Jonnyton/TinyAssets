Checked the hook's list. The only running dispatch is this review's own output path, and the vanished entries are stale reviews outside this brief's exact scope, which the brief says to ignore. The brief forbids me from taking implementation lanes, dispatching, or writing files, so there is nothing further to advance. To make sure the wrapper preserves the findings rather than this note, the full review follows unchanged.

# Remaining-design review: model-selector PR3832 at f8299c49

**Head revalidated** on 2026-09-13 from the worktree: `git rev-parse HEAD` = f8299c49ec83ea65bee2cbf882dc897be9112e54, branch codex/select-agent-models, tracked tree clean. Two untracked files exist and are outside this scope. Read-only review, source reasoning only. No tests run, no subprocess or agent dispatched, nothing edited.

## What the source constrains

**Native selection has no propagation channel today.** The Codex adapter takes its model from a process-global env var at `tinyassets/providers/codex_provider.py:232` and passes it as `-m` at line 773. The Claude adapter builds its argv at `tinyassets/providers/claude_provider.py:444` and again at line 844 with no model flag at all. An owner-scoped requested id reaches neither CLI. The env var is exactly the process-global leakage the spec forbids at `openspec/changes/select-agent-models/specs/agent-model-selection/spec.md:142`.

**The validator refuses before any catalogue matters.** `_native_default` at `tinyassets/providers/model_selection.py:156` raises on any nonempty native id. `_selection_definition` at line 180 refuses every non-HTTP provider. The store's `_validate_work_selection` at `tinyassets/storage/provider_work_authority.py:2626` requires a native selection to have no snapshot. The router at `tinyassets/providers/router.py:656` refuses any `selected_model` for a native agent, correctly, because `SelectedModel` is an HTTP-shaped record with cost caps and a wire contract.

**Observation is already separated; discovery and request are not.** `ProviderResponse.model` is a label and `reported_model` is attested evidence at `tinyassets/providers/base.py:295`. Codex fills the label with `provider-default` and leaves the attestation empty at `codex_provider.py:1041`. The native journal record keeps `configured_model` and `reported_model` apart at `tinyassets/interactive_http_agent.py:283`. So "observed id" exists. "Provider default" and "requested id" do not exist as separate facts anywhere on the selection or reservation path.

**The synthesized native catalogue overstates its basis.** `_native_models` at `tinyassets/providers/served_model_plan.py:154` emits one empty-id model flagged fresh, owner-filtered and tool-capable from binding facts alone. That is defensible for a provider default, but the flags are the same ones a real enumeration would carry, so the picker cannot tell them apart once enumeration exists.

**Workflow tools are refused at four places, all correct, none test-pinned.** `check_served_agent_tool_authority` at `tinyassets/provider_assignment.py:1308` rejects any carrier. The router refuses agent kinds with a carrier at `router.py:494`, requires the converse operation at line 666, and refuses engine tools with a selected model at line 672. A grep of `tests/` for those four messages returns no match. These gates can be relaxed without any test going red.

**The chat coordinator's authority hooks are served-only.** The round-intent observer runs from `after_provider_claim` at `router.py:1066` with a served budget reservation. The workflow path arms its carrier inside `_authorize_attempt` at `tinyassets/foreground_run_provider.py:671` before `router.call`, so no equivalent hook fires. The carrier exposes provider, selection and custody digest at `tinyassets/provider_work_authority.py:1346` but not the reservation id or member binding tuple that `RoundInput` requires at `tinyassets/storage/agent_turn_records.py:108`.

**The aggregate allowance is sized for one launch per node attempt.** Foreground admission computes `max_invocations` per node times fallbacks times retry slots at `foreground_run_provider.py:457`. Every reservation increments `_call_index` at line 590 and mints a fresh invocation key. A tool turn with two inference rounds on a one-node run exhausts the receipt. Token share per reservation at line 661 is fine, because settled rows charge actuals and free headroom for the next round.

**The lifecycle fences a workflow tool needs already exist.** Founder home, run status, immutable branch digest at `foreground_run_provider.py:584`, current member at line 628, and for background the exact task, lease and activation tuple at `tinyassets/background_served_provider.py:895`. The engine MCP route is keyed by actor and graph and exists only for allowlisted serving universes at `tinyassets/engine_mcp_http.py:80`.

## Decision 1: native discovery and explicit execution

**Contract: three separated facts, one adapter per installed executor, no name table in the kernel.**

Register a `native_model_source` on the provider class, next to the existing `agent_execution_kind` attribute at `codex_provider.py:687`. The plan builder already resolves the provider object through the router registry at `served_model_plan.py:150`, so no provider-name dispatch is added. The adapter declares:

```
basis: "owner_declared" | "executor_enumerated"
enumerate(credential_snapshot_dir, deadline_s) -> NativeCatalogue | None   # None = no enumeration route
request_arguments(model_id) -> tuple[str, ...]                             # "" -> ()
```

`NativeCatalogue` carries provider, observed_at, default_model_id, opaque model ids, and the custody reference digest and generation it ran under. Its `recheck()` re-reads custody and applies the same five-minute window as `assert_discovery_snapshot_current`. Make `PreparedPlan.snapshots` hold objects with `recheck()` so `served_model_plan.py:70` and line 101 stop calling the HTTP-only function directly.

The selection record for native becomes a `NativeSelection(provider, default_model_id, requested_model_id, basis, observed_at)`. Provider default is what the catalogue or executor reports as default, empty when unknown. Requested id is what goes to argv, empty meaning omitted. Reported model stays where it is, on the response and journal. Router line 656 distinguishes by type, not by provider name: a native agent accepts `NativeSelection` and refuses `SelectedModel`.

**Smallest complete path for existing native providers.** The catalogue-first framing in the brief has the order backwards. Owner-declared explicit ids are already valid in `ModelAccess` at `tinyassets/provider_assignment_manifest.py:44` and were anticipated in `connection-model-authority.md:55`. What is missing is propagation. So:

1. Widen `_native_default` into `_native_selection(provider, model_id, access, catalogue)`. Empty id keeps today's behaviour. A nonempty id under explicit scope that appears in `access.model_ids` yields an owner-declared selection with no catalogue needed. A nonempty id under discovered scope requires a fresh `NativeCatalogue` containing it, else refuse with `native_catalogue_unavailable`.
2. Add a router-owned `ModelConfig.native_model_id` overwritten from authority exactly as `selected_model` is at `router.py:655`. When a selection record is present the adapters use it and ignore the env var entirely. Codex emits `-m` only for a nonempty requested id. Claude emits `--model` only for a nonempty id and never `--fallback-model`.
3. `_native_models` lists the executor default plus every explicit `access.model_ids` entry as owner-declared rows with `availability_basis="executor_default"` or `"owner_declared"`. Enumeration, when it runs, adds rows with `"executor_enumerated"`.
4. Codex enumeration runs `codex app-server` over stdio under a fresh owner credential snapshot, outside the admission lock and outside any SQL transaction, with the snapshot cleaned up in `finally`, never the host home. Claude has no proven CLI enumeration route in the evidence note and the SDK is excluded by Hard Rule 3, so Claude returns `None` from `enumerate` and the picker labels enumeration unknown.
5. In `_validate_work_selection` at `storage/provider_work_authority.py:2626`, a native nonempty id validates against explicit scope or a caller-prepared `NativeCatalogue`, and writes basis and observed_at into `model_evidence_json`. `selected_work_model` at `tinyassets/providers/work_model_selection.py:51` branches on the evidence kind to rebuild a `NativeSelection`.

## Decision 2: selected HTTP workflow tool execution

**Split the coordinator into a kernel and two adapters.** Do not make workflows carry a `provider_request`, and do not widen `check_served_agent_tool_authority`. The kernel keeps everything in `InteractiveHttpAgentTurn` that is about progress: journal transitions, history projection, tool dispatch, hold classes, capacity traversal. It receives an adapter:

```
check() -> owner_user_id                      # every round and every tool
infer(prompt, system, config, observer, kind) # one admitted inference
engine_identity() -> (actor_id, graph_id)     # from authority facts only
```

The chat adapter is today's `_check_scope` and `router.call` with the served context, moved verbatim. The workflow adapter's `check()` runs founder home, run status running, branch digest, receipt and claim active, a short read transaction on `_current_selected_member_authority` for the current carrier's provider, and for background the exact task, lease and activation tuple factored out of `_authorize_launch`. Its `infer()` wraps `_authorize_attempt` and calls the router with the carrier context. The kernel must not import `provider_assignment`.

**Router edits, authority-derived, no provider names.** Replace the operation literal at `router.py:666` with `operation != model_authority.operation`; the carrier already exposes `operation` at `provider_work_authority.py:1363`. Replace the served-only precondition at line 494 with: exactly one of a served request plus context selection, or a carrier whose selection reports `supports_tools`. Fire `_agent_observer(invocation_carrier, None, cfg)` on the carrier path at the same pre-dispatch point as line 1070. Keep the refusal at line 672 until the adapter, journal and budget pieces land, and pin it with a test first.

**Carrier accessors.** Add read-only `reservation_id`, `member_binding_id`, `member_binding_generation` and `member_binding_digest` after `provider_work_authority.py:1356`, read from the sealed reservation. No seal change.

**Journal lineage.** `RoundInput` version 2 adds `authority_kind` with values served_request or work_invocation, and `work_receipt_id`, empty for chat. The loader at `agent_turn_records.py:132` is strict on version, so this is additive and versioned. A workflow turn must never be projectable as a chat turn during inspection or scoped reset.

**Per-round reservation under the same receipt.** Each inference round calls `_reserve_and_arm_run_carrier_in_transaction` under the same receipt and claim, which is already how retries work. The admission arithmetic at `foreground_run_provider.py:457` must multiply each node's term by one plus a compiled `max_agent_rounds` taken from the immutable branch snapshot, default zero so existing workflows keep today's exact numbers. Pre-launch refusals already settle cancelled-before-launch at `router.py:952`. The existing check at line 463 still refuses a plan that exceeds the smallest member ceiling.

**Engine identity from receipt facts.** `_call` at `foreground_run_provider.py:770` must overwrite `engine_mcp_enabled`, `engine_mcp_actor_id` and `engine_mcp_graph_id` from the receipt's principal and universe the same way it overwrites the credential snapshot dir. Caller config never chooses the actor. If `read_engine_mcp_route` finds no route, hold with the existing `engine_tools_unavailable` reason before any reservation.

**Retry interaction.** A turn ending in `held_tool_unknown` or an orphaned `inference_started` round makes the node fail with that class and is not eligible for the compiled policy retry, because a fresh turn could replay an uncertain effect. `not_sent`, `capacity_no_effects` and pre-intent failures remain retryable. This is the workflow twin of the whole-turn refusal recorded at `http-agent-loop.md:42`.

**Can one implementation serve both?** Yes for the loop, no for authority. Chat keeps the live request capability, served budget rows, the set-once launch allowance and the converse operation. Workflows keep receipt, claim, one-use carriers, run status and consumer lease. The adapter is the only object that knows which world it is in. Sharing the authority code, or making one side impersonate the other, is what would collapse the contracts.

## Structured disagreements

1. **AGREE.** Keep `check_served_agent_tool_authority` at `provider_assignment.py:1303` chat-only. New callers get an adapter; the fence is not widened.
2. **AGREE.** Per-round reservation under the existing receipt and claim via repeated `_reserve_and_arm_run_carrier_in_transaction`. No new budget store, no new work id.
3. **DISAGREE_EVIDENCE** with "discovery adapter first". No argv channel exists at `codex_provider.py:232` and `claude_provider.py:444`, and `_native_default` refuses nonempty ids at `model_selection.py:156`. A catalogue with nowhere to go selects nothing. Owner-declared explicit ids plus propagation deliver selection now; enumeration extends the list afterwards.
4. **DISAGREE_CONCERN.** `_native_models` at `served_model_plan.py:154` flags a synthesized single row as fresh and owner-filtered. Require an `availability_basis` that separates executor default, owner declared and executor enumerated.
5. **DISAGREE_EVIDENCE** with "each inference uses the existing aggregate allowance" as already satisfiable. `max_invocations` at `foreground_run_provider.py:457` counts one launch per node attempt and `_call_index` at line 590 charges every round. A two-round turn exhausts a one-node run. The compiled per-node round ceiling is a pre-build decision.
6. **DISAGREE_CONCERN.** The four refusals at `router.py:494`, `:666`, `:672` and `provider_assignment.py:1308` are not pinned by any test. Relaxing them during integration cannot fail. Pin them before touching them.
7. **AGREE.** The journal is progress, never permission. Reuse it verbatim and add lineage fields only.
8. **AGREE.** A shared kernel with injected adapters serves both surfaces without collapsing ownership or lifecycle.
9. **DISAGREE_CONCERN.** Claude enumeration has no proven CLI seam in `native-discovery-evidence.md`, and the SDK it cites is excluded. Do not block the MVP on it; ship owner-declared ids and honest attestation for Claude and mark enumeration unknown.
10. **AGREE.** No automatic `--fallback-model`, and selection authority ignores `TINYASSETS_CODEX_MODEL` entirely.

## Prior-review coverage versus new decisions

| Item | Status |
|---|---|
| Version 4 manifest receipt, version 3 reservation with selection, carrier derivation, member budget sums | Covered by the September 11 extra review; landed |
| Explicit native ids in `ModelAccess` | Anticipated at `connection-model-authority.md:55`; the validator widening is new but small |
| `NativeSelection` record type and native evidence in `model_evidence_json` | New authority content under the existing schema |
| Owner-snapshot enumeration subprocess | New custody use, owner-scoped, no new grant |
| Router authority-derived agent permission, carrier observer hook, carrier accessors | New call-site semantics, no storage |
| `RoundInput` version 2 lineage fields | New additive storage decision |
| Compiled `max_agent_rounds` in admission arithmetic | New authority arithmetic |
| Kernel and adapter split | Refactor, no authority change |

## Required before build

- R1. Record the three-fact native contract and `NativeSelection` type; widen the validator for explicit ids.
- R2. Record the owner-snapshot enumeration rule: outside locks, snapshot cleaned, never host home, Codex only for now.
- R3. Record the router changes: authority-derived operation check, carrier observer, carrier accessors.
- R4. Record `RoundInput` version 2.
- R5. Record `max_agent_rounds` in the immutable plan and the held-unknown no-retry rule.
- R6. Pin the four existing refusals with tests before any relaxation.
- R7. Record that workflow `_call` sets engine identity from receipt facts.

## Optional follow-up, not blocking the MVP

Claude enumeration adapter when a CLI seam exists. Bounding `run_graph` nesting depth from a workflow tool beyond the aggregate budget. The background consumer holding its thread lock across an async multi-round turn. Picker input for adding an owner-declared id. Scoped-reset classification for work-lineage journal rows. Native account capacity scope, already conservative.

## Bounded implementation order

1. R6 pin tests, red-proof against the unfixed tree where behaviour will change.
2. `NativeSelection`, validator widening, `ModelConfig.native_model_id`, adapter argv. Ships owner-declared native selection for chat and workflows.
3. `_native_models` basis labels and picker rows.
4. Kernel and adapter split with the chat adapter only; existing interactive tests must pass unchanged.
5. Carrier accessors, `RoundInput` v2, router edits, workflow adapter, admission arithmetic, engine identity. Remove the line 672 refusal last.
6. Codex enumeration adapter and discovered-scope native selection.
7. Sync specs from what shipped.

## Minimum integration evidence

Positive:

- Native explicit id reaches argv: bind Codex with explicit ids including one nonempty, run a one-node workflow preferring it against a counting fake CLI; assert `-m` argument, reservation model id, owner_declared evidence, once-only settlement, main choice unchanged, and that a set `TINYASSETS_CODEX_MODEL` is ignored.
- Same id through chat: `NativeInput.model` carries it, the footer still says model not reported because the CLI attests nothing.
- Codex enumeration under a fake stdio app-server: subprocess home is the snapshot dir, snapshot removed afterwards, enumerated ids appear with the enumerated basis, a discovered-scope selection of one executes.
- Foreground HTTP agent turn with tools: real store, compiler and router, synthetic wire returning tool requests then text, fake engine route; two reservations under one receipt both settled, journal rounds carry work lineage, tool result recorded, run completes. Background twin under a lease.

Negative:

- The four pinned refusals stay green before and after.
- Nonempty native id outside explicit scope refuses before any subprocess; Claude argv has no `--model` for the empty id.
- Native catalogue older than the window or custody rotated refuses discovered scope; explicit ids still run.
- One node with a round ceiling of one and a wire requesting tools twice: second round refused with the aggregate class, first result preserved, turn held, no third network call.
- Run cancelled between inference and tool: tool not sent, no engine call. Member revoked between rounds: next round refused, prior result kept. Lease expiry likewise.
- Engine raises after send: `held_tool_unknown`, compiled retry does not start a new turn.
- A `provider_request` passed through workflow kwargs is refused, extending the checks at `foreground_run_provider.py:717`.
- Universe not allowlisted for engine routes holds before any reservation.

Final proof stays a rendered conversation through the live connector after deploy with the sha gate, plus one workflow node on a different HTTP model exercising a real tool.

## What this review does not establish

No tests, ruff, oracle, canary or provider calls were run. The design here is reasoned from source at f8299c49 only. Nothing approves PR3832 as a whole, the two untracked files, deployment, or complete model support.

VERDICT: ADAPT

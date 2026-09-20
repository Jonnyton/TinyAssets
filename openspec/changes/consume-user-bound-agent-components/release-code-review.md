Per the review brief, the dispatch queue above belongs to a different worktree (`0a7f`) and is out of scope for this read-only bounded review. I am not acting on it. Repeating the complete findings and exact head as instructed.

**Reviewed head:** `f9b91ed7f566dbce9a0d155c489efa94faafac99` (base `f65ceeb9`, clean worktree). Read-only; one focused test run; no subagents, peers, edits, or memory writes.

## Verification I ran

`python -m pytest -q -rs --tb=short -p no:cacheprovider tests/test_work_consumer_model_bridge.py` on Windows Python 3.14: 8 passed, 0 skipped, 15.08s, only the pre-existing asyncio deprecation warnings. This is the extended public-handle test (foreign public Branch, explicit remix, receiver-owned selection, initial dispatch and crash-after-admission, lost callback, capacity fallback, exact reply evidence). The documented 606/606 matched cohort is not re-claimed here.

## Answers

**1. Remix/install approval, exact pin, no creator authority, no engine self-install — AGREE.**
`consumer_selection.py:54-108` requires the binding be `created_by`/`updated_by` the owner, `status == configured`, no `provider_ref`, role `app_experience`, at most one active, and the definition fingerprint unchanged. `converse_turn` (`consumer_runtime.py:205-216`) refuses with `consumer_remix_required` when the pinned snapshot's author is not the owner; `_source_authority` (`conversation_run_admissions.py:254-261`) uses the same public-or-author rule as `_resolve_readable_branch` (`api/branches.py:532-534`). Components carry only pin + field map; provider authority comes from a fresh `_ForegroundRunProviderSession(principal_id=owner)` in `bind()`. Engine served `write_graph` refuses `agent_binding` (`engine_mcp_server.py:1670-1680`). Disabled selection `{version,state}` falls through to default chat; nested `invoke_branch*`/`node_ref` refused at load.

**2. One atomic admission, original intent, owner-scoped status, both tables classified — AGREE.**
`reserve_prepared_turn` writes run + `conversation_run_admissions` + `run_input_admissions` in one runs transaction after re-checking selection revision and preference generation. Digest includes universe and model_choice; conflict raises `IntentConflict`. `read_turn` returns uniform `not_found` for unauthenticated/wrong owner/missing. Both tables are in `PERSON_KEYED_DESPITE_UNIVERSE` and `_KNOWN_ROOT_RUN_TABLES`; reset expiry is witness-gated and idempotent.

**3. Static registry, held guard, CAS, v1 options, independent nomination, held-not-replayed — AGREE.**
`run_input_origins._adapter` is static; missing module → `OriginHeld` before executor submission. Worker path holds `try_run_execution_lock`, `require_held`, `start_in_transaction` CAS; `interrupted` returns without mutation; `OriginHeld` preserves the row. v1 hard-codes recursion 100 / None. Boot and 300s scans select only `execution_started_at IS NULL AND claim_token IS NULL AND status='queued'`. `settle_admitted_consumer` only calls `project_terminal`, which never submits.

**4. Preferences as data, frontier-only fallback, fresh authorization — AGREE.**
Captured document is validated against current generation at reserve; `WorkCandidateData` refuses partial explicit orders and fits only Automatic; `fit` refuses a changed fit; exhaustion is append-only; only `AllProvidersExhaustedError` with a non-None `capacity_boundary` advances; `WorkAgentAdapter.infer` re-authorizes via `_authorize_attempt` before switching.

**5. Node-specific attribution, no duplicate reply/tool — AGREE.**
`direct_reply_node` requires a single template writer of a str, non-reduced key; `_reply_execution` matches exactly one `ran` event whose `response == reply`, else None. Per-invocation `WriterExecutionReceipt` in the compiler. Client saves the key before the second send, polls `read_graph conversation_turn` (empty graph_id resolves to the bound founder home, `api/helpers.py:100-114`), dedupes by `consumer_turn_id`, and restore reads status before any converse.

**6. Imports without file adapter, pure held status, baseline intact — AGREE.**
`run_input_direct.py` is absent from the tree and only imported lazily for `direct`. `classify_admission_observation` is pure and emits no options/input. Compiler change is additive and signature-gated. Default converse now runs a read-only WAL probe of `agent_bindings` per call; all earlier converse guards already read the same DB, so no new failure surface in practice.

## Necessary corrections

None found that break a basic-safety invariant in scope.

## Optional post-MVP hardening

- `_call_captured_prompt` (`foreground_run_provider.py:205-251`) has no `visited` set; termination relies on `order_models` excluding the exact exhausted `(capacity identity, model)`. Sound today, fragile if exhaustion identity ever changes.
- `validate_prepared_turn` fails a queued-unstarted turn on any binding revision bump (a layout Apply during the recovery window), projected as a platform failure. Consider comparing only turn-relevant fields.
- If an app_experience binding with `turn_consumer` leaves `configured` or gains `provider_ref`, default chat returns `consumer_turn_held` and the app's Restore-default is disabled by `eligible()`. Owner-side disable should stay reachable.
- Exact replay of a terminal turn still submits a worker task before observing; skip `_dispatch` when projection is committed/expired.
- Harness honesty: with an active selection, plain connector `converse` returns `consumer_request_required` until the harness supplies the object. Correct and non-silent, but the control-station guidance does not describe it yet.

**VERDICT: APPROVE** at `f9b91ed7f566dbce9a0d155c489efa94faafac99`. Gates landing only; deployed two-owner app acceptance and canonical spec sync remain required.

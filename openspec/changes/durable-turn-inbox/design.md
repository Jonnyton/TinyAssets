## Context

**What #4278 shipped.** `deploy/wait_for_turns.sh` polls `scripts/turns_in_flight.py`, which runs in a sibling container against the data volume. The swap is held while any live seat or live-owned graph run exists. The loop proceeds on idle, on an unhealthy daemon, on three unknown answers, on a queued recovery workflow, or after 45 minutes. While waiting it refreshes a TTL'd `/data/.deploy-pending.json`, which `get_status.deploy_pending` reads.

**The gap.** When turns keep overlapping, idle never comes, and the cap cuts whatever is running. The lead ruled (2026-10-02) that an admission hold must not ship without persist and replay.

**The bigger plan.** #4263 D11/S8 needs the same thing for the owner handover: frontends queue turn starts while the owner changes, new requests never fail, and the incoming message is persisted first. This change builds that queue. `execution-owner-lease` (next) makes the owner handover drain it.

**Constraints.**
- Hard Rule 8: fail loudly, never a mock reply.
- Never replay an effect.
- Every user is the founder of their own universe, and authority is re-derived, never carried.
- Clean cutover: no compatibility shims while early.

## Goals / Non-Goals

**Goals:**
- A message sent during a deploy hold is never lost and never silently dropped.
- The owner sees it queued at once and sees the reply after the update, in the same thread.
- The deploy can reach zero in-flight turns under steady chat load, so the cap stops being the normal exit.
- Exactly one answer per queued message, and at most one execution of its effects.

**Non-Goals:**
- Keeping the open client stream alive across the swap. That needs blue-green frontends: #4272 plus `execution-owner-lease`.
- Holding `run_graph`/automation run admission. Automations are already durable: the pump re-polls and a wake that cannot start waits. A `run_graph` admitted during the hold counts as in flight, and the deploy waits for it up to the cap. This is stated as a gap, not solved here.
- Resuming a turn that the cap or a yield cut. That turn is settled and the user is told, as today.

## Decisions

### D1. The hold is a field on the existing marker, and it expires with it
At `TURN_HOLD_AFTER_S` (default 600, i.e. ten minutes into a wait), `wait_for_turns.sh` passes `--hold` and the marker carries `"hold": true`. The daemon reads it through the same reader as `get_status` (`_load_deploy_pending`). An expired marker means no hold, so a deploy job that dies mid-wait releases the hold within one TTL (60s). Nothing is persisted for the hold beyond the marker.

*Alternative rejected:* a daemon-side admission flag set over an RPC. There is no frontend/owner RPC until S8, and a flag the deploy cannot clear on crash would be worse.

### D2. Admission point: the server `converse` handler, after auth, before any turn work
The hold check runs once the caller is proven to be the authenticated owner of the resolved universe. It runs before any seat is taken, before the journal row is created, and before any provider call. During a hold, the handler persists the inbox row and the thread rows (D4), then returns at once. A turn that already holds a seat when the hold starts is in flight: it runs to completion, and the deploy waits for it.

### D3. A dedicated inbox table in the data-root journal database
`deferred_turns` lives in `<data_root>/.tinyassets.db`, beside `agent_turns`, with one writer: the daemon. Columns:
- `inbox_id` (uuid PK)
- `owner_user_id` (the authenticated caller's id, as `converse` resolves it)
- `universe_id`, `session_id`
- `message` (verbatim, per Hard Rule 9)
- `input_method`
- `model_choice_json`, `consumer_request_json`
- `founder_turn_no`
- `state`: `queued`, then `claimed`, then `answered`, `failed` or `interrupted`
- `claim_boot`
- `created_at`, `updated_at`
- `result_ref`

It is a new table, so there is no migration of existing rows. Account deletion's schema-derived sweep picks up `universe_id`, which `account-deletion` requires.

*Alternative rejected:* reusing `conversation_run_admissions` and its run envelope. That ties a queued chat to a `runs` row, and `recover_in_flight_runs` interrupts any queued run whose owner died, which is exactly the swap. It would also give the default conversation the custom-consumer machinery it does not use today.

### D4. The thread shows it at once, with no conversation-store schema change
At enqueue, the founder's message is recorded as a normal founder row (`record_turn`, `ext_id = queued:<inbox_id>:founder`). A platform notice row follows it (`ext_id = queued:<inbox_id>`): "Queued: TinyAssets is finishing an update. Your message will be answered right after it." Both ext ids make enqueue idempotent.

At replay, the turn's conversation history is the thread minus that founder row, because the message itself is passed as `founder_message`. The reply is recorded as the reply to that row. The notice stays: it is a true account of what happened.

### D5. Replay re-derives authority and runs the same served path
The `converse` tool body is split into two parts:
- the caller-facing part: auth, request resolution, the hold check;
- `_served_turn(universe_id, actor_id, message, ...)`, which is everything after.

The boot drainer calls `_served_turn` for each `queued` row, with no request context, after these re-checks:
- `check_current_home(owner, universe)` still binds the universe to the owner;
- `universe_access_allows(owner, universe)` still holds;
- a `consumer_request` binding still exists at the stored revision.

Any refusal settles the row as `failed`, with the standard failure notice. Nothing is silently skipped.

Provider authority is whatever a served turn for that owner and universe resolves today, from current state, through the same code. Nothing from enqueue time is trusted except the message, the model choice and the identifiers. **This is the part the cross-family review must attack (Q1).**

### D6. At-most-once effects: claim, then answer; a crash mid-replay becomes interrupted
The drainer moves `queued` to `claimed` (stamping `claim_boot`) in one transaction before it runs the turn. If the turn succeeds or fails, it records the outcome and moves the row to `answered` or `failed`.

A later boot that finds a row `claimed` under a different boot never runs it again, because its tools may have run. It settles the row `interrupted` and posts the existing interrupted-turn notice, the same uncertainty-preserving rule `agent_turn_reconcile` applies.

The drainer runs rows in `created_at` order. Rows for different universes run concurrently, up to the seat limits. Rows for one universe run one at a time.

### D7. The deploy waits for zero while holding
`wait_for_turns.sh` keeps all of its outcomes. Holding just makes `idle` reachable: in-flight turns finish, and no new turn starts. After the swap, the new boot drains the queue. The marker is cleared after the swap, not before, so the hold covers the swap itself. A crashed job releases the hold within one TTL.

### D8. What the client sees
For a held turn, `converse` returns the queued notice text as its reply, plus `{"queued": {"inbox_id", "reason": "deploy_pending"}}` in the JSON envelope. The tool contract is unchanged: the reply is still the text the client renders verbatim.

The app's thread poll shows the reply when it lands. Today a claude.ai-style MCP client sees it on the next `converse`, through the thread history. A push notification for the reply is `notify-owner-of-requests`' job and is out of scope here.

## Risks / Trade-offs

- **[Replay without a live request misses something only the request carried]** Mitigation: the request carries identity only. D5 re-derives everything, and Q1 asks the reviewer to find any request-scoped grant a served turn depends on.
- **[A deploy holds admission, then crashes]** The marker TTL releases the hold within 60s. A turn that tried to start meanwhile was queued, not refused, and the still-running old daemon drains its own queue on the next marker-free poll (the drainer also runs on a timer, not only at boot).
- **[Queue grows during a long wait]** Bounded by how fast owners send. Each row is small. The drainer runs them under the existing seat limits.
- **[A replayed reply arrives minutes later and reads oddly]** The queued notice tells the owner it will happen. The reply is in the same thread, in order.

## Migration Plan

New table, created on first write. The hold is off unless a deploy sets it. Roll back by reverting. A queued row left after a revert is drained by nothing; the revert must drain or settle open rows first. This is a stated precondition of the rollback, not an automatic step.

## Open Questions

- **Q1 (authority).** Does any part of a served founder turn depend on the live request: an OAuth access token, a per-request provider grant, the request's session for consent, or the identity binding cache? If so, the replay must re-obtain it or settle the row `failed` with a "send it again" notice.
- **Q2.** Should the drainer also run on a timer in the OLD daemon when a hold lapses without a swap? Proposed: yes, every 30s when no hold is set.
- **Q3.** Does the default for `TURN_HOLD_AFTER_S` (600s) fit the founder's turn lengths? Proposed: 600s, so a single long turn is never held behind a fresh one for more than ten minutes before admission closes.

## Review: Codex gpt-6-astra shape refute, 2026-10-02, ADAPT

The design above is the version that was reviewed. Do not build it as written. These are the findings that change it:

1. **P1, Q1 answered NO.** A served turn needs a live, process-local provider-request capability (`auth/middleware.py:297`, `_PROVIDER_REQUESTS`). The MCP wrapper revokes it before the response returns (`universe_server.py:385`), so it cannot survive a deploy. The identity ContextVar (`current_actor_id`, `api/permissions.py:236`) and the founder tier also come only from the live request: the tier is an admin-ACL check through the contextual actor (`api/interlocutor.py:184`). D5's re-checks would pass, and replay would still fail, or run at T0. Replay needs a new, reviewed deferred-execution authority path.
2. **P1.** Execution success is not durable delivery: `record_exchange` is best-effort (`universe_server.py:3143`). A replay needs a frozen terminal and an idempotent, repairable thread projection (the pattern in `storage/conversation_run_admissions.py:460-537`). It also must not duplicate the `interrupted:<turn_id>` notice from `agent_turn_reconcile`.
3. **P1.** D3's premise is wrong. Runs carrying `run_input_admissions` are excluded from orphan recovery (`runs.py:150`). Queued, unstarted `canonical_consumer` admissions are recovered (`run_input_origins.py:81`). Custom-consumer turns are asynchronous: a return means pending, not answered.
4. **P1.** Account deletion sweeps by the CURRENT home (`account_deletion.py:350`), so rows queued under a former home survive.
5. **P2.** D4 breaks ordering and the learned cursor. A running turn's `turn_began_at` predates queued rows, and `settle_learned_cursor` can advance across them.
6. **P1.** Carryover and steering are deleted before they are persisted (`agent_steering.py:217,227`), so a crash mid-replay loses owner text.
7. **P1 (concern).** There is no admission/cutover barrier. A request can pass the hold check, then miss both the inbox and the seat count before the swap.
8. **AGREE.** The D6 claim-then-never-rerun rule is sound for at-most-once, as long as the drainer stays in the single writer process.

**Proposed disposition (sent to the lead):** supersede this change with `execution-owner-lease` (#4263 S8). There, the frontend queues the LIVE request in memory for the seconds an owner handover takes, so no replay authority is needed.

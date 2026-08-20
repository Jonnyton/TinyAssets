# Slice 3 record-wiring seam — why async action-result delivery can't record at the enqueue site

**Date:** 2026-08-19
**Context:** Serving-reliability program, Slice 3 (deliver an async action's terminal
result back to the originating Slack conversation as a follow-up). The delivery
CORE (`tinyassets/storage/action_result_outbox.py` + `tinyassets/action_result_delivery.py`)
is built + tested. This audit records why the **record-side** wiring is a
cross-boundary change, not the "minimal wire" the change proposal first assumed.

## The finding in one line

`run_id` and the Slack conversation origin are **never in scope at the same place**,
so nothing can `outbox.record(run_id, origin…)` today without a new origin-carrier.

## The two ends of the seam (file:line anchors)

**End A — the Slack origin lives here, but the run_id does not.**
`tinyassets/app_ingress.py::deliver_app_event` (def at `app_ingress.py:84`) has in
local scope: `workspace_id, channel_id, thread_ts, event_id, api_app_id`, plus
`routed.universe_id / routed.agent_binding_id / routed.binding_revision` (from
`_route`, `app_ingress.py:131`). It calls converse (`app_ingress.py:307`):

```python
reply = converse(routed.universe_id, prompt,
                 actor_id=_actor_id(workspace_id, external_sender_id),
                 founder_grant=grant, conversation_history=history)
```

`converse` returns only `reply: str`. **No run_id comes back.**

**End B — the run_id lives here, but no Slack field does.**
The run is minted and enqueued deep below converse, triggered by the model calling
the `run_graph` engine tool during its own turn:

- `universe_intelligence.py:801` — `converse` → `_call_writer(...)` runs the writer
  LLM turn with engine MCP tools `("read_graph","get_status","run_graph")`.
- `engine_mcp_server.py:242` — `run_graph(branch_def_id, run_name, inputs_json)` →
  `universe_server.run_graph` under `_bind_founder_identity(_RUN_CAPABILITIES)`.
- `universe_server.py:1107` → `api/runs.py:562` `_action_run_branch(kwargs)` — kwargs
  = `{branch_def_id, inputs_json, run_name, universe_id, recursion_limit_override,
  resume_from}`. **No Slack field.** Calls `execute_branch_async(...)` (`api/runs.py:706`).
- `runs.py:3187` `execute_branch_async(base, *, branch, inputs, run_name, actor,
  provider_call, recursion_limit_override, _enqueue_universe_id)` → `_execute_branch_core`
  (`runs.py:3092`), where `run_id = _prepare_run(...)` (minted at `runs.py:787`,
  `uuid.uuid4().hex[:16]`) and `executor.submit(_worker)` queues the background run.

Between End A and End B the call crosses `converse` (no origin params) and a fresh
engine-MCP-identity tool turn. **There is no context object spanning that boundary
that carries the Slack event.** The persisted run row DOES carry `queue_universe_id`
+ `actor=universe:<uid>` (`runs.py:274,784`), so universe_id is durable — but nothing
Slack-conversation-shaped is.

Original proposal task 3.1 ("record at `_action_run_branch` when an app origin is
present") is therefore built on a false premise: no app origin is present there.

## The recommended fix (its own change, needs Codex review)

Bring `run_id`s **UP** to `deliver_app_event`, do not thread origin **DOWN** into the
engine (which would cross the security-sensitive engine-MCP identity boundary):

- `converse` captures the `run_graph` engine-tool results produced during the writer
  turn (each result carries a `run_id`) and returns the enqueued run_ids alongside
  `reply`.
- `deliver_app_event` — which already holds the Slack origin — calls
  `outbox.record(run_id, workspace/channel/thread/event/app_binding/universe)` for
  each returned run_id.

This touches writer-turn stream capture (Slice 1 already added stream parsing in
`claude_provider.py`, so the machinery exists), so it is a real change, not a wire.

## Data-shape notes for the delivery tick's `get_run` seam

`get_run(base, run_id)` (`runs.py:1035`) returns `_row_to_run` fields (`runs.py:496`):
`status, actor, output(dict), error, last_node_id, queue_universe_id, …`. It does
**not** return `public_result_ref`, `result_url`, `failed_phase`, `terminal_phase`,
or `revision`. `action_result_delivery.compose_summary` reads those optional keys and
safely falls back to a generic (leak-free) message when absent — so the CORE is
content-safe against the real run dict; the wiring must **deliberately** populate a
public result ref (e.g. from a known field inside `run["output"]`) rather than dump
`output`, to preserve the no-leak guarantee.

## Cadence tick home

Production periodic work uses daemon threads started in `universe_server.main()` —
e.g. `_served_budget_lease_loop` (`universe_server.py:2915`, thread at `:2933`). The
`Scheduler._tick_loop` (`scheduler.py:551`) exists but `get_or_create_scheduler` has
no production caller in this worktree. So the delivery tick should be a sibling
daemon thread in `main()`, matching the established idiom.

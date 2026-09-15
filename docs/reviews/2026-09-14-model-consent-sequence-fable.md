# Fable 5.1 model-consent sequence review

September14 2026. Subprocess6620 completed341seconds/exit0. Full deliverable
recovered from its assigned session021b95be-aa6e-4318-b8a1-fb0901e3e326,
assistant message22:53:32UTC; terminal stdout again contained only a hook recap.
This is architecture review, not exact-code or live acceptance.

Review complete. Everything below is from reading the code in this worktree at 497d8860; it is a shape verdict, not exact-code verification of an implementation that does not exist yet.

## Recommendation: state-classified answer handler, no new receipt

The existing rail pattern (act, then `resolve_request`, refusal leaves the row pending) is the right frame, and the assignment digest already is the request-specific receipt for the second stage. Do not add a progress column or a new failure schema. What is needed is a three-state classifier at answer time plus one small fence added to `set_serving`.

**Why revision alone cannot carry the sequence.** Two facts from the code change the proposed fence:

- Enabling serving does not bump the agent binding revision. `set_binding_serving_in_transaction` updates only status/updated_by/updated_at with a `revision = ?` guard (`tinyassets/custom_agents.py:1305-1310`). Binding does bump it and resets status to `configured` (`custom_agents.py:1250-1253`). So the row moves (R, any) → bind → (R+1, configured) → enable → (R+1, serving). There is no "original+2".
- Assignment state is per universe, not per agent binding (`load_provider_assignment(base, universe_id=uid)`, `provider_serving_binding.py:569`), and provider binding ids are deterministic from owner+universe+provider (`provider_serving_binding.py:553-558`). Another owner binding can advance the generation without touching our revision, and `provider_ref` equality does not detect that (`served_model_plan.py:278`).

The pending and failed intermediate states are written at the same generation as the eventual ready state: pending at G+1 (`provider_serving_binding.py:631-677`), failed at G+1 by `_write_failed_assignment` (`178-207`), ready at G+1 (`753-768`). So "generation == G+1" alone is ambiguous; state and content must be part of the fence.

### Ask-time (creation) validation

Add a `bind_model_access` branch to `_validated_action` (`tinyassets/api/pending_requests.py:156`, closed allowlist at `233-237`) and an ask verdict at the `request_from_user` seam where `_extend_ask_verdict` runs (`682-704`). The verdict runs as the founder principal (served path binds identity at `engine_mcp_server.py:1578`) and must:

1. Parse `model_access` per member with `ModelAccess.from_json` exactly as the app route does (`tinyassets/api/custom_agents.py:310-316`), factored into one shared helper so there is no second parser. Non-empty, root in membership, unique.
2. `get_binding(base, universe_id=uid, binding_id)`; require `created_by == actor` and `revision == expected_revision`; refuse otherwise. The agent got the revision from the pinned `agent_binding` read, so a stale ask just means re-read.
3. Current-home fence: `check_current_home(conn, owner, uid)` in a store transaction, the same call `set_serving` makes (`provider_serving_binding.py:1038`). Bind itself has no home check, so this is the only place it lands before the owner sees the tab.
4. Resolve every member with `_resolve_serving_source(base, uid, owner, name, access)` (`provider_serving_binding.py:349`) so unknown, unowned, or held providers fail at raise time, not on the owner's click.
5. Read the current assignment and capture server-side into the action: `expected_assignment_generation` (0 if none) and `current_membership` (provider → `access.document()`), discarding any agent-supplied values the way `policy_snapshot` is (`pending_requests.py:688-698`). Preserve rule: refuse a proposal that drops a currently accepted provider. Changes to an existing member's scope or caps are allowed only because they are disclosed line by line from the server-captured diff.
6. Fields: add the type to the "nothing to type" set (`pending_requests.py:533`), so `recordable` is empty and no field can prefill an answer. `dont_ask_again` is already forced off for non-`answer` actions (`1340-1341`), and the served surface has no answer operation (`engine_mcp_server.py:1566-1574`); the new type inherits both.

### Deterministic disclosure

Add a `bind_model_access` branch to `_grant_sentence` (`pending_requests.py:968`). Derived only from the stored action, it must name: binding, root provider, each added member and each changed member as "from → to" (scope, model ids, caps with `None` rendered as free models only), and the reconnect clause: "disconnects this agent and reconnects it on the new access; if reconnect fails it stays off until you answer again or fix the reason." The answer-time dedupe check (`1366-1374`) already binds the executed row to the rendered one.

### Answer-time classifier

Dispatch beside `grant_workspace_consent` (`pending_requests.py:1412`) into `_bind_model_access(...)`. Observe binding (revision, status, created_by, provider_ref) and assignment (state, generation, owner, provider, candidate documents). Let R, G, M be the stored expected revision, generation, and proposed membership. `match(a)` means `a.owner == actor and a.provider == root and {c.provider: c.access.document()} == M`.

| State | Condition | Act |
|---|---|---|
| A untouched or our own dead attempt | `revision == R` and (`assignment is None and G == 0`, or `generation == G`, or `generation == G+1 and state in {pending, failed} and match`) | `bind_serving_provider(expected_revision=R, model_access=M)` then enable |
| B bound, not serving | `revision == R+1`, `status == configured`, `state == ready`, `generation == G+1`, `match`, `provider_ref == assignment.binding_id` | enable only, pinned to the observed `assignment_digest` |
| C done | same as B but `status == serving` | `resolve_request(answered, decision=allowed)`, no act |
| else | | return `provider_authority_denied` with detail, leave pending |

The State A acceptance of failed/pending at G+1 is required, otherwise the retry after a bind that failed between its two transactions (`provider_serving_binding.py:786-789`) is permanently refused. Content match is what identifies those states as ours: only a bind with exactly that membership writes them.

**Enable stage fence (the one code change outside the rail).** `set_serving` has no assignment parameter. Add an optional `expected_assignment_digest` kwarg checked inside the exclusive admission and `BEGIN IMMEDIATE` block (`provider_serving_binding.py:1003-1012`), against `load_provider_assignment_in_transaction` for the legacy path and `prepared.assignment` for the prepared path. The digest commits to owner, universe, provider, generation, binding id, custody, and manifest (`133-175`), so it closes the cross-binding republication gap that revision CAS misses. `prepared.recheck` already refuses "model assignment changed during discovery" (`served_model_plan.py:91`), but that compares to what `prepare` captured, not to what the owner consented to.

**Partial failure and retry.** After State A's bind succeeds and enable raises, return `{"error": "provider_authority_denied", "stage": "reconnect", "bound": true, "detail": ...}` without resolving. The next answer lands in State B and never re-binds, so no second publication. If enable succeeds and `resolve_request` returns False (`storage/pending_requests.py:315-316`), the next answer lands in State C and resolves without acting. Map exceptions the way the app route does (`api/custom_agents.py:327-331, 345-349`). Wrap the two stages in onboarding's `_gesture_lock(uid)` (`onboarding/serving.py:69`) to reduce spurious CAS refusals against the app's own connect gesture, but treat it as process-local convenience, not a fence. The cross-process fence is the admission file lock plus revision CAS plus the digest pin; the admission lock is non-reentrant (`provider_assignment.py:1020-1021`), so the handler cannot hold it across both stages and must not try.

### Tests that must go red on the unfixed tree

1. Raise-time refusals with rail count 0: foreign binding, stale revision, non-home universe, unknown/held provider, proposal dropping an existing member (pattern at `tests/test_pending_requests.py:255`).
2. Sentence determinism and content: two asks with different prose but same action yield identical sentences that include every member, free-only rendering, and the reconnect clause.
3. Happy path: R+1, `serving`, ready at G+1 with candidates equal to M, other members' documents byte-identical, row answered with decision allowed.
4. Stale revision before answer: refused, generation unchanged, row pending (pattern at `test_pending_requests.py:287`).
5. Partial: `set_serving` raises once. Assert error carries stage reconnect, revision R+1, status configured, row pending. Re-answer with a spy proving `bind_serving_provider` is not called, generation still G+1, then serving and answered.
6. Interleaved: after partial, owner rebinds by hand to different membership. Re-answer refused, nothing enabled.
7. Crash after enable: `resolve_request` returns False once. Re-answer resolves via State C with neither stage called.
8. Failed bind retry: force the second bind transaction to raise. Assert failed at G+1 and revision R, then re-answer publishes ready at G+2 and serves.
9. Cross-binding: another owner binding publishes ready at G+1 with different content. Answer refused.
10. Unit: `set_serving(expected_assignment_digest=wrong)` raises inside the transaction and leaves status unchanged.
11. Served: `pending_request operation=answer` refused for this type; `dont_ask_again` on it records no suppression.

## Structured disagreement

**AGREE**
- Typed rail action, never a served bind: the served agent is the founder principal (`engine_mcp_server.py:1578`), and the served surface deliberately omits answer (`1562-1565`).
- Validate on creation and again on answer; downstream refusal leaves the row pending, matching extend_http (`pending_requests.py:1439-1442`).
- Disclosure must include reconnect: bind resets status to `configured` (`custom_agents.py:1252`), so a serving agent goes dark on an access-only ask that stops there.
- Exact payload plus server-observed state is enough provenance. No new receipt mechanism.

**DISAGREE_EVIDENCE**
- "After both stages, original+2": false. Enabling serving does not increment revision (`custom_agents.py:1305-1310`). A handler coded to R+2 strands every completed consent as pending.
- "On owner answer, bind only if exact original state": too strict. A bind that fails between its two transactions leaves failed at G+1 with revision R (`provider_serving_binding.py:178-207, 786-789`), which the exact-original rule refuses forever.
- "Retry may reconnect if revision is original+1 and generation is original+1": insufficient alone. Generation G+1 is shared by pending, failed, and ready (`631-677`, `753-768`), and the same digest-free check passes when another owner binding republished the universe assignment (`569`, `553-558`). The enable stage needs the digest pin.

**DISAGREE_CONCERN**
- Answering performs remote discovery through the owner's grant before the lock (`provider_serving_binding.py:998-1002`). That is the owner clicking, so it is acceptable, but the tab should not promise an instant result.
- Re-asks after state changes accumulate pending rows the agent cannot dismiss, against `MAX_PENDING` (`storage/pending_requests.py:203`). Consider auto-dismissing superseded pending rows of this type at raise time. Not a blocker.
- Claude-code hold depends on an environment variable read at resolve time (`provider_serving_binding.py:397`). Ask-time and answer-time processes could disagree. Answer-time re-validation covers it.

VERDICT: ADAPT

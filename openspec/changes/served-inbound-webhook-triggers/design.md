# Design: served inbound webhooks

## Shape

This adds no new primitive. The hook store, the receiver and the owner-scoped
handlers already exist and are proven by `test_webhook_inbound_hardened.py`.
The change exposes those handlers on the served surface, as
`user-owned-automations` already did for automations (PR #3447).

```
app agent ──write_graph target=webhook op=create branch_id=B──▶ engine_mcp_server
   pins: _GRAPH_ID (universe U), _ACTOR_ID (owner P)
   admission: _engine_run_admit(fail_closed, kind=engine)   (same as automation create)
   _extensions_impl(action=mint_webhook, universe_id=U, branch_def_id=B)
      ├─ _branch_run_scope_error: P must hold write on U
      ├─ _resolve_owned_branch: B.author ∈ {P, universe:U}
      └─ webhook_hooks.mint(U, B, owner_principal_id=P) → raw token (shown once)

POST /mcp/hooks/<token> ─▶ handle_hook ─▶ enqueue_universe_branch_run(U, B, principal_id=P)
   actor universe:U, provider = U's current serving assignment via P's foreground session
   run_name "webhook", visible in read_graph target=runs; failures carry failure_class
```

## Decisions

- **D1: Pins, not parameters.** The served schema gains no universe, owner or
  graph field. `test_documented_webhook_operations_are_the_dispatched_ones`
  asserts this.
- **D2: The token goes to the owner's own agent.** The connector already hands
  the same URL to the owner's chatbot. The served agent acts as the owner
  (memory `no-anonymous-actions-execution-attached-to-universe`). The URL lets a
  caller trigger only that one branch as that universe. Deliveries are
  rate-limited, deduplicated and capped per universe.
- **D3: Revoke by prefix, fail closed on ambiguity.** `revoke_by_prefix`
  requires exactly one active non-Source row in the pinned universe with that
  12-character prefix. Zero or many matches revoke nothing. It never reaches
  another universe (mutation-checked).
- **D4: `next_due_at` comes from `_due_instant`.** It is not a second
  scheduler. For interval triggers it is the anchor plus one period. For cron
  triggers it is the first matching local minute within 366 days, found by
  skipping days and then hours. An owed run reports its owed instant, and a
  paused or retired row reports `''`.

## Out of scope (tracked, not fixed here)

- Non-Source event types (`canon_change`, `branch_run_completed`, `canon_upload`,
  `pr_open`) have no emitter anywhere in `tinyassets/`. A subscription to one is
  stored but never fires. See the updated concern
  `2026-09-02-non-source-event-subscriptions-never-fire.md`.
- A refused delivery (unknown or revoked token) answers with a uniform 404 and
  is visible only in the server log. The owner cannot see refused deliveries.
- Webhook signature verification (HMAC) belongs to C26.

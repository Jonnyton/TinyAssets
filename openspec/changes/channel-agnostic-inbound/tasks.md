# Tasks — channel-agnostic inbound

## Phase 1 — Floor 1: universal inbound webhook (shippable slice)
- [ ] 1.1 `tinyassets/storage/webhook_hooks.py`: per-universe hook-token store — table
      `webhook_hooks(token PK, universe_id, branch_def_id, created_at, revoked_at)`;
      `mint(universe_id, branch_def_id)` (unguessable token), `resolve(token)` (active only),
      `revoke(token)`, `list_for_universe(universe_id)`. Content-free (ids + token only).
- [ ] 1.2 Tests: mint→resolve; revoke→resolve None; unknown→None; per-universe scoping.
- [ ] 1.3 `tinyassets/webhook_inbound.py::handle_hook(token, body, headers)` — resolve or
      404-indistinct; size cap; enqueue via the gated run path (`_action_run_branch`-equivalent)
      as `actor=universe:<uid>`, author-gated; `inputs={"webhook": {...}}`; per-token rate limit;
      return `(status, payload)`. Transport-agnostic (testable without a server).
- [ ] 1.4 Mount `Route("/hooks/{token}", handle, methods=["POST"])` in `create_streamable_http_app`
      (`universe_server.py`). Bind it AFTER discovery, before the MCP catch-all.
- [ ] 1.5 Tests: valid token → 202 + run enqueued as the universe; unknown/revoked/malformed →
      404 indistinct + nothing enqueued; cross-universe token cannot trigger another branch;
      oversized body → 413/400; body passed as input verbatim.
- [ ] 1.6 Mint/revoke/list user operation (MCP-reachable via `runtime_ops`/extensions), authorized
      to the caller's OWN universe only; returns the full `https://<domain>/hooks/<token>` URL.
- [ ] 1.7 Tests: mint for own branch → URL; mint for a branch the universe does not own → refused.
- [ ] 1.8 Plugin mirror rebuild + parity; ruff; targeted pytest green.
- [ ] 1.9 Codex cross-family review (public-surface security: token unguessable + per-branch,
      no identity from request, author-gated run, 404-indistinct, rate-limited, dark-until-tunnel).
- [ ] 1.10 Land; the code is DARK until the tunnel exposes `/hooks/*` (founder-gated infra +
      §11 canary). Document the enable step.

## Phase 2 — Floor 3: activate the event bus (built next)
- [ ] 2.1 Start `get_or_create_scheduler(base, run_fn=execute_branch_async)` at daemon boot, behind
      provider-authority safeguards (effect-only branches need none).
- [ ] 2.2 Admit a namespaced `source:<id>` event_type past `VALID_EVENT_TYPES` (`scheduler.py`).
- [ ] 2.3 Let the Floor-1 webhook OPTIONALLY `emit_event` for subscription fan-out + idempotency.
- [ ] 2.4 Tests + Codex review + land.

## Phase 3 — Floor 2: source nodes (built last, only for non-webhook channels)
- [ ] 3.1 A kept-live node kind (opaque channel logic, supervised, emits via `emit_event`).
- [ ] 3.2 Rebuild Twitter as a node-shaped, vault-backed connector (replace the hard-coded
      env-var `twitter_post` effector) — the founder's "connect Twitter" test.

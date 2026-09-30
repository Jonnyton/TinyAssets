# Design: two doors

## The principle

**Owner surfaces are complete. Bounding is a model-door projection. The only
per-account input is account type.**

A bound exists because a model's context window is small. An owner's screen has
no such window. When both read through one path, a model-sized bound reaches the
owner and cuts the most for the heaviest user. On 2026-09-30 that was the founder.
The fix is to separate the paths, so the bound cannot reach the owner, rather than
list the owner's reads as exceptions.

## Shape

```
                      tinyassets/api/graph_reads.py   (domain: complete, owner-gated)
                         ^                         ^
                         |                         |
   owner door  ----------+                         +----------  model door
   tinyassets/owner_door/                          universe_server.read_graph
   /app/api/read, /app/api/status                  + _structured_return ceiling
   (no bound; cannot import one)                   + model_options projection
                                                   engine_mcp_server (own dispatcher, own ceiling)
```

- **`graph_reads.read_graph(target, ...)`** is the `read_graph` dispatch moved
  verbatim from `universe_server`. It returns a JSON string, exactly as before. It
  does the owner gating it always did, because each domain function gates itself
  (`_owner_gate`, `require_founder_home`, admin ACL). It knows nothing about
  models or sizes.
- **Connector (`universe_server.read_graph`)** keeps its public signature and
  docstring (the tool contract). It calls `graph_reads.read_graph` and applies the
  model-door projections: `model_options` becomes `compact_model_options`, and
  `_structured_return` applies the ceiling.
- **Owner door (`tinyassets/owner_door/`)** has two handlers:
  - `POST /app/api/read` takes a JSON object of `read_graph` arguments.
  - `POST /app/api/status` takes `universe_id`, `include_conversation`,
    `conversation_before` and `conversation_limit`.

  Each handler checks the identity, runs the domain read in a worker thread under
  the request identity, and returns the domain's document unchanged, refusals
  included. A domain document can carry `error` as data (a failed run's reason),
  so this door does not reinterpret it. Arguments the door cannot accept get a
  4xx. A server failure is a 500, never an empty document.

## Why this is structural, not a rule

Three facts are asserted mechanically in `tests/test_owner_door_import_boundary.py`:

1. **The owner door cannot reach a bound.** No module under
   `tinyassets/owner_door/` imports `engine_result_bounds`, `engine_read_views`,
   `universe_server` or `engine_mcp_server`. That covers function-level imports
   too, because the check walks the whole AST.
2. **The domain layer cannot bound.** `graph_reads` imports none of those
   modules. So the owner door, which calls only `graph_reads` and `api.status`,
   has no path to a bound: not directly, and not through the domain.
3. **The bound lives only at the model door.** Every importer of
   `engine_result_bounds` in `tinyassets/` belongs to the model-door set
   (`universe_server`, `engine_mcp_server`, `engine_read_views`). A new importer
   fails the test, so the next person to bound something must do it at the model
   door.

A future session adding a new app read has nowhere to put an exemption. The app
reads through a door that has no bound, and the model door has no reason to know
the app exists. A future session adding a bound can only add it at the model door.

## Why the owner door is a route, not a flag on the connector

We rejected "complete when the caller is the app" on `/mcp` in
`bounded-model-facing-catalogue-read`, for good reason. The server would be
guessing the caller's kind from a transport fact. A model driving the founder's
browser session looks exactly like the app. With two routes nothing is guessed:
the route is the door. A model driving the founder's browser reads a rendered
page, not raw JSON, so complete data at the owner door is correct for it too.

## Authority: no new authority

- `/app/*` is already bearer-challenged by `auth.middleware._auth_challenge_path`
  (`_is_app_path`). The new routes sit under `/app/api/`, so they inherit that.
  `_app_identity_required()` re-checks for a named identity.
- Every read executes under `identity_context(identity)`, the same identity the
  MCP tool would run under, and reaches the same domain function with the same
  owner gate. The owner door adds no gate and removes none. A non-owner gets the
  same refusal the connector gives (`not_found` / `permission_denied`), which the
  tests assert.
- Reads only. `/app/api/read` refuses any target the dispatcher does not know,
  exactly as `read_graph` does, and it accepts only the dispatcher's own parameter
  names with their declared types. Unknown keys return 400.
- The edge already routes `tinyassets.io/app/*` to the daemon (`wrangler.toml`),
  so this needs no edge change.

## Complete domain reads

- `storage.pending_requests.list_pending(universe_dir)` has no `limit`. It returns
  every pending row, and it **raises** on a storage failure rather than returning
  `[]`. An unreadable queue shown as "nothing pending" is the silent failure this
  change removes. Callers that reconcile (`model_bootstrap`,
  `connection_lifecycle`, `agent_access`) already passed `limit=None`.
- `api.pending_requests.list_requests(universe_id)` has no `limit`. The
  connector's `limit` argument no longer reaches it. On the model door the
  ceiling bounds the whole document, visibly.
- `withdraw_request`'s `still_on_rail` check read `limit=500`, which was a cliff.
  It now reads the complete list.
- History: `conversation_store.load_recent_readonly(..., before=<turn id>)` does a
  keyset page, older than that turn. `api.status.get_status` accepts
  `conversation_before` and `conversation_limit`, and it always reports `has_more`
  and `next_before`. The app shows "Show earlier messages" whenever `has_more` is
  true. A page is something the client asks for, never a silent default.

## What remains in the connector's exempt set, and why

`_connector_ceiling_exempt` shrinks from four entries to three. Each has a
**contract** reason. None of them is "the app reads it" or "it is big":

| Entry | Keep? | Reason |
|---|---|---|
| `run_file` | keep | Exact bytes plus a `next_offset` cursor, already bounded by the caller's `file_max_bytes`. A marker destroys both. |
| `conversation` | keep | A lossless chunk read, bounded by the caller's `output_max_chars`, with a cursor. The same class as `run_file`. |
| `conversation_turn` | keep | The universe's committed reply, which is the same payload `converse` returns. `converse` is outside the ceiling because the reply *is* the product. |
| `model_options` | **remove** | Its only reason was the app's picker, and that moved to the owner door. On the connector it becomes `compact_model_options`, the projection the engine already serves, so one definition covers both model-door surfaces. `model_options_summary` stays as a synonym. |

## Account type is the only per-account input

- `usage_policy.AccountType` is a `str` enum: `FREE = "free"` and
  `SUBSCRIPTION = "paid"`. The value stays `"paid"` because that is what Stripe
  checkout has already stored.
- `limits_for(account: AccountType)` takes it.
- `universe_owner.account_type_of(base, owner_id)` is the one resolver. It
  replaces `tier_of`, and it reads the subscription recorded on the account's home.
- `account_type_for_universe(base, universe_id)` goes through `owner_of`, so a
  subscriber's second universe is a subscription universe. That is the
  per-account scope the founder decided on 2026-09-30. Today `get_tier(that
  universe_dir)` reads it as free.
- The per-universe `get_tier` readers (`usage_policy.limits_for_universe`,
  `universe_seats` in 2 places, `effectors/outbound_boundary` in 2 places) route
  through it.
- `TierLimits.is_paid` has no caller and is deleted.
- A boundary test pins that only `universe_owner` and `subscription_state` itself
  call `get_tier`.

### Inventory: behaviour derived from per-account data volume

Found at `origin/main` fb7caf2f:

| Where | What | Disposition |
|---|---|---|
| `universe_server` ceiling on `read_graph` | 24 KB bound on owner reads | fixed: owner door |
| `list_requests(limit=10)`, connector `limit=30` | rail cut at 30 | fixed: complete |
| `list_pending` swallow -> `[]` | unreadable queue reads as empty | fixed: raises |
| `withdraw_request` `limit=500` | `still_on_rail` wrong past 500 | fixed: complete |
| `get_status` `recent_conversation` 30 turns | history cut with no signal | fixed: `has_more` + cursor |
| `refreshRail` catch-all | rail vanishes silently | fixed: loud state |
| installed-UI library (`read_graph target=app_ui`) through the connector | "Could not read your installed UIs (unexpected app UI reply)" on the main account, 2026-09-30 | fixed: owner door |
| every other app read (`agent_binding(s)`, `agent(s)`, `runs`, `run`, `run_output`, `automations`, `universe_file(s)`, `conversation`, `conversation_turn`, `model_options`, `get_status`) | same ceiling | fixed: owner door (`app.html`, `app_layout.js`, `app_ui.js`) |
| `llm_deposit` `list_bindings(limit=30)` then filter by owner | owner's binding missed past 30 newer ones | fixed: reads every binding (`limit=None`) |
| `api.universe_file_reads.MAX_LIST_ENTRIES=500` | folder listing cut, with `truncated: true` | finding: visible but no cursor; follow-up |
| read list targets default `limit=30` (runs, automations, agents, goals, graphs) | model-door page defaults | finding: the owner door never defaults; `app_ui` passes explicit pages |
| `list_resolved(limit=5)` "recently_answered" | a labelled recent window | keep: it is named as recent |
| 4000-char per-turn peek | preview with `truncated` + lossless chunk expansion | keep: explicit, and the client can expand it |

## Risks

- **Cross-user reads through the new route.** This is mitigated by construction:
  the route calls the same domain function under the same identity. Tests assert
  that a second account gets the connector's refusal for another owner's home,
  on the rail, bindings and status.
- **Two paths drifting.** There is one dispatcher. The connector adds only
  projections. A parity test asserts that for a small document both doors return
  identical JSON.
- **App tests that stub `MCP.*` reads.** They move to `Owner.*` stubs. The
  behaviour they assert does not change.
- **Concurrent lanes.** PR #4152 touches `app.html`. The limits lanes own
  `universe_seats` and storage. The `AccountType` routing is a small edit at their
  call sites, done here because the founder asked for one input now.

## 1. Storage and authority

- [ ] 1.1 Add `open_to_all`, `discoverable`, `sender_rate_limit` to
  `graph_receivers` with an additive column migration, and convert the positional
  receiver INSERT to an explicit column list.
- [ ] 1.2 Split the receiver predicates: `_permitted_receiver` (deliver/connect)
  honours `open_to_all`; a new `_visible_receiver` (inspect/discover) additionally
  honours `discoverable`. Revoked stays refused on both.
- [ ] 1.3 Add `discover_receivers` to storage: discoverable + unrevoked only,
  sender view, substring search, bounded limit.
- [ ] 1.4 Reject the reserved attribution names in a receiver's `input_keys`, and
  validate the exposure flags and rate limit bounds loudly.

## 2. Delivery

- [ ] 2.1 Inject `delivery_sender_id` / `delivery_sender_universe_id` from the
  link row into the validated inputs, for whichever the receiver's own pinned
  snapshot declares.
- [ ] 2.2 Enforce the per-sender rolling-window rate limit inside the acceptance
  transaction, before resource admission, on first acceptance only.
- [ ] 2.3 Return `sender_id` / `sender_universe_id` on the receiver's side of the
  delivery receipt (and only the receiver's side).

## 3. Surface and guidance

- [ ] 3.1 Wire `discover_receivers` through the extensions read actions and
  `read_graph target="receivers"` on both the connector and served engine
  wrappers; extend the dispatch docstring action list.
- [ ] 3.2 Document the exposure fields on both `write_graph` descriptions.
- [ ] 3.3 Add the `delivering` handbook chapter, the resident index bullet, and
  the `control_station` pointer.

## 4. Prove

- [ ] 4.1 Cross-user tests through the real handles, two principals: an open
  receiver accepts a stranger with attribution in the owner's run; a closed one
  refuses and is undiscoverable; the sender cannot read the owner's
  branch/nodes/run; the rate limit trips and the refusal names itself.
- [ ] 4.2 Mutation-check the open/closed gate, the discoverable gate and the
  attribution injection; record red -> green.
- [ ] 4.3 ruff, plugin mirror rebuild, touched-area pytest set-compared against
  `origin/main`, and a cross-family review verdict.

## 1. Storage and authority

- [x] 1.1 Add `open_to_all`, `discoverable`, `sender_rate_limit` to
  `graph_receivers` with an additive column migration, and convert the positional
  receiver INSERT to an explicit column list. The migration runs inside the writer
  transaction and `migrate_in_transaction` refuses outside one.
- [x] 1.2 Split the receiver predicates: `_permitted_receiver` (deliver/connect)
  honours `open_to_all`; `_visible_receiver` (inspect/discover) additionally
  honours `discoverable`. Revoked stays refused on both.
- [x] 1.3 Add `discover_receivers` to storage: discoverable + unrevoked only,
  sender view, substring search, bounded limit.
- [x] 1.4 Reject the reserved attribution names in a receiver's `input_keys`, and
  validate the exposure flags and rate limit bounds loudly. `None` means KEEP on
  update rather than reverting to the default.

## 2. Delivery

- [x] 2.1 Inject `delivery_sender_id` / `delivery_sender_universe_id` from the
  link row into the validated inputs, for whichever the receiver's own pinned
  snapshot declares, and count them as platform-supplied in projection preflight so
  a receiver declaring them without a default can still be created.
- [x] 2.2 Enforce the per-sender rolling-window rate limit inside the acceptance
  transaction, before resource admission, on first acceptance only — and inside the
  file-copy pre-flight, which runs above every acceptance fence.
- [x] 2.3 Return `sender_id` / `sender_universe_id` on the receiver's side of the
  delivery receipt (and only the receiver's side).
- [x] 2.4 Refuse a reserved attribution name in the ADMITTED contract at
  acceptance, closing the legacy-receiver file-substitution path, and make replay
  compare sender content against the stored record rather than recomputing
  attribution.

## 3. Surface and guidance

- [x] 3.1 Wire `discover_receivers` through the extensions read actions and
  `read_graph target="receivers"` on both the connector and served engine
  wrappers; extend the dispatch docstring action list.
- [x] 3.2 Document the exposure fields on both `write_graph` descriptions.
- [x] 3.3 Add the `delivering` handbook chapter, the resident index bullet, and
  the `control_station` pointer.

## 4. Prove

- [x] 4.1 Cross-user tests through the real handles, two principals: an open
  receiver accepts a stranger with attribution in the owner's run; a closed one
  refuses and is undiscoverable; the sender cannot read the owner's
  branch/nodes/run; the rate limit trips and the refusal names itself.
  `tests/test_open_receivers.py` (30) + `tests/test_open_receiver_file_rate_limit.py`
  (1, real custody copy).
- [x] 4.2 Mutation-check the gates, the attribution and the review's findings:
  23 rows, all caught, no forks; red at base recorded in the PR body.
- [x] 4.3 ruff, plugin mirror rebuild, and touched-area pytest set-compared
  against `origin/main` (323 passed / 4 skipped / 0 failures on both sides over the
  17 pre-existing modules).
- [x] 4.4 Round-1 cross-family Codex review: ADAPT, 7 findings, all folded.

## 5. Landing

Merged as squash `c2c11fe0` on 2026-09-26; CI green on the merged head (18 pass,
0 failures, including `required-tests`).

- [ ] 5.1 `python scripts/deployed_sha.py --assert-contains c2c11fe0` — merged is
  not deployed. Lead-owned, running 2026-09-26.
- [ ] 5.2 `python scripts/mcp_public_canary.py --url https://tinyassets.io/mcp
  --assert-handles` — the canonical handle set is unchanged, so it must report the
  same six plus optional `get_status`. Lead-owned, running 2026-09-26.
- [x] 5.3 Synced both spec deltas into `openspec/specs/` and archived this change.
  The delta files were REWRITTEN from the stored specs first, because they were
  authored before the cross-family review changed two behaviours (update now keeps
  unspecified exposure fields; reserved attribution names are refused in a stored
  contract at acceptance too) — an archived delta that describes a rejected shape is
  a misleading record. `graph-execution-substrate` gained 3 requirements,
  `live-mcp-connector-surface` 2, and its existing
  "Graph handles expose structured cross-user delivery controls" had discovery added
  to its control enumeration rather than a second definition of that fact.
- [x] 5.4 Filed the concurrent-copy residual as
  `docs/concerns/2026-09-26-rate-limited-sender-can-still-copy-concurrent-files.md`
  (P2) so it outlives this change directory.

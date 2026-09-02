# Design: full channel access

Revised after Codex design rounds 1-3 (2026-09-02, ADAPT each; the design
rounds are closed at three). Round 1 showed the
materialised-wildcard shape (`/{path+}` rows, `*/*` scopes and consents) is
not actually full (`/` and any query string would still be refused), touches
seven readers, exposes `*/*` to the git transport, and leaves consents
behind on removal. The simpler shape it proposed is adopted: **one
`access_mode` on the connection**, read by the four enforcement points.

## D1. The ask

`request_from_user` action shapes gain one field:

```json
{"type": "extend_http", "destination": "github", "access": "full"}
{"type": "connect_http", "destination": "github", "auth_scheme": "bearer",
 "access": "full", "hosts": ["api.github.com"]}
```

- `extend_http` with `access: full` carries no endpoints or scopes.
- `connect_http` with `access: full` names the channel's host(s) (`hosts`,
  1..4 entries) because a new key has no stored hosts yet; it may not also
  carry `endpoints`. The hosts are stored as the connection's declared hosts
  (one `GET` endpoint per host at `/{path+}` is recorded only so the
  existing host-derivation and SSRF host pin have something to read; the
  authority is the mode, not those rows).
- `_validated_action` refuses `access` values other than `"full"` and
  refuses `access: full` combined with `endpoints` or `scopes`.

## D2. Storage: `outbound_connections.access_mode`

- Column `access_mode TEXT NOT NULL DEFAULT 'exact'`; values `exact` |
  `full`. Migration adds the column; every existing row is `exact`.
- `ConnectionResource` / `ConnectionView` carry `access_mode`; the ledger
  gains `set_access_mode(connection_id, mode, expected_mode)` (CAS on the
  previous mode) used by the answer path.
- `delete_connection` / `remove_http` remove the row, so the mode goes with
  the key. (See D6 for consents.)

## D3. Enforcement: four readers, after safety, never instead of it

1. **Outbound HTTP** (`_SsrfHardenedHttpDriver.__call__`): method validation
   and the canonical URL parse run first (non-HTTPS, userinfo, ports other
   than 443, dot segments, encoded separators, double encoding are refused
   there); `_enforce_endpoint_allowlist` then matches the host against the
   connection's declared hosts and, only when the host matched and
   `access_mode == "full"`, admits any path, any query and any of the five
   verbs instead of the template match. DNS resolution and the global-address
   check run AFTER the allowlist, immediately before the socket, exactly as
   today: the full branch bypasses none of them (Codex round 2, R1).
   "Full" is bounded to the 1-4 hosts the agent declared for the channel,
   never to every host the credential might reach.
2. **Git scopes** (`has_git_scope(connection, kind, repo)`): `True` for any
   repository when the connection is `full`, else exact membership. The
   stored-scope grammar is unchanged: no `*/*` ever reaches
   `require_git_scope` or the transport.
3. **Workspace consents** (`_require_consent` for checkout/push in
   `effectors/workspace.py`): the call site already holds `resource` after
   `_read_connection`, host derivation and scope validation; it passes the
   resource's `access_mode` (or the resource) down, and the helper is
   satisfied for any repository on the connection's git host when the mode
   is `full`, else the exact consent row as today. The connection and host
   checks stay exact. Provision is NOT enabled by this change:
   `_check_provision_consent` has no call site and checkout refuses requested
   provisioning outright today; a full grant pre-authorizes it for the
   release that enables it, and this design says so rather than pretending
   provision runs (Codex round 2, R2).
4. **Inventory and rail** (`cloud_connections` projection,
   `_granted_lines`, `_grant_sentence`): a `full` connection is rendered as
   `access: "full"` with the sentence in D5, never as wildcard rows.

## D4. Raise time and answer time

- `_extend_preview` (from the rail change, #2769): when the ask is `full`
  and the stored connection is already `full`, the verdict is `unchanged`
  and the rail answers `already_held`. When the ask is `full` and the
  connection is `exact`, the verdict is `extends` with `access_mode: full`
  in its payload; the answer path calls `set_access_mode` under CAS instead
  of writing endpoints.
- `connect_http` with `access: full` provisions with `access_mode = full`.
- An `exact` ask on a `full` connection is `already_held` too. There is no
  downgrade path in this change: an owner retracts a full grant by removing
  the key (`remove_http`) and depositing again with exact endpoints. Flagged
  below as a decision (Codex round 2, R4).

## D5. The rail sentence

"Full access to your {destination} key: anything the key itself can do at
{hosts}, and git clone or push to any repository it can reach on
{git_host}, including checking that repository out and running its build in
your universe's sandbox. You do not need to paste it again." The git clause
appears only when a git host resolves for the channel.

## D6. Consents are removed with the key (a defect Codex found, fixed here)

`remove_http` deletes the ledger connection but leaves
`.effector_consents.db` rows active; because the connection id is
deterministic for `(universe, destination)`, re-depositing the same
destination reactivated the old consents. `remove_http` now revokes every
consent row keyed on the connection id, for `exact` and `full` alike.

## D7. Served guidance

The ask docs say: "When you need a key for a service, ask for full channel
access (`"access": "full"`); it is one yes and you will not need to ask
again for that channel. Ask for exact endpoints only when the owner asked
for less." The manual "Add a key yourself" form is unchanged in this change
(the owner chooses there; see the decisions below).

## D8. Tests

- `access_mode` migration; `set_access_mode` CAS.
- Full mode admits `/`, a query string, every verb, on a declared host;
  refuses another host, userinfo, a non-443 port, an encoded separator.
- `has_git_scope` any repo when full; exact otherwise.
- Checkout, push and provision consent checks pass for an arbitrary repo on
  the git host when full; fail on another host.
- The raise-time verdicts: full-on-exact extends; full-on-full and
  exact-on-full are `already_held`.
- Inventory renders `access: "full"` and no wildcard row; the rail sentence.
- `remove_http` revokes the consents; a re-deposit starts with none.

Three proofs Codex round 3 asked for by name, because the wording above
would let a weaker test pass:

- **Resolved-address refusal on a full connection.** With the resolver
  patched so the declared host resolves to a loopback or private address, a
  request on a `full` connection is refused by the global-address check
  that runs after the allowlist and before the socket. Parse-time refusals
  alone do not prove the full branch left that check in place.
- **The workspace call site, not the helper.** Checkout and push run
  through the effector's own handlers in `effectors/workspace.py` (the call
  site that today passes no resource or mode to `_require_consent`): a
  `full` connection with no consent row checks out and pushes an arbitrary
  repository on the git host; an `exact` connection without the row is
  refused there. Calling `_require_consent` directly proves nothing about
  the integration D3 changes.
- **Scoped consent cleanup.** Two connections in one universe, each with
  consent rows across several sinks; `remove_http` on the first revokes
  every row keyed on that connection id and leaves the second connection's
  rows active. The existing primitive revokes one exact `(sink,
  destination)` pair, so the cleanup needs a by-connection revoke, and a
  universe-wide one fails this test.

## Decisions taken here, flagged for the founder

1. **"Full" includes checkout, push, provision and running the repository's
   build in the sandbox.** The founder's words were "full channel access";
   a full grant that still asked for a consent per repository would be the
   third ask again. Reversible: drop reader 3 from D3.
2. **All-or-exact.** No owner-wide (`owner/*`) form; that is a second policy
   language for a case nobody has asked for.
3. **The agent's ask defaults to full; the manual form does not change.**
   The founder said what the agent should have asked for; they did not
   speak to the form.
4. **No downgrade verb.** Retracting a full grant is remove-and-redeposit.
   A narrowing verb is a different, destructive intent (the ledger already
   refuses narrowing on extend) and can be its own change if an owner asks.
5. **"Full" is bounded to the declared hosts**, never dynamically to every
   host the credential could reach.

## Dependency

Builds on `_extend_preview` / `_extend_ask_verdict` from PR #2769
(request-rail-honest-asks); this branch rebases on main once that lands.

# Floor 1 (inbound webhook) — cross-family review log (Codex)

## Round 1 → VERDICT: adapt (before routing `/hooks/*` publicly)

Confirmed sound: a request cannot redirect a stored binding (actor/provider derive from the
stored `universe_id`); unknown vs revoked tokens are indistinct with no timing oracle on a
256-bit token; the store persists no bodies/headers. Findings to fix before public exposure:

1. **Cross-universe ownership + author gate (CRITICAL).** mint/revoke/list must enforce
   `universe_access_allows(uid, write=True)`; mint must require the authenticated subject to be
   the branch AUTHOR (the claimed author gate does NOT exist on the direct enqueue — direct
   `execute_branch_async` bypasses universe-scope dispatch + ledgering that `_action_run_branch`
   does). Revalidate the binding before every enqueue.
2. **Body cap after unbounded buffering (CRITICAL).** The route `await request.body()` buffers
   the whole body before the 256 KB check → an anon attacker forces full buffering with junk
   tokens. Reject oversized `Content-Length` + stream/count chunks, aborting at 256 KB.
3. **Admission is not durable/aggregate (HIGH).** Invalid-token requests are unlimited (each
   opens SQLite + reruns schema DDL before lookup); valid-token limit is process-local, resets
   on restart, multiplies per worker, keyed only by token; minting has no quota (many tokens
   bypass). Each admitted request writes a durable run row + submits to an unbounded pool. Need
   pre-lookup origin/IP limiting + durable per-universe/token admission + bounded queue depth +
   replay/idempotency.
4. **Channel-signature verification impossible (HIGH).** `_decode_body` parses/UTF-8-replaces, so
   the branch never gets the exact signed bytes → forwarding `X-Hub-Signature` is useless; the
   URL becomes the sole auth. Preserve bounded RAW bytes (or exact base64) alongside the parsed
   convenience value.
5. **Revocation unreachable (HIGH).** The callable `extensions` schema has no `token` param and
   the dispatcher only routes `run_branch` (run_graph → run_branch), so mint/revoke/list — though
   registered in `_RUN_ACTIONS` — are NOT reachable through the MCP/chatbot surface. Wire them
   into the actual dispatch + schema so an owner can mint/revoke after a leak.

Also: tokens are stored plaintext (a read-only DB disclosure grants invocation authority —
consider hashing at rest); all non-Authorization/Cookie headers persist into tenant run input
(a proxy-injected Access/OIDC assertion would too — tighten the forward set).

Floor 1 is DARK until the tunnel routes `/hooks/*`, so these gate the PUBLIC-exposure step, not
the code landing. Status: store + receiver + route + ops built, 20 tests (mock ownership/enqueue
+ streaming — Codex notes those boundaries are untested). Fixes owed before go-live.

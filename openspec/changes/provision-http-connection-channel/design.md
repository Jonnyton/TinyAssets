# Design — connect_http (provision a generic http connection)

## Handler shape (mirror connect_llm)

`tinyassets/api/http_connection.py::connect_http(*, universe_id="", payload=None) -> dict`,
dispatched from `universe_server.py` write_graph `target=="connection"` as a new
`operation=="connect_http"` sibling of `connect_llm` (before the
`_cloud_connections_impl` GitHub fall-through). Returns `json.dumps(result)`; no
costly/submit/admission wrapper (the vault write takes its own per-universe lock).

### Auth (stronger of the two precedents)
1. `permissions.is_authenticated_request()` + `actor = current_actor_id()`;
   reject empty/`anonymous` → `{"error":"authentication_required"}`.
2. `uid = _request_universe(universe_id)`; require an explicit `admin` row from
   `list_universe_acl(base, universe_id=uid)` (NOT `universe_access_allows`, which
   admits write-collaborators and can public→read short-circuit). Denial →
   uniform `{"error":"not_found","resource":"connection"}` (existence-probe safe).

### Payload (JSON object)
```
{ "destination": "<stable channel key, e.g. slack:acme>",   # required
  "auth_scheme": "bearer|header|basic|none",                # required, validated
  "secret": "<token>",                 # required unless auth_scheme=none; <=200k
  "header_name": "<X-…>",              # required iff auth_scheme=header
  "allowed_endpoints": [ {"host":"slack.com","path_template":"/api/chat.postMessage","methods":["POST"]}, … ] }  # >=1
```
Validate: `destination` non-empty + used as the SINGLE key for both the vault
record (`service` and `destination`) and the connection `destination` (keeps the
resolver lookup key == consent/soul-authority key — the map's two-destination
alignment). `auth_scheme` ∈ supported subset. `allowed_endpoints` normalized via
the ledger's own `_parse_allowed_endpoints` (host lower-cased, path template +
methods validated) — reject empty (SSRF boundary). Reject `oauth1a` (resolver
returns one secret; 4-secret schemes unsupported).

### Steps
1. Vault deposit: `write_credential_vault(_universe_dir(uid),
   [{"credential_type":"http","service":<destination>,"destination":<destination>,
   "token":<secret>}], owner_user_id=actor, universe_id=uid)`. List-wrapped.
   `credential_ref = f"vault://http/{destination}"`. Setting `service==destination`
   makes the upsert key `(http, destination)` distinct per channel AND the
   resolver finds it by `destination`. Map `PermissionError` →
   `credential_ownership_transfer_unsupported`, `ValueError` →
   `connection_setup_invalid`, else `deposit_failed` (fail-closed, atomic).
   auth_scheme=none → skip deposit, `credential_ref="vault://http/"`+none path.
2. `ledger = ConnectionLedger(Path(base)/"outbound.db",
   verify_authenticated_principal=lambda: actor)`.
3. Deterministic ids: `sha256(actor∥uid∥"http"∥destination)` → `http_<32>` /
   `http_grant_<32>` (mirror `cloud_connections._ids`).
4. Idempotent create: `get_connection_resource` first; if None →
   `create_connection(connection_id, owner_user_id=actor, connection_class="http",
   connection_type="http", auth_scheme, scopes=tuple(sorted(methods)),
   provider="http", destination, credential_ref, allowed_endpoints)`; else if
   owner/type/revoked mismatch → `{"error":"connection_conflict"}`.
5. Idempotent grant: `get_grant` first; if None → `grant_connection(grant_id,
   connection_id, owner_user_id=actor, universe_id=uid,
   unprompted_action_cap=ActionCap("http_calls", <cap>, "requests"))`; else
   conflict-check.
6. Return `{"status":"connected","connection_id","grant_id","destination",
   "auth_scheme","allowed_endpoints":[…as_dict],"next":"grant effector consent
   for <destination>, then build a node with effect authenticated_external_call"}`.
   Never echo `credential_ref`/secret.

## Decisions / risk handling (from the substrate map)
- **Two-destination alignment:** one `destination` value serves the vault key,
  the connection destination, and the later consent/soul-authority key. Documented
  + enforced by construction.
- **Upsert-vs-resolver key mismatch:** solved by `service==destination`.
- **Allow-list is load-bearing + caller-supplied:** normalized/validated by the
  ledger before storage; empty rejected. This is the real egress boundary.
- **Feature flag:** `TINYASSETS_OUTBOUND_HTTP_CONNECTIONS_ENABLED` gates the
  effect at dispatch; creating the connection does not require it. Return does not
  falsely imply live posting — the `next` hint covers consent; the flag is a
  deploy prerequisite tracked as a host-action.
- **oauth1a excluded** (single-secret resolver).
- **Redaction:** only redacted `ConnectionView`/projection returned; secret-free
  error envelopes (mirror connect_llm).

## Out of scope (Slice 2)
Served-surface build verbs (write_graph target=branch + connect_http + consent +
webhook mint on `engine_mcp_server.py`) so the universe builds channels itself;
`oauth1a`/multi-secret; a typed http credential bundle.

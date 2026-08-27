## Design

### Authorization and reconciliation

The authenticated WorkOS `sub` is the only user identifier sent to Pipes. `connect` calls `POST /data-integrations/github/authorize` with that server-derived `user_id` and a fixed return target under the canonical MCP site. The response contains only the authorization URL. `reconcile` calls `GET /user_management/users/{sub}/connected_accounts/github`; only a connected account in the `connected` state is accepted.

Reconciliation creates deterministic IDs from `(owner, universe, provider, destination)` and stores `workos-pipes://github/{owner}` as an opaque credential reference. It grants only the fixed pull-request reader/writer scopes and a bounded action cap. Existing matching active records replay; mismatched or duplicate active records fail closed.

### Credential custody

The adapter process receives no token. The spawned trusted broker resolves `workos-pipes://github/{owner}` by calling `POST /data-integrations/github/credentials` with the server-only `WORKOS_API_KEY` and the owner ID encoded in the reference, validates the response, and passes the token only to the existing GitHub network driver. The resolver compares the reference owner to the ledger resource owner and rejects malformed IDs. WorkOS errors are redacted to a generic unavailable result.

### API shape

`write_graph target=connection operation=connect|reconcile` uses the authenticated principal and requested universe only. `read_graph target=connections` returns provider, destination, scopes, grant IDs, and `connected`/`needs_authorization` status, never credential references or tokens. Cloud-automation prerequisite output includes `connection_action` when no grant is available.

### Safety

No callback endpoint stores bearer state; WorkOS retains the OAuth account and the user returns to the MCP surface to reconcile. All state-changing calls require the existing universe write ACL. Tests use an injected HTTP transport and assert no secret crosses the JSON/API boundary.

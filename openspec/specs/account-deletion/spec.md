# Account Deletion

> As-built baseline (2026-09-02, PR #2773): describes landed behavior. Written from what shipped, per the spec-driven-development standard's "build it, prove it live, then write the spec from what shipped" rule for single-surface behaviour. Future changes arrive as OpenSpec change deltas against this capability.

## Purpose

Google Play requires any app that lets people create an account to offer account deletion both inside the app and on a public web page, and `/legal` promises GDPR Article 17 erasure. This capability is that path: a self-service, immediate, per-principal deletion of everything the platform holds for a signed-in user, with a content-free receipt and honest reporting of what could not be removed.

## Requirements

### Requirement: Self-Service Deletion Route

The onboarding app SHALL expose `POST /mcp/app/account/delete`. The route SHALL require a resolved non-anonymous identity (401 otherwise), a same-origin JSON request (403 otherwise — the same login-CSRF guard as the token endpoint), and a body whose `confirm` field is exactly `DELETE` (400 otherwise). It SHALL delete only the identity that made the request; a client-supplied principal or universe id SHALL be ignored. On success it SHALL drop the request's refresh-session handle, clear the refresh cookie, and return `{"deleted": true, "home_removed", "billing", "identity"}` with `Cache-Control: no-store`. When the deletion is refused before anything changed it SHALL return 409 `deletion_refused`.

#### Scenario: A stray or cross-site post cannot delete an account

- **WHEN** the route is called without an identity, from a foreign `Origin`, with a non-JSON content type, or without `confirm: "DELETE"`
- **THEN** it responds 401 / 403 / 403 / 400 respectively and no deletion runs

#### Scenario: The signed-in principal is deleted and signed out

- **WHEN** a signed-in user posts `{"confirm": "DELETE", "session_ref": <handle>}` from the app's own origin
- **THEN** `delete_account` runs for that identity's `user_id`, the handle is dropped, the `ta_rt` cookie is deleted, and the response carries the receipt fields above

### Requirement: Everything The Platform Holds For The Principal Is Removed

`tinyassets.account_deletion.delete_account(base_path, founder_sub=...)` SHALL remove, for exactly that principal: the `founder_home` binding; the bound home universe directory (soul, memory, conversation history, credential vault, every per-universe store); root-database rows keyed by that home — the same reviewed set `scoped_reset` plans (`universes`, `universe_rules`, `universe_notes`, `universe_work_targets`, `universe_hard_priorities`, `universe_snapshots`, `branches` + `branch_heads`, `user_requests`, `vote_windows` + `vote_ballots`) plus `webhook_hooks` / `webhook_admissions` / `webhook_inflight`; `universe_acl` rows for the home and for the principal; the principal's own `user_requests` and `vote_ballots` elsewhere; `outbound.db` connections, grants, connector artifacts and remix edges the principal owns; and every `.auth.db` row keyed by the principal's `user_id`. It SHALL cancel the home's Stripe subscription immediately (not at period end) and delete the WorkOS user record through the management API when `WORKOS_API_KEY` is configured.

#### Scenario: Deleting A leaves B untouched (the cross-user floor)

- **WHEN** two principals each own a home with rows in every store above and A is deleted
- **THEN** no row, file or grant of A remains in any store, and every row, file and grant of B is byte-for-byte as before — including B's remix edge onto A's artifact being removed with A's artifact while B's own artifact stays

#### Scenario: A principal without a home still loses grants, tokens and identity

- **WHEN** a principal who never founded a home but holds a grant on another universe and daemon-issued tokens is deleted
- **THEN** those grants and tokens are removed, the identity deleter runs, billing reports `not_configured`, and the other universe is unchanged

### Requirement: Refuse Before Changing, Report After

Deletion SHALL be refused, with nothing changed, for an empty or `anonymous` principal or when the bound home path escapes the data root or is not a plain directory. Once the home directory has been staged (atomic rename under `.deleting/`), the account is unreachable; a failure to remove the staged directory, to cancel billing, or to delete the identity SHALL be recorded in the receipt (`home_removed: false` + `home_staged_path`, `billing: "error"`, `identity: "error"`) and logged at ERROR with a principal fingerprint only — never swallowed, never carrying a secret or the raw principal.

#### Scenario: An escaping binding changes nothing

- **WHEN** a principal's `founder_home` row points at `../outside`
- **THEN** `delete_account` raises `AccountDeletionError` and the binding row and the outside directory are still present

#### Scenario: Billing and identity failures are visible, not hidden

- **WHEN** the billing or identity step raises
- **THEN** the data deletion still completes, the receipt says `error` for that step, and the ERROR log line contains neither the exception text nor the principal

### Requirement: The Public Web Page And The In-App Path Exist And Agree

`tinyassets.io/account` SHALL document the in-app steps (Account → type DELETE → Delete my account), what is removed immediately, what is retained (content-free audit records keyed by an opaque id, payment-processor invoices, backups until rotation), and the email route for people who cannot sign in (handled within 30 days). The app SHALL show an **Account** control on both the chat header and the Connect screen that opens a view with the same explanation and a typed-`DELETE` confirmation. `RETAINED` in `tinyassets.account_deletion` and the retention sentence on `/legal` SHALL name the same three items.

#### Scenario: The app page carries the path

- **WHEN** `app.html` is served
- **THEN** it contains the `btn-account`, `btn-connect-account` and `btn-delete-account` controls, posts to `/mcp/app/account/delete` with `confirm:"DELETE"`, and states that deletion cannot be undone

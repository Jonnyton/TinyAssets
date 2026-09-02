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

### Requirement: The Deleted Row Set Is Derived From The Schema

The row set SHALL be computed from the live database schema rather than a hand-maintained table list, because no list survives migration: a table carrying `universe_id` SHALL lose the deleted universe's rows, and a table carrying a principal column (`founder_sub`, `user_id`, `actor_id`, `owner_user_id`, `owner_actor`, `owner_actor_id`, `bound_by_actor_id`, `authorizing_principal_id`, `principal_id`, `remixed_by_user_id`) SHALL lose the deleted person's rows. `created_by` SHALL NOT be a deletion key: authorship is not ownership, and sweeping it would delete rows this person authored inside another person's universe. The only hand-maintained parts SHALL be the exception sets — preserved (commons and ledgers), redacted (audit), blocking (unsettled money) and indirectly scoped (reached through a parent). The same rule SHALL apply to the satellite databases beside the root one (`outbound.db`, `.auth.db`).

#### Scenario: A universe-scoped table is never swept by person

- **WHEN** the deleted principal authored a branch inside another person's universe
- **THEN** that branch, and that universe's branch count, are unchanged after deletion

#### Scenario: An access grant follows the person, not the universe

- **WHEN** the deleted principal holds a grant on another person's universe
- **THEN** the grant is removed, and that universe's own rows and files are unchanged

#### Scenario: A new person-keyed table cannot be silently missed

- **WHEN** the live root database contains a table with a person or universe column
- **THEN** it is covered by the derived plan, or named in exactly one exception set

### Requirement: Everything The Platform Holds For The Principal Is Removed

`tinyassets.account_deletion.delete_account(base_path, founder_sub=...)` SHALL remove, for exactly that principal: the `founder_home` binding; the bound home universe directory (soul, memory, conversation history, credential vault, every per-universe store); the schema-derived root-database rows above; `outbound.db` connections, grants, connector artifacts and remix edges the principal owns; and every `.auth.db` row keyed by the principal. Rows entangled in two-way `ON DELETE CASCADE` (`request_admissions`, `request_admission_events`, `branch_tasks_v2`, `branch_heads`, `vote_ballots`) SHALL be counted before any of them is deleted, so the receipt states what was actually destroyed rather than whichever table the cascade reached last. Audit rows SHALL be redacted rather than deleted — actor replaced by an opaque fingerprint, summary, target and payload emptied — which is what makes the retention sentence published on `/legal` true. It SHALL cancel the home's Stripe subscription immediately (not at period end) and delete the WorkOS user record through the management API when `WORKOS_API_KEY` is configured; that upstream deletion, not local sweeping, is what ends sessions on devices whose opaque refresh handles this process cannot enumerate.

#### Scenario: A cascade never hides what was deleted

- **WHEN** the principal's own request, admission and task are removed together
- **THEN** the receipt counts all three, not only the one the cascade reached first

#### Scenario: An audit row survives without the person or the content

- **WHEN** an action record names the deleted principal and their page
- **THEN** the row remains, its actor reads `deleted:<fingerprint>`, and its summary, target and payload are empty

#### Scenario: Deleting A leaves B untouched (the cross-user floor)

- **WHEN** two principals each own a home with rows in every store above and A is deleted
- **THEN** no row, file or grant of A remains in any store, and every row, file and grant of B is byte-for-byte as before — including B's remix edge onto A's artifact being removed with A's artifact while B's own artifact stays

#### Scenario: A principal without a home still loses grants, tokens and identity

- **WHEN** a principal who never founded a home but holds a grant on another universe and daemon-issued tokens is deleted
- **THEN** those grants and tokens are removed, the identity deleter runs, billing reports `not_configured`, and the other universe is unchanged

### Requirement: Someone Else's Data And Live Work Refuse The Deletion

Deletion SHALL refuse, changing nothing, when another founder is bound to the same home, when another person holds a grant or owns requests, branches, snapshots, votes or ballots inside it, when another person's admitted work depends on requests there, when a daemon, request, task, vote or rollout is still active, or when the principal has unsettled financial state. The foreign-ownership and active-work analysis SHALL be the operator path's (`scoped_reset._inspect_database`), query for query, so the two paths agree about whose rows are whose. The one deliberate divergence SHALL be dependent request rows: a reset preserves them, a deletion removes the principal's own and blocks only on foreign ones. Refusal reasons SHALL name no person and no content, and SHALL be shown to the user.

#### Scenario: A second founder on the same home blocks the deletion

- **WHEN** two principals' `founder_home` rows reference one universe and one asks to delete
- **THEN** the deletion is refused, the universe and both bindings are unchanged, and the reason names a second founder

#### Scenario: Another person's request in the universe blocks the deletion

- **WHEN** a different user's request lives in the home being deleted
- **THEN** the deletion is refused and that request still exists

### Requirement: A Deleted Account Is Not Re-Founded By A Live Token

Deletion SHALL write a tombstone for the principal, and `ensure_founder_home` SHALL refuse to create a home for a tombstoned principal. Without it, an already-issued token on another device would pass local authentication before the identity provider removes the user, and first-contact would hand the person a brand-new universe seconds after they deleted their account. The operator's scoped identity reset SHALL clear the tombstone, because that operation deliberately keeps the login.

#### Scenario: First contact refuses a deleted principal

- **WHEN** a deleted principal's still-valid token reaches first contact
- **THEN** no universe is created and no binding is written

### Requirement: Refuse Before Changing, Report After

Deletion SHALL be refused, with nothing changed, for an empty or `anonymous` principal or when the bound home path escapes the data root or is not a plain directory. Once the home directory has been staged (atomic rename under `.deleting/`), the account is unreachable. Every later phase SHALL run independently of the others, so a failure in one never prevents the phase that cancels the money; each failure SHALL be recorded in the receipt (`unfinished_phases`, plus `home_removed`/`billing`/`identity`) and logged at ERROR with a principal fingerprint only — never swallowed, never carrying a secret or the raw principal. A deletion that leaves any phase unfinished SHALL also write a durable, content-free receipt under `.account-deletions/` so the host can finish it, and the app SHALL tell the user rather than report a deletion that did not fully happen.

#### Scenario: An escaping binding changes nothing

- **WHEN** a principal's `founder_home` row points at `../outside`
- **THEN** `delete_account` raises `AccountDeletionError` and the binding row and the outside directory are still present

#### Scenario: Billing and identity failures are visible, not hidden

- **WHEN** the billing or identity step raises
- **THEN** the data deletion still completes, the receipt says `error` for that step, and the ERROR log line contains neither the exception text nor the principal

#### Scenario: A failed row phase still stops the money

- **WHEN** a satellite database is locked and its deletion phase fails
- **THEN** billing cancellation and identity deletion still run, and a durable receipt names the unfinished phases

### Requirement: The Public Web Page And The In-App Path Exist And Agree

`tinyassets.io/account` SHALL document the in-app steps (Account → type DELETE → Delete my account), what is removed immediately, what is retained (content-free audit records keyed by an opaque id, payment-processor invoices, backups until rotation), and the email route for people who cannot sign in (handled within 30 days). The app SHALL show an **Account** control on both the chat header and the Connect screen that opens a view with the same explanation and a typed-`DELETE` confirmation. `RETAINED` in `tinyassets.account_deletion` and the retention sentence on `/legal` SHALL name the same three items.

#### Scenario: The app page carries the path

- **WHEN** `app.html` is served
- **THEN** it contains the `btn-account`, `btn-connect-account` and `btn-delete-account` controls, posts to `/mcp/app/account/delete` with `confirm:"DELETE"`, and states that deletion cannot be undone

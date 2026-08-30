## ADDED Requirements

### Requirement: The `workspace` sink checks out, pushes and discards a repository through the credential-blind worker

A node MAY declare the effect sink `workspace` with a packet
`{"sink": "workspace", "connection_id", "grant_id", "op": "checkout" |
"push" | "discard", …}`. `checkout` carries `repo` (canonical
`owner/name`), `ref`, optional `depth` (default 50), `storage` (`"scratch"`
default, or `"universe"` to pin), optional `provision`; `push` carries the
workspace capability, the local commit SHA, and a branch slug; `discard`
carries the workspace capability. The sink SHALL run every credentialed git
operation in the outbound worker against a worker-private staging
repository that is never mounted into a jail, populate the workspace from
staging without credentials, and for `push` fetch the workspace's commit
into fresh staging as a local path remote before pushing from staging. The
connection SHALL carry the `git_read` (checkout) or `git_write` (push) scope
bound to the exact `(host, owner/name)`; HTTPS on 443 only; the host SHALL
pass the same public-unicast DNS/IP classification the HTTP driver applies.
`checkout` and `push` SHALL each require a typed consent record
(`workspace_checkout`, `workspace_push`) for `(connection, repo)`, requested
through the request rail; a remix SHALL re-request them under the remixer's
connection.

#### Scenario: a checkout populates a scratch lease without a credential in reach of user code
- **WHEN** a `checkout` packet for `owner/name@main` is dispatched under a connection with `git_read` for that repository and a `workspace_checkout` consent
- **THEN** the worker clones into staging with the trusted helper, the lease directory is populated from staging without credentials, staging is deleted, and the evidence records repo, ref, resolved SHA, depth and bytes — never the token, never a host path

#### Scenario: a hook planted in the checkout never runs with a credential
- **WHEN** code in the workspace writes `.git/hooks/pre-push` or sets `credential.helper` in `.git/config` and the branch then pushes
- **THEN** the credentialed push runs from a fresh staging repository whose config is the worker's, the planted hook never executes in that process, and the push succeeds or fails on the remote's answer alone

#### Scenario: push policy
- **WHEN** a `push` names the remote's `HEAD` branch, is not a fast-forward, or names a branch outside `tiny/…`
- **THEN** the push is refused before the wire as `workspace_push_refused`; force and delete pushes are never sent

#### Scenario: a push whose outcome is lost is reconciled, not repeated blindly
- **WHEN** the daemon restarts between sending a push and recording its receipt
- **THEN** the journaled intent `(connection, repo, remote_ref, sha, expected_old_sha)` is reconciled with `ls-remote` on resume; the same SHA already at the ref is success, anything else is `workspace_push_refused` with the observed ref

### Requirement: Branch policy for workspace pushes is fixed

The sink SHALL resolve the remote `HEAD` before any push and SHALL refuse
that ref unconditionally; it SHALL push only branches named
`tiny/<universe-short>/<slug>` by exact commit SHA as a fast-forward refspec;
it SHALL never force-push or delete a ref. Host branch protection remains an
additional remote refusal, reported verbatim as a fixed error class.

#### Scenario: the default branch cannot be pushed to
- **WHEN** a push targets the branch the remote reports as `HEAD`
- **THEN** it is refused as `workspace_push_refused` and no bytes are sent

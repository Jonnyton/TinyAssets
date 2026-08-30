## ADDED Requirements

### Requirement: The `workspace` sink checks out, pushes and discards a repository through the credential-blind worker

The runtime SHALL provide the effect sink `workspace` with operations `checkout`, `push` and `discard`, and SHALL perform every credentialed git operation in the outbound worker against a worker-private staging repository that is never mounted into a jail.
A `checkout` packet carries `repo` (canonical `owner/name`), `ref`, optional
`depth` (default 50), `storage` (`"scratch"` default or `"universe"`) and
optional `provision`; a `push` packet carries the workspace capability, a
local commit SHA and a branch slug; `discard` carries the capability. The
worker SHALL populate the lease from a bundle it creates from staging into a
freshly initialised repository, so the workspace's `.git` holds no remote,
no host path and no credential. For `push`, the worker SHALL accept only a
bundle the jail created from one synthetic ref at the exact commit, copied
as a bounded regular file through the held lease directory handle with
beneath/no-symlink semantics, SHALL verify it credential-free in fresh
staging (`bundle verify`, fsck-checked `index-pack`, strict `fsck`), and
only then SHALL push from staging; no host-side git process SHALL ever read
the workspace's `.git`. The connection SHALL carry the `git_read`
(checkout) or `git_write` (push) scope bound to the exact `(host,
owner/name)`; the transport SHALL use HTTPS on 443 with the address pinned
in git's transport (`http.curloptResolve`) to an address the outbound
driver's classification validated as public unicast. `checkout`, `push`
and provisioning SHALL each require a typed consent record
(`workspace_checkout`, `workspace_push`, `workspace_provision`) for
`(connection, repo)`, requested through the request rail; a remix SHALL
re-request all three under the remixer's connection. Evidence SHALL be
bounded and SHALL never contain the token or a host path.

#### Scenario: a checkout populates a scratch lease without a credential in reach of user code
- **WHEN** a `checkout` packet for `owner/name@main` is dispatched under a connection with `git_read` for that repository and a `workspace_checkout` consent
- **THEN** the worker clones into staging with the broker and the pinned address, bundles, deletes staging, populates a fresh repository in the lease from the bundle, and the evidence records repo, ref, resolved SHA, depth and bytes — never the token, never a host path

#### Scenario: a gitfile or alternates in the workspace cannot make the worker read another repository
- **WHEN** code in the workspace replaces `.git` with a gitfile pointing elsewhere, adds alternates or replace refs, and the branch then pushes
- **THEN** the worker reads only the bundle file the jail produced, verifies it credential-free, and nothing outside the bundle's objects is read or sent

#### Scenario: a hook planted in the checkout never runs with a credential
- **WHEN** code writes `.git/hooks/pre-push` or sets `credential.helper` in `.git/config` and the branch then pushes
- **THEN** the credentialed push runs from staging whose config is the worker's; the planted hook never executes in that process

#### Scenario: a push whose outcome is lost is reconciled, not repeated blindly
- **WHEN** the daemon restarts between sending a push and recording its receipt
- **THEN** the journaled intent `(connection, repo, remote_ref, sha, expected_old_sha)` is reconciled with `ls-remote` on resume; the same SHA already at the ref is success, anything else is `workspace_push_refused` with the observed ref

#### Scenario: provisioning without its consent is refused
- **WHEN** a `checkout` declares `provision` and the connection has no `workspace_provision` consent for the repository
- **THEN** the checkout completes without provisioning and the node's evidence records `workspace_provision_refused` naming the missing consent

### Requirement: Branch policy for workspace pushes is fixed

The sink SHALL resolve the remote `HEAD` before any push and SHALL refuse that ref unconditionally, SHALL push only branches named `tiny/<universe-short>/<slug>` by exact commit SHA as a fast-forward refspec, and SHALL never force-push or delete a ref.
Host branch protection remains an additional remote refusal, reported as a
fixed error class.

#### Scenario: the default branch cannot be pushed to
- **WHEN** a push targets the branch the remote reports as `HEAD`
- **THEN** it is refused as `workspace_push_refused` and no bytes are sent

### Requirement: Provisioning admits only registry-pinned dependencies and never executes build code with network

The runtime SHALL admit for provisioning only Python requirement records of the form `name[extras]==version ; marker --hash=…` and only Node dependencies whose every lockfile resolution is a pinned `https://registry.npmjs.org/` tarball, SHALL fetch Python wheels with `--only-binary=:all:` and `--require-hashes` and Node tarballs with `--ignore-scripts`, in a jail that holds no checkout and whose egress permits only the declared registry hosts after per-address validation, and SHALL install offline in the workspace jail.
Manifests SHALL be read through the held lease directory handle with
beneath/no-symlink semantics as bounded regular files, and the offline
install SHALL be bound to their digests. Direct URLs, paths, VCS
references, includes and option lines SHALL be refused as
`workspace_provision_refused`.

#### Scenario: an sdist-only or URL requirement is refused before any network
- **WHEN** the requirements file contains `git+https://…`, a local path, `-r other.txt`, or a package with no wheel available
- **THEN** provisioning is refused as `workspace_provision_refused` naming the offending line, and the resolver never runs

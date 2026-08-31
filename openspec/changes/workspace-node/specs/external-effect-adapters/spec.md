## ADDED Requirements

### Requirement: The `workspace` sink checks out, pushes and discards a repository through the credential-blind worker

The runtime SHALL provide the effect sink `workspace` with operations `checkout`, `push` and `discard`, and SHALL perform every credentialed git operation in the outbound worker against a worker-private staging repository that is never mounted into a jail.
A `checkout` packet carries `repo` (canonical `owner/name`), `ref`,
`storage` (`"scratch"` default or `"universe"`) and optional `provision`;
there is no `depth`: the worker SHALL clone the full history of the
requested ref (`--single-branch --no-recurse-submodules`) and both
directions SHALL use prerequisite-free bundles, verified as such in an
empty repository. A `push` packet carries the workspace capability, a
local commit SHA and a branch slug; `discard` carries the capability. The
boundary SHALL be: no credentialed git process ever opens a workspace or
reads its `.git`; no host-side git process opens a workspace's `.git`
after the workspace is published to user code; a host-side, credential-free
initializer MAY populate a fresh, unpublished generation from a verified
bundle (`git init`, fetch from the bundle, checkout, strict `fsck`), and
publication SHALL happen only after fetch, checkout, `fsck` and staging
deletion all succeed, leaving `.git/config` with no remote, no host path
and no credential. For `push`, the worker SHALL accept only a bundle the
jail created from one synthetic ref at the exact commit, copied as a
bounded regular file through the held directory handle with
beneath/no-symlink semantics, SHALL verify it credential-free in fresh
staging (`bundle verify` refusing prerequisites, fsck-checked
`index-pack`, strict `fsck`), and only then SHALL push from staging. The
connection SHALL carry the `git_read` (checkout) or `git_write` (push)
scope bound to the exact `(host, owner/name)`; the transport SHALL use
HTTPS on 443 with the address pinned in git's transport
(`http.curloptResolve`) to addresses the outbound driver's classification
validated as public unicast. `checkout`, `push` and provisioning SHALL
each require a typed consent record (`workspace_checkout`,
`workspace_push`, `workspace_provision`) for `(connection, repo)`,
requested through the request rail; a remix SHALL re-request all three
under the remixer's connection. `discard` SHALL immediately revoke the
capability and enqueue the storage transition through the outbox; a
failure of the discard itself is `workspace_discard_failed`. Evidence
SHALL be bounded and SHALL never contain the token or a host path.

#### Scenario: a checkout populates a scratch lease without a credential in reach of user code
- **WHEN** a `checkout` packet for `owner/name@main` is dispatched under a connection with `git_read` for that repository and a `workspace_checkout` consent
- **THEN** the worker clones the full history into staging with the broker and the pinned address, bundles, deletes staging, populates a fresh repository in the unpublished lease from the bundle, publishes it, and the evidence records repo, ref, resolved SHA and bytes — never the token, never a host path

#### Scenario: a history deeper than fifty commits crosses the bridge both ways
- **WHEN** the repository has 200 commits on the requested ref and the branch later pushes a commit on top of them
- **THEN** the checkout bundle and the push bundle each verify with no prerequisites in an empty repository, and the push succeeds

#### Scenario: a gitfile or alternates in the workspace cannot make the worker read another repository
- **WHEN** code in the workspace replaces `.git` with a gitfile pointing elsewhere, adds alternates or replace refs, and the branch then pushes
- **THEN** the worker reads only the bundle file the jail produced, verifies it credential-free, and nothing outside the bundle's objects is read or sent

#### Scenario: a hook planted in the checkout never runs with a credential
- **WHEN** code writes `.git/hooks/pre-push` or sets `credential.helper` in `.git/config` and the branch then pushes
- **THEN** the credentialed push runs from staging whose config is the worker's; the planted hook never executes in that process

#### Scenario: a push whose outcome is lost is reconciled, not repeated blindly
- **WHEN** the daemon restarts between sending a push and recording its receipt
- **THEN** the journaled intent `(connection, repo, remote_ref, sha, expected_old_sha)` is reconciled with `ls-remote` on resume; the same SHA already at the ref is success, anything else is `workspace_push_refused` with the observed ref

#### Scenario: a discarded workspace is gone to the same run
- **WHEN** a branch discards its workspace and a later node in the same run calls `ws.read`
- **THEN** the capability is already revoked, the call raises inside `run()`, and the node fails as `code_node_failed` naming the discard

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

### Requirement: Provisioning admits only registry-pinned dependencies through a canonicalising grammar and never executes build code with network

The runtime SHALL admit for provisioning only Python requirement records that, after refusing option lines, includes, direct URLs, local paths, VCS and environment references, parse as a PEP 508 requirement with no URL, exactly one `==` specifier with no wildcard and a PEP 440 version, at least one `--hash=sha256:<64 hex>`, optional extras, and an optional marker using only `python_version`, `python_full_version`, `sys_platform`, `platform_machine`, `platform_system`, `implementation_name` and `os_name`; and only Node projects whose `package-lock.json` (version 2 or 3) has no workspaces or `link:` entries and whose every installable entry carries `resolved` parsing exactly to an `https://registry.npmjs.org/…tgz` URL and a `sha512-` integrity, with every dependency section (`dependencies`, `devDependencies`, `optionalDependencies`, `peerDependencies`, top-level and nested) holding semver ranges only.
The resolver SHALL receive only the reconstructed canonical texts (sorted
canonical requirement records; canonical JSON of the manifest and
lockfile), never the original files; SHALL fetch Python wheels with
`--only-binary=:all:` and `--require-hashes` and Node tarballs with
`--ignore-scripts`, in a jail that holds no checkout and whose egress
permits only the declared registry hosts after per-address validation;
and SHALL install offline in the workspace jail bound to the manifests'
digests. Manifests SHALL be read through the held directory handle with
beneath/no-symlink semantics as bounded regular files. Admission and
consent refusals are `workspace_provision_refused`; resolver transport,
cache-bound and offline-install failures are `workspace_provision_failed`.

#### Scenario: an sdist-only or URL requirement is refused before any network
- **WHEN** the requirements file contains `git+https://…`, a local path, `-r other.txt`, `pkg>=1.0`, or a pinned package with no wheel available
- **THEN** provisioning is refused as `workspace_provision_refused` naming the offending line (or the resolver refuses the sdist under `--only-binary=:all:` as `workspace_provision_failed`), and no build backend ever executes

#### Scenario: a lockfile resolution outside the registry is refused
- **WHEN** the lockfile carries an entry resolved to `git+https://…`, `file:…`, `https://registry.npmjs.org.evil.example/…`, or one with a `sha256-` integrity
- **THEN** provisioning is refused as `workspace_provision_refused` naming the entry, and the resolver never runs

# External Effect Adapters

> As-built baseline (2026-07-22, change `backfill-independent-shipped-contracts`): describes shipped local completion-path adapter behavior and current limitations. Shared authority, consent, and receipt semantics remain owned by `external-effect-receipts`.

## Purpose

The shipped Branch-completion effect dispatch, sink-specific adapter behavior, system-authored evidence, and current partial-write/finalization boundaries.

## Requirements

### Requirement: Declared node effects dispatch at node time and a failed effect fails its node

As each node of a Branch run completes, the runtime SHALL inspect that node's
declared `effects`, find matching packets only in the node's declared output
keys (rendered against the state merged with the node's delta), and dispatch
the registered sink adapter before the next node runs. The full result SHALL
be kept in memory for the rest of the run so a later node may reference an
earlier node's `response.status` / `response.body` (`$ta.effect`) only when
that node is a graph ancestor; persisted evidence stays bounded. A packet MAY
declare `accept_statuses` (a list of integers) at its top level; a delivered
call answered ≥ 400 with a status not in that list, a packet refused before
the wire, an adapter crash or an unknown sink SHALL fail the node and the run
(`external write failed - <node>/<sink>: <error> [<kind>]`), and later nodes
SHALL NOT run. Each node's effects fire at most once per run. The post-run
dispatcher remains only for callers that compile without an effect chain and
SHALL NOT run for a chain-compiled run. All other clauses of this requirement
are unchanged.

#### Scenario: a later node reads an ancestor's full body
- **WHEN** node `fetch` delivered a 6.8 KB document and node `edit` (a graph descendant) references `fetch.response.body.content`
- **THEN** the reference resolves to the full body, not the 4 KiB persisted preview

#### Scenario: a sibling cannot be referenced
- **WHEN** two nodes fan out from the same parent and one references the other's effect
- **THEN** the packet is refused as `invalid_body_transform` naming the missing ancestor, every run, regardless of which sibling ran first

### Requirement: External-write receipt keys are system-authoritative and visible in run snapshots
Before adapter dispatch the runtime SHALL move any Branch-authored `external_write_results` or `external_write_errors` value to the corresponding `_branch_authored_*` quarantine key. System-generated adapter evidence SHALL then own the canonical keys. The composed run snapshot SHALL expose canonical external-write results and errors from persisted run output so callers do not need a separate output-only read.

#### Scenario: Forged result is quarantined
- **WHEN** Branch output already contains `external_write_results`
- **THEN** the value is moved to `_branch_authored_external_write_results` before system adapter evidence is written at the canonical key

#### Scenario: Snapshot exposes system receipt
- **WHEN** a completed run persisted adapter evidence
- **THEN** the run snapshot includes its `external_write_results` and any `external_write_errors`

### Requirement: GitHub pull-request effects apply destination gates and optional-hint receipts
The `github_pull_request` adapter SHALL parse only a matching packet from declared output keys. A packet without a destination SHALL remain on the Phase-1 dry-run compatibility path. For a destination-bearing packet, a soul-authority resolver result of denied — from a declared non-match or a soul-read failure — SHALL dry-run, while undeclared authority SHALL fall through to the legacy gates owned by `external-effect-receipts`. A real write SHALL require an exact destination capability and consent; a bound vault credential SHALL outrank environment-vended credentials and SHALL never be returned in Branch-visible evidence. A non-empty caller hint SHALL use the shared atomic receipt lifecycle, but an omitted hint SHALL proceed unreceipted. The adapter SHALL materialize blobs, tree, commit, and head ref before opening the PR, so a later failure can leave partial remote branch state. A successful external write whose receipt finalization fails SHALL still return success evidence marked `receipt_finalize_failed`.

#### Scenario: Missing consent remains a dry run
- **WHEN** a valid destination packet has a credential but no active consent row
- **THEN** the adapter returns destination-specific dry-run evidence and performs no GitHub write

#### Scenario: Concurrent reservation prevents duplicate PRs
- **WHEN** a non-empty hint is supplied and another run holds the same idempotency reservation
- **THEN** the adapter returns `reason=concurrent_in_flight` without invoking PR creation

#### Scenario: Successful duplicate returns recorded evidence
- **WHEN** the idempotency receipt already records a successful PR
- **THEN** the adapter returns a dedup hit with that evidence and performs no external write

#### Scenario: Missing hint opts out of receipts
- **WHEN** an otherwise authorized destination packet omits its idempotency hint
- **THEN** the adapter may materialize the branch and create the PR without reserving or finalizing a receipt

#### Scenario: PR failure can leave materialized branch state
- **WHEN** remote branch materialization succeeds but PR creation fails
- **THEN** the adapter returns failure evidence and releases any receipt reservation without deleting the already-created remote objects or ref

### Requirement: GitHub merge effects bind packet-declared mode to exact head SHA and delegate policy enforcement
The `github_merge` adapter SHALL require a valid repository destination, positive PR number, one of `merge`, `squash`, or `rebase`, packet-supplied authorization mode `github_branch_protection`, a destination capability, and a 40-character expected head SHA. It SHALL fetch the current PR, require it to be open and non-draft, and reject a mismatched head before calling the merge endpoint; wiki positions SHALL be audit context only and SHALL NOT supply the required mode string. The adapter does not query branch-protection configuration, status checks, or reviews itself; it delegates those controls to GitHub's merge endpoint and treats API refusal as structured failure.

#### Scenario: Expected head mismatch refuses stale authorization
- **WHEN** the current PR head differs from the packet's expected head SHA
- **THEN** the adapter returns a stale-authorization error and does not call the merge endpoint

#### Scenario: GitHub API accepts a bound merge
- **WHEN** destination capability is present, the packet names the required mode, the PR is open and non-draft, the expected head matches, and GitHub's merge endpoint accepts the request
- **THEN** the adapter returns merge evidence without independently proving which repository protection, check, or review rules GitHub enforced

#### Scenario: Wiki position cannot authorize merge
- **WHEN** a packet supplies review context but omits `github_branch_protection` authorization
- **THEN** the adapter returns `missing_merge_authorization` and performs no merge

### Requirement: Twitter effects preserve destination binding with transitional authority and optional receipts
The `twitter_post` adapter SHALL derive the posting account from the destination and reject a payload handle that resolves to a different account. A soul-authority resolver result of denied — from a declared non-match or a soul-read failure — SHALL dry-run, while undeclared authority SHALL fall through to exact destination consent and credential gates. The adapter SHALL accept a non-empty caller hint or deterministically derive a SHA-256 hint from source run id, sink, handle, and text, then use the shared receipt lifecycle. A successful post whose receipt finalization fails SHALL remain successful evidence marked `receipt_finalize_failed` and SHALL not be rolled back.

#### Scenario: Twitter payload cannot redirect the authorized account
- **WHEN** a Twitter packet's payload handle differs from the account derived from its authorized destination
- **THEN** the adapter returns `handle_authority_mismatch` and performs no post

#### Scenario: Twitter duplicate is idempotent
- **WHEN** a prior successful receipt exists for the derived Twitter idempotency hint
- **THEN** the adapter returns recorded post evidence and does not call the external API again

#### Scenario: Undeclared soul falls through
- **WHEN** the universe declares no effect-authority grants for the Twitter destination
- **THEN** the adapter continues to exact consent and credential gates rather than requiring a soul grant

### Requirement: Wiki writeback requires a hint but retains transitional authority and best-effort finalization
The `wiki_write_back` adapter SHALL reject a soul-authority resolver result of denied — from a declared non-match or a soul-read failure — while undeclared authority SHALL fall through to exact destination consent. It SHALL require a non-empty idempotency hint, universe context, and an existing same-universe `.md` file under `pages/` or `drafts/`, with at least one subdirectory and no empty, dot, or traversal segments, before reserving a shared receipt. It SHALL append or update the marked result section. If the page write succeeds but receipt finalization fails, the adapter SHALL return successful evidence marked `receipt_finalize_failed`; it SHALL not undo the page write.

#### Scenario: Wiki writeback requires an explicit idempotency hint
- **WHEN** an otherwise authorized wiki-writeback packet omits its idempotency hint
- **THEN** the adapter returns a dry run with `reason=missing_idempotency_hint` and leaves the page unchanged

#### Scenario: Wiki writeback stays inside the universe wiki
- **WHEN** a consented packet targets a valid same-universe page and holds a reservation
- **THEN** the adapter appends or updates the marked section, reports old/new hash evidence, and attempts receipt finalization; a failed finalization adds `receipt_finalize_failed` without undoing the page write

### Requirement: Windows desktop effects gate host actions but provide only narrow evidence redaction
The host-local Windows desktop adapter SHALL require explicit affirmative user approval in the packet, exact per-universe consent, and an attested interactive Windows desktop runtime before any host action. A missing approval SHALL error, missing consent SHALL dry-run, and a non-Windows or non-interactive runtime SHALL return `no_host_available` before a receipt or action. A non-empty idempotency key SHALL use shared duplicate/in-flight reservation handling, while an omitted key SHALL proceed unreceipted. The default action runner SHALL return stable handles for action paths, but evidence redaction only drops four exact path-named keys and converts actual `Path` objects. Auto-generated runtime attestation SHALL contain the raw home-directory string; an injected attestation is appended unchanged and may omit it. The sanitizer SHALL NOT be treated as a general string-path or protected-byte confidentiality boundary. A successful action whose receipt finalization fails SHALL remain successful evidence marked `receipt_finalize_failed`.

#### Scenario: User approval is mandatory
- **WHEN** a Windows desktop packet lacks affirmative user approval or contains negative approval text
- **THEN** the adapter returns `approval_required` before checking consent, reserving a receipt, downloading, or launching anything

#### Scenario: Wrong runtime is refused before action
- **WHEN** approval and consent exist but runtime attestation is not an interactive Windows desktop
- **THEN** the adapter returns `no_host_available` and performs no host-local action

#### Scenario: Default action paths use handles but attestation retains home
- **WHEN** an approved, consented action succeeds using the default action runner and auto-generated runtime attestation
- **THEN** action receipts use stable path handles while the appended runtime attestation still contains its raw `home` string

#### Scenario: Missing idempotency key permits an unreceipted action
- **WHEN** all host gates pass but the packet has no idempotency key
- **THEN** the adapter runs the action without a receipt reservation or exactly-once claim

> Synced 2026-08-30 from change `external-call-body-encoding` (landed #2692, live proof 2026-08-30 04:4xZ: run `3f86d7b9fde04bff` fetched README and wrote it back with one appended line in ONE run, bytes never through a model).

# External effect adapters — body transforms



### Requirement: The outbound packet can encode, decode, reference and join body text without the model carrying the bytes

The generic `authenticated_external_call` effector SHALL treat a one-key JSON
object anywhere inside `request.body` (object values and list elements) whose
key is one of `$ta.base64`, `$ta.from_base64`, `$ta.ref`, `$ta.effect`,
`$ta.concat`, `$ta.replace` as a transform applied in the effector process
before the wire request reaches the credential-blind worker. The `$ta.` namespace SHALL be
reserved: any other one-key object whose key starts with `$ta.` is refused,
and every other key — a user's own `$ref`, `$set` — is sent as written.
`{"$ta.base64": X}` sends the base64 of X's UTF-8 bytes; `{"$ta.from_base64": X}`
yields the UTF-8 text of base64 X (whitespace-tolerant; bytes that are not
UTF-8 text are refused — text files); `{"$ta.ref": "key.a.0.b"}` yields a
value from the run's state whose root `key` MUST be one of the emitting node's
declared `input_keys` or a state_schema-defaulted key — narrower than the
compiler's render view, never the whole final state; `{"$ta.effect":
"node.response.body.x"}` yields `response.body` (traversed as JSON) or
`response.status` — never headers — from the evidence of a node STORED EARLIER
in the branch whose generic-call effect already fired in this run (effects
fire in storage order; `write_graph` appends nodes in the order given);
`{"$ta.concat": [X, …]}` joins texts; `{"$ta.replace": {"in": X, "old": A,
"new": B, "count": n}}` replaces exactly `count` (default 1) occurrences of
`A` inside `X` with `B`, every operand (`count` included) resolved through the
same transforms, the key set closed (`in`, `old`, `new`, `count` only) and the
work charged in UTF-8 bytes; it SHALL refuse the whole call when `old` is
empty, absent from the input, or occurs a number of times other than `count`,
or when `count` is not a positive integer — and the not-found refusal SHALL
show the input around the longest prefix of `old` that does occur (whitespace
made visible with `repr`), because the author cannot see the fetched bytes
(live 2026-08-30: two runs guessed at a newline where the file had a space).
X MAY itself be a transform. JSON-encoded strings are traversed and lists
indexed. This SHALL be the only knowledge the effector gains beyond shape: one
encoding and the run it belongs to, never a service. The `$ta.*` vocabulary
is FROZEN as of change `sandboxed-code-node` (#2719): a new edit shape is a
code node, not an operator.

Bounds SHALL refuse the whole call before anything is sent, as the effector's
secret-free error dict (`error_kind: invalid_body_transform`; paths and types
in the message, never values): a body nested deeper than 32 levels anywhere;
a cumulative working set over 32 MiB, charged in bytes as each value is
produced (text as UTF-8, a referenced object as its JSON) so a repeated
reference is refused as soon as the charges cross the budget rather than
after materialising every copy; a transformed body over 8 MiB; a wrong type;
a referenced value JSON cannot carry; an unfenced, unresolvable or
out-of-range path; a `$ta.` key beside other keys. A body containing no
`$ta.*` key SHALL be sent byte-for-byte as today.

The effect evidence that is PERSISTED (and shown to a model through
`read_graph target="run"`) SHALL keep at most a 4 KiB preview of a response
body, with its size and sha256, and header NAMES only — never header values,
which the worker does not sanitize beyond exact credential echoes; the full
response SHALL be available only to later nodes' transforms within the same
dispatch.

#### Scenario: A file write sends text, the effector encodes it

- **WHEN** a packet's `request.body` is `{"message": "m", "content": {"$ta.base64": "<text>"}}`
- **THEN** the request sent carries `content` as the base64 of the text's UTF-8
  bytes and no `$ta.` key remains

#### Scenario: Append one line without the model touching the file's bytes (the live case)

- **GIVEN** a branch with two nodes declaring `effects: ["authenticated_external_call"]`,
  `fetch` (a GET packet for the file) stored before `write`
- **WHEN** `write`'s body is
  `{"sha": {"$ta.effect": "fetch.response.body.sha"}, "content": {"$ta.base64": {"$ta.concat": [{"$ta.from_base64": {"$ta.effect": "fetch.response.body.content"}}, "<new line>\n"]}}}`
- **THEN** in ONE run the fetch fires, then the write sends base64 whose decoded
  bytes are exactly the fetched file plus the new line; the model authored only
  the new line; and the persisted fetch evidence holds a bounded preview of the
  file, not the file (2026-08-29 without this: `422 content is not valid Base64`,
  then `README.md +2/-87`, then a re-typed file `+22/-14`; #2691 reached `+1/-0`
  only on the third attempt)

#### Scenario: References are fenced to what the node may see

- **WHEN** a packet uses `{"$ta.ref": "private"}` and `private` is not among the
  node's declared `input_keys` or schema-defaulted keys
- **THEN** the call is refused with `invalid_body_transform`, the message names
  the key but not its value, and nothing is sent
- **AND** `{"$ta.effect": "fetch.response.headers.set-cookie"}` (a header),
  `{"$ta.effect": "later.response.body"}` (a node stored later), or an unknown
  node are refused the same way

#### Scenario: A user's own `$`-keys are not transforms, and unknown `$ta.*` keys are refused

- **WHEN** `request.body` contains `{"schema": {"$ref": "#/$defs/X"}}` or `{"$set": …}`
- **THEN** it is sent exactly as written
- **AND WHEN** it contains `{"$ta.bas64": "…"}`
- **THEN** the call is refused (`unknown transform`), never sent as payload

#### Scenario: Bounds refuse before allocation

- **WHEN** a body references a 5 MiB fetched blob a hundred times, or nests
  1,100 plain objects, or would serialize past 8 MiB
- **THEN** the call is refused with `invalid_body_transform` at the first
  bound crossed — the working-set charge, the depth scan, or the size check —
  never a crash (`effector_crashed`) and never a partially built body

#### Scenario: One line of a fetched file is changed without the model carrying the file

- **WHEN** a write node's body uses `$ta.replace` over the decoded content of
  an earlier fetch node, with `old` the exact current line and `new` the
  intended line
- **THEN** the written file differs from the fetched one only in that line,
  byte for byte elsewhere (live 2026-08-30: PR #2720, `-2/+1`, run
  `ecabc10d41294d7f`, opened and merged uncoached in one write run)

#### Scenario: A typo in the old text changes nothing, and the refusal shows the real bytes

- **WHEN** `old` does not occur in the fetched text, or occurs twice with
  `count` 1
- **THEN** the call is refused with `invalid_body_transform` and nothing is
  sent; a not-found refusal quotes the input near the closest partial match
  with newlines and spaces visible

#### Scenario: a code node's output feeds the next packet
- **WHEN** a code node returns `{"content": <text>, "sha": <sha>}` under its declared `output_keys` and the next node's packet body uses `{"$ta.base64": {"$ta.ref": "content"}}` with `content` in its `input_keys`
- **THEN** the write carries the code node's text, base64-encoded by the effector, and the model never carried the bytes

### Requirement: The `workspace` sink checks out, pushes and discards a repository through the credential-blind worker

The runtime SHALL provide the effect sink `workspace` with operations `checkout`, `push` and `discard`, and SHALL perform every credentialed git operation in the outbound worker against a worker-private staging repository that is never mounted into a jail.
A `checkout` packet carries `repo` (canonical `owner/name`), `ref`, `storage`
(`"scratch"` default or `"universe"`) and optional `provision`; there is no
`depth`: the worker SHALL clone the full history of the requested ref
(`--single-branch --no-recurse-submodules`) and both directions SHALL use
prerequisite-free bundles. A `push` packet carries the workspace capability, a
local commit SHA and a branch slug; `discard` carries the capability.

The boundary SHALL be: no credentialed git process ever opens a workspace or
reads its `.git`; no host-side git process opens a workspace's `.git` after the
workspace is published to user code; a host-side, credential-free initializer
MAY populate a fresh, unpublished generation from a verified bundle (`git init`,
fetch from the bundle, checkout, strict `fsck`), and publication SHALL happen
only after fetch, checkout, `fsck` and staging deletion all succeed, leaving
`.git/config` with no remote, no host path and no credential.

For `push`, the worker SHALL accept only a bundle the jail created from one
synthetic ref at the exact commit, copied as a bounded regular file through the
held directory handle with beneath/no-symlink semantics, and SHALL verify it
credential-free in fresh staging. `bundle verify` alone SHALL NOT be treated as
the gate: measured on git 2.53, a bundle made from a shallow clone passes it,
because the shallow boundary is not a declared prerequisite. The fsck-checked
import is what catches that, so the push path SHALL run both, in that order —
`bundle verify` refusing declared prerequisites, then an fsck-checked
`index-pack`/fetch into an empty repository, then a strict `fsck` — and nothing
SHALL cross the boundary on a `verify` alone.

The connection SHALL carry the `git_read` (checkout) or `git_write` (push) scope
bound to the exact `(host, owner/name)`; the transport SHALL use HTTPS on 443
with the address pinned in git's transport (`http.curloptResolve`) to addresses
the outbound driver's classification validated as public unicast.

`checkout`, `push` and provisioning SHALL each require a typed consent record
(`workspace_checkout`, `workspace_push`, `workspace_provision`). The consent's
destination key SHALL include the **connection id** as well as the repository
(`<operation>:<connection_id>:<host>/<owner>/<name>`): a universe can hold more
than one connection to the same host, and keying on the repository alone would
let a consent given for one credential authorize work under another. A remix
SHALL re-request all three under the remixer's connection. `discard` SHALL
require no new consent — discarding a capability the run already holds grants
nothing — and SHALL immediately revoke that capability and enqueue the storage
transition through the outbox; a failure of the discard itself is
`workspace_discard_failed`. Evidence SHALL be bounded and SHALL never contain
the token or a host path.

#### Scenario: a checkout populates a scratch lease without a credential in reach of user code
- **WHEN** a `checkout` packet for `owner/name@main` is dispatched under a connection with `git_read` for that repository and a `workspace_checkout` consent
- **THEN** the worker clones into staging with the broker and the pinned address, bundles, deletes staging, populates a fresh repository in the lease from the bundle, and the evidence records repo, ref, resolved SHA and bytes — never the token, never a host path

#### Scenario: a shallow bundle does not cross the boundary on a passing verify
- **WHEN** a push presents a bundle built from a shallow clone, which `bundle verify` accepts because the shallow boundary is not a declared prerequisite
- **THEN** the fsck-checked import into an empty repository refuses it for not carrying all necessary objects, and no bytes are pushed

#### Scenario: a consent granted for one connection does not authorize another
- **WHEN** a universe holds `workspace_push` for `owner/name` through one connection and dispatches a push for the same repository through a second connection
- **THEN** the second is refused for a missing consent, because the connection id is part of the consent's destination

#### Scenario: a gitfile or alternates in the workspace cannot make the worker read another repository
- **WHEN** code in the workspace replaces `.git` with a gitfile pointing elsewhere, adds alternates or replace refs, and the branch then pushes
- **THEN** the worker reads only the bundle file the jail produced, verifies it credential-free, and nothing outside the bundle's objects is read or sent

#### Scenario: a discard needs no consent of its own
- **WHEN** a run discards a workspace it holds
- **THEN** the capability is revoked and the storage transition is enqueued without any consent lookup, because discarding what you already hold authorizes nothing new

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

The runtime SHALL admit for provisioning only Python requirement records that, after refusing option lines, includes, direct URLs, local paths, VCS schemes and `${VAR}` references, parse under `packaging` as a PEP 508 requirement with no URL, exactly one `==` specifier with no wildcard and a PEP 440 version, at least one `--hash=sha256:<64 hex>`, optional extras, and an optional marker using only `python_version`, `python_full_version`, `sys_platform`, `platform_machine`, `platform_system`, `implementation_name` and `os_name`; and only Node projects whose `package-lock.json` (version 2 or 3) has no `workspaces` key and no `link:` entry and whose every installable entry carries a `resolved` parsing exactly to an `https://registry.npmjs.org/…tgz` URL with no userinfo, query or fragment, and a `sha512-` integrity, with every dependency section (`dependencies`, `devDependencies`, `optionalDependencies`, `peerDependencies`, at the top level and inside each lockfile entry) holding node-semver ranges only — a dist-tag such as `latest` is not a range.
The pinned version SHALL be validated and then carried **verbatim**: rewriting
it would hand the installer a string the manifest never wrote. A marker SHALL be
canonicalised from the ORIGINAL text rather than from `str(Marker)`, which
re-quotes every literal with double quotes and so moves the clause boundaries of
a literal containing one; the canonical form SHALL be re-parsed and refused
unless it yields the same tree.

The resolver SHALL receive only **reconstructed** canonical texts — sorted
canonical requirement records, and canonical JSON rebuilt field by field from
what admission validated — never the original files. Reconstruction is what
prevents a version 2 lockfile's second, v1-shaped `dependencies` graph from
reaching the installer with a URL the `packages` map never mentioned; the rebuilt
lockfile always declares `lockfileVersion` 3 and carries no legacy graph. A field
that is present but does not validate SHALL be refused, never dropped, and
`scripts` SHALL NOT be carried into the reconstructed manifest at all, so the
offline install cannot run a lifecycle script the root manifest asked for.

**Provisioning is wholly unavailable in this release.** A `checkout` that
declares `provision` SHALL complete as a checkout and SHALL refuse the
provisioning half as `workspace_provision_refused` **before any manifest is
read** — no file is opened through the lease handle, no grammar runs, no command
is built, and no consent is consulted. The refusal SHALL say that provisioning
is unavailable rather than name a missing consent, because a hint naming a
consent implies that granting it would make provisioning run.

The grammar (`tinyassets.workspace_provision`) and the command layer
(`tinyassets.workspace_resolver`) exist as LIBRARY CODE WITH NO CALLER, so their
rules bind nothing yet and are recorded here as what slice B will wire, not as
what this release does: only Python records that parse as a PEP 508 requirement
with no URL, one `==` specifier, a PEP 440 version, at least one
`--hash=sha256:<64 hex>` and a marker over the seven admitted variables; only
Node projects whose lockfile (version 2 or 3) has no `workspaces` key and no
`link:` entry and whose every installable entry resolves to an
`https://registry.npmjs.org/…tgz` with a `sha512-` integrity; reconstructed
canonical texts rather than the original files; a staged digest recomputed from
the bytes on disk; `--only-binary=:all:` with `--require-hashes` and without
`--no-deps`; `--ignore-scripts`; and an offline install with no index.
`workspace_provision_failed` is classified in the taxonomy and is not raised by
anything in this release.

#### Scenario: a checkout that asks for provisioning gets a checkout and a refusal
- **WHEN** a `checkout` packet declares `provision`
- **THEN** the checkout completes, the evidence records `workspace_provision_refused` saying provisioning is unavailable in this release, no manifest is opened and no consent is looked up

#### Scenario: an sdist-only or URL requirement is refused before any network
- **WHEN** slice B wires the grammar and the requirements file contains `git+https://…`, a local path, `-r other.txt`, or `pkg>=1.0`
- **THEN** provisioning is refused as `workspace_provision_refused` naming the offending line, and no resolver command is built

#### Scenario: a lockfile resolution outside the registry is refused
- **WHEN** the lockfile carries an entry resolved to `git+https://…`, `file:…`, `https://registry.npmjs.org.evil.example/…`, `https://cdn.registry.npmjs.org/…`, or one with a `sha256-` integrity
- **THEN** provisioning is refused as `workspace_provision_refused` naming the entry

#### Scenario: a version 2 lockfile's legacy graph cannot reach the installer
- **WHEN** a version 2 lockfile's `packages` map is clean and its top-level `dependencies` tree names a tarball on another host
- **THEN** the staged lockfile is rebuilt from validated fields only, declares `lockfileVersion` 3, and carries no legacy graph and no such URL

#### Scenario: the staged text is bound to what was admitted
- **WHEN** the bytes that land on disk differ from the admitted plan for any reason
- **THEN** staging refuses, because the digest is recomputed from the file the installer would read rather than from what was intended

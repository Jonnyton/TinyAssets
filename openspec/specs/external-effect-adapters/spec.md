# External Effect Adapters

> As-built baseline (2026-07-22, change `backfill-independent-shipped-contracts`): describes shipped local completion-path adapter behavior and current limitations. Shared authority, consent, and receipt semantics remain owned by `external-effect-receipts`.

## Purpose

The shipped Branch-completion effect dispatch, sink-specific adapter behavior, system-authored evidence, and current partial-write/finalization boundaries.

## Requirements

### Requirement: Declared node effects dispatch after run completion without changing terminal success
After a normal or resumed Branch run completes, the runtime SHALL inspect each node's declared `effects`, find matching packets only in that node's declared output keys, and dispatch the registered sink adapter. Returned per-node, per-sink evidence SHALL be stored in system-authored `external_write_results`; only evidence with a truthy `error` SHALL also be flattened into `external_write_errors`, so dry-run refusals remain results rather than errors. Per-sink exceptions SHALL become structured crash evidence and SHALL NOT reverse the completed run status. As-built limitation: a top-level effector import or dispatch exception is logged and returns an empty evidence map, so that failure is not persisted as structured run evidence. Nodes without declared effects SHALL produce no adapter work.

#### Scenario: Declared sink receives its matching packet
- **WHEN** a completed node declares a supported effect and one declared output key contains that sink's packet
- **THEN** the runtime dispatches that adapter and records its result under the node and sink in `external_write_results`

#### Scenario: Adapter error does not fail the run
- **WHEN** a sink adapter returns evidence with a truthy `error` or raises inside per-sink dispatch
- **THEN** the runtime records result and flattened error evidence and the Branch run remains completed

#### Scenario: Dry-run refusal is not flattened as an error
- **WHEN** an adapter returns dry-run evidence without an `error` field
- **THEN** the evidence remains in `external_write_results` and no corresponding `external_write_errors` row is created

#### Scenario: Top-level dispatch crash loses structured evidence
- **WHEN** the effector module import or top-level dispatch raises
- **THEN** the runtime logs the exception, returns an empty evidence map, and still completes the Branch run without persisted adapter evidence

#### Scenario: Resume completion also dispatches effects
- **WHEN** a previously interrupted run reaches completion through `resume_run`
- **THEN** its declared effects use the same dispatch and evidence path as an initial completion

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
`$ta.concat` as a transform applied in the effector process before the wire
request reaches the credential-blind worker. The `$ta.` namespace SHALL be
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
`{"$ta.concat": [X, …]}` joins texts. X MAY itself be a transform. JSON-encoded
strings are traversed and lists indexed. This SHALL be the only knowledge the
effector gains beyond shape: one encoding and the run it belongs to, never a
service.

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

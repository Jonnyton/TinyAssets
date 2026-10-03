# Inventory R1 repair: acquisition contract before the scanner

Status: implementation blocked on this contract's design disposition. This file
is a bounded handoff, not a completed R1 fold or permission to run an inventory.
Source: #4273 at `a2c28a3696f86936658e39c2be5d630734f33250`; original
[Codex R1 ADAPT](https://github.com/TinyAssets/TinyAssets/pull/4273#issuecomment-5947901737).
No source data, production inventory, credentials or host settings were accessed.

## Why the bounded patch cannot certify E1

E1 requires a zero-count migration oracle over operational fields decoded in each
encoding, excluding verbatim content, on a consistent production copy. E3.4 names
SQLite online backup. The existing script accepts any directory and has no
acquisition boundary. A directory called a copy, successful `integrity_check`, or
an `immutable=1` URI cannot establish how its database/WAL family or its JSON and
LanceDB state were captured. Per-database backup does not make independent stores
one cross-store snapshot. Existing raw byte scans also cannot identify hashed
dependencies or distinguish checkpoint operational identifiers from user text.

The existing layout fence is useful and must be reused: `storage_layout.py`
documents process-lifetime shared locks for managed writers, including host jobs
and children. However, `require_layout`, `check` and `_open_lock` can create/chmod
the lock or initialize the marker. None is a read-only inventory admission API.
An exclusive lock on an arbitrary already-copied directory also says nothing about
the copy's earlier acquisition. Do not introduce another fence or assume a
producer merely because a caller wrote a manifest saying `consistent: true`.

## Proposed acquisition and scanner boundary

One trusted acquisition invocation must capture and then scan its private artifact
without accepting a caller-supplied consistency assertion. It acts only on a
managed root for which all writer entry points honor the existing layout fence.
This requires an offline source window; the inventory must refuse a busy/live
root immediately instead of stopping services or waiting for them. Scheduling
that window or operating on production is separate host work, not this repair.

1. Add a narrow read-only admission adapter for the existing `.layout.lock` and
   `.layout.json`. Open the existing lock without create/chmod, with regular-file
   and no-link checks, and acquire exclusive/nonblocking. Refuse missing lock,
   missing/unknown/non-stable marker, unsupported lock/containment enforcement,
   submount/reparse traversal, or incomplete managed-writer coverage. Recheck the
   marker after locking. Never call the initializing public layout APIs.
2. Keep that fence for the whole acquisition. Managed daemon, workers, timer jobs
   and their children must be absent by the fence contract; prove this with the
   actual entry-point lock behavior on fixtures. A root under an uncontrolled
   independent writer cannot be declared consistent and is outside this mode.
3. Capture source bytes through rooted, no-follow descriptors into a fresh private
   scratch directory outside the source. Enumerate boundedly and reject links,
   special files and path replacement; never resolve a path outside the root.
   Copy a complete known database family under the same fence. Open SQLite only
   on that private family, then use its backup API to create the final standalone
   scan database. Recovery/sidecar creation is allowed only inside disposable
   scratch. Never open a source SQLite or LanceDB store with their library APIs.
4. Capture JSON, marker and LanceDB bytes during the same fence interval. Open
   LanceDB only on the completed private artifact. Release the source fence only
   after acquisition completes or is explicitly aborted. Record exporter version,
   captured path/type/byte hashes, layout, fence interval and completed categories.
   No raw contents or credential values enter the report.
5. The scanner receives only the artifact created by that invocation. A saved
   artifact may be reused only with independently trusted acquisition evidence
   and matching hashes. A plain user manifest/directory is unverified input and
   cannot produce `migration_ready: true`; do not build a new signing authority
   merely to accept it. Artifact-import trust is a separate follow-up unless
   existing trusted provenance can be demonstrated.

This is a proposed offline contract, not a claim that a read-only mount freezes
another writable mount, that SQLite immutability is established by an option, or
that a copied lock file authenticates the source. If the existing writer fence
cannot cover all acquisition writers, stop and return the specific uncovered
writer; do not silently fall back to live scanning.

## Scanner fold after the contract is accepted

- Classification is an exact creator-backed name registry. Add singular
  `workspace` from `fantasy_daemon/api.py`; remove generic Markdown, database and
  lock-extension rules. Sidecar/backup families derive only from registered DB
  basenames; a name like `agent-project.db.bak-x` stays unknown. Keep the explicit
  worker-supervisor family only with its documented creator. Cite each added
  name's creator; fixture expectations must stop endorsing arbitrary extensions.
- Separate operational schemas/fields and explicit verbatim exemptions through a
  creator/encoding coverage registry. Scan generated columns with `table_xinfo`,
  schema SQL including CHECK expressions and identifier literals, JSON keys and
  relevant values, and LanceDB identifier rows. Decode checkpoint serialization
  and account for derived-identity dependencies through their owning serializers.
  Unknown encoding/creator or missing decoder is incomplete, not zero. Tasks 3/4
  own migration of derived identities; that does not excuse E1 discovery coverage.
- Use bounded iterative traversal, pruning documented verbatim workspace/repos
  before descent and reporting each exemption. An unrecognized platform subtree
  cannot be silently pruned. Enforce entry, total-byte, file/value-byte, row and
  wall-time limits; cancellation returns an explicit incomplete report. SQLite
  gets a progress deadline; fetch only relevant affinity columns with bounded
  values/batches. Avoid sorting/materializing the full tree or loading whole
  oversized BLOBs before applying the limit.
- Report all unreadable, oversized, unsupported, unknown and skipped paths with
  category/reason. Only explicit verbatim exemptions count as covered without
  scanning content. Include known database backups. `--no-values` must omit JSON
  values as well as SQLite/LanceDB values and say the resulting report is partial.
  Distinguish row counts from matching cells; do not sum cell counts under a row
  label. Avoid exposing record values or secrets in examples/errors.

## Fail-closed limit and exits

The repaired scanner must report `complete`, `migration_ready`, `coverage`,
`exemptions`, `unscanned` and counts separately. A complete pre-migration report
may contain nonzero findings; only complete post-migration operational zero with
the required reader/digest proofs is migration-ready. A names-only report is
never migration-ready. Unknown entries, acquisition errors, unreadable stores,
unsupported encodings or exhausted limits produce `complete: false`,
`migration_ready: false` and nonzero exit by default. Removing `--strict` must
never turn incomplete into success. No incomplete category gets an apparent zero.

Until acquisition and the E1 coverage registry are implemented and proven, the
current #4273 script must not be used as a no-write or migration-readiness oracle.
Do not add a CLI success path based only on a caller asserting that a root is a
snapshot. This documentation does not add runtime enforcement: the original
unsafe entry point remains unchanged and the PR remains draft/ADAPT.

## Required bounded proofs and handoff

Use synthetic creator fixtures only. No real inventory, production probe, secret
read or deployment is needed to build the repair.

| Proof | Required result |
|---|---|
| Managed writer holds layout lock | Acquisition refuses promptly; no source file, marker or sidecar created/changed |
| Offline acquisition with WAL commits, JSON and LanceDB | One fenced artifact preserves committed state; all library writes stay in scratch |
| Missing marker/lock, malformed artifact or unverifiable writer | Explicit incomplete refusal; no initializing fallback |
| Symlink/reparse home/file/store, path replacement, FIFO/device/submount | No escape or blocking read; explicit refusal |
| Unknown extension names versus creator-known DB/sidecar/backup | Unknown remains unknown and exits nonzero |
| Oversized tree/BLOB/JSON, cancellation and SQLite work budget | Bounded consumption; listed incomplete category; nonzero exit |
| CHECK with nested expression, generated field, JSON actor, checkpoint and derived identity | Correct operational findings with verbatim bytes explicitly exempt |
| Same row matching several columns and names-only mode | Accurate row/cell labels; no value scan in names-only; no readiness claim |

Next owner first resolves this acquisition design against the existing fence and
E1 coverage requirements, then implements the original R1 fold with red/green
regressions. Run focused inventory tests, Ruff, mirror/import checks and Linux
fence/containment proofs. Retain historical evidence as historical; obtain the
required current review receipt only after actual implementation. No new broad
refute or production pass was performed for this handoff.

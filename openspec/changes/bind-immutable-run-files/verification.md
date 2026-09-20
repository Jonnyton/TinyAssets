# Foundation verification — not complete file capability

2026-09-19, isolated `codex/run-input-file-custody-proposal` worktree. Corrected
design/disposition committed before runtime code at `1000bd83`; current origin/main
integrated non-destructively at `9f29213c` (including merged PR #3881). No public
capture/read route, scheduling migration, user workflow/account or production
setting changed. Required CI and exact-code review have not run for this slice.

## Red-first and implemented core

- `python -m pytest -q tests/test_run_file_foundation.py`: initially 9 expected
  failures/1 pass (missing manifest preservation and byte-only API). Intermediate
  run caught the separate immutable-version snapshot dropping its manifest.
- `test_run_file_store.py` and `test_run_input_admissions.py` each initially failed
  collection because their planned storage module did not exist. After implementation,
  the 3 new files pass 27 tests on native Windows and Linux.
- Implemented optional lossless `io_manifest` through branch model, stored graph,
  update/fork, immutable version and authoring validation; absent legacy manifest
  remains absent so existing snapshot hashes do not change.
- Extracted `reserve_transfer_bytes` without adding workspace jobs; existing
  `reserve_operation_bytes` retains its job behavior. Scope mismatch refuses;
  existing byte settlement records actual consumed transport after failed copies.
- Added internal exact allocation/operation journal, prewrite key inventory,
  immutable owned object/binding and cleanup-debt transactions. Tests cover capacity
  races, changed replay, bundle validation before insertion, explicit config,
  owner/run binding, same-owner reuse and no receipt dependency.
- Added internal run-owned execution envelope preserving pinned projected snapshot
  or version/hash reference, not a second `inputs_json` copy. Tests cover erasure
  independence, version integrity, owner check before private deserialization,
  changed acceptance and transaction requirements. It deliberately has no unguarded
  start API; worker/migration/start-guard wiring is not yet implemented.

These are internal storage seams, not physical streaming proof. Callers still
must implement the reviewed held-operation, tombstone/current authority,
publication/collector and actual physical deletion proof before invoking them.

## Focused regression proof

Command suite (same 14 files on each OS):

```text
python -m pytest -q -rs tests/test_run_file_foundation.py tests/test_run_file_store.py tests/test_run_input_admissions.py tests/test_workspace_pool.py tests/test_branch_definitions_db.py tests/test_branches.py tests/test_authoring_file_io.py tests/test_authoring_sessions.py tests/test_delivery_public.py tests/test_delivery_runtime.py tests/test_delivery_node_rpc.py tests/test_delivery_account_deletion.py tests/test_run_branch_version.py tests/test_branch_versions_rollback_columns.py
```

- Native Windows, Python 3.14: **371 passed, 2 skipped** in 30.13s. Skips are
  `test_workspace_pool.py:1380` POSIX fork and `test_delivery_node_rpc.py:302`
  Linux bubblewrap. New core tests have no skips.
- Linux, Python 3.11: **373 passed, 0 skipped/0 deselected** in 92.39s.
  Canonical `scripts/linux_oracle.py` could not connect to Docker Desktop's
  `dockerDesktopLinuxEngine` pipe. Used the established WSL Ubuntu Docker fallback:
  `tinyassets-workspace-browser-probe:e2d3edcc`, immutable image ID
  `sha256:1b69d8536490285c7c7a13f1efe53ebe847696a99ae567dbbd2b9761ee0c530a`.
  Read-only current worktree mounted `/src`, workdir `/src`, network none,
  memory 2g, pids 1024, seccomp unconfined; `PYTHONDONTWRITEBYTECODE=1`,
  `TMPDIR=/tmp`, `TINYASSETS_DATA_DIR=/tmp/tinyassets-test-data` and
  `-p no:cacheprovider`. No host/user data mounted.
- `python packaging/claude-plugin/build_plugin.py`: **469 runtime files,
  import probe OK**. All new/changed canonical runtime files mirrored.
- Ruff passes changed modules/tests except the pre-existing 8 E501 decorative
  mojibake separator lines in `daemon_server.py`; same eight found at the pinned
  integrated HEAD via `git show HEAD:tinyassets/daemon_server.py | python -m ruff
  check --stdin-filename tinyassets/daemon_server.py - --output-format concise`.
  No unrelated cleanup performed. `git diff --check` and strict OpenSpec pass.

## Next integrated work and shared ownership

File lane owns custody/run envelope, byte-only extraction, physical lease/generation
use/capture claims and compiler/effector adapters. Cloud lane owns FamilyFence,
root/epoch/closing and lease/lock/outbox lifecycle. Agreed API dependency is cloud
core `1b99c8c4`: `try_family_fence`, `FamilyAdmission.require`, and the planned
`BranchExecutionContext.workspace_family` snapshot. The context is not authority;
fresh fence/row validation and separate byte/placement authority remain required.
Legacy `None` is not inferred from lineage. The cloud commit is not yet integrated
here; no duplicate lock manager was created.

Still open: strict runtime manifest/reference admission, authoring service/native
Windows adapter proof, producer namespace-empty/exclusion claims, all origin/read/
materialization adapters, all-delivery active legacy-worker fencing and run-keyed
start migration, account tombstone/cleanup service, rollout config, exact-code
review, CI/deployment and ordinary two-owner app proof. Receiver retry stays queued.

## Physical stream checkpoint (2026-09-19)

`test_run_file_streams.py` was red first: 9 expected missing-method failures.
The existing held-file/root traversal is extended by an internal bounded stream
helper; no public read authority, authoring adapter, producer snapshot or account
service is enabled. Stage iteration and incremental digest checks hold neither
SQLite nor root coordinator; only final same-parent no-clobber link/unlink
publication holds the physical coordinator. Caller must inventory both names and
hold operation exclusion through binding; interrupted two-name publication is
cleanup debt, not a second allocation. Unsupported hard-link filesystems refuse.

- Native Windows `python -m pytest -q tests/test_run_file_streams.py
  tests/test_execution_blob_proof.py`: **40 passed, 1 skipped** (POSIX FIFO/symlink
  fixture). Exact 10 MiB non-UTF8 stream, ordered binary/empty members, bounded
  memory (<3 MiB traced stage peak), chunk readback, no-clobber, cancellation,
  short writes and ENOSPC preserve exact actual read/write diagnostics. These are
  native physical primitive tests, not the remaining authoring adapter gate.
- Linux fallback container described above, same two tests plus the three core
  tests: **66 passed, 2 skipped** (existing Windows-only blob-proof fixtures).
  All new stream tests execute on Linux. No live data or network used.
- Root coordinator stays available while stream source is paused; cancellation
  prevents the next write. This is not yet the separate family-close/claim test.

The shared lifecycle protocol now explicitly uses short family-fence transitions
and durable exclusive physical capture claims. Stop/OOM need not wait behind file
IO. Required quiescence is the particular producer namespace/tree plus exact
mount/generation and source exclusivity, not an entire otherwise-running family.

## Shared execution-guard checkpoint (2026-09-19)

`test_run_execution_lock.py` first failed collection because the proposed common
module was absent. After implementation, **8 passed on native Windows** and
**8 passed, zero skips on Linux** (same disposable fallback environment above).
Proof covers independent spawned-process contention, crash release without
sidecar replacement, same-process thread contention, database/run scoping,
expired/constructed/PID-mismatched guard refusal and ordinary no-admission runs.
Command: `python -m pytest -q tests/test_run_execution_lock.py` (Linux adds
`-p no:cacheprovider`). Ruff, mirror build/import probe and diff check pass.

This adds no runtime acquisition/recovery caller yet. Cloud owns ordinary managed
execution/epoch/cleanup integration; file lane owns admitted/prepared dispatch.
Both consume this exact common lock. Stop never waits for it. Cross-lane shape
review and integrated Stop/remote-worker recovery tests remain required before
activation; no claim of managed-worker protection from an unused primitive.

## Prepared admission/worker checkpoint (2026-09-19)

Fable 94507 exact guard-checkpoint review and the lead's accepted queued-handoff
ADAPT are retained in `execution-guard-review.md` and its disposition. The later
prepared worker is NOT included in that review approval.

- Start tests were red first (7 absent-API failures), and worker tests first
  failed collection for the absent runtime module. New storage start state uses
  common guard plus expected status/owner/universe/claim CAS and cancellation
  intent checks. Only queued/unstarted may start; interrupted/resumed rows never
  auto-restore. Zero-row claim means no execution. Already-started queued state
  remains no-replay debt pending exact managed recovery, not invented kernel proof.
- Shared origin callback receives existing `author_conn` and `runs_conn`, so
  source authorization does not reenter a writer. Provider binding occurs only
  after committed start and outside both writers, under fresh owner identity.
  Graph/inputs are reloaded from the immutable envelope/run row, not a callback
  replacement. Same run, same guard, same existing executor, no second queue.
- Focused 9-file cohort: native Windows **100 passed, 1 POSIX-only stream skip**;
  Linux **101 passed, zero skips** in the recorded disposable fallback environment.
  Files: `test_run_file_foundation`, `test_run_file_store`, `test_run_file_streams`,
  `test_run_input_admissions`, `test_run_execution_lock`, `test_run_input_start`,
  `test_run_input_runtime`, `test_delivery_runtime`, `test_delivery_attempts`.
  Tests cover saturated pool/free guard, five terminal/resume late-worker winners,
  immutable input/target reuse, no local-context leakage, actual SQLite writer
  availability during provider bind, marker replay refusal and foreign owner refusal.
- These worker tests use a traced invocation boundary and one traced terminal
  seam. Real graph integration REQUIRES the cloud lane's `_execution_guard`
  invocation seam and `terminalize_unstarted_run(base, *, run_id, execution_guard,
  status, error)` CAS. There is deliberately no old-runtime fallback. Native
  Windows worker tests pass after aligning that exact keyword-only contract.

No public origin adapter or legacy dispatch migration is enabled. Complete
ordinary managed lifecycle, exact namespace recovery, source custody service,
all file adapters, exact-head review/deployment and real two-owner proof remain open.

## Strict file contract checkpoint (2026-09-19)

New `test_run_file_contract.py` was red first (missing module). Opt-in strict
parsing reuses authoring `IODeclaration`/`Manifest` vocabulary and keeps legacy
default behavior unchanged. Exact references preserve display metadata as data,
reject path/extra keys and bool-as-int, require immutable owned-row equality,
and apply bounded file/bundle/state contracts without granting ownership.

Native Windows and Linux each: **48 passed, zero skips**, command
`python -m pytest -q tests/test_run_file_contract.py tests/test_authoring_file_io.py
tests/test_run_file_foundation.py` (Linux uses documented fallback). This includes
explicit >8 MiB runtime declaration versus unchanged legacy clamp, 13 malformed
declaration variants, duplicate names, exact reference metadata, zero-byte and
optional empty bundles, and required dict/list state shape. No public route is
enabled by these pure helpers. Mirrors/import and lint pass.

## Authoring source and acceptance-fence checkpoint (2026-09-19)

Internal handle adapter streams exact owned server-private immutable bodies,
rechecking expiry/revocation between bounded chunks. Final short metadata fence
serializes revocation with binding; it holds no writer during copy/hash or physical
publication. Lock order is operation, canonical author/tombstone, source-authoring,
runs. Reverse-order audit: AuthoringStore transactions touch only their own store;
service publication returns from that transaction before other work; account
deletion commits tombstone first and processes satellite stores in separate phases.

Red-first missing adapter/fence tests now pass on native Windows and Linux:
`python -m pytest -q tests/test_run_file_authoring_source.py
tests/test_authoring_file_io.py tests/test_authoring_sessions.py`: **65 passed,
zero skips on each OS**, using the recorded disposable Linux fallback. Includes
3 MiB non-UTF8 input, original metadata, foreign/refused scope, revocation and
expiry between chunks, bounded lock contention, and independent spawned-process
revocation blocked until actual custody binding commits. The fixture creates a
real internal authoring handle; this is not public upload/whole acceptance proof.
Canonical authority, operation exclusion, service orchestration and all public
file adapters remain open. Prepared worker review/disposition retained separately;
its requested integration corrections are not yet claimed complete.

## Real prepared-run integration checkpoint (2026-09-19)

Cloud `af3156ba` and its queued-only terminal CAS correction `f13224a4` merged
non-destructively after the lead dispositioned Fable 38182. Source-authoring
checkpoint is `6a1ffd8a`. Review corrections now implemented: pre-marker seam
compatibility refusal, exact queued-only local terminal predicate, true
`request_cancel` intent-before-dispatch, and actual marker-agnostic same-attempt
pre-invocation terminal settlement. Callback actor is captured before preparation;
secondary settlement failures are logged. Restart markers remain no-replay debt.

New integration suite first reproduced four failures: both missing/incompatible
hook cases, independent reset entering during settlement, and pending recovery
starting execution. The existing shared maintenance barrier plus clean-state
check now encloses run guard through provider settlement; no service root/recovery
initializer is called. New tests use the actual graph invocation and terminal
hooks, not traced substitutes. Provider callbacks are deterministic local fixtures,
not live provider/account evidence.

`python -m pytest -q tests/test_run_input_integration.py
tests/test_run_input_runtime.py tests/test_run_input_start.py
tests/test_workspace_family_execution_guard.py`: native Windows **49 passed,
zero skips**; Linux **49 passed, zero skips**, recorded disposable fallback.
Includes independent-process reset exclusion through settlement, reset-first
waiting before run guard/marker, nested existing service/worker shared leases,
actual graph success/Stop, null-marker cancellation and post-marker binder failure
with cancellation/resumed winners. Older traced worker tests remain useful unit
contracts but are no longer the sole integration evidence.

No public origin, legacy-worker migration or file reader/materializer is activated.
Nested synchronous common dispatch still needs trusted depth/child-pool parity;
all-origin file capability, exact-head review, CI/deploy and two-owner proof remain
open. These tests do not prove cloud producer namespace emptiness or file custody
service orchestration.

## Legacy recovery exclusion correction (2026-09-19)

Root's storage-review integration finding reproduced in four red cases: an aged
admitted run with no family assignment was interrupted by another process's read
or startup sweep, both before and after the durable start marker. Current ordinary
`create_run(...queue_universe_id=...)` assigns family metadata immediately; the
fixture deliberately models an existing reservation whose universe is assigned
after insertion. Common admission must protect both forms, not depend on timing.

Both legacy paths now exclude `run_input_admissions` using their existing runs
connection. The status-write transaction covers schema/predicate lookup and the
conditional rewrite so concurrent admission cannot slip between probe and retire.
Read-time rewrite also rechecks family-null predicates. Absent legacy table is
supported without schema creation; a malformed present table/view fails closed.
No new writer connection, authority grant, recovery queue, marker reset or replay.

Native Windows/Linux: **48/48 passed, zero skips** for
`test_run_input_recovery.py test_run_input_integration.py
test_workspace_family_execution_guard.py test_workspace_family_transitions.py`.
After adding corrupt-schema tests, the final recovery file alone passed **12/12
on each OS**. Same recorded commands/environment. Prepared started debt still
requires exact guarded recovery; exclusion is not a claim that cleanup is complete.

## Standalone binary custody service checkpoint (2026-09-19)

New `test_run_file_capture.py` first failed collection for its absent service.
Internal standalone capture now connects existing immutable authoring handles,
bounded streams, per-operation OS exclusion, tombstone/current admin fences,
prewrite inventory, short serialized capacity measurement, exact ready-object
transaction and separate existing transfer ledger settlement. No API is exposed.
The new operation guard uses the existing kernel-lock primitive, not a second
workspace-family manager or TTL lease. Both publisher and future collector must
own this same stable sidecar through their operation.

Native Windows **67 passed, 1 skipped** (POSIX FIFO/symlink fixture); Linux **68
passed, zero skips** for `test_run_file_capture.py test_run_file_lock.py
test_run_file_streams.py test_run_file_authoring_source.py
test_run_file_foundation.py test_authoring_file_io.py`. Same recorded disposable
Linux environment. Exact 3 MiB binary plus zero-byte bundle, same-label replay
after source revoke, changed-order conflict, foreign/revoked grants, revocation
during copy, actual partial ENOSPC, publication-before-DB fault and cross-process
operation exclusion/crash release are covered. Failure retains exact inventoried
cleanup debt and conservative retained allocation; transport records actual
logical copy bytes, including consumed bytes on ENOSPC. No fake run/job rows.

One integration test reproduced metadata callback execution inside the physical
root coordinator. Corrected publication checks authority/cancellation before and
after the short physical section, never under it; final ready-object commit
still revalidates source/grant/tombstone. Cancellation while awaiting publication
can leave an invisible inventoried body, not a ready reference. The regression is
included in the final cohort above. No user/provider code executes inside fences.

Remaining independently releasable single-owner path: public capture/read/release
adapters and policy/discovery, direct/versioned binding, actual selected-entry and
declared downstream chunk RPC, finite unbound retention/collector, account erase
and reset classification, final exact review/CI/deploy/app evidence. This checkpoint
does not implement those, or claim workspace producer snapshot, cross-owner file
delivery, all origins, reader/download, materialization, cleanup or completed
file capability. Full broader tasks remain open.

## Shared envelope erasure/reset correction (2026-09-19)

Consumer integration supplied two red failures; reproduced independently here:
even an empty `run_input_admissions` table was unclassified by existing root
run-history reset inspection, and real account erasure after a home rebind left
the private envelope in the old universe, blocking deletion of its parent run
with a foreign-key failure. Added only the envelope to known run history and
owner-keyed personal erasure despite a universe column. No widening of reset
scope, source attribution deletion or blind file custody cleanup.

`python -m pytest -q tests/test_run_input_erasure.py
tests/test_account_deletion.py tests/test_scoped_reset_mutation_proof.py`:
native Windows **62 passed**, Linux **62 passed**, zero skips. Two-owner test
uses real `delete_account` after home rebinding and verifies peer envelope/run
remain. External billing/identity callbacks are local fixtures. File custody's
separate physical cleanup/reset classification remains a release gate.

## Reader and exact per-file cleanup checkpoint (2026-09-19)

Reader/collector tests were red first for absent modules; subset cleanup was red
for the missing selective-release contract. Internal owned run-bound reader now
returns exact <=1 MiB base64 chunks/metadata, rechecks current authority before
return, and holds operation exclusion against collection. No arbitrary custody
ID alone grants a read. Known read bytes settle through the byte-only ledger;
unmeasured failures conservatively retain their bounded reservation.

Collector consumes only existing revoked cleanup debt under the same operation
guard, verifies physical-root identity and server inventory, removes exactly its
`.part`/`.body` names, proves absence and only then releases/reconciles capacity.
No recursive scan, pathname payload, TTL takeover, ready-object deletion or SQL
writer across physical cleanup. Per-file release refuses active bindings and
preserves bundle siblings after successful cleanup. Root inspection subsequently
found sibling reads incorrectly refused while a subset cleanup remained pending;
the correction and added proof are recorded below. Unknown deletion keeps capacity debt and an explicit
cleanup-pending result; retry cannot resurrect a released object or replay copy.

`python -m pytest -q tests/test_run_file_reader.py tests/test_run_file_cleanup.py
tests/test_run_file_store.py`: native Windows **27 passed**, Linux **27 passed**,
zero skips. Includes binary ranges/zero-byte EOF, foreign scope/invalid ranges,
revoke-before-return, active-binding refusal, sibling read after selective release,
repeated release, failed cleanup/retry capacity, changed capture replay, corrupt
inventory/path refusal, live operation exclusion and unchanged transport charge
after cleanup. Earlier full reader/capture/cleanup integration: **19/19** on each
platform. These are internal services, not public reader/RPC, scheduled retention,
account physical erasure or completed end-to-end file capability.

## Finite retention and pending-cleanup sibling correction (2026-09-19)

Nine new retention cases started red. Operation timestamps now give staging and
successfully published unbound inputs one hour each at their respective start;
unknown migrated deadlines remain zero and cannot authorize deletion. The existing
five-minute daemon maintenance loop scans a rotating bounded batch, rechecks
expiry under the operation guard and runs writer, and revokes only unbound ready
members. Terminal bound inputs stay retained. New bindings cannot race expiry
into accepting an expired unbound object. No SQL writer spans physical cleanup,
no TTL steals a live operation lock, and cleanup never refunds transport bytes.

Root reproduced an a2003223 isolation error: ready sibling binding succeeded but
reading failed while another object's cleanup was pending. The regression now
reads that sibling both through its terminal binding and a new queued-run binding
before cleanup can succeed. The shared visibility rule verifies the ready object
is outside an exact valid cleanup inventory; four journal corruption/membership
cases fail closed for both read and binding. Pending deletion capacity remains
unchanged until exact absence proof.

`python -m pytest -q tests/test_run_file_retention.py tests/test_run_file_store.py
tests/test_run_file_reader.py tests/test_run_file_cleanup.py`: native Windows
**40 passed**, Linux **40 passed**, zero skips, using the established read-only
WSL Docker fallback command/image above. Additional
cases cover unknown migration ages, bounded rotation past a live operation,
failed-deletion debt/retry, no database creation when subsystem is absent,
preservation of terminal bindings and expiration of only their unbound siblings.
Account physical cleanup and all public/run-node adapters remain open.
Ruff, plugin mirror/import probe, `py_compile` of the existing maintenance entry
point and `git diff --check` pass. This is not a deployed scheduling proof.

## Account physical custody and reset classification (2026-09-19)

Four tests first reproduced real account deletion failing its runs phase on file
FKs, missing physical cleanup, and unclassified root file tables. Added exact
tombstone-authorized owned-operation settlement before generic runs-store row
deletion. A busy lock or failed physical step keeps the store phase visibly
unfinished; inventory/debt remain until existing maintenance or an explicit
deletion retry can settle them. An existing pending subset is settled before
remaining siblings are erased. Current zero allocation/released state is checked
again before FK-ordered row deletion. Owner identity, not the current home, scopes
every file row. Root reset classifies and preserves this run history; it does not
gain authority to discard accepted file contents.

`python -m pytest -q tests/test_run_file_erasure.py tests/test_run_input_erasure.py
tests/test_account_deletion.py tests/test_scoped_reset_mutation_proof.py
tests/test_run_file_retention.py tests/test_run_file_reader.py
tests/test_run_file_cleanup.py tests/test_run_file_store.py`: native Windows
**107 passed**, Linux **107 passed**, zero skips (same explicit WSL read-only
fallback). The two-owner fixtures use identical bytes in independent physical
copies, bind terminal runs, rebind the deleted owner's home, invoke real
`delete_account`, and verify the peer's bytes/rows/bindings survive. Also checks
busy operation fencing, retained deletion debt through failure, maintenance
recovery, retry and refusal without a real tombstone. Existing active-work
deletion refusal is unchanged; this is not a new Stop/cancellation implementation.
Ruff and plugin mirror/import probe pass. Public adapters and rendered acceptance
remain OPEN; no production/user data was touched.

## Shared prepared carrier and post-unwind notification (2026-09-19)

Lead approved additive trusted concurrency/status-callback fields for direct
file-run parity and the consumer's optional post-unwind `on_settled` notification.
No new executor, depth authority, queue or start marker. New tests first failed
on the absent API, then prove exact option propagation, notification after the
run guard unlocks, one notification after a pre-start authority refusal,
exception isolation/visible logging, and pool cancellation leaving canonical
queued/unstarted truth untouched. Callback does not prove terminal state.

`python -m pytest -q tests/test_run_input_runtime.py tests/test_run_input_integration.py
tests/test_run_input_start.py tests/test_run_input_recovery.py
tests/test_run_input_admissions.py`: Windows **55 passed**, Linux **55 passed**,
zero skips before the additional published-version regression (10 existing
LangGraph Python-3.14 deprecation warnings on Windows). These
include actual graph/settlement/reset integration, not only traced invocation.
This shared seam is not public file adapter completion.

Consumer's real published-run integration exposed that canonical executable
snapshots omit `name`; the common worker rejected the valid pin during runtime
validation. Reproduced red using real `publish_branch_version` and actual graph
execution. Applied the established `_load_branch_version` presentation fallback
to a detached copy only, after envelope/hash validation; no persisted bytes or
content digest change. The regression asserts exact before/after stored
snapshot/hash and completed graph result. Final cohort: Windows **56 passed**
(12 existing LangGraph warnings), Linux **56 passed**, zero skips. The first
post-fix attempt exposed a test-provider fixture accepting keyword arguments
only; corrected that fixture to the existing positional provider contract and
reran the full cohort on both platforms. Ruff, mirror/import and diff checks pass.

## Execution-use integration and declared binding checkpoint (2026-09-19)

Non-destructively merged exact cloud execution-use checkpoint `3f98a648`; merge
retains source provenance and does not import later dirty kernel/compiler
activation. Read the full retained ADAPT and implementation receipt. Prepared
worker signatures remain compatible. Added transaction-local whole-declaration
metadata/owner validation before file binding and a worker revalidation seam
which refuses missing bindings rather than creating them. This is not yet public
direct admission or actual file RPC wiring.

`python -m pytest -q tests/test_run_file_binding.py tests/test_run_execution_use.py
tests/test_run_execution_lock.py tests/test_run_input_runtime.py
tests/test_run_input_integration.py tests/test_workspace_execution_use_lifecycle.py`:
Windows **53 passed, 1 skipped** (the fork-only identity case), Linux **54 passed,
zero skips**, same established read-only WSL fallback. Includes actual late RPC
lifetime and shared prepared graph tests plus ordered multi-file metadata,
foreign-owner/released-object refusal and missing-admission binding checks.

## Trusted file-node RPC checkpoint (2026-09-19)

Resumed the preserved binding/node helpers at `c66fa7f1`. Seven actual sandbox
tests first failed because `read_run_file` was not routed. The compiler now
supplies a trusted run/owner/placement source, intersects explicit node input
keys with immutable file declarations, and freezes that incoming view separately
for each invocation. Child RPC accepts only file ID, offset and count. Reads
require the pinned execution-use lifetime, persisted running identity, no cancel
or family closing, original run binding, exact reference metadata and the
downstream declaration's count/media/byte constraints. Whole-state/default
visibility never substitutes for explicit file input declaration.

Actual graph proof consumes the same captured 3 MiB non-text file plus zero-byte
member at a non-default graph placement and again after explicitly forwarding
the bundle. It checks exact SHA-256 results and refuses forged run/owner/node/
source/incoming selectors and undeclared state access. A narrower downstream
byte declaration refuses before its read. Its first assertion expected the
internal size reason; corrected to the existing public ManifestViolation code
(`manifest.invalid_reference@forwarded`), not a runtime behavior change.

Final `python -m pytest -q tests/test_run_file_node_rpc.py
tests/test_run_file_node.py tests/test_run_file_binding.py`: native Windows
Python 3.14 **20 passed**, Linux Python 3.11 **20 passed**, zero skips. Before the
last downstream-declaration check, the Linux combined file/delivery/enqueue/use
cohort passed **103 tests, zero skips**; native Windows corresponding non-file
cohort passed **83 tests, one Linux-bubblewrap skip**. Commands used
`tests/test_delivery_node_rpc.py tests/test_node_enqueue_verb.py
tests/test_node_enqueue_concurrency.py tests/test_workspace_execution_use_lifecycle.py`.
The unchanged Docker Desktop pipe remained unavailable; Linux used the same
immutable WSL oracle image and read-only/current-tree isolation recorded above.
Ruff and diff checks pass; plugin mirror/import probe passes (486 runtime files).

This is a compiler/RPC integration milestone, not public capture/direct dispatch
or deployment. Origin recovery awaits the lead's actual cross-family review
disposition. The common foundation also requires the cloud lane's correction for
ordinary non-managed runs incorrectly entering family-only recovery; no release
may strand those rows. Experimental cgroup/bootstrap fixtures are not a file
reader dependency and must not be wholesale shipped from branch ancestry.

## Explicit admitted-origin recovery checkpoint (2026-09-20)

Full independent Fable96232 ADAPT is retained in
`docs/reviews/2026-09-20-admitted-origin-shape-review.md`; root accepted the
corrections recorded in `origin-recovery-amendment.md` before implementation.
Added only the reviewed origin kind/version/options fields with additive legacy
defaults and exact immutable replay comparison. Direct v1 keeps original typed
recursion/concurrency values; canonical consumer v1 keeps `{}` and resolves its
separate exact correlation. Unknown/legacy/options/correlation disagreement is
held, not guessed from files or terminalized.

One static `dispatch_initial_run` registry entry is used by independent bounded
admission nomination in the existing boot/five-minute maintenance loop. The scan
has its own run cursor, includes runs without file operations and excludes all
durably started rows. Worker guard/CAS and empty-context execution remain common.
Direct preparation reads explicit persisted owner/universe/actor and current
source/home authority, revalidates file bindings, then constructs its provider
session outside writers. Valid depth-zero self-root family provenance is not
mistaken for child-pool provenance; malformed/foreign roots refuse.

Inspection found an exception path that could rewrite a queued row with corrupt
prior start markers to failed. Settlement now distinguishes a marker committed
by this guarded attempt from prior/ambiguous marker evidence; the latter stays
held unchanged. Regressions cover either lone marker component and correlation
conflict, and prove no new start marker. An actual direct sandbox graph completes
through the registry, and subsequent recovery does not replay it. Original
runtime recursion7/concurrency3 survive changing the ambient default to999.

`python -m pytest -q tests/test_run_input_origin.py tests/test_run_input_origins.py
tests/test_run_input_runtime.py tests/test_run_input_admissions.py
tests/test_run_input_integration.py tests/test_run_input_recovery.py
tests/test_run_input_start.py`: Windows **85 passed** (14 existing LangGraph
deprecation warnings), Linux **85 passed**, zero skips. Same pinned WSL oracle,
read-only current-tree mount, network disabled and previous bounded test limits.
Ruff, diff check and plugin mirror/import proof pass (489 runtime files).

Still unconnected: public direct reserve-only intake, public capture/read/release,
consumer acceptance stamp/registry switch (consumer owns its static exports),
and full shared foundation activation correction. This checkpoint is an internal
shared dependency, not an independently deployable file capability or a final
cross-family code approval. Existing wider origin/live acceptance tasks stay open.

## Reserve-only direct file intake checkpoint (2026-09-20)

Added internal `reserve_direct_run`: current owner/home/source authority under
the author fence, then run+origin snapshot/options+whole file binding in one runs
transaction under the existing reset barrier. It performs no initial events,
lineage, provider binding or submission. Only the common registry worker starts
the result. Version-pinned intake derives its file contract from the admitted
version, not a caller's alternate mutable Branch. Strict exact-JSON input
validation precedes insertion; failed bundle metadata rolls back every run,
envelope and binding. Nonzero/bool depth and any nested parent refuse.

`python -m pytest -q tests/test_run_file_direct.py tests/test_run_input_origins.py`:
Windows **22 passed** (10 existing LangGraph warnings), Linux **22 passed**, zero
skips. Both direct and real published-version paths reserve without lineage/start
effects, then execute actual chosen-entry and downstream sandbox reads of the
3 MiB binary plus empty member with exact hashes. Current operational family
activation remains cloud-owned; no public route is installed by this helper.

## Public same-owner slice candidate (2026-09-20)

Canonical and pinned served graph handles now expose owned authoring capture,
disclosed capacity/retention/chunk limits, exact bound readback and selective
release. Direct definition and alternative immutable `branch_version_id`
intake both reserve the run/envelope/bindings before the common registry starts
execution. Mixed selectors and unreadable private versions refuse. Existing
scalar execution remains on its prior executor; admitted files do not construct
the request-context provider before the durable start CAS. Submission failure
returns the original accepted run ID and a no-replacement warning, never implies
that a failed response means no run was accepted.

`59ca33f6` supplies the pure shared metadata classifier also consumed by the
consumer release. Owner-only public status reads five admission metadata columns
without graph/input decoding. Queued prior start markers report uncertainty and
no automatic replay; unknown/corrupt/legacy origins report unavailable. The row
status remains unchanged. This projection is not execution-death evidence and
cannot authorize retirement or retry.

Commands: `python -m pytest -q -rs tests/test_run_file_public.py
tests/test_run_branch_version.py tests/test_engine_mcp_server.py
tests/test_engine_mcp_hardening.py tests/test_engine_mcp_routes.py
tests/test_engine_mcp_write_graph_patch.py tests/test_run_input_observation.py`:
Windows Python3.14 **211 passed, 3 skipped** (Windows symlink creation); Linux
Python3.11 **214 passed, zero skipped**. Actual public-route proof captures a
3 MiB binary plus empty member, executes chosen entry/downstream in the sandbox
for both direct and published-version starts, and exports exact chunks.

The separate file/lifecycle cohort (contract/store/streams/capture/authoring-source/
cleanup/retention/erasure/reader/node/node-rpc/binding/direct/input-erasure plus
required-input-preflight) initially returned Windows **141 passed, 1 skipped,
1 failed**, Linux **142 passed, 1 failed**. The sole failure was the old preflight
unit fixture mocking only the final version executor while providing no version
snapshot, now resolved before selecting the scalar/file adapter. The fixture now
supplies that same branch contract; the complete preflight module rerun passed
**22 Windows / 22 Linux, zero skips**, without runtime changes to mask the issue.
Other cohort results remain valid at identical runtime bytes. The remaining
Windows skip is the POSIX symlink/FIFO fixture, exercised on Linux.

Final combined rerun of both cohorts at the frozen candidate, after correcting
that test fixture: **353 passed, 4 skipped** on Windows (56 existing LangGraph
deprecations); **357 passed, zero skips** on Linux. This supersedes the earlier
split reruns as exact-current-tree suite evidence, not as deployed proof.

Ruff, diff check and plugin mirror/import proof pass (490 runtime files). Linux
used the recorded immutable WSL oracle image, read-only current-tree mount,
network disabled, 2GiB memory and 1024 process limit; Docker Desktop remains
unavailable. No live user/account/workflow was changed or tested by this builder.

Release still requires isolated assembly atop the corrected shared foundation,
independent exact-head review, configured global custody capacity, required CI,
deployed SHA/canary and ordinary rendered app-agent acceptance. This is not a
claim that wider nested/resume/workspace/cross-owner custody criteria are done.

## Isolated assembly in progress (2026-09-20)

The isolated file release starts at consumer `f9b91ed7`, preserving corrected
managed-root activation and its common origin/runtime/model bridge. The source
candidate `4dd99ba4` is not merged wholesale. See `release-inventory.md`.

Initial integrated public-file/direct/origin + consumer scope/model/public-turn
and delivery-erasure cohort: **93 passed**, plus the already-known consumer
maintenance AST fixture failure at that base. Consumer's docs/test-only successor
`d3fa5f91` corrects the enclosing cursor scope; the file layer must also bind its
new file cursor in that fixture. No production-loop change is required.

Expanded 48-file Windows cohort: **832 passed, 6 skipped, 3 failed**. The three
failures are lower-level file node/RPC fixtures that relied on the superseded
implicit managed-family enrollment to create an execution-use guard. On the
corrected foundation these manually prepared runs have no guard unless explicitly
provided. Actual reserve/common-dispatch/public direct/version tests pass. The
fixture correction must provide a real held guard, retain no-guard denial and
never re-enable auto enrollment or weaken file authority. Linux counterpart is
still running at this checkpoint. This assembly is not yet frozen for review.

Broader Ruff checking found eight pre-existing E501 warnings on mojibake divider
comments in `daemon_server.py`; `git show f9b91ed7:tinyassets/daemon_server.py |
python -m ruff check --stdin-filename tinyassets/daemon_server.py --output-format
concise -` produces the same eight, with only downstream line shifts. File hunks
do not touch those comments; no unrelated cleanup is included.

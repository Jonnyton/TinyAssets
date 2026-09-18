# Cross-user accepted-delivery runtime integration

September 18, 2026 UTC. Isolated branch `codex/cross-user-delivery-mvp`, based
on current main. Selectively integrated only canonical runtime/tests from the
three September 9 implementation units and their directly related approved
design/review artifacts. No private workflow was edited.

The internal runtime submits an existing reserved attempt through the normal
executor in a fresh Context. Under the attempt's OS lock it revalidates current
receiver admin/graph ownership and the pinned snapshot, persists execution-start
before any provider work, binds the receiver's provider explicitly, invokes the
shared prepared-run worker, then publishes only a safe terminal receipt. Ordinary
run recovery happens before boot dispatch; the existing maintenance loop runs
subsequent passes. An executing attempt without a live lock becomes interrupted,
never automatically replayed. No caller-supplied identity or sender context is
copied into receiver execution.

## Verification

`python -m pytest -q tests/test_receiver_projection.py tests/test_receiver_links.py
tests/test_delivery_reservations.py tests/test_delivery_attempts.py
tests/test_prepared_run_worker.py tests/test_run_transaction_insert.py
tests/test_delivery_runtime.py tests/test_webhook_delivery_proof.py`

- Windows Python 3.14: 155 passed, 40 dependency deprecation warnings, 34.10s.
- Native WSL Docker through `scripts/linux_oracle.py --` with that exact test
  selection: 155 passed, no skips, 35.86s; Python 3.11.16, git 2.47.3,
  bubblewrap 0.12.0. Docker Desktop's pipe was absent; the existing native engine
  was used without installing/restarting a service.
- Ruff on changed canonical runtime and seven delivery test files passed.
- Plugin build staged 451 files and its import probe passed; diff check passed.
- OpenSpec strict validation passed. All ten proposed public action verbs
  passed `check_primitive_exists.py action <verb>` against origin/main.

Tests use real graph execution, SQLite, executor threads and OS locks. Only the
provider is deterministic. Separate assertions cover explicit receiver provider
binding, fresh request context, stale sender context exclusion, restart before
execution, interrupted started work, live lock exclusion, revoked receiver admin,
safe processing failures, and unsupported file-reference envelopes.

## Remaining gates and scope

This proves internal execution of previously accepted structured occurrences.
It does not yet expose public intake, output mapping/provenance, owner-directed
retry, public/served management or receipt actions. Runtime file staging,
immutable run-owned artifact bundles, exact-byte chunk reads and accounting remain
unimplemented. File delivery is not promised or represented as ordinary JSON.
Public/served wiring, exact-head independent review, CI, deployment and two-user
rendered acceptance remain open; the full OpenSpec change is not complete.

## Structured public wiring follow-through — 03:45 UTC

The subsequent bounded implementation connects receiver/create/update/revoke,
output_link/connect/disconnect, run_graph deliver_output and receiver/output_links/
delivery reads through canonical scopes/dispatch/ledger and graph-pinned served
wrappers. Inputs require exact JSON, declared source outputs, receiver input types,
current owner/admin authority, permitted sender/generation and actual receiver
resource admission. Unsupported file-reference envelopes fail before run
reservation. The sender ledger targets delivery_id and cannot carry private run IDs.

Eight public-control regressions pass: real canonical expose/connect/send/process/
two-sided read; replay/conflict/foreign-owner denial; invalid input; foreign file
reference; disconnect; revoke; receiver admission refusal; safe ledger target;
and served wrapper confinement (some cases contain several related assertions).

Command: `python -m pytest -q tests/test_delivery_public.py
tests/test_delivery_runtime.py tests/test_receiver_links.py
tests/test_engine_mcp_server.py tests/test_canonical_dispatch.py --tb=short`.
Windows: 181 passed, 3 platform skips, 22.35s. Native WSL Linux oracle with the
same selection: 184 passed, no skips, 24.56s, same Python/git/bwrap versions above.
The tar warning concerned concurrent Python bytecode cache metadata only; no
runtime source was edited during the Linux snapshot. Ruff, mirror and diff checks
passed after all code edits.

This supersedes only the earlier public structured intake/wiring limitation.
Full artifact transfer, in-node RPC/effect provenance and explicit receiver retry
remain open. Exact-head approval, CI, deploy and rendered two-owner acceptance
are not claimed by local tests.

## Release-blocking account erasure correction — 04:30 UTC

Fable's public-candidate verdict was conditional DARK ONLY until delivery records
participate in account erasure. This correction is a release blocker fix, not a
claim the original approval covered the new head. Main `1bd4b4f4` was merged
forward cleanly; its changes since base `64e29743` contain no changes to
`tinyassets/runs.py` or `tinyassets/api/runs.py`, preserving the reviewed run seam.

Explicit satellite-store targets delete attempts before personal two-party
receipts, dependent links, then scoped receiver endpoints. Each union predicate
is counted once before writes; failure rolls back the store and reports an
unfinished phase while billing and identity cleanup continue. Surviving receiver
allowlists remove only the exact deleted principal. Existing universe-scoped
ownership semantics remain intact: peer-owned accepted runs and their input
content are not erased as a generic cascade. Public intake rollback must retain
this cleanup support for persisted delivery tables.

Canonical handle signatures remain unchanged; the served `read_graph` wrapper
DOES gain optional `query` for validated collaboration reads. Saying all served
signatures were unchanged would be incorrect.

Windows focused delivery/account cohort: 107 passed in 31.54s. Native WSL Docker
Linux oracle: same 107 passed, no skips, 23.60s; Python 3.11.16/git 2.47.3/bwrap
0.12.0. The Windows Docker Desktop pipe was absent, so the existing WSL engine
ran the unchanged oracle with its repo-root locator overridden in memory (a
Windows linked-worktree git path cannot resolve inside WSL). No service or repo
configuration changed. Final additional full-failure receipt and isolated actual
maintenance-loop test: four targeted Windows tests passed; final complete Linux
cohort passed 108 tests with no skips in 23.72s; final Windows cohort passed the
same 108 tests in 30.63s (ten existing dependency warnings). The delivery boot and
tick exception handling is separate from budget reconciliation, preventing a
delivery exception from disabling budget cleanup.

Plugin regenerated (464 files, import probe passed), full mirror parity and Ruff
passed. Final exact-head independent review, CI and ordinary two-user rendered
acceptance still gate exposed delivery; none are inferred from these local tests.

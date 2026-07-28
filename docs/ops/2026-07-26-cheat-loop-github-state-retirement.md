# Retired GitHub-state migration

This runbook covers the final removal of GitHub state created by the retired
privileged cheat/community patch loop. The state is migration data, not a
current product surface. Equivalent automations are ordinary user-authored,
copyable, remixable designs.

## Current disposition

Apply is blocked. As of 2026-07-27, read-only production inventory found:

- all 28 exact retired label definitions;
- 1,963 retired-label associations across 884 unique items;
- 221 open issues, 297 closed issues, and 366 closed or merged pull requests;
- 98 open pull requests, including 21 with auto-merge requests; and
- workflow database ID `317815472` (`auto-enroll-merge.yml`) still active.

The terminal-proven label receipt binds all 29 Link-header connections (six
multi-page) at digest
`sha256:6407b7f78a15c9160805b858cb000b0a5ea6801f8917478d6d2e3451db7d331c`.

The 2026-07-27 terminal-proven live attribution receipt captured 833 workflow
runs, 21 complete job connections, the one-entry reviewed default-branch
source history, and one exact run/job/step/log proof for each of the 21
enrollments. All 21 classify `attributed`; none classify explicit or ambiguous.
Its inventory-only receipt digest is
`sha256:c5063d6f38071b9a9f4fc9ee415c664f65708cdb7d41ea963270314804534b37`.
Both receipts are bound to implementation revision `4a4b9efe` and include terminal
GitHub Link-header evidence. This remains historical capture, not mutation
authority: the workflow is active and `apply_complete=false`.

Closed items remain untouched as history. Generic labels and explicit
user/maintainer auto-merge requests are preserved.

The label gate is concretely false: workflow `community-loop-watch` (database
ID `268723091`) is active, still recreates and routes
`community-loop-red`, and GitHub reports run `25906701411` queued since
2026-05-15. `scripts/merge_readiness.py` still consumes
`ready_for_checker`. These producers/consumers must be retired and the run
inventory drained before label apply.

## Safety model

`scripts/retire_cheat_loop_github_state.py` has a read-only command-line
surface. Its GitHub reader exposes structured operations instead of arbitrary
arguments: REST calls always synthesize explicit GET requests, and GraphQL
accepts only the reviewed query with exact plain repository variables. Every
read pins `github.com` rather than inheriting an ambient CLI host. It can
produce RFC 8785/JCS receipts. Offline `verify` checks schema, normalization,
bindings, and digest integrity; it explicitly does not re-verify external
GitHub provenance. Receipt digests are unkeyed integrity checks, not signatures
or authenticators; editing a receipt and recomputing every digest does not
create external provenance or mutation authority. There is deliberately no
live GitHub mutator in this increment.

Every live plan binds the repository node identity, source revision,
terminal-proven paginated inventory, operation, and plan digest. Array-valued
REST reads receipt each GitHub Link-header hop and the terminal absence of
`rel="next"`; a terminal page that fills the requested page-size bound remains
ambiguous, and observed counts are never copied into a fictitious server total.
If an exact-multiple boundary produces that fail-closed result, keep the
receipt rejected and rerun the read-only inventory with a different explicit
`per_page` value in the 1-100 range. Review and test that request-bound change;
never weaken the terminal guard or hand-edit/re-digest the ambiguous receipt.
Each page retains its canonical request endpoint so offline validation can
re-derive the bound and request digest instead of trusting a self-declared
`page_size`. The apply key is derived from
that body. A dedicated SQLite journal uses WAL, `synchronous=FULL`,
`busy_timeout`, and `BEGIN IMMEDIATE`. Immutable per-target intent is committed
before an exact remote pre-read. Drift is held for replanning; the engine never
guesses, rolls back, relabels, or re-enrolls.

The journal serializes one executor. A crashed or interrupted apply stays
blocked until recovery is explicitly authorized; it is never silently reaped.
Recovery first reconciles every prior intent against an exact remote read.

GitHub has no expected-state compare-and-swap for label deletion or
`disablePullRequestAutoMerge`. `clientMutationId` is correlation, not a CAS.
The unavoidable race after the immediate pre-read is minimized by making no
intervening API call and requiring an exact post-read before recording success.

## Read-only inventory

From the claimed worktree:

```powershell
python scripts/retire_cheat_loop_github_state.py inventory `
  --operation retired_labels_v1 `
  --repo Jonnyton/TinyAssets `
  --out output/github-label-retirement-plan.json

python scripts/retire_cheat_loop_github_state.py inventory `
  --operation auto_merge_v1 `
  --repo Jonnyton/TinyAssets `
  --with-attribution `
  --out output/github-auto-merge-retirement-plan.json
```

The label reader uses the repository issues endpoint once per exact label,
with `state=all` and `per_page=100`. It follows each exact `rel="next"` URL,
validates API origin, repository, endpoint, query scope, order, uniqueness, and
the bounded terminal page, and receipts per-page request/response digests.
GitHub Search is not used, so its 1,000-result cap cannot truncate the receipt.

The auto-merge reader fully pages open pull requests and records the exact PR
identity, current head, repositories, draft/state tuple, and full
`autoMergeRequest`. With `--with-attribution`, it also fully pages workflow
runs and candidate jobs, verifies the reviewed default-branch workflow Git
blob, and hashes bounded run-log archives while retaining only non-secret proof
markers. The exact raw GraphQL Actions identity is
`Bot/github-actions/MDM6Qm90NDE4OTgyODI=`. That actor alone remains ambiguous:
attribution additionally requires one matching run/job/step window and one log
member proving the exact PR, repository, auto-squash command, and successful
enrollment line. If an otherwise eligible competing run's log is unavailable,
the receipt binds `log_unavailable` to that captured run and preserves the PR
as ambiguous; a failed read never makes another candidate appear unique.

Stable GitHub APIs do not expose the exact historical default-branch commit
used by a `pull_request_target` run. The collector therefore never substitutes
`run.head_sha` or mutable pull-request association data as a workflow-source
commit. It verifies reviewed blob
`1e3d8996644756a8fedf1baacd473cffd614c91b`, whose enrollment command was the
only default-branch implementation governing these runs. Historical run head
and current PR head remain separate fields: #1505 and #1558 advanced after
enrollment and are not made ambiguous merely by that later change.

## Gates before any live adapter may be added or used

All gates are conjunctive and must be rechecked immediately before each
mutation:

1. The apply key and confirmed plan digest exactly match the receipt.
2. Repository node identity, source revision, and default branch match.
3. The authenticated viewer has `ADMIN` or `MAINTAIN` plus the exact endpoint
   capability.
4. OpenSpec task 4.2 and every retired-label producer/consumer are removed.
5. Workflow `317815472` is `disabled_manually`; every queued, requested,
   waiting, pending, or in-progress run is cancelled and the fully paginated
   run inventory is drained.
6. Every connection is terminal and observed counts match authoritative
   totals.
7. Auto-merge attribution contains exactly one historical run/job/step/source
   proof per eligible enrollment. Human enrollments are explicit and
   preserved. Missing or duplicate proof is ambiguous and blocks apply.
8. A fresh exact inventory still matches the planned digest.

## Intended label order

After the gates pass, the later live adapter must:

1. Persist one intent per exact retired label on each open item.
2. Re-read item node ID, number, state, and the full label set.
3. Remove only the named retired label. Never patch title, body, state, or
   comments. If the item closed, leave it untouched.
4. Prove zero open associations with another full scan.
5. Publish or reconcile one repository notice using an immutable marker bound
   to repository ID, apply key, and plan digest.
6. Only after all item and notice intents succeed, persist an intent and delete
   each definition bound by node ID, name, color, and description.
7. Prove the exact 28 definitions are absent and all generic preserved labels
   remain.

Missing state without a prior same-key intent is foreign drift, not success.
Partial item or notice failure deletes no definitions.

## Intended auto-merge order

Disable and verify workflow `317815472`, cancel and drain runs, then take the
inventory. For each exactly attributed enrollment, persist its full tuple
before pre-read, disable it, and persist the post-read. A changed tuple is
skipped for a fresh plan. A null request after restart reconciles only when a
same-key intent and unchanged PR identity/head prove the intended delta.

The workflow source cannot be deleted until a final fully paginated rescan
proves a complete receipt, a disabled and drained workflow, and zero attributed
or ambiguous open enrollments.

## Obligations before a live mutator

The 2026-07-27 Claude Opus 5 opposite-provider review required three
inventory-truthfulness corrections: structured read-only request construction,
terminal Link-chain receipts, and explicit separation of offline integrity
verification from external provenance. The current reader closes those
inventory-only findings. A later live-adapter change must still close these
findings before it can apply:

1. Re-fetch and match the exact source/run/job/step/log identities and archive
   digests in every future live adapter's immediately fresh per-action proof;
   the inventory receipt alone never authorizes mutation.
2. Move the focused suite into the normal `tests/` collection after the active
   broad test-file claims release.

The earlier recovery, executor fencing, row-count, per-action freshness, and
raw Actions-actor-form findings are closed in the current read-only
implementation and focused suite. They remain mandatory invariants for any
future adapter.

These are not authorization to add the adapter. OpenSpec tasks 3.6/3.7, task
4.2, producer shutdown, workflow disable/drain, and opposite-provider review
remain conjunctive gates.

## Verification

```powershell
python scripts/retire_cheat_loop_github_state_test.py
python scripts/retire_cheat_loop_github_state.py verify `
  output/github-label-retirement-plan.json
```

Successful offline verification reports `integrity_valid=true` and
`external_evidence_verified=false`. Attribution-bearing auto-merge receipts
can only be produced by live `inventory --with-attribution`; offline `plan`
rejects imported attribution evidence. Verification reconstructs the exact
dry-run receipt envelope and rejects unknown top-level, connection, pagination,
page, and terminal fields even when a caller recomputes every digest. The
retired-label inventory also closes definition and association record schemas,
validates their exact collector-shaped scalar values, and rejects every
non-array or non-empty label `planned_actions` value while label apply is
unimplemented. A collector-through-build-through-verify regression binds the
live reader shape to those exact schemas.

Receipt JSON and journal errors exclude credentials, authorization headers, raw
GraphQL bodies, and log output. Any 401, 403, 429, 5xx, secondary-rate-limit,
pagination, schema, digest, or remote-state anomaly stops the migration for
review.

## Context

TinyAssets retired the cheat loop in principle on 2026-06-25, and PLAN.md now
states the stronger product rule: recurring task automation is a user-authored,
copyable, remixable composition of platform primitives. The shipped tree still
contains the opposite behavior:

- `file_bug` creates a trigger receipt and silently calls
  `_maybe_enqueue_investigation`;
- two host environment variables select a product-wired investigation handler;
- `bug_investigation` is a dedicated request type with payload adaptation and
  executor special cases;
- completed runs can mutate wiki pages through an automatic Patch Packet
  attachment path;
- extension actions expose an auto-ship validator and PR writer backed by a
  dedicated ledger, while `get_status` publishes `auto_ship_health`;
- deployment configuration, a named community-loop watch workflow, and current
  operator guidance keep the product loop alive;
- production deploy configuration and the Claude plugin mirror ship the path;
- tests pin the retired behavior as supported.

This is not a migration from one privileged loop to another. General Goal
canonicals, requests, queues, graph execution, and wiki writes already provide
the primitives from which a user can build the same outcome explicitly.

## Goals / Non-Goals

**Goals:**

- Remove the full product-wired bug-investigation automation, including both
  Goal-ID and branch-definition environment routes.
- Make `file_bug` a filing operation with no hidden task, receipt, run,
  dispatcher/triage route, or write-back side effect.
- Delete filing-effort classification and dispatch-route policy that emits
  carrier, daemon-pickup, fast-lane, or opposite-family-checker semantics;
  preserve ordinary filing fields and duplicate detection.
- Remove dedicated `bug_investigation` handling from the runtime, deployment
  configuration, generated plugin payload, current operator guidance, and
  behavior-pinning tests.
- Remove the auto-ship validator, action wrappers, PR writer, ledger/storage,
  configuration, auth/extension registration, and status projection.
- Retire the `community-patch-loop` capability and all named shipped artifacts.
- Remove patch-loop/community-loop product presentation and fallback data from
  the production React/Next website and retained Svelte rollback tree while
  preserving truthful generic user-workflow activity.
- Preserve generic composition and execution primitives.
- Remove hard-coded patch-intake writer/checker/access policy while preserving
  explicit requester pickup incentives, directed-daemon selection, and the
  user's soul-declared loop dispatch as ordinary user-authored routing.
- Remove both website `community_change_context` wire callers first; after they
  unblock the legacy-registration owner and its exact-six cutover lands, delete
  the internal product action, auto-change/auto-fix queue semantics,
  hard-coded provider-family review rule, tests, and plugin behavior.
- Move read-only uptime, deploy, clean-clone, and revert-rate observation to a
  generic uptime/alarm successor with no task-dispatch self-heal.

**Non-Goals:**

- Removing Goal canonical selection used by explicit `run_canonical` behavior.
- Removing the generic dispatcher, BranchTask, request/trigger primitives, node
  enqueue, or wiki write capabilities.
- Removing generic evaluation or explicit GitHub-effect primitives from which a
  user may compose a reviewed shipping workflow.
- Removing generic GitHub reads or PLAN lookup primitives from which a user may
  build their own review-context workflow.
- Removing `_universe_loop_dispatch`,
  `TINYASSETS_SOUL_LOOP_DISPATCH`, or a user's explicit
  soul-declared `loop_branch_def_id`; those are the user-authored automation
  path this retirement is meant to preserve.
- Removing explicit requester pickup-incentive or directed-daemon inputs. They
  remain bounded pickup signals and never imply acceptance, release, merge, or
  a platform-selected writer/checker workflow.
- Defining a new scheduler, bug-investigation workflow, or compatibility alias.
- Rewriting historical plans and audits that are clearly identified as history.

## Decisions

### 1. Delete the privileged path instead of disabling it

The runtime SHALL remove the hidden `file_bug` trigger, its receipt store, both
handler-selection environment variables, dedicated request type, payload
adapter, executor packet extraction, and automatic wiki attachment. A no-op
environment variable, feature flag, compatibility alias, or dormant module
would continue to ship the retired product shape and invite reactivation.

Alternative considered: leave the code disabled by default. Rejected because
the host explicitly retired it and the project forbids preserving bad shapes as
compatibility shims.

### 2. Retire both configuration routes as one automation

`TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID` was the original fallback and
`TINYASSETS_BUG_INVESTIGATION_GOAL_ID` selected the later canonical path. Both
still cause a platform-owned filing event to initiate user task work. The
implementation SHALL remove both rather than retaining the Goal route as a
renamed cheat loop.

Alternative considered: remove only the branch-definition fallback. Rejected
because the remaining Goal route would still be a privileged, host-configured
automation.

### 3. Preserve primitives, not the product-specific composition

Goal canonical resolution stays available to explicit callers. Generic
dispatcher/request admission, BranchTask execution, node enqueue, and wiki
writes also remain. A user-authored design may explicitly accept a filing-like
input, run a chosen graph, and publish an output through those public
capabilities, subject to normal identity, authority, and execution rules.

There is no automatic migration of existing environment configuration into a
new workflow. Operators remove the obsolete variables; users independently
choose whether to create or install a workflow.

### 4. Treat generated/plugin runtime as shipped product

The implementation is incomplete until the Claude plugin is rebuilt from the
clean source tree and its runtime contains none of the retired module, imports,
environment names, request-type special cases, trigger-receipt code, auto-ship
modules, actions, or status projection.
Source-only deletion with stale packaged copies is a failed removal.

### 5. Delete auto-ship composition while preserving generic effects

The auto-ship validator, PR creator, ledger, extension action registration,
configuration, and `auto_ship_health` status field SHALL be removed. A disabled
flag or read-only ledger is still a privileged product-specific shipping
composition. Generic packet evaluation and explicit GitHub-effect primitives
remain only where they are independently useful outside this retired loop.

Existing `auto_ship_attempts.jsonl` files are historical data. The runtime
SHALL stop reading, writing, or resetting them; deployment may archive or
delete them according to operator data-retention policy without adding a
runtime migration reader.

### 6. Split the read-only observer from the alarm sink

The useful health subset moves to a generically named
`scripts/platform_uptime_watch.py` plus
`.github/workflows/platform-uptime-watch.yml` under
`uptime-and-alarms`. The observer only reads public/API evidence, emits a
bounded generic evidence artifact/stdout result, and exits. It has no
repository/wiki/issue write credential or call. An independently owned alarm
sink may consume that output and use its narrow incident authority; it is not
part of the observer and cannot dispatch a workflow, repair, or user task.

Workflow permissions are job-scoped. The observer may have only the read
permissions required for checked evidence (`contents:read`, `actions:read`,
and metadata); it MUST NOT have `actions:write`, `contents:write`,
`pull-requests:write`, `issues:write`, or reusable/manual input capable of
enabling dispatch. A distinct sink job may have `issues:write` only if the
canonical incident owner requires it. No `community-loop` named executable,
workflow, label, artifact, or status field survives.

### 7. Remove website product presentation, not generic activity truth

The production React/Next website and retained Svelte rollback tree SHALL both
remove the `/patch-loop` product surface, checked-in
`community-loop-status.json`, community-loop workflow/label/issue fallbacks,
and fine-print branding. Both build and remain scan-clean before retirement;
this change does not delete the production tree or decide a framework
migration. `/patch-loop` becomes a truthful soft landing to generic
patterns/commons rather than a dead route or hidden compatibility application.

The `/loop` surface may remain only as a generic view of user-authored
workflow activity with explicit live/snapshot provenance. Platform uptime
evidence comes from the generic uptime observer/alarm contract and MUST NOT be
used as proof that a privileged task loop is moving.

### 8. Quarantine retired queued work before workers can claim it

Removing the direct executor is insufficient because the generic dispatcher
accepts otherwise unknown request classes. At upgrade, an idempotent
pre-worker migration SHALL atomically identify every v1/v2
`bug_investigation` row and trigger receipt. Pending/queued rows become
terminally refused or quarantined with an immutable retirement reason.

Claimed/running rows first become non-admissible and non-claimable. The
retirement coordinator then consumes the
`harden-background-provider-execution-authority` (#1803) authority-store-first
protocol before changing queue state:

- prove the old owner dead or atomically invalidate its execution-claim
  generation;
- with no reservation, produce the exact non-authorizing reconciliation proof;
- atomically cancel and release only a `reserved`-before-launch reservation;
- preserve consumed authority for conclusive `succeeded`/`failed` work; and
- convert a readable `launch_started` or `indeterminate` receipt to
  `fenced_indeterminate`, with no release, retry, resume, or inferred outcome;
  an unreadable authority store preserves the existing row/receipt and holds
  the retirement attempt without queue mutation.

Only after that authority transaction releases may the coordinator take the
queue lock and apply the existing-state transitions owned by
`daemon-runtime-and-dispatch`: conclusive rows exact-CAS to `cancelled`;
readable ambiguous work is not reset/terminalized and only its receipt is
fenced (v2 may additionally set its existing disabled/quarantine fields by
exact CAS); unreadable work receives no queue mutation. A concurrent heartbeat
or lease change makes the CAS fail and restarts reconciliation. Ambiguous work
remains non-runnable until authoritative evidence makes it conclusive, after
which retirement may finish without re-execution. Completed rows remain
immutable history and replay/read paths cannot resubmit them.

This retirement gate is the first *classification and admission* stage of the
startup/first-use boundary: #1803 SHALL NOT issue new authority for or sweep a
retired row as ordinary provider-capable/non-provider work. Its
authority-store reconciliation invariants remain the required sub-protocol
before queue terminalization, not a later blanket recovery pass.

After cutover, dispatcher admission and claim both fail closed on the retired
request class before branch-run or universe-cycle execution. No compatibility
consumer, generic reinterpretation, payload salvage, or automatic write-back
is permitted. Migration records counts, row identities/digests, prior/final
states, and retention action without deleting completed history.

### 9. Remove compatibility vocabulary and automatic filing routes

Product-only `auto_ship_ship_classes.yaml`, auto-ship modules/ledger/actions,
and community-loop merge-readiness classifier are deleted. Independently
useful coding-packet evaluation may remain only after removing the
`AUTO_SHIP_READY`, `APPROVE_AUTO_SHIP`, and `auto_shipped` aliases and
community-loop vocabulary; generic `KEEP_READY`, `APPROVE`, and ordinary
release evidence remain.

`file_bug` also stops publishing automatic dispatcher-facing fast-lane,
carrier-review, navigator-triage, or daemon-pickup claims. Delete
`classify_filing_effort`, `filing_effort_dispatch_route`, their product
constants/tokens, markdown/frontmatter/response fields, and behavior-pinning
tests rather than leaving a dormant policy helper. Ordinary filing fields,
per-kind duplicate detection, and explicitly submitted tags remain. Public
prompts, control-station copy, current exec plans/specs/milestones,
discoverable wiki plans, plugin mirrors, and behavior tests are updated or
clearly archived so no current guidance promises the retired loop.

The product-wired intake classifier also leaves.
`tinyassets.api.market.classify_patch_request` currently injects
`claimable_by=[free_daemon, paid_daemon]`,
`code_writer_gate=claude_or_codex`, and
`checker_gate=opposite_family_checker` into every submitted request, after
which `tinyassets.api.universe` persists and queues that classification. This
is the writer/checker team hidden in platform policy. Remove the classifier and
the persisted `request_classification` field; pending legacy metadata is
ignored/stripped rather than treated as authority. Rename the surviving
pickup-only boundary/normalizer constants away from patch-loop vocabulary.
Explicit requester incentives, directed-daemon assignments, and
soul-declared loop dispatch remain under their independent authority owners.

The hidden-but-dispatchable `community_change_context` product stack also
leaves in dependency order. This lane first removes both website wire callers
and proves no supported production/rollback site still calls the hidden name;
that releases the caller gate on `retire-legacy-live-mcp-tools`. That owner
then removes and rebuilds the exact six legacy MCP registrations under its
telemetry/host gates. After cutover, this lane removes the internal action and
action-map row, `_CHANGE_LOOP_PLAN_HEADINGS`, auto-change/auto-fix queue
aggregation, hard-coded Codex-writer/Claude-checker standard,
wrapper/plugin/tests, and leaves no internal compatibility dispatch. Generic
GitHub reads, PLAN reads, and graph composition remain available for a
user-authored review-context design.

The active `loop-uptime-maintenance` agent skill and its catalog routes are
retired, not left as an emergency backdoor. Its incident records may remain
only as clearly historical evidence outside an active skill package. Website
editing guidance is rewritten around generic provenance-labelled workflow
activity and separately sourced uptime evidence. Canonical `.agents/skills`
changes are mirrored into `.claude/skills` with the normal sync gate.

The push/deploy-triggered `announce-patch.yml` effect and repository-wide
`auto-enroll-merge.yml` standing merge instruction are deleted. Auto-enrollment
turns an authorized generic PR-create effect into eventual merge without the
separate merge capability, exact head SHA authorization, and receipt required
by the existing GitHub merge contract; branch checks do not supply that
missing authority. Future merge enrollment or public announcement must be an
explicitly selected user/maintainer workflow with its own narrow authority and
receipt. Generic PR-create, exact-head merge, and outbound-effect primitives
remain available. The patch announcement script leaves when it has no
independent explicit consumer.

Workflow deletion is not sufficient because GitHub persists auto-merge
enrollment on each pull request. The migrator first persists a write-ahead
receipt plus idempotency key, disables and verifies the live workflow, and
cancels/drains queued or running instances so no enrollment can race the
snapshot or zero check. It then snapshots every open auto-enrolled PR's
number/node id, exact head SHA/state/repository/draft tuple and full
`autoMergeRequest` fields (actor/time, merge method, commit fields) with
historical Actions/repository attribution evidence at `enabledAt`.
Current-source uniqueness is not enough because GitHub Actions workflows share
an actor identity.

Each disable requires a durably persisted per-PR intent and an immediate exact
tuple pre-read; because GitHub offers no expected-head CAS, changed tuples are
skipped for a fresh plan. Apply post-reads and persists outcomes, and restart
reconciles an already-disabled planned tuple under the same key. Explicit
user/maintainer enrollments remain untouched; ambiguous provenance is held for
host review. A final full open-PR rescan must prove the workflow remains
disabled/drained, the receipt is complete, and attributed plus ambiguous
counts are zero before workflow-file deletion.

Live GitHub labels are executable routing/status vocabulary, not harmless
documentation. Before apply, rollout disables/removes every retired-label
producer (including the community-loop watch workflow) and drains active runs.
It then paginates every definition and every open/closed issue/PR association
to exhaustion into a digest-bound migration receipt; removes the retired
labels from open items without closing them or rewriting their content;
publishes one repository-wide retirement notice linked to the receipt; then
deletes these 28 definitions:

`auto-bug`, `auto-change`, `auto-checker-dispatched`,
`auto-checker-failed`, `auto-fix-already-fixed`, `auto-fix-attempted`,
`auto-fix-auth-expired`, `auto-fix-auth-missing`, `auto-fix-blocked`,
`auto-fix-branch-push-blocked`, `auto-fix-claude-subscription-missing`,
`auto-fix-codex-subscription-missing`, `auto-fix-exhausted`,
`auto-fix-pr-blocked`, `auto-fix-provider-exhausted`,
`auto-fix-retries-1` through `auto-fix-retries-5`, `auto-fix-reviewed`,
`auto-fix-stale-gate`, `auto-fix-superseded`, `auto-fix-writer-failed`,
`community-loop-red`, `loop-consent`, `priority:loop-discipline`, and
`ready_for_checker`.

Closed item bodies remain historical; their former label association is
recoverable from the receipt after definition deletion. Generic labels remain,
including `daemon-request`, `request:*`, `payment:*`, `gate-required`,
`checker:*`, `writer:*`, `writer-pool:*`, `needs-human`,
`priority:primitive-*`, `patch_request`, `merge-effector`, and `secure-merge`.
The blank `patch_request` label remains only as generic filing/effect trace
vocabulary and has no workflow/runtime consumer; it does not preserve a hidden
request classifier or writer/checker route. No workflow, script, site fallback,
or runtime consumer may continue matching a retired label.

`ready_for_checker` is retired even though it has no current open association:
its live definition advertises the loop's source, duplicate, stale-base, and
scope-split pre-check policy, and its historical PR associations belong in the
same receipt.

Current loop-team souls and generated website snapshots are shipped prompt/data
surfaces, not archival truth. The six shipped `docs/souls` loop-role souls and
their core-team manifest are removed, and canonical/legacy snapshots are
regenerated so they cannot resurrect the retired branch, area, roles, or
automatic filing promise.

Task 2.5's claimed/running-row terminalization depends on the #1803 runtime
authority store and reconciliation protocol landing first. Retirement may
still land fail-closed admission, pending/queued quarantine, and unrelated
surface deletion before that dependency. Runtime replacement before #1803
requires all legacy workers quiesced and a locked preflight proving no retired
v1 `running` or v2 `running`/`cancel_requested` row. Otherwise an absent,
unimplemented, unavailable, or unreadable store takes the
unreadable-authority path: preserve row/receipt, perform no queue CAS or
release, and stop deployment until #1803 becomes authoritative.

## Risks / Trade-offs

- **Existing host configuration expects automatic investigations** -> Remove the
  variables from deployment and current runbooks in the same change; do not
  silently redirect them. Filing remains successful and explicit.
- **An obsolete external flag implies a dormant product loop** -> Delete the
  `AUTO_FIX_DISABLED` GitHub repository variable during rollout and record its
  absence. Never substitute another disabled/no-op flag.
- **Broad deletion accidentally damages generic execution** -> Keep canonical
  dispatcher and general queue tests, and add negative tests proving only the
  product-specific request type/path disappeared.
- **Stale generated plugin resurrects removed code** -> Rebuild the plugin, scan
  both source and package output, and test source/package parity.
- **Consumers call removed extension actions** -> Return the ordinary
  unknown-action behavior; do not retain aliases. Document that shipping is a
  user-built workflow composed from general effects.
- **Deleting the workflow leaves durable merge instructions behind** ->
  Receipt-snapshot open enrollments, disable only exact workflow-attributed
  tuples with pre/post reads, preserve explicit choices, and stop on ambiguous
  provenance rather than guessing.
- **Historical documents trigger false-positive scans** -> Limit zero-reference
  gates to shipped runtime, active deployment/configuration, current runbooks,
  plugin payloads, and executable tests. Historical artifacts may retain
  accurately labeled history.
- **Queued legacy `bug_investigation` rows exist at deployment** -> Fail closed
  at admission/claim, reconcile claimed/running authority under #1803 before
  queue CAS, preserve ambiguous work fenced without release, retain immutable
  completed history, and never add a compatibility consumer.

## Migration Plan

1. Add negative tests for `file_bug` side effects, filing-route classifiers,
   the community-context action, and absence of the retired
   configuration/request type in source and package output.
2. Remove the wiki trigger/receipt integration and the dedicated
   `bug_investigation` module and executor special cases.
3. Remove auto-ship modules, actions, ledger/reset/status integration,
   configuration, current docs, and behavior-pinning tests.
4. Rename the useful watch subset into a read-only generic uptime observer,
   separate it from the incident sink, least-privilege its workflow jobs, and
   remove workflow-dispatch self-heal.
5. Remove both production/rollback website `community_change_context` wire
   callers and prove the hidden-name caller gate is clear.
6. Let `retire-legacy-live-mcp-tools` complete its exact-six registration and
   packaged-mirror cutover, then remove the unreachable internal
   `community_change_context` stack without a compatibility action.
7. Remove environment/default/deploy/runbook references and update generic
   dispatcher/examples.
8. Remove website patch-loop/community-loop presentation, homepage narrative,
   legacy community-context callers, and snapshots from the production
   React/Next tree and retained Svelte rollback tree; retain only
   provenance-correct generic workflow activity, build both, and correct active
   website guidance that still reverses their deploy/rollback ownership.
9. Before workers or ordinary #1803 recovery start, activate fail-closed
   admission for the retired class, classify legacy rows, and reconcile any
   authority-store record under #1803's lock ordering. Apply only existing
   v1/v2 state/field transitions from the daemon-runtime delta; do not invent a
   retired/fenced task status. A pre-#1803 deployment must quiesce legacy
   workers and prove no claimed row or stop before runtime replacement.
10. Rebuild the Claude plugin and verify its runtime mirrors the clean source.
11. Run focused tests, full relevant suites, lint, plugin build/probe, and
   repository scans for shipped references.
12. Before deployment, inspect production for obsolete environment keys,
   migrated request/receipt evidence, auto-ship ledger/config state, and open
   auto-merge enrollments; disable only receipt-proven workflow enrollments and
   remove/archive the other retired state without executing it.
13. Deploy and run the normal public MCP, clean-clone, production deploy, and
   website deploy canaries. Verify `file_bug` in a rendered chatbot conversation
   files the page without an investigation/trigger side effect and `get_status`
   contains no cheat-specific health projection.
14. Fold canonical specs back explicitly rather than asking OpenSpec to create
   an invalid zero-requirement capability: apply the six non-retired
   capability deltas to their canonical specs, verify the nine
   `community-patch-loop` removal headings exactly match the nine remaining
   canonical requirements, physically delete
   `openspec/specs/community-patch-loop/`, and run strict validation. Archive
   this change with `openspec archive retire-cheat-loop --yes --skip-specs`
   only after tasks 0.1 through 6.6, every migration receipt, authority gate,
   and release proof are complete; task inspection MUST show exactly 6.7 still
   pending. A scoped working-tree/index diff proof SHALL then show only the six
   reviewed canonical updates, physical capability deletion, and this
   foldback's coordination edits, with no unrelated change. After archive,
   mark 6.7 complete in the archived task record, remove the STATUS row,
   strictly validate, and commit the entire foldback atomically. The archived
   delta remains the removal audit trail; `--skip-specs` prevents archive from
   aborting on, or resurrecting, an empty capability.

Rollback is by reverting the removal commit only if ordinary bug filing or
generic workflow execution regresses. The retired automation is not an
acceptable rollback target for loss of automatic investigation behavior.

## Open Questions

None for the target contract. Any future curated investigation workflow is an
ordinary commons design and requires its own user-facing OpenSpec change.

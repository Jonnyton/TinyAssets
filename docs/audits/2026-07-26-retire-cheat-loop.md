# Cheat-Loop Retirement Audit

**Date:** 2026-07-26
**Environment:** Windows worktree
`C:\Users\Jonathan\Projects\wf-retire-cheat-loop-current`, based on exact
`origin/main` `ba273312484d8717eaa12f2cd66e6629458aa36b`
**Finding:** current shipped source contradicts the host-approved architecture;
the cheat loop is disabled in some places but is not deleted from the build.
**Target:** `openspec/changes/retire-cheat-loop/`

## Decision

The retirement boundary is the entire privileged product composition, not only
the original branch-definition fallback:

1. hidden typed-filing trigger and receipt;
2. Goal-ID and branch-definition handler configuration;
3. dedicated `bug_investigation` queue/execution/write-back behavior;
4. auto-ship validator, PR action, ledger, status, and configuration;
5. community-loop named runtime, workflow, artifact, label, package, and test
   surfaces;
6. active loop skills, catalog routes, and shipped loop-team souls;
7. hard-coded patch-request and filing-effort
   claimant/writer/checker/triage composition;
8. hidden `community_change_context` product dispatch and website callers;
9. automatic patch-announcement and implicit auto-merge composition plus
   durable open-PR enrollments; and
10. generated website/plugin snapshots or prompts that can resurrect the
   retired behavior.

TinyAssets retains the domain-agnostic pieces from which a user may build these
outcomes: Goal canonicals, requests, BranchTasks, graph execution, node enqueue,
evaluation, explicit effects, and wiki operations. Task automations are
user-authored designs that can be published, copied, remixed, and combined.

The useful uptime/deploy/revert observer is not the cheat loop. It moves to the
`uptime-and-alarms` capability under generic names, loses workflow-dispatch
self-heal, and remains observational except for the canonical operational
alarm/incident sink.

## Evidence Commands

Freshness-stamped 2026-07-26:

```text
rg -n -i --glob '!openspec/changes/archive/**' "cheat[ _-]?loop|CHEAT_LOOP|cheatloop" .
rg -n "TINYASSETS_BUG_INVESTIGATION_(GOAL_ID|BRANCH_DEF_ID)|_maybe_enqueue_investigation|_resolve_investigation_handler|enqueue_investigation_request" .
rg -n -i "community[_ -]loop|auto[_ -]ship|TINYASSETS_AUTO_SHIP" tinyassets fantasy_daemon scripts .github deploy packaging/claude-plugin tests docs/ops
rg -n "bug_investigation|attach_patch_packet|trigger_receipt" tinyassets fantasy_daemon packaging/claude-plugin tests deploy .github docs/ops
rg -n "classify_patch_request|request_classification|code_writer_gate|checker_gate|claimable_by" tinyassets packaging/claude-plugin tests
rg -n "classify_filing_effort|filing_effort_dispatch_route|carrier-review-before-daemon-pickup|merge-instant-fast-lane|opposite-family-checker" tinyassets packaging/claude-plugin tests
rg -n "community_change_context|_CHANGE_LOOP_PLAN_HEADINGS|Codex-written PRs|latest auto-fix" tinyassets packaging/claude-plugin tests WebSite/site WebSite/site-react
rg -n -i "loop-uptime|community[_ -]loop|auto[_ -]fix|patch[_ -]loop" .agents/skills .claude/skills .github/workflows docs/souls WebSite/site/src/lib/content WebSite/site-react/lib
rg -n "auto-change loop" PLAN.md STATUS.md
gh variable list --repo Jonnyton/TinyAssets
gh label list --repo Jonnyton/TinyAssets --limit 300 --json name,description
gh issue list --repo Jonnyton/TinyAssets --state open --label <retired-label> --limit 1000 --json number
gh pr list --repo Jonnyton/TinyAssets --state open --limit 1000 --json id,number,headRefOid,isDraft,headRepository,baseRefName,state,autoMergeRequest
gh run list --repo Jonnyton/TinyAssets --workflow deploy-site-react.yml --limit 10 --json databaseId,status,conclusion,createdAt,headSha,url
openspec validate retire-cheat-loop --strict
```

The last command passed on 2026-07-26 after all proposal artifacts were
complete. These searches are diagnostic inventory, not proof of implementation;
the runtime is still unchanged in this target-only lane.

An engine-level read-only `buildUpdatedSpec` dry-run on 2026-07-26 parsed and
built all six surviving canonical deltas. The public-website result reported
`renamed=1, modified=2`, contained the renamed requirement, and replaced the
historical patch-loop/community-watch scenario. A separate parser comparison
proved the `community-patch-loop` delta's nine removed headings exactly equal
the canonical capability's nine requirements. The CLI's normal archive path
cannot validly write zero requirements, which is why the reviewed physical
delete plus `--skip-specs` procedure is load-bearing.

The authenticated repository-variable read on 2026-07-26 returned
`AUTO_FIX_DISABLED=true` (last updated 2026-06-06) and
`WORKOS_REQUIRE_AUTH=0`; only the former belongs to this retirement.

The authenticated label/open-item read on 2026-07-26 found 28 live
product-loop definitions: `auto-bug`, `auto-change`, two `auto-checker-*`,
twenty `auto-fix-*`, `community-loop-red`, `loop-consent`, and
`priority:loop-discipline`, plus `ready_for_checker`, whose live description
still promises loop PR pre-checks and whose historical PR associations must be
receipt-preserved (292 PR associations, zero open issues). Representative
open-issue counts were
`auto-bug=40`, `auto-change=213`, `auto-fix-attempted=185`, and
`priority:loop-discipline=42`; `community-loop-red` and `loop-consent` had zero
open issues. These are active external routing/status claims, not merely
historical source vocabulary.

## Current Shipped Consumers

### Filing intake and receipt

| Surface | Current behavior | Retirement |
|---|---|---|
| `tinyassets/api/wiki.py:2430-2570` | `file_bug` imports `bug_investigation` and `trigger_receipts`, creates a pending receipt, reads a retired env key, enqueues, appends `## Investigation`, and returns `investigation`/`trigger` blocks | Remove the entire post-filing automation block; filing returns filing metadata only |
| `tinyassets/wiki/trigger_receipts.py` | Dedicated mutable receipt store for the filed-page auto-trigger | Delete when the filing trigger is removed |
| `tinyassets/bug_investigation.py` | Product module for payload mapping, request creation, handler selection, comment formatting, and Patch Packet wiki mutation | Delete, not disable |
| `tinyassets/api/wiki.py:2343-2453,2572-2576` | Filing also publishes fast-lane, carrier-review, navigator-triage, and daemon-pickup claims even without proving a separate route owner | Remove automatic routing/triage claims; preserve only inert independently owned filing-incentive metadata |

Both handler routes are the same retired automation:

- `TINYASSETS_BUG_INVESTIGATION_GOAL_ID`
- `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID`

Keeping the Goal route while deleting only the branch-definition fallback would
leave a host-configured product loop and would not satisfy the directive.

The filing path also imports `classify_filing_effort` and
`filing_effort_dispatch_route` from `tinyassets/api/market.py:238-379`. Those
helpers publish `carrier-review-before-daemon-pickup`,
`merge-instant-fast-lane`, navigator/daemon pickup policy, and
`opposite-family-checker` semantics into filing markdown, frontmatter, and the
response. They leave with their constants and behavior-pinning tests. Ordinary
filing fields and per-kind duplicate detection remain.

### Hidden patch-request composition

| Surface | Current behavior | Retirement |
|---|---|---|
| `tinyassets/api/market.py:202-235` | `classify_patch_request` injects free/paid daemon claimants, a Claude/Codex writer gate, and an opposite-family checker gate | Delete the classifier; ordinary request submission does not choose a platform writer/checker team |
| `tinyassets/api/universe.py:2157-2174` | Persists `request_classification` into submitted requests/tasks | Stop writing it and ignore/strip pending legacy metadata as non-authorizing residue |
| `tinyassets/work_targets.py:546-553` | Copies the hidden classification into downstream targets | Remove the propagation while preserving explicitly authorized generic routing inputs |
| pickup and soul dispatch | Explicit requester incentives, directed-daemon selection, `_universe_loop_dispatch`, `TINYASSETS_SOUL_LOOP_DISPATCH`, and a user soul's `loop_branch_def_id` | Preserve as bounded user-authored routing under their existing authority owners; none grants provider, credential, effect, release, or merge authority |

### Hidden community-change context

`tinyassets/universe_server.py:1305-1346` still registers the hidden legacy
`community_change_context` wrapper, while
`tinyassets/api/universe.py:3227-3420+` retains the internal product action,
plan-heading policy, auto-change/auto-fix queue aggregation, and hard-coded
"Codex-written -> Claude-family checker" standard. The package mirror and
tests pin it; `WebSite/site/src/lib/mcp/live.ts` and
`WebSite/site-react/lib/live.ts` still call it.

This lane first removes both website wire callers, which unblocks the
`retire-legacy-live-mcp-tools` exact-six hidden MCP registration cutover. After
that owner's tasks 4.1/4.4 remove/rebuild the hidden registration, this lane
deletes the internal action, action-map row, wrapper/plugin behavior, and tests
rather than preserving a dispatchable compatibility path. Generic GitHub
reads, PLAN reads, and graph composition remain for user-authored
review-context workflows.

### Dedicated execution behavior

`fantasy_daemon/__main__.py:789-865,941,1004` treats
`bug_investigation` as a direct-execution request, synthesizes a legacy payload,
recursively recovers several Patch Packet shapes, and writes the result back to
the wiki. This is not generic completed-run reuse. The retirement removes the
request-type and packet/write-back special cases while preserving ordinary
BranchTask run reuse.

Additional active references include:

- `tinyassets/dispatcher.py:126` request-priority example;
- `tinyassets/graph_compiler.py:1632` direct-execution commentary;
- `tinyassets/api/canonical_dispatch.py` historical integration prose (the
  generic canonical resolver itself remains);
- `deploy/cloud-daemon-settings.json` request priority and safety-net comment;
- `.github/workflows/deploy-prod.yml:619` production env installation;
- `docs/ops/post-redeploy-validation-runbook.md` current setup and validation
instructions.

The generic dispatcher currently accepts arbitrary request classes when no
priority allow-list is present. Therefore deleting the direct-execution branch
alone is unsafe: pending or lease-recovered `bug_investigation` rows could fall
into an ordinary universe cycle. The cutover must run an idempotent pre-worker
migration that terminally refuses/quarantines pending rows, denies the class at
admission/claim, and handles claimed/running
rows only through #1803's authority proof plus existing queue states. Readable
ambiguous work is fenced without reset; unreadable work is not queue-mutated.
Completed history remains immutable and no generic reinterpretation or replay
execution is allowed.

Current `origin/main` also carries
`harden-background-provider-execution-authority` (#1803), whose graph delta
adds a lazy first-use recovery coordinator and provider-authority
reconciliation. Retirement must first make the class non-admissible and
non-claimable, but must not blanket-cancel or terminalize a running row before
consulting the authority ledger. Its migration consumes #1803's
authority-store-first protocol: prove death or invalidate the claim generation;
release only `reserved`-before-launch authority; preserve conclusive consumed
authority; fence readable `launch_started`/`indeterminate` state without
release or retry; preserve and hold on unreadable authority without queue
mutation; then queue-CAS the exact task/claim/lease generation only after a
successful reconciliation proof. #1803 must never issue new authority for,
resume, or sweep the retired class as ordinary work.

Current source does not yet implement #1803's `ProviderWorkAuthorityStore`.
Therefore the implementation lane may land fail-closed admission,
pending/queued quarantine, and other surface deletion, but it cannot
terminalize a claimed/running legacy row until #1803 lands. Runtime replacement
before #1803 is allowed only after every legacy worker is quiesced and a locked
preflight proves no retired v1 `running` or v2
`running`/`cancel_requested` row. Otherwise the absent/unimplemented store is
the unreadable-authority hold: preserve row/receipt, perform no queue CAS or
release, and stop deployment.

### Auto-ship composition

The following are executable product-loop modules, not generic primitives:

- `tinyassets/auto_ship.py`
- `tinyassets/auto_ship_pr.py`
- `tinyassets/auto_ship_ledger.py`
- `tinyassets/api/auto_ship_actions.py`

They are wired into shipped behavior through:

- `tinyassets/api/extensions.py:54,625-649`
- `tinyassets/auth/provider.py:401,487,555,583`
- `tinyassets/api/status.py:120-388,1390-1442`
- `tinyassets/scoped_reset.py:134`
- `deploy/compose.yml:65-72`
- `deploy/tinyassets-env.template:98-111`
- `deploy/DEPLOY.md:368,420-421`
- `scripts/droplet.py:8,19,96,112`

The public extension actions are `validate_ship_packet` and
`open_auto_ship_pr`; the public status residue is `auto_ship_health`. All leave.
The `get_status` handle remains. Existing `auto_ship_attempts.jsonl` files become
historical operator data; the runtime receives no compatibility reader.

The live GitHub repository also retains the external
`AUTO_FIX_DISABLED` variable. A disabled flag still advertises a dormant
platform product, so rollout deletes the variable and records its absence.
Current generic provider-chain diagnostics in `tinyassets/graph_compiler.py`,
its generated plugin mirror, and their behavior tests still promise visibility
to an "auto-fix loop"; those references are rewritten to name only their
independent consumers (for example chatbots and run events). Website
`auto-fix` queue/label fallbacks leave with the retired presentation. Generic
mojibake auto-fix tooling and accurately historical documents are unrelated.
The current universe guidance string and provider-source/plugin comments that
describe "latest auto-fix runs" or credentials "used by auto-fix" are also
rewritten around their actual generic diagnostic consumers.

### Active agent and repository automations

The retirement scan must include active control-plane instructions, not just
Python runtime:

- `.agents/skills/loop-uptime-maintenance/` and its `.claude` mirror instruct
  agents to drive `chatbot -> file_bug -> loop investigates -> ships`, create
  synthetic filing canaries, and write new incidents under the active skill;
- `using-agent-skills` routes agents into that loop skill, while
  `website-editing` treats a GitHub community-loop monitor as a live fallback;
- `.github/workflows/announce-patch.yml` automatically reacts to main/deploy
  events and contains an outbound X-post path; its configured
  `scripts/social/patch_announcement.py` path is already stale relative to the
  shipped `scripts/patch_announcement.py`.

These are privileged compositions, not generic primitives. The active loop
skill/catalog routes, automatic patch-announcement workflow, and orphaned
patch-announcement script leave. Historical incident records may remain only
outside an active skill package with explicit historical labeling.

`.github/workflows/auto-enroll-merge.yml` also leaves. It makes auto-merge the
default for every eligible same-repository PR to `main`, so a generic
PR-creation effect can acquire eventual merge without the separately required
merge capability, exact head SHA authorization, and receipt. Current branch
protection checks do not restore that missing authority boundary. Generic
PR-create and exact-head merge effects remain separately available to an
explicit user/maintainer workflow.

An authenticated GraphQL read on 2026-07-26 found 21 open pull requests with
auto-merge still enabled, all by `app/github-actions`. GitHub persists those
instructions on the PR, so deleting the workflow would not revoke them.
Rollout snapshots each open enrollment's PR/node/head/state/repositories/draft,
full auto-merge request, and historical attribution evidence into a
digest-bound write-ahead receipt under an idempotency key. Before inventory or
mutation, apply disables/verifies the live workflow and cancels/drains active
runs. The repository scan found this workflow is the sole current
`gh pr merge --auto` source, while historical Actions evidence at each
`enabledAt` supplies attribution because the GitHub Actions actor is shared.
Apply persists each per-PR intent, re-reads the exact tuple, disables only
attributed enrollments, post-reads/persists the outcome, and reconciles
already-disabled planned tuples after a crash. It preserves explicit
user/maintainer enrollments and holds ambiguous provenance for host review.
Workflow deletion requires a final full rescan, complete receipt,
disabled/drained workflow, and zero attributed or ambiguous open enrollments.

### Live GitHub label migration

Before deleting label definitions, implementation snapshots the exact
definition plus every fully paginated open/closed issue and PR association into
a digest-bound, idempotent migration receipt. Fresh inventory observed 693 open
issue, 783 closed issue, and 485 closed PR retired-label associations in
aggregate, so pagination is a release condition. Before apply, every producer
is disabled/removed and active runs are drained; at minimum the
`community-loop-watch` replacement in task 4.2 must land first because the old
workflow can recreate `community-loop-red`. Apply removes retired labels from
open items without closing them or changing their bodies, publishes one
repository-wide retirement notice linked to the receipt, and then deletes the
28 definitions. Closed bodies remain historical and the receipt preserves
their former association.

The preserved generic vocabulary includes `daemon-request`, `request:*`,
`payment:*`, `gate-required`, `checker:*`, `writer:*`, `writer-pool:*`,
`needs-human`, `priority:primitive-*`, `merge-effector`, and `secure-merge`.
After rollout, no workflow, script, website fallback, runtime, or active skill
may consume a retired label.

The blank `patch_request` label is explicitly preserved as generic filing/effect
trace vocabulary, not a loop route: the live repository has one closed request
issue and its merged exact-head merge-effector PR bearing it, and the current
source scan finds no workflow or runtime consumer. This does not preserve the
removed `request_classification` policy or any automatic writer/checker route.

### Shipped prompt and snapshot residues

`docs/souls/community-loop-core-team-v1.md` and the Ada, Elias, Mira, Noor,
Soren, and Vera loop-role souls are active prompt assets and leave. Generated
canonical/legacy website snapshots also retain the patch-loop area, automatic
post-`file_bug` branch promise, and retired tags:

- `WebSite/site/src/lib/content/mcp-snapshot.json`
- `WebSite/site/src/lib/content/repo-snapshot.json`
- `WebSite/site-react/lib/mcp-snapshot.json`

They are regenerated from the clean source or removed with an unshipped mirror;
checked-in generated data cannot serve as a compatibility backdoor.

Generic evaluation code or explicit GitHub-effect authority may remain only
where it has an independent owner and does not preserve an auto-ship action,
ledger, flag, or implicit composition.

Additional active compatibility/product residue has an exact disposition:

| Surface | Retirement |
|---|---|
| `auto_ship_ship_classes.yaml` | Delete the product-only ship classifier configuration |
| `tinyassets/coding_packet_rubric.py` | Remove `AUTO_SHIP_READY`, `APPROVE_AUTO_SHIP`, and `auto_shipped`; retain generic `KEEP_READY`/`APPROVE` rubric behavior only |
| `tinyassets/evaluation/coding_process.py` | Remove auto-ship wording while retaining independently useful trajectory evaluation |
| `tinyassets/providers/codex_provider.py` | Remove auto-fix product wording while retaining generic provider invocation behavior |
| `scripts/merge_readiness.py` | Remove the community-loop classifier/branding; retain only if renamed and proven independently useful as a generic read-only PR classifier |
| `scripts/post_x_update.py` | Preserve only as an explicitly invoked generic outbound primitive after removing patch-announcement/product-loop wording |
| `tinyassets/effectors/validate_patch.py` | Preserve the explicit validation primitive while removing TinyAssets/"our loop" product-composition comments |
| `tinyassets/api/prompts.py`, `tinyassets/universe_server.py` | Remove current community-loop promises/triage wording without broadening public tools |
| `docs/ops/bot-identity-setup.md` | Rewrite current product-bot/community-loop and automatic-merge guidance around explicit user/maintainer workflow authority |
| `docs/exec-plans/active/2026-04-25-file-bug-wiring.md`, current auto-ship specs/milestones, `pages/plans/` | Archive or rewrite current/discoverable guidance so it cannot be mistaken for a live supported product |
| corresponding tests and plugin mirrors | Rewrite for generic behavior or delete with the retired surface |

`CLAUDE.md` may continue documenting an explicit human/agent-selected
`gh pr merge --auto` command as a user/maintainer choice; it is not the
repository-wide standing workflow and does not bypass the separate merge
authorization decision.

### Named community-loop watch

The useful subset of `scripts/community_loop_watch.py` reads public GitHub
evidence for:

- public MCP observation freshness;
- P0 outage incidents;
- Tier-3 clean-clone smoke;
- production and website deploys;
- recent revert rate.

However, `.github/workflows/community-loop-watch.yml:212-218` dispatches the
watch workflow again as a self-heal follow-up. That is not purely observational.
The workflow also ships community-loop names in its filename, display name,
concurrency group, label, JSON artifact, incident title, and tests.

The successor is split:

- `scripts/platform_uptime_watch.py`;
- `.github/workflows/platform-uptime-watch.yml`;
- generic uptime/alarm label and evidence artifact names;
- a read-only observer job with only `contents:read`, `actions:read`, and
  metadata, no write or dispatch permission/input, which emits bounded
  evidence and exits;
- a distinct canonical alarm/incident sink consumer that may have narrowly
  scoped `issues:write` but no actions/content/PR write, workflow dispatch,
  repair, or user-task authority.

This behavior belongs in `uptime-and-alarms`. No executable or build artifact
named `community-loop` survives.

### Public website presentation

The current production React/Next site and retained Svelte rollback source both
expose the retired product. Fresh GitHub evidence on 2026-07-26 shows five
successful `deploy-site-react` runs (latest 2026-06-27); the current workflow
deployment chronology and `deploy-site.yml` identify React as live and Svelte
as dispatch-only rollback. The `deploy-site-react.yml` header, older cutover
runbook, and website skill still say React is not live and must be corrected.

- `WebSite/site/src/lib/mcp/live.ts` reads
  `community-loop-watch.yml`, community-loop labels/issues, and
  `/community-loop-status.json`, and calls `community_change_context`;
- `WebSite/site/static/community-loop-status.json` is a checked-in product
  snapshot;
- `WebSite/site/src/lib/components/ChatDemo.svelte` narrates the privileged
  file-to-daemon-to-gates-to-live loop on the homepage;
- `WebSite/site/src/routes/fine-print/+page.svelte` names the workflow;
- `WebSite/site-react/lib/live.ts` calls `community_change_context`, and its
  fine print mirrors the same shape;
- canonical site requirements name `/patch-loop` and the community-watch
  fallback.

The migration removes the patch-loop application and fallback data from both
trees, makes `/patch-loop` a static soft landing to user-authored
patterns/commons, and keeps `/loop` only as provenance-labeled generic workflow
activity. Generic platform uptime evidence remains a separate observation and
never proves that task work is moving. Both the deployed React tree and Svelte
rollback tree must build and pass the same absence scan; this retirement does
not delete the live React source or decide a new framework migration.

### Plugin payload

The Claude plugin runtime currently mirrors at least:

- `runtime/tinyassets/bug_investigation.py`;
- `runtime/tinyassets/wiki/trigger_receipts.py`;
- `runtime/tinyassets/api/wiki.py` trigger wiring;
- `runtime/tinyassets/auto_ship.py`;
- `runtime/tinyassets/auto_ship_pr.py`;
- `runtime/tinyassets/auto_ship_ledger.py`;
- `runtime/tinyassets/api/auto_ship_actions.py`;
- auto-ship extension/auth/status wiring and cheat-specific comments.

Source deletion without a clean plugin rebuild leaves the retired build
available to Tier-2/Tier-3 installs. Package scans and source/package parity are
therefore release gates.

## Tests That Pin Retired Behavior

The implementation must delete or rewrite behavior-positive tests, including:

- `tests/test_bug_investigation.py`
- `tests/test_bug_investigation_flow.py`
- `tests/test_bug_investigation_wiring.py`
- `tests/test_bug_investigation_dispatcher.py`
- `tests/test_bug_investigation_canonical_cutover.py`
- `tests/test_wiki_trigger_receipts.py`
- `tests/test_auto_ship.py`
- `tests/test_auto_ship_pr.py`
- `tests/test_auto_ship_ledger.py`
- `tests/test_auto_ship_health_status.py`
- `tests/test_validate_ship_packet_action.py`
- `tests/test_auto_ship_ship_classes_config.py`
- auto-ship alias cases in `tests/test_coding_packet_rubric.py`
- `tests/test_merge_readiness.py` community-loop branding/assumptions
- filing-effort route cases in `tests/test_wiki_tools.py` and related filing
  suites
- `tests/test_api_universe.py` and metadata/docstring tests that pin
  `community_change_context`
- auto-ship cases in `tests/test_universe_server_isolation.py`,
  `tests/test_api_status.py`, and reset/config tests
- `tests/test_community_loop_watch.py`
- `tests/test_community_loop_watch_workflow.py`
- website live/fine-print/static/build tests in canonical site and any retained
  React mirror

Replacement tests assert absence and preserve unrelated contracts:

1. `file_bug` creates no task/receipt/run/write-back, filing-effort
   classification, or automatic dispatcher/triage route even with stale env
   keys;
2. retired actions, including `community_change_context`, receive ordinary
   unknown-action behavior after the legacy-registration cutover;
3. `get_status` works without `auto_ship_health`;
4. generic canonical execution, dispatcher, completed-run reuse, evaluation,
   effects, and wiki writes still work;
5. queued/running retired rows are migrated/fenced before workers and completed
   history remains non-executable;
6. the generic observer has no write/dispatch credentials or calls; the alarm
   sink is independently least-privileged;
7. the auto-merge migrator preserves explicit enrollments and proves no
   workflow-owned open enrollment remains;
8. site routes/data/fine print/homepage expose no privileged patch/community
   loop or retired context caller;
9. source, active config/specs/plans/wiki guidance, websites, executable tests,
   workflows, and plugin output contain no retired shipped references.

Historical design notes and audits may retain accurately labeled history. They
must not be used as active configuration or current runbooks, and scan tests
must distinguish history from shipped surfaces.

## OpenSpec Disposition

The target modifies seven capabilities:

- `community-patch-loop`: all nine as-built requirements are removed, then the
  main capability is physically deleted. OpenSpec rejects an empty capability,
  so the reviewed foldback procedure explicitly applies the six surviving
  canonical deltas, verifies the exact nine-heading removal set, deletes the
  canonical directory, strictly validates, and archives with `--skip-specs`;
  normal archive sync is forbidden because it aborts or would recreate an empty
  skeleton;
- `daemon-runtime-and-dispatch`: owns exact v1/v2 retirement transitions,
  #1803 reconciliation ordering, and pre-#1803 worker quiescence/deploy stop;
- `development-coordination-runtime`: owns receipt-backed retirement of live
  GitHub routing/status labels and standing workflow auto-merge enrollments
  without losing open work, explicit choices, or generic labels;
- `graph-execution-substrate`: gains the explicit user-authored composition
  boundary, deletes the product community-context action after its
  legacy-registration dependency, and preserves generic run reuse without
  implicit write-back;
- `wiki-commons`: loses trigger receipts and all derived filing-effort routing,
  and makes typed filing side-effect boundaries explicit;
- `uptime-and-alarms`: gains the generic read-only observation successor.
- `public-website-surface`: removes the privileged patch-loop route/status
  fallback from the React production and Svelte rollback trees, corrects their
  deployment ownership, and keeps only provenance-correct generic
  workflow/uptime truth.

There is no new product capability, compatibility period, replacement loop, or
runtime alias.

## Release Gates

Implementation is not complete until all of the following are fresh and green:

1. focused runtime/config/workflow/plugin tests and ruff;
2. plugin rebuild/probe plus source/package absence scan;
3. strict validation of this change and all OpenSpec;
4. production env/queue/receipt/ledger quarantine and cleanup evidence;
5. `retire-legacy-live-mcp-tools` task 4.1 cutover evidence plus absence of the
   internal `community_change_context` action/callers;
6. receipt-backed live-label and auto-merge enrollment migrations, with zero
   workflow-owned open enrollment and no hidden ambiguity;
7. rendered chatbot `ui-test` through `https://tinyassets.io/mcp` proving
   filing-only behavior and absence of the status projection;
8. canonical website plus any retained mirror build/absence evidence and normal
   public MCP, Tier-3 clone, production deploy, and website deploy observation;
9. post-fix real-user evidence, or an explicit short watch item if none exists.

This audit authorizes no runtime edit. It records the verified target boundary
for the later claimed implementation slice.

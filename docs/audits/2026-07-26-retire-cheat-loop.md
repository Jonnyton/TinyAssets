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
7. automatic patch-announcement composition; and
8. generated website/plugin snapshots or prompts that can resurrect the
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
rg -n -i "loop-uptime|community[_ -]loop|auto[_ -]fix|patch[_ -]loop" .agents/skills .claude/skills .github/workflows docs/souls WebSite/site/src/lib/content WebSite/site-react/lib
gh variable list --repo Jonnyton/TinyAssets
gh label list --repo Jonnyton/TinyAssets --limit 300 --json name,description
gh issue list --repo Jonnyton/TinyAssets --state open --label <retired-label> --limit 1000 --json number
openspec validate retire-cheat-loop --strict
```

The last command passed on 2026-07-26 after all proposal artifacts were
complete. These searches are diagnostic inventory, not proof of implementation;
the runtime is still unchanged in this target-only lane.

The authenticated repository-variable read on 2026-07-26 returned
`AUTO_FIX_DISABLED=true` (last updated 2026-06-06) and
`WORKOS_REQUIRE_AUTH=0`; only the former belongs to this retirement.

The authenticated label/open-item read on 2026-07-26 found 27 live
product-loop definitions: `auto-bug`, `auto-change`, two `auto-checker-*`,
twenty `auto-fix-*`, `community-loop-red`, `loop-consent`, and
`priority:loop-discipline`. Representative open-issue counts were
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

`.github/workflows/auto-enroll-merge.yml` is separately classified and remains.
It is repository-maintainer integration guarded to non-draft same-repository
PRs targeting `main`, with branch protection and required checks as the merge
policy. It does not consume universe/task/graph state and does not install
implicit merge authority into a generic GitHub effect. Generic
`allow_auto_merge` and merge-effector inputs remain explicit.

### Live GitHub label migration

Before deleting label definitions, implementation snapshots the exact
definition plus every open/closed issue and PR association into a
digest-bound, idempotent migration receipt. It removes retired labels from open
items without closing them or changing their bodies, publishes one
repository-wide retirement notice linked to the receipt, and then deletes the
27 definitions. Closed bodies remain historical and the receipt preserves
their former association.

The preserved generic vocabulary includes `daemon-request`, `request:*`,
`payment:*`, `gate-required`, `checker:*`, `writer:*`, `writer-pool:*`,
`needs-human`, `priority:primitive-*`, `merge-effector`, and `secure-merge`.
After rollout, no workflow, script, website fallback, runtime, or active skill
may consume a retired label.

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
| `scripts/merge_readiness.py` | Remove the community-loop classifier/branding; retain only if renamed and proven independently useful as a generic read-only PR classifier |
| `tinyassets/api/prompts.py`, `tinyassets/universe_server.py` | Remove current community-loop promises/triage wording without broadening public tools |
| `docs/exec-plans/active/2026-04-25-file-bug-wiring.md`, current auto-ship specs/milestones, `pages/plans/` | Archive or rewrite current/discoverable guidance so it cannot be mistaken for a live supported product |
| corresponding tests and plugin mirrors | Rewrite for generic behavior or delete with the retired surface |

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

Canonical `public-website-surface` truth and shipped website code still expose
the retired product:

- `WebSite/site/src/lib/mcp/live.ts` reads
  `community-loop-watch.yml`, community-loop labels/issues, and
  `/community-loop-status.json`;
- `WebSite/site/static/community-loop-status.json` is a checked-in product
  snapshot;
- `WebSite/site/src/routes/fine-print/+page.svelte` names the workflow;
- `WebSite/site-react/lib/live.ts` and its fine print mirror the same shape;
- canonical site requirements name `/patch-loop` and the community-watch
  fallback.

The migration removes the patch-loop application and fallback data, makes
`/patch-loop` a static soft landing to user-authored patterns/commons, and
keeps `/loop` only as provenance-labeled generic workflow activity. Generic
platform uptime evidence remains a separate observation and never proves that
task work is moving. A non-shipped React mirror is deleted; a retained mirror
must build and pass the same absence scan.

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
- auto-ship cases in `tests/test_universe_server_isolation.py`,
  `tests/test_api_status.py`, and reset/config tests
- `tests/test_community_loop_watch.py`
- `tests/test_community_loop_watch_workflow.py`
- website live/fine-print/static/build tests in canonical site and any retained
  React mirror

Replacement tests assert absence and preserve unrelated contracts:

1. `file_bug` creates no task/receipt/run/write-back or automatic
   dispatcher/triage route even with stale env keys;
2. retired actions receive ordinary unknown-action behavior;
3. `get_status` works without `auto_ship_health`;
4. generic canonical execution, dispatcher, completed-run reuse, evaluation,
   effects, and wiki writes still work;
5. queued/running retired rows are migrated/fenced before workers and completed
   history remains non-executable;
6. the generic observer has no write/dispatch credentials or calls; the alarm
   sink is independently least-privileged;
7. site routes/data/fine print expose no privileged patch/community loop;
8. source, active config/specs/plans/wiki guidance, websites, executable tests,
   workflows, and plugin output contain no retired shipped references.

Historical design notes and audits may retain accurately labeled history. They
must not be used as active configuration or current runbooks, and scan tests
must distinguish history from shipped surfaces.

## OpenSpec Disposition

The target modifies seven capabilities:

- `community-patch-loop`: all nine as-built requirements are removed, then the
  empty main capability is deleted;
- `daemon-runtime-and-dispatch`: owns exact v1/v2 retirement transitions,
  #1803 reconciliation ordering, and pre-#1803 worker quiescence/deploy stop;
- `development-coordination-runtime`: owns receipt-backed retirement of live
  GitHub routing/status labels without losing open work or generic labels;
- `graph-execution-substrate`: gains the explicit user-authored composition
  boundary and preserves generic run reuse without implicit write-back;
- `wiki-commons`: loses trigger receipts and makes typed filing side-effect
  boundaries explicit;
- `uptime-and-alarms`: gains the generic read-only observation successor.
- `public-website-surface`: removes the privileged patch-loop route/status
  fallback and keeps only provenance-correct generic workflow/uptime truth.

There is no new product capability, compatibility period, replacement loop, or
runtime alias.

## Release Gates

Implementation is not complete until all of the following are fresh and green:

1. focused runtime/config/workflow/plugin tests and ruff;
2. plugin rebuild/probe plus source/package absence scan;
3. strict validation of this change and all OpenSpec;
4. production env/queue/receipt/ledger quarantine and cleanup evidence;
5. rendered chatbot `ui-test` through `https://tinyassets.io/mcp` proving
   filing-only behavior and absence of the status projection;
6. canonical website plus any retained mirror build/absence evidence and normal
   public MCP, Tier-3 clone, production deploy, and website deploy observation;
7. post-fix real-user evidence, or an explicit short watch item if none exists.

This audit authorizes no runtime edit. It records the verified target boundary
for the later claimed implementation slice.

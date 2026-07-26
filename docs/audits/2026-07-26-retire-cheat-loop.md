# Cheat-Loop Retirement Audit

**Date:** 2026-07-26  
**Environment:** Windows worktree
`C:\Users\Jonathan\Projects\wf-retire-cheat-loop-final`, based on
`origin/main` at lane creation  
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
   surfaces.

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
openspec validate retire-cheat-loop --strict
```

The last command passed on 2026-07-26 after all proposal artifacts were
complete. These searches are diagnostic inventory, not proof of implementation;
the runtime is still unchanged in this target-only lane.

## Current Shipped Consumers

### Filing intake and receipt

| Surface | Current behavior | Retirement |
|---|---|---|
| `tinyassets/api/wiki.py:2430-2570` | `file_bug` imports `bug_investigation` and `trigger_receipts`, creates a pending receipt, reads a retired env key, enqueues, appends `## Investigation`, and returns `investigation`/`trigger` blocks | Remove the entire post-filing automation block; filing returns filing metadata only |
| `tinyassets/wiki/trigger_receipts.py` | Dedicated mutable receipt store for the filed-page auto-trigger | Delete when the filing trigger is removed |
| `tinyassets/bug_investigation.py` | Product module for payload mapping, request creation, handler selection, comment formatting, and Patch Packet wiki mutation | Delete, not disable |

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

Generic evaluation code or explicit GitHub-effect authority may remain only
where it has an independent owner and does not preserve an auto-ship action,
ledger, flag, or implicit composition.

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

The successor is:

- `scripts/platform_uptime_watch.py`;
- `.github/workflows/platform-uptime-watch.yml`;
- generic uptime/alarm label and evidence artifact names;
- no workflow/task dispatch or repair;
- the existing canonical alarm/incident sink for reporting red/green state.

This behavior belongs in `uptime-and-alarms`. No executable or build artifact
named `community-loop` survives.

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
- auto-ship cases in `tests/test_universe_server_isolation.py`,
  `tests/test_api_status.py`, and reset/config tests
- `tests/test_community_loop_watch.py`
- `tests/test_community_loop_watch_workflow.py`

Replacement tests assert absence and preserve unrelated contracts:

1. `file_bug` creates no task/receipt/run/write-back side effect even with stale
   env keys;
2. retired actions receive ordinary unknown-action behavior;
3. `get_status` works without `auto_ship_health`;
4. generic canonical execution, dispatcher, completed-run reuse, evaluation,
   effects, and wiki writes still work;
5. the generic uptime observer never dispatches a workflow/task or performs a
   repair;
6. source, active config, current runbooks, executable tests, workflows, and
   plugin output contain no retired shipped references.

Historical design notes and audits may retain accurately labeled history. They
must not be used as active configuration or current runbooks, and scan tests
must distinguish history from shipped surfaces.

## OpenSpec Disposition

The target modifies four capabilities:

- `community-patch-loop`: all nine as-built requirements are removed, then the
  empty main capability is deleted;
- `graph-execution-substrate`: gains the explicit user-authored composition
  boundary and preserves generic run reuse without implicit write-back;
- `wiki-commons`: loses trigger receipts and makes typed filing side-effect
  boundaries explicit;
- `uptime-and-alarms`: gains the generic read-only observation successor.

There is no new product capability, compatibility period, replacement loop, or
runtime alias.

## Release Gates

Implementation is not complete until all of the following are fresh and green:

1. focused runtime/config/workflow/plugin tests and ruff;
2. plugin rebuild/probe plus source/package absence scan;
3. strict validation of this change and all OpenSpec;
4. production env/queue/ledger cleanup evidence;
5. rendered chatbot `ui-test` through `https://tinyassets.io/mcp` proving
   filing-only behavior and absence of the status projection;
6. normal public MCP, Tier-3 clone, production deploy, and website deploy
   observation;
7. post-fix real-user evidence, or an explicit short watch item if none exists.

This audit authorizes no runtime edit. It records the verified target boundary
for the later claimed implementation slice.

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
- Make `file_bug` a filing operation with no hidden task, receipt, run, or
  write-back side effect.
- Remove dedicated `bug_investigation` handling from the runtime, deployment
  configuration, generated plugin payload, current operator guidance, and
  behavior-pinning tests.
- Remove the auto-ship validator, action wrappers, PR writer, ledger/storage,
  configuration, auth/extension registration, and status projection.
- Retire the `community-patch-loop` capability and all named shipped artifacts.
- Preserve generic composition and execution primitives.
- Move read-only uptime, deploy, clean-clone, and revert-rate observation to a
  generic uptime/alarm successor with no task-dispatch self-heal.

**Non-Goals:**

- Removing Goal canonical selection used by explicit `run_canonical` behavior.
- Removing the generic dispatcher, BranchTask, request/trigger primitives, node
  enqueue, or wiki write capabilities.
- Removing generic evaluation or explicit GitHub-effect primitives from which a
  user may compose a reviewed shipping workflow.
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

### 6. Move observational canaries to uptime-and-alarms

The useful health subset moves to a generically named
`scripts/platform_uptime_watch.py` plus
`.github/workflows/platform-uptime-watch.yml` under
`uptime-and-alarms`. It may update the canonical operational incident/alarm
sink, but MUST NOT enqueue tasks, select a user workflow, dispatch another
workflow as self-heal, write repository/wiki state, or advertise an auto-fix
loop. No `community-loop` named executable, workflow, label, artifact, or
status field survives.

## Risks / Trade-offs

- **Existing host configuration expects automatic investigations** -> Remove the
  variables from deployment and current runbooks in the same change; do not
  silently redirect them. Filing remains successful and explicit.
- **Broad deletion accidentally damages generic execution** -> Keep canonical
  dispatcher and general queue tests, and add negative tests proving only the
  product-specific request type/path disappeared.
- **Stale generated plugin resurrects removed code** -> Rebuild the plugin, scan
  both source and package output, and test source/package parity.
- **Consumers call removed extension actions** -> Return the ordinary
  unknown-action behavior; do not retain aliases. Document that shipping is a
  user-built workflow composed from general effects.
- **Historical documents trigger false-positive scans** -> Limit zero-reference
  gates to shipped runtime, active deployment/configuration, current runbooks,
  plugin payloads, and executable tests. Historical artifacts may retain
  accurately labeled history.
- **Queued legacy `bug_investigation` rows exist at deployment** -> The runtime
  SHALL not special-case or execute them as the retired product loop. Deployment
  must inspect/clear such operator-owned legacy queue state explicitly rather
  than add a compatibility consumer.

## Migration Plan

1. Add negative tests for `file_bug` side effects and absence of the retired
   configuration/request type in source and package output.
2. Remove the wiki trigger/receipt integration and the dedicated
   `bug_investigation` module and executor special cases.
3. Remove auto-ship modules, actions, ledger/reset/status integration,
   configuration, current docs, and behavior-pinning tests.
4. Rename the useful watch subset into generic uptime/alarm artifacts and remove
   its workflow-dispatch self-heal.
5. Remove environment/default/deploy/runbook references and update generic
   dispatcher/examples.
6. Rebuild the Claude plugin and verify its runtime mirrors the clean source.
7. Run focused tests, full relevant suites, lint, plugin build/probe, and
   repository scans for shipped references.
8. Before deployment, inspect production for obsolete environment keys, legacy
   request rows, and auto-ship ledger/config state; remove/archive them without
   executing them.
9. Deploy and run the normal public MCP, clean-clone, production deploy, and
   website deploy canaries. Verify `file_bug` in a rendered chatbot conversation
   files the page without an investigation/trigger side effect and `get_status`
   contains no cheat-specific health projection.

Rollback is by reverting the removal commit only if ordinary bug filing or
generic workflow execution regresses. The retired automation is not an
acceptable rollback target for loss of automatic investigation behavior.

## Open Questions

None for the target contract. Any future curated investigation workflow is an
ordinary commons design and requires its own user-facing OpenSpec change.

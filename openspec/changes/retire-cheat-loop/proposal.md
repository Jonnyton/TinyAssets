## Why

The historical cheat loop was declared retired, but the shipped runtime still
contains its privileged `file_bug` -> investigation path, Patch Packet
write-back, auto-ship validator/ledger/PR actions, status projection, named
watch workflow, plugin copies, and production configuration. That contradicts
TinyAssets' model: task automation is a user-authored design composed from
public primitives, not a product-specific hidden loop.

## What Changes

- **BREAKING** Remove the implicit investigation trigger, trigger receipt, and
  automatic dispatcher/triage routing metadata from `file_bug`; filing a page
  performs only the documented filing operation. Delete
  `classify_filing_effort`, `filing_effort_dispatch_route`, their route
  constants/tokens, stored/response metadata, and behavior-pinning tests;
  generic filing fields and duplicate detection remain.
- **BREAKING** Remove the dedicated `bug_investigation` request type, payload
  adapter, handler resolution, execution special cases, and automatic Patch
  Packet write-back from shipped runtime and tests.
- **BREAKING** Remove the platform `classify_patch_request` policy and its
  hard-coded free/paid claimant, Claude/Codex writer, opposite-family checker,
  and persisted `request_classification` metadata. Preserve explicit requester
  pickup incentives, directed-daemon selection, and user soul-loop dispatch as
  bounded user-authored routing under their independent authority owners.
- **BREAKING** Remove `validate_ship_packet`, `open_auto_ship_pr`, the
  `auto_ship` validator/ledger/PR modules and storage, all auto-ship
  configuration, and `get_status.auto_ship_health`. The `get_status` handle
  remains; only the cheat-specific projection leaves its response.
- Remove both `TINYASSETS_BUG_INVESTIGATION_GOAL_ID` and
  `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID` from runtime configuration,
  production deployment, runbooks, and the Claude plugin runtime mirror.
- Delete the obsolete external `AUTO_FIX_DISABLED` GitHub repository variable
  and remove current runtime/plugin/test/website promises and labels that call
  generic provider diagnostics or workflow activity an "auto-fix loop." Do
  not replace the variable with another disable flag or no-op alias.
- Retire the `community-patch-loop` capability and every named shipped
  community-loop artifact rather than leaving a disabled or renamed product
  loop.
- First remove the production and rollback website
  `community_change_context` wire callers so the caller migration unblocks
  `retire-legacy-live-mcp-tools`. After that owner removes and rebuilds the
  exact six hidden MCP registrations, delete the product-specific internal
  action, handler, plan-heading/auto-change queue logic,
  Codex-writer/Claude-checker rule, plugin behavior, and tests. Preserve no
  dispatchable internal compatibility path.
- Snapshot and remove the 28 live GitHub label definitions that encode retired
  loop routing/status, strip them from open issues/PRs without closing or
  rewriting user content, preserve generic request/gate/checker/payment labels,
  including non-routing `patch_request` filing/effect trace vocabulary, and
  publish an idempotent migration receipt plus repository-wide notice.
- Remove the public website's privileged patch-loop route/status fallback,
  checked-in community-loop JSON, `community_change_context` callers, homepage
  loop narrative, workflow/label assumptions, and fine-print branding across
  the production React/Next tree and retained Svelte rollback tree. Preserve a
  generic user-workflow activity view only when it has live/snapshot provenance
  and does not imply a platform-owned loop.
- Keep generic Goal canonical selection, dispatcher/request admission, node
  enqueue, graph execution, wiki/GitHub effect primitives, evaluation
  primitives, and workflow composition available so users can build, publish,
  copy, remix, and combine their own investigation, shipping, or recurring-task
  designs.
- Move read-only uptime, clean-clone, deploy, and revert-rate observation into
  the generic `uptime-and-alarms` capability. The observer only reads, emits
  bounded evidence, and exits; the independently owned alarm sink may consume
  that evidence but neither surface can dispatch repair or user task work.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `community-patch-loop`: remove every requirement and retire the capability
  after its generic observation subset moves to `uptime-and-alarms`. Because
  OpenSpec rejects a zero-requirement canonical spec, final foldback SHALL
  explicitly apply the six surviving capability deltas, physically delete the
  reviewed `community-patch-loop` canonical directory, strictly validate the
  resulting tree, and archive this change with `--skip-specs`; it SHALL NOT
  attempt a normal all-removals sync that aborts or recreates an empty spec.
- `daemon-runtime-and-dispatch`: migrate retired v1/v2 queue rows through only
  existing statuses/fields, #1803 authority reconciliation, exact queue CAS,
  and a pre-#1803 worker-quiescence/deployment stop.
- `development-coordination-runtime`: retire the live GitHub routing/status
  label taxonomy through a receipt-backed migration that preserves open work
  and generic coordination labels.
- `graph-execution-substrate`: make the user-authored composition boundary
  explicit while preserving generic execution primitives.
- `uptime-and-alarms`: own the generic read-only platform/deploy/revert
  observation successor without community-loop or self-heal task dispatch.
- `wiki-commons`: remove the hidden filed-page trigger receipt/enqueue behavior
  and automatic dispatcher/triage claims so typed filing is an atomic wiki
  operation with no privileged automation.
- `public-website-surface`: remove the patch-loop route/status snapshot and
  community-loop fallback/branding while preserving truthful generic workflow
  activity and separately sourced platform-uptime evidence.

## Impact

The implementation slice removes cheat-loop consumers from
`tinyassets/bug_investigation.py`, `tinyassets/api/wiki.py`,
`fantasy_daemon/__main__.py`, `tinyassets/auto_ship*.py`,
`tinyassets/api/auto_ship_actions.py`, extension/auth action registration,
`get_status`, dispatcher/compiler comments and defaults, queued legacy request
state, hard-coded patch-request and filing-effort classification/routing
metadata, the internal `community_change_context` action and callers,
coding-packet auto-ship aliases/config/rubrics, merge-readiness branding,
public prompts/control-station copy, active plans/wiki guidance,
`tinyassets/wiki/trigger_receipts.py`, `scripts/community_loop_watch.py`,
`.github/workflows/community-loop-watch.yml`, production configuration, the
production React/Next website and retained Svelte rollback tree, checked-in
website status JSON, the external `AUTO_FIX_DISABLED` repository variable, active agent
skills and loop souls, automatic patch-announcement workflow, current
"auto-fix loop" wording, generated Claude plugin runtime mirror, and tests that
assert the retired behavior. The repository auto-enrollment workflow also
leaves because it escalates generic PR creation into merge without the
separately required merge authority and receipt. A crash-safe, idempotent
external migration write-ahead records and quiesces the workflow, drains active
runs, and then snapshots/reconciles/disables every still-open auto-merge
enrollment historically proven to have been created by it, while preserving
explicit user/maintainer enrollments and holding ambiguous provenance for
review.
Historical design/audit records may retain clearly marked history; current
operator guidance, configuration, build outputs, behavioral specs, and agent
instructions must not advertise or exercise the retired path or capability.

Existing generic primitives are not replaced or aliased. Users who want bug
investigation, patch generation, PR effects, scheduled work, or similar
automation compose those behaviors as ordinary workflows and explicitly run or
connect them under the same authority rules as any other user design.

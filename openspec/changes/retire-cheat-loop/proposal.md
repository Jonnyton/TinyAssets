## Why

The historical cheat loop was declared retired, but the shipped runtime still
contains its privileged `file_bug` -> investigation path, Patch Packet
write-back, auto-ship validator/ledger/PR actions, status projection, named
watch workflow, plugin copies, and production configuration. That contradicts
TinyAssets' model: task automation is a user-authored design composed from
public primitives, not a product-specific hidden loop.

## What Changes

- **BREAKING** Remove the implicit investigation trigger and trigger-receipt
  side effects from `file_bug`; filing a page performs only the documented
  filing operation.
- **BREAKING** Remove the dedicated `bug_investigation` request type, payload
  adapter, handler resolution, execution special cases, and automatic Patch
  Packet write-back from shipped runtime and tests.
- **BREAKING** Remove `validate_ship_packet`, `open_auto_ship_pr`, the
  `auto_ship` validator/ledger/PR modules and storage, all auto-ship
  configuration, and `get_status.auto_ship_health`. The `get_status` handle
  remains; only the cheat-specific projection leaves its response.
- Remove both `TINYASSETS_BUG_INVESTIGATION_GOAL_ID` and
  `TINYASSETS_BUG_INVESTIGATION_BRANCH_DEF_ID` from runtime configuration,
  production deployment, runbooks, and the Claude plugin runtime mirror.
- Retire the `community-patch-loop` capability and every named shipped
  community-loop artifact rather than leaving a disabled or renamed product
  loop.
- Keep generic Goal canonical selection, dispatcher/request admission, node
  enqueue, graph execution, wiki/GitHub effect primitives, evaluation
  primitives, and workflow composition available so users can build, publish,
  copy, remix, and combine their own investigation, shipping, or recurring-task
  designs.
- Move read-only uptime, clean-clone, deploy, and revert-rate observation into
  the generic `uptime-and-alarms` capability. Its successor may report through
  the normal alarm sink but cannot dispatch repair or user task work.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `community-patch-loop`: remove every requirement and retire the capability
  after its generic observation subset moves to `uptime-and-alarms`.
- `graph-execution-substrate`: make the user-authored composition boundary
  explicit while preserving generic execution primitives.
- `uptime-and-alarms`: own the generic read-only platform/deploy/revert
  observation successor without community-loop or self-heal task dispatch.
- `wiki-commons`: remove the hidden filed-page trigger receipt/enqueue behavior
  so typed filing is an atomic wiki operation with no privileged automation.

## Impact

The implementation slice removes cheat-loop consumers from
`tinyassets/bug_investigation.py`, `tinyassets/api/wiki.py`,
`fantasy_daemon/__main__.py`, `tinyassets/auto_ship*.py`,
`tinyassets/api/auto_ship_actions.py`, extension/auth action registration,
`get_status`, dispatcher/compiler comments and defaults,
`tinyassets/wiki/trigger_receipts.py`, `scripts/community_loop_watch.py`,
`.github/workflows/community-loop-watch.yml`, production configuration, the
generated Claude plugin runtime mirror, and tests that assert the retired
behavior. Historical design/audit records may retain clearly marked history;
current operator guidance, configuration, build outputs, and behavioral specs
must not advertise or exercise the retired path or capability.

Existing generic primitives are not replaced or aliased. Users who want bug
investigation, patch generation, PR effects, scheduled work, or similar
automation compose those behaviors as ordinary workflows and explicitly run or
connect them under the same authority rules as any other user design.

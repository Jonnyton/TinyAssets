## Why

`moderation-and-abuse-response` was specified as one of four target capabilities
inside `complete-independent-full-platform-targets`, but its implementation
started *outside* that change on draft PRs #1662 (`codex/moderation-abuse-runtime`)
and #1667 (`codex/moderation-flag-planner`). That is exactly the
partial-implementation drift the parent change's design warned about: code
landing for one capability while its delta spec is held in a change that cannot
be synced or archived until all four are complete.

The parent change's task 6.3 requires that any unfinished capability with its own
implementation lane be split into a **surviving, independently complete active
change**. This change is that split: the delta spec, the implementation tasks,
and the acceptance/sync/archive ownership move here so the moderation lane can
land, sync, and archive on its own timeline without waiting on packaged-tray,
node-authoring, or handoff work — and without dragging three target-only deltas
into canonical specs.

Nothing about the requirements changed in the split. The delta spec moved
verbatim; the tasks moved with their premise-verification notes intact.

## What Changes

- Take sole ownership of the target-only `moderation-and-abuse-response`
  capability: community flagging, reversible soft-hide, independent review,
  appeals, moderator integrity/recusal, rate limits, and its §14 scale proof.
- Carry the parent change's section-2 implementation tasks verbatim, including
  the in-flight fence: `tinyassets/moderation/models.py`, `policy.py`,
  `service.py`, and the two named test files are being written on draft PRs
  #1662/#1667, so no second lane may write them.
- Assign the ownership the parent change could not: implementation lands in the
  moderation PR lane (#1662/#1667 or their successors), acceptance is the §14
  proof plus the AGENTS.md rendered-chatbot rule where a user-visible surface
  changes, and this change syncs its delta into `openspec/specs/` and archives
  itself in that same landing lane.
- Keep moderation behavior behind the canonical MCP handle routers. This change
  adds no standalone advertised MCP handle.

## Capabilities

### New Capabilities

- `moderation-and-abuse-response`

## Impact

No runtime or canonical spec changes from this proposal itself — it is a
governance split of an existing active change. The implementation it governs adds
`tinyassets/moderation/` (models, store, policy, service), the next numbered
storage migration, moderation routing through existing `tinyassets/api/` handles,
and moderation/authority/concurrency tests.

Dependency edges that survive the split:

- `complete-independent-full-platform-targets` task 5.5 (handoff/outcome
  disputes) depends on `tinyassets/moderation/service.py` from this change. That
  dependency is a read of this change's owner, not shared ownership.
- The parent change remains active for `packaged-tray-installation`,
  `node-authoring-and-autoresearch`, and `real-world-handoffs-and-outcomes`.

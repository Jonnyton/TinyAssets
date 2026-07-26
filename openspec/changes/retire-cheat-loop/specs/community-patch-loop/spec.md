## REMOVED Requirements

### Requirement: Bug Filing Enqueues A Canonical Investigation Request

**Reason**: The implicit Goal/environment-selected enqueue is part of the
retired cheat loop and violates the rule that task automation is user-authored
composition.

**Migration**: Remove both investigation environment variables. Users may build
an explicit workflow from generic request, graph execution, and wiki primitives;
`file_bug` becomes filing-only.

### Requirement: Investigation Runs Attach A Patch Packet To The Wiki Bug Page

**Reason**: Dedicated `bug_investigation` execution and automatic Patch Packet
write-back grant hidden product-specific behavior and authority to one request
class.

**Migration**: User-authored workflows explicitly publish authorized results
through ordinary wiki write primitives. No compatibility request type or
automatic attachment path remains.

### Requirement: Auto-Ship Validation Is A Pure Dry-Run Safety Envelope

**Reason**: The validator is a product-specific shipping composition from the
retired cheat loop even when it reports dry-run decisions.

**Migration**: Retain independently useful generic evaluation primitives.
Authors who want a shipping workflow compose evaluation, approval, and effect
steps as an ordinary user design.

### Requirement: Auto-Ship PR Creation Is Feature-Flagged Off And Never Merges

**Reason**: A disabled product-specific PR action still ships the retired
automation surface and configuration.

**Migration**: Remove the action and flags. User-authored workflows use ordinary
authorized GitHub-effect primitives where available; unknown legacy action names
receive the normal unknown-action result.

### Requirement: Auto-Ship Attempts Are Recorded In An Append-Only Ledger

**Reason**: `auto_ship_attempts.jsonl` and its lifecycle exist only for the
retired product loop.

**Migration**: Stop reading and writing the ledger. Existing files are
historical operator data that may be archived or deleted under ordinary
retention policy; no runtime compatibility reader remains.

### Requirement: Loop Health Is Watched By Read-Only Monitors

**Reason**: The useful observations are platform uptime concerns, not a
community patch-loop capability; the named workflow also contains task-dispatch
self-heal behavior that is not observational.

**Migration**: Move only read-only public MCP, P0 incident, Tier-3 clone, deploy,
and revert-rate observation into `uptime-and-alarms` under generically named
script/workflow/artifact/label surfaces. Remove workflow-dispatch self-heal.

### Requirement: Auto-ship PR creation is scoped, idempotent, and stale-head safe

**Reason**: Scoped safety does not make the dedicated auto-ship PR action a
generic primitive; it remains a privileged product composition.

**Migration**: Remove the action and preserve any independently owned generic
GitHub authorization/effect boundary for explicit user-authored workflows.

### Requirement: Auto-ship health is a read-only status projection

**Reason**: `get_status.auto_ship_health` exposes a dedicated product-loop
ledger and keeps the retired capability in the public connector response.

**Migration**: Keep the `get_status` handle but remove this field and all
auto-ship ledger reads. Generic uptime state remains owned by
`uptime-and-alarms`.

### Requirement: Branch-task restarts reuse completed runs and recover nested Patch Packets

**Reason**: The requirement combines a generic run-reuse property with
product-specific `bug_investigation` packet recovery and automatic wiki writes.
The latter are the retired cheat loop.

**Migration**: Preserve generic durable run reuse in its ordinary execution
owner, without special request types, packet-field interpretation, or wiki
mutation.

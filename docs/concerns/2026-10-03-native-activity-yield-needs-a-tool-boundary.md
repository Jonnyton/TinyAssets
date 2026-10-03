# Native activity yield still lacks an execution boundary

PR #4221 remains a draft and is not ready to merge. Its Activities contract
requires an owner-request yield to end the run as completed and release the
seat, with no further tools. Pause and stop also require a tool boundary.

The HTTP workflow agent now carries the activity's server-captured run and
generation into its existing tool/inference checks. It ends a yielded run
normally and releases the work claim without another model request. The
regressions in `tests/test_activity_http_yield.py` cover this path, including a
model reply that batches another tool after the owner request.

Native agents execute their own internal tool loop inside one provider call.
The HTTP coordinator's between-step check cannot fence that loop. Native
providers also expose tools outside the engine MCP route (for example
WebFetch), so an MCP-only check would not establish the promised boundary.
Polling activity state and cancelling a native process leaves a next-tool
race and cannot establish that effects settled before a completed yield.

Before the whole Activities feature can merge, a dedicated design/disposition
must establish a native pre-tool boundary and ordinary yield completion with
process/seat release, and prove it on Linux. This change does not introduce a
native routing protocol, change native tool policy, or claim this blocker is
resolved. Account activation and reset-triggered resumption remain outside
this repair.

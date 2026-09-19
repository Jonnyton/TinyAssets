I'll read the prior review, the supervisor, the tool client, and the workflow refusal path, then give a verdict.

Reading done. Writing the verdict now.

**VERDICT: ADAPT.** The seam is necessary and the shape is mostly right. Three adaptations are required before it ships; the rest is deferrable.

## Race confirmed

- `tinyassets/engine_mcp_http.py:342` publishes the route immediately after `Popen` at line 211. The listener binds only after the child imports the whole stack and uvicorn runs lifespan, at `tinyassets/engine_mcp_server.py:2710`. On the 1 vCPU box that gap is seconds.
- `tinyassets/engine_tool_client.py:203` refuses on a missing route and line 213 makes exactly one connect. A connection refused becomes `engine_tools_unavailable` with no retry.
- `tinyassets/workflow_agent.py:174` refuses a missing route before the reservation is even taken. A first background run after approval hits the 15-second poll at line 319 as well.
- The supervisor sleeps unconditionally at `tinyassets/engine_mcp_http.py:319`, and its `servers` dict and writer are closure-local. Nothing can wake it today.

**AGREE** the seam is required and no tools-free greeting or per-user enrollment belongs here. **AGREE** the pin must be reread throughout the wait rather than cached.

## Where readiness lives

Put one helper in `engine_mcp_http`, the module that already owns the route map and supervisor, and call it from exactly one consumer: `open_engine_tools` in place of the immediate refusal at `tinyassets/engine_tool_client.py:203`. Do not put waiting in the reader. The reader is called per tool call from `_check_route` at line 97 and from the server-side gate at `tinyassets/engine_mcp_server.py:273`, and neither may block.

The workflow path then drops its route pre-check and keeps an authority pre-check only. That is safe: the finally block at `tinyassets/workflow_agent.py:200` already settles the reservation as cancelled-before-launch when the adapter never launched, which is exactly what a readiness timeout inside `turn.run()` produces. The reservation lease is capped at 3600 seconds, so a 30-second wait cannot outlive it. Background and foreground then share one contract through the coordinator at `tinyassets/agent_turn_coordinator.py:199`.

**DISAGREE_CONCERN** on the alternative of publishing only ready listeners. It removes the connect race but not the 15-second poll penalty, and it requires the supervisor to probe children on a thread that must never die. Keep the route as a pin and let the caller wait.

## Required adaptations

1. **Wait only when this process owns the supervisor.** The supervisor starts only under streamable-http at `tinyassets/universe_server.py:3987`. In any other process the flag may be on with nobody spawning, and a 30-second stall is dead time. If no supervisor was started in-process, do one route read and return, which is current behaviour and keeps every existing test green. Replace the sleep at line 319 with an event wait so a module-level wake function can trigger a tick.
2. **Authority decides decline versus wait.** `engine_tools_authorized` at `tinyassets/engine_mcp_http.py:116` is derived from the serving binding, admin ACL and not-deleted principal. Env only supplies the kill switch at line 124, which can deny but never grant. Not authorized means decline now with no wait. Authorized with no route means startup lag, so wake and wait. Recheck authority every loop so a revocation mid-wait declines. This answers the env question: no access is created.
3. **Probe never retries the handshake.** Poll the route reader plus a bare loopback TCP connect with a sub-second timeout, sending nothing. Once the socket accepts, make exactly one MCP connect and one discovery. If that fails, raise unavailable. Retries live only before the first byte is sent. This preserves the no-replay contract at `tinyassets/engine_tool_client.py:160`.

TCP-ready is sufficient here. uvicorn runs lifespan startup before it binds the listening socket, so an accepted connection means the FastMCP session manager is initialised. Bearer is checked per request at `tinyassets/engine_mcp_server.py:2695` and owner authority per tool call at line 273. Nothing changes on the server.

Fire the wake from two places: after the commit at `tinyassets/provider_serving_binding.py:1107` so the server warms during the seconds between approval and first send, and from the helper itself so a crash or restart still recovers. Only wake when authorized and routeless, so an already-routed turn costs nothing.

## Bounds

Cap the wait at the smaller of the caller timeout and 30 seconds. With the in-process wake that is start time only. Without it, the poll worst case is 15 seconds plus start, which fits but is tight under load. The helper must use async sleep so the coordinator's existing cancellation at `tinyassets/agent_turn_coordinator.py:187` cancels it. Waiting turns hold a slot for at most 30 seconds and the wake is debounced by the event, so shared capacity does not worsen.

## Release blockers versus deferrable

Blockers for this seam:

- The three adaptations above.
- The mutation tests below, each run against the unfixed tree first and required red.

Still blocking general admission but not this seam: the per-server RSS measurement from the prior review. This seam adds no process, it only changes when the first connect happens.

Deferrable: a same-tick port reuse race where a retired universe's port is reassigned before a turn connects. The bearer differs per server object, so the request gets a 401, and the map is rewritten in the same tick. Note it, do not fix it here. Also deferrable: the claude and codex providers still read the route once and fall back to stdio at `tinyassets/providers/claude_provider.py:405`. That path works today.

## Required focused tests

One new file, using the existing fake client and route fixtures from `tests/test_engine_tool_client.py` plus an injected probe function.

- New serving universe, authority present, no route, supervisor event present. The route appears and the probe succeeds after two polls. First open succeeds with exactly one connect and one discovery.
- Unauthorized principal, and a revocation that lands mid-wait. Both decline immediately with no probe attempted and no wake fired for the unauthorized case.
- Timeout and cancellation. The probe never succeeds. No connect, no discovery, no inference, and in the workflow path the reservation settles as cancelled-before-launch.
- Malformed route: wrong actor on the entry, bad version, bad secret shape. The helper keeps waiting until the deadline and never connects to that port, never reads another entry.
- Probe succeeds, then the single MCP connect fails. Unavailable is raised with no second probe and no second connect.
- No supervisor in-process with the flag on. One route read, immediate decline, no wait.
- Existing `test_changed_route_refuses_without_dispatch` must stay green unchanged, proving per-call rechecks still see revocation with no waiting introduced.

The finished file `output/engine-tools-shape-review.md` is the same text as the prior review I already read and folded in, so its verdict is already acted on. The running item is this review's own output slot, and the remaining four belong to another session's worktree. This session is read-only with no dispatch allowed, so there is nothing further to advance here.

The ADAPT verdict above stands as the deliverable.

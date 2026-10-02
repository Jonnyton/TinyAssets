# Design: the thin agent loop (target architecture S7)

## Context

`AgentTurnCoordinator` already is a vendor-neutral HTTP agent loop: it calls
the model through `ApiKeyHttpProvider`, which reaches the upstream only via
`ConnectionLedger.resolve_exact_scoped_proxy` and the credential-blind broker
worker, and it journals every round and tool call in `agent_turns`. What it
was not is *thin*: each turn ran `asyncio.run` on the worker thread that
claimed it, and its tools came from the per-command-center engine MCP process,
whose four file/shell tools each start a bubblewrap jail. This change keeps
the coordinator, the router, the broker and the journal, and changes where the
turn lives and where its tools run.

## Decisions

### 1. One event loop in the execution owner; a turn is a task on it

`ExecutionOwner` runs one `asyncio` loop on a daemon thread. A caller submits
`turn.run()` and waits; the task is created with a copy of the caller's
context, so the served request's identity, the owner's stop handle and the
launch scope read exactly what `asyncio.run` on the caller's thread read.
`run_coroutine_threadsafe` chains cancellation, so a cancelled wait cancels the
task, which cancels the box execution and the model call under it.

The broker is still request/close and synchronous, so a waiting round still
holds an executor thread. The owner's default executor is sized for that
(`TINYASSETS_AGENT_LOOP_THREADS`, default 512), not Python's ~32, which would
queue the 33rd waiting turn. S6's streaming broker contract removes the thread.

A shared loop has one new failure mode: synchronous work a turn does on the
loop (a journal write waiting on SQLite's busy timeout) stalls every turn. The
owner measures it rather than assuming it away: a watchdog records the worst
scheduling lag and logs any stall over 1 s.

### 2. Tools are routed by name, once, never by the model

`open_loop_tools` builds the turn's inventory from its grant:

| Tools | Where they run | Why there |
|---|---|---|
| `read` `write` `edit` `bash` | the turn's box, `BoxProvider.start_exec` | user content lives in the box (D1) |
| `history` `activity` | the loop, read-only | platform-visible records; listing never wakes a box (D7) |
| every other served tool | the engine route, unchanged | its gates (rules, auto-review, consent) live there |

The handle is bound once (`BoxProvider.bind(cc, account=owner, turn=turn_id)`)
when the session opens and held by the session; no call looks a box up by name.

### 3. `op_id` is the journal position; unknown holds

`op_id = "{turn_id}:{round}:{call}"`, computed by the coordinator from the
journal row it has just marked `started`. The D2 contract makes `start_exec`
idempotent by `op_id`, so:

- a lost `start_exec` reply is asked again with the same `op_id`, once;
- a broken stream is resumed from its last offset, once;
- anything still unresolved, `unknown_after_restore` included, raises an
  unknown outcome. The coordinator journals `unknown`, the turn ends
  `held_tool_unknown`, and nothing is re-issued under a new id.

Only `BoxOperationRefused` -- the box host refusing BEFORE the operation
existed (stale epoch, foreign handle) -- is reported as not sent, and only on
the first attempt: refused on the retry means the first may have run.

`edit` is two executions (`op_id/read`, `op_id/write`). The write carries the
sha256 of the bytes read and the box writes only if the file still has them,
via temp file and rename, so a concurrent `bash` or another agent of the same
command center wins instead of being overwritten.

### 4. The scripts are the tool jail's

The four tools run the same `sh` scripts and return the same text as
`universe_tools`, with argv (never a command string to the box API) and the
box's root (`/cc`, or the handle's `root`). `tests/test_agent_loop_box_tools.py`
pins argument parity with the engine's tools and runs the scripts on a real
POSIX shell.

### 5. Switch, and the failure when it is on without a box

`TINYASSETS_AGENT_LOOP=thin` selects `ThinLoopChatAdapter` in
`make_interactive_agent_turn`. With the switch on and no box provider
configured, a turn granted a box tool is refused before its first inference
(`box_unavailable`). It is never served by the tool jail instead: a fallback
that looks like the new path would make the switch unfalsifiable.

## Measurement: memory per waiting turn

`scripts/measure_agent_loop_memory.py`, 2026-10-01, the Linux oracle image
(python 3.11.16), 500 concurrent turns, a mock SSE server in its own process
holding every stream open with `: ping` until all 500 wait, then completing
them (each folded by `agent_chat_codec.fold_chat_stream`):

| Context per turn | RSS before | RSS with 500 waiting | Per waiting turn |
|---|---|---|---|
| 64 KiB | 59.9 MiB | 171.3 MiB | **228 KiB** |
| 8 KiB | 60.4 MiB | 89.9 MiB | **61 KiB** |

Command: `docker run --rm -v <tree>:/src:ro -w /src tinyassets-linux-oracle:<tag>
python -B scripts/measure_agent_loop_memory.py --turns 500 [--context-kb 8]`.

Read it with what it excludes: the transport is a direct streaming client to
the mock, i.e. the loop side of S6's streaming broker. **Today's broker spawns
one worker process per in-flight round**: measured at 29 MiB RSS (18 MiB
anonymous) just for its imports, before it resolves a credential. Until S6,
that, not the loop, is the per-waiting-turn cost of an HTTP turn. Against the
CLI path (~77 MB PSS per waiting subprocess in production) the loop's own
share is two to three orders of magnitude smaller, inside the ~1 MB D6 estimated.

## Risks

- **Loop stalls.** Measured by the watchdog, not prevented. If production shows
  stalls, the fix is moving the journal's SQLite writes off the loop, not a
  loop per turn.
- **Interface drift.** `BoxExec` is a structural subset of D2 written before
  the `BoxProvider` module landed; event and status attribute names
  (`kind`/`data`/`offset`/`code`, `state`) are assumptions to reconcile with
  the S4 driver.
- **Two tool routes during the cutover.** While the switch is off the engine
  route serves the four tools; while it is on, the box does. No turn ever has
  both.

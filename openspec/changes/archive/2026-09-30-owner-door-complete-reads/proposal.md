# Two doors: the owner's app reads complete data, the model door bounds

**Tier: public API surface, design principle, app transport.** A new owner route
family, a changed connector read and a PLAN.md principle are hard to reverse, so
this gets a proposal before code. Founder approved the design on 2026-09-30
("yes that design is approved, build it"), including the PLAN.md paragraph.

## Why

Live 2026-09-30, after a deploy: the founder's "Waiting on you" rail vanished
while the free test account kept it. The code was the same for both accounts. The
data was not.

- The app read the rail through the MCP connector
  (`MCP.listRequests` -> `read_graph target=pending_requests`).
- The connector applies a model-context ceiling to `read_graph` (24 KB,
  `engine_result_bounds`, `universe_server._structured_return`).
- The founder's 7 pending requests were 34 KB, so the app got a truncation marker
  with no `pending` list. `refreshRail` swallowed that and never unhid the rail.

A cross-family review found more of the same class. The rail showed at most 30
requests (the connector's default `limit=30`). The app's restore-access check
(`read_graph target=agent_binding`) could be truncated too. History showed only
the last 30 turns, with no sign that anything was missing. A narrow patch that
added entries to the connector's exempt list (PR #4151) was rejected.

Founder, verbatim: *"the issue you need to fix is that you shouldnt have been able
to make the mistake, we cannot have single account patching happen again... there
are only two account types, free or subscription and we dont care what connections
they have. so arcetectually, not in some rule but arcetectually it should be so
clear that a future session would not be able to make this mistake not cause of a
rule but because its arcetetually odvious".*

The root cause is structural. The owner's own screen and a model's context window
shared one read path. So a bound that exists for models reached the owner, and it
cut the most for the heaviest user. An exempt list maintained by hand is a rule,
and the next new read would miss it.

## What changes

1. **Two doors.**
   - **Owner door** (`tinyassets/owner_door/`, routes `/app/api/read` and
     `/app/api/status`): the app on web, phone and desktop. It authenticates as
     the owner through the same bearer middleware and the same per-read owner
     gates as today, and it returns complete data. The package holds no size,
     limit or truncation logic. An import-boundary test fails if it can reach the
     ceiling or the projection modules.
   - **Model door** (the MCP connector and the served-agent engine): keeps context
     bounding, applied as a projection only at that door.
2. **One read dispatcher.** The `read_graph` target dispatch moves out of
   `universe_server` into `tinyassets/api/graph_reads.py`, a domain module that
   cannot import the bounding modules. Both doors call it. The connector wraps it
   with the ceiling. The owner door returns it as is.
3. **Shared domain reads are complete.** `list_requests` and `list_pending` return
   every pending row with no default page. A storage failure raises instead of
   reading as "nothing pending". Conversation history pages by an explicit cursor
   (`conversation_before`) and always says whether older turns exist.
4. **The connector's exempt list shrinks to contracts.** `model_options` leaves
   it. On the connector it becomes the same compact projection the engine already
   serves, so both model-door surfaces have one definition, and the complete
   catalogue is the owner door's. `run_file`, `conversation` and
   `conversation_turn` stay, each with a contract reason that has nothing to do
   with the app (see design).
5. **Account variation has one input.** An `AccountType` value (FREE |
   SUBSCRIPTION) is resolved in one place (`universe_owner.account_type_of`,
   per account) and is the only thing `usage_policy.limits_for` takes. The four
   per-universe `get_tier` readers route through it.
6. **Owner surfaces fail loudly.** A failed or partial rail read keeps the rail
   visible and says it couldn't load.
7. **Every app read moves to the owner door**: `app.html`, `app_layout.js` and
   `app_ui.js`. Actions (`converse`, `write_graph`) stay on MCP, because the
   ceiling applies only to `read_graph` and they return acknowledgements or the
   universe's own reply.

Supersedes PR #4151 (`rail-complete-list`).

## Out of scope

- Default `limit=30` on other list reads (runs, automations, agents, graphs,
  goals) is listed as a finding in design.md. Those reads either have an explicit
  page the client already drives (`agent_bindings`) or are commons searches,
  where a result page is the product. The owner door never supplies a default of
  its own.
- The retired rolling-window meters (`effects`, `compute_seconds`) belong to
  `two-dimension-usage-limits`.

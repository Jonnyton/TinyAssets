# A universe can see that it is unpowered and cannot do anything about it

**Filed 2026-09-03.** **Severity: P1** — it is the difference between a universe
that can be fixed by its owner from anywhere and one that can only be fixed from
one surface.

## What happened

The founder's universe `tiny` spent a full day unable to run any prompt node
(`permission_denied:provider_not_bound`) while workspace and HTTP branches
completed normally. It diagnosed the failure correctly, then said:

> What remains is **selection, not registration**. I do have the
> OpenAI-compatible HTTP provider registered already, including
> `provdef_3c41c478f9196b528187e17ab304b18e`, but my universe is still not
> actually serving through it. **I do not have a served tool exposed in this
> session to change that binding directly, so I can verify the state but not
> flip it from here.**

It was right. Binding is `POST /mcp/app/serving/bind` — an *app* route. Nothing
in the MCP tool surface (`read_graph` / `write_graph` / `run_graph` / …) selects
which registered provider serves the universe. `read_graph target="compute"`
lists them; nothing chooses one.

Calling that route once from the founder's app session returned
`{"status":"serving","provider":"codex",...}` and the universe was live again.
The capability existed the whole time and was unreachable from where the problem
was visible.

## Why it matters

- **It splits diagnosis from repair.** The agent that can see the fault cannot
  fix it, and the surface that can fix it does not show the fault.
- **It contradicts a standing rule.** What an agent may DO is meant to be
  user-configurable through the chatbot/MCP surface, and every user action is
  meant to be reachable through a user surface. Selection is a user action with
  no user-facing route outside one web app.
- **Registration and selection being separable is deliberate** (the deposit is
  write-only by spec, and the server-side auto-bind was correctly withdrawn in
  #2761). That is not in question. The gap is that only ONE of the two halves
  has a tool.

## What a fix looks like

A `write_graph` operation on the compute target — "serve on this definition_id"
— carrying the same ownership gate `_open_serving_context` already applies, so
authority is unchanged and only reachability grows. The bind route and the tool
must share one implementation, or they will drift into two answers to one
question.

## Not to be confused with

The wall this sat behind until 2026-09-03: the deployed `serving/bind` accepted
only two hard-coded names and refused everything else `unsupported_service`.
That is fixed and deployed (`6039f6fe`). This concern is what remained
afterwards.

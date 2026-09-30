# A universe's own multi-agent system: live screen, app wakes, consented publish

## Why

In a live acceptance run on 2026-09-30, a universe was asked for an always-on
team of agents with its own screen, published for other people. It built an
external service and asked for a hosting destination and a code-host token.
The served guidance now maps that request onto agent nodes, automations, `/u`
files and an app UI (#4104). A custom UI can read automations, runs and run
output through its bridge (#4105). Three gaps remain, and each changes public
surface, authority or what becomes public, so they are specced first.

1. **A screen cannot read the files the agents share.** Agents coordinate
   through files in `/u`, such as a board, a queue or a log. The connector has
   no read target for them, so no bridge call can reach them.
2. **A screen cannot wake an agent.** The bridge's `sendMessage` reaches only
   the one selected conversation. Nothing lets a click start one of the owner's
   own agents.
3. **A universe cannot publish what it built.** Publishing from the served
   surface was deferred until a consent gate existed (`engine_mcp_server.py`,
   the note after `remix_shape`). The app has no way to publish a UI either:
   `AppUI.publishPayload` has no caller. The universe could only tell the
   person, and the person had nowhere to press.

## What Changes

- **Read the universe's files, owner-only.** New connector targets:
  `read_graph target="universe_files"` lists one directory, and
  `target="universe_file"` reads one file in bounded chunks. Both take a path
  relative to `/u`, go through the existing no-follow readers, and are readable
  only by a caller who holds admin on that universe. The bridge gains
  `listFiles(dir)` and `readFile(path, offset)`, pinned to the viewer's home.
- **An app event wakes the owner's own subscribed agent.** A new automation
  event type, `app_event`, has a required `event_filter` of `{"name"}`. It is
  emitted by `run_graph operation="emit_event"` with
  `inputs_json {"name", "data"}` and by the bridge's
  `tinyassets.emit(name, data)`. It rides the existing event path, so it wakes
  only subscriptions the emitting principal owns, in their own home, with
  `inputs.event.data`. A UI can wake only what the owner subscribed to that
  name; it cannot run an arbitrary branch.
- **Publishing is a consented ask.** A new pending-request action type,
  `publish`, can be raised by the served agent. It names a public name and
  description, the owner's own `branch_ids`, an optional `ui_id` from their
  library, and optional `automation_ids` whose triggers travel. The tab is
  written by the platform from the action, not by the agent: it lists
  everything that becomes public. The action pins a content digest of every
  item. Confirming re-checks the digests (if anything changed, nothing is
  published and the ask stays pending). It then makes each branch public,
  publishes a version of each, and publishes ONE definition whose components
  are the UI, a `tinyassets.branch-ref.v1` per workflow, and a
  `tinyassets.automation-spec.v1` per trigger. The served agent cannot answer
  its own ask; that stays on the person's surfaces.
- **Installing needs no new primitive, and the guidance names the steps.** The
  second user's universe runs `read_commons_shape agent_definition_id=...`,
  then `remix_shape` for each branch-ref (private copies), then saves the UI to
  `app_ui` (private), then creates its own automations from the specs against
  the copies. Every copy runs as the installer, in their universe.

## Impact

- Public MCP surface: two new `read_graph` targets and one new `run_graph`
  operation on the connector (handles unchanged). Three read-only bridge
  actions plus one wake action.
- Authority: one new owner-confirmed ask type. Publishing still happens only
  on an answer from the person's own surface.
- Storage: no new table. `app_event` joins the event-type set. Definitions
  carry two new component kinds as data.
- Specs: `live-mcp-connector-surface`, `user-owned-automations`,
  `universe-custom-agents`.

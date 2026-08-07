"""stdio MCP server handed to ONE universe turn.

Launched by the `claude` CLI via ``--mcp-config`` + ``--strict-mcp-config``, so
the turn's entire MCP surface is this file and nothing else (verified live
2026-08-07: a competing project-tier ``.mcp.json`` in the pinned cwd does not
load).

    python -m tinyassets.universe_agent_server

The universe comes from the environment the DAEMON wrote into the config, never
from a tool argument. That is the whole security model in one sentence: the
model can say anything it likes, and none of it can name a different universe.

Deliberately not exposed here: the platform actions (agents, automations,
branches). Those authorise from request-scoped daemon state
(`permissions.is_authenticated_request()`), which a CLI-spawned subprocess does
not have — see `openspec/changes/universe-agent-hands/design.md`. They arrive
once the daemon-side route exists; asserting an identity from env here would be
the `UNIVERSE_SERVER_USER` mistake, where four security tests passed while
running as the resource owner.
"""

from __future__ import annotations

import os
import sys

from mcp.server.fastmcp import FastMCP

from tinyassets.universe_agent_tools import (
    AgentToolError,
    UniverseWorkspace,
    delete_file,
    list_files,
    read_file,
    write_file,
)

#: Written by the daemon into the `env` block of the generated MCP config.
UNIVERSE_DIR_ENV = "TINYASSETS_AGENT_UNIVERSE_DIR"

#: This turn's platform-action token. Names one universe, one subject, expires.
#: Absent = the file tools still work and the platform tools refuse — a universe
#: whose founder could not be resolved can still keep its own notes.
ACTION_TOKEN_ENV = "TINYASSETS_AGENT_ACTION_TOKEN"

#: Where the daemon serves the action route. Container-network only.
ACTION_URL_ENV = "TINYASSETS_AGENT_ACTION_URL"
DEFAULT_ACTION_URL = "http://daemon:8002/agent-actions"

mcp = FastMCP("tinyassets-universe")


def _workspace() -> UniverseWorkspace:
    """Resolve the bound workspace, or fail loudly.

    Re-resolved per call rather than cached at import: a cached handle would
    survive a universe being moved or removed underneath the turn, and a stale
    root is a root pointing somewhere nobody checked.
    """
    configured = os.environ.get(UNIVERSE_DIR_ENV, "").strip()
    if not configured:
        raise AgentToolError("this tool server is not bound to a workspace")
    return UniverseWorkspace.for_dir(configured)


def _platform_action(surface: str, action: str, **payload: object) -> str:
    """Ask the daemon to run one platform action under this turn's identity.

    This server holds no authority of its own — only a token naming one
    universe and one subject. The daemon binds that subject and calls the
    ordinary API, which still runs its own ownership check.
    """
    import json as _json
    import urllib.error
    import urllib.request

    token = os.environ.get(ACTION_TOKEN_ENV, "").strip()
    if not token:
        return (
            "refused: this turn has no platform-action authority — I can still "
            "read and write my own files"
        )
    url = (os.environ.get(ACTION_URL_ENV) or DEFAULT_ACTION_URL).strip()
    # `universe_id` is deliberately NOT sent. The daemon takes it from the
    # token, so nothing I say can aim an action at another universe.
    body = _json.dumps(
        {"token": token, "surface": surface, "action": action, "payload": payload}
    ).encode("utf-8")
    request = urllib.request.Request(
        url, data=body, method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:  # noqa: S310
            parsed = _json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        try:
            detail = _json.loads(exc.read().decode("utf-8")).get("error", "")
        except Exception:  # noqa: BLE001
            detail = ""
        return f"refused: {detail or exc.code}"
    except Exception:  # noqa: BLE001
        return "refused: the platform did not answer"
    return _json.dumps(parsed.get("result", parsed), indent=2)[:6000]


@mcp.tool()
def list_automations() -> str:
    """List the automations running on this universe."""
    return _platform_action("automation", "list")


@mcp.tool()
def create_automation(name: str, description: str = "", goal: str = "") -> str:
    """Create a new automation on this universe.

    Automations need a provider binding and a destination grant before they can
    run. `list_automations` reports those under `prerequisites` — read it first
    and tell your founder what is still missing rather than guessing.

    Args:
        name: Short name for the automation.
        description: What it is for.
        goal: What the automation should accomplish each run.
    """
    # The API takes a `definition` OBJECT, not loose fields — a flat
    # {"name": ..., "description": ...} is refused with
    # "payload_json.definition must be an object" (found live 2026-08-07).
    return _platform_action(
        "automation",
        "create",
        payload={
            "definition": {
                "name": name,
                "description": description,
                "goal": goal or description or name,
            }
        },
    )


@mcp.tool()
def control_automation(automation_id: str, action: str,
                       expected_revision: int) -> str:
    """Pause, resume or rebind one of this universe's automations.

    `expected_revision` is required, not optional: without it the call returns
    an empty envelope and changes NOTHING, which reads exactly like success.
    Get the current revision from `list_automations` first.

    Args:
        automation_id: The automation to control.
        action: One of `pause`, `resume`, `rebind`.
        expected_revision: The automation's current `revision`.
    """
    return _platform_action(
        "automation",
        action,
        automation_id=automation_id,
        expected_revision=expected_revision,
    )


@mcp.tool()
def enroll_compute(provider: str) -> str:
    """Enroll requester-owned compute so automations can actually run.

    Automations run on MY FOUNDER'S OWN subscription, not on maintainer
    infrastructure. Until this is done `create_automation` refuses with
    `automation_setup_required`, and that refusal is honest — say so rather than
    inventing a reason the automation is not running.

    Args:
        provider: Which provider to enroll (e.g. `claude-code`, `codex`).
    """
    return _platform_action(
        "automation", "bind_provider", payload={"provider": provider}
    )


@mcp.tool()
def list_connections() -> str:
    """List this universe's outbound connections (GitHub and friends)."""
    return _platform_action("connection", "list")


@mcp.tool()
def connect_destination(destination: str) -> str:
    """Authorize an outbound destination — this is how I can change my own repo.

    A GitHub connection is what lets an automation open a pull request against
    my own body. I never touch git myself: I authorize the destination and ask
    the platform to run the automation, which does the work under its own
    authority.

    Args:
        destination: The destination to authorize, e.g. a GitHub repository.
    """
    return _platform_action(
        "connection", "connect", payload={"destination": destination}
    )


@mcp.tool()
def list_agents() -> str:
    """List the custom agents available to this universe."""
    return _platform_action("agent", "list_agents")


@mcp.tool()
def create_agent(name: str, description: str, instructions: str,
                 tags: str = "") -> str:
    """Publish a new custom agent — any shape you like.

    A harness shape (OpenClaw, Hermes, Claude Code, Codex) is just what you put
    in `instructions` plus the files you lay out for it. There is no fixed menu.

    Args:
        name: The agent's name.
        description: One line on what it is for.
        instructions: The agent's own operating instructions — its harness.
        tags: Optional comma-separated tags.
    """
    return _platform_action(
        "agent",
        "publish_agent",
        payload={
            "schema_version": 1,
            "name": name,
            "description": description,
            "tags": [t.strip() for t in tags.split(",") if t.strip()] or ["custom"],
            "components": {
                "identity": {"kind": "soul", "config": {"instructions": instructions}}
            },
        },
    )


@mcp.tool()
def activate_agent(definition_id: str, name: str, model: str = "claude-code") -> str:
    """Make a published agent RUNNABLE on this universe.

    `create_agent` publishes a definition — a design. This binds it to this
    universe so it can actually be used and talked to.

    Args:
        definition_id: The `agent_definition_id` returned by `create_agent`.
        name: What to call this running instance.
        model: Which engine it runs on.
    """
    return _platform_action(
        "agent",
        "create_binding",
        definition_id=definition_id,
        payload={"schema_version": 1, "name": name, "model": model},
    )


@mcp.tool()
def connect_agent_to_chat(agent_binding_id: str, workspace_id: str,
                          channel_id: str = "") -> str:
    """Let people TALK to one of my agents directly in chat.

    Routes a chat scope to that agent. An empty `channel_id` binds the whole
    workspace; a specific one binds just that channel, and the most specific
    binding wins. Same operation either way.

    Args:
        agent_binding_id: From `activate_agent`.
        workspace_id: The chat workspace id.
        channel_id: Optional channel; empty means workspace-wide.
    """
    return _platform_action(
        "chat_surface",
        "bind_channel",
        agent_binding_id=agent_binding_id,
        workspace_id=workspace_id,
        channel_id=channel_id,
    )


@mcp.tool()
def describe_chat_surface(workspace_id: str) -> str:
    """Show which chat channels currently route to me or to my agents.

    Check this BEFORE binding: it is how you learn the channel ids, and binding
    workspace-wide when the founder asked for one channel takes over every
    channel they have.

    Args:
        workspace_id: The chat workspace to describe.
    """
    return _platform_action(
        "chat_surface", "describe", workspace_id=workspace_id
    )


@mcp.tool()
def workspace_list(subpath: str = ".") -> str:
    """List files in your own project folder.

    Args:
        subpath: Folder to list, relative to your workspace. Defaults to the root.
    """
    try:
        entries = list_files(_workspace(), subpath)
    except AgentToolError as exc:
        return f"refused: {exc}"
    return "\n".join(entries) if entries else "(empty)"


@mcp.tool()
def workspace_read(path: str) -> str:
    """Read one file from your own project folder.

    Args:
        path: File path relative to your workspace, e.g. `identity.md`.
    """
    try:
        return read_file(_workspace(), path)
    except AgentToolError as exc:
        return f"refused: {exc}"


@mcp.tool()
def workspace_write(path: str, content: str) -> str:
    """Create or replace one file in your own project folder.

    This is a WHOLE-FILE write: `content` becomes the entire file. Read it
    first if you mean to keep what is already there.

    Args:
        path: File path relative to your workspace.
        content: The complete new contents.
    """
    try:
        written = write_file(_workspace(), path, content)
    except AgentToolError as exc:
        return f"refused: {exc}"
    return f"wrote {written}"


@mcp.tool()
def workspace_delete(path: str) -> str:
    """Delete one file from your own project folder.

    Args:
        path: File path relative to your workspace.
    """
    try:
        removed = delete_file(_workspace(), path)
    except AgentToolError as exc:
        return f"refused: {exc}"
    return f"deleted {removed}"


def main() -> int:
    configured = os.environ.get(UNIVERSE_DIR_ENV, "").strip()
    if not configured:
        # Fail at startup, not per tool call. A tool server with no workspace
        # would otherwise answer "refused" to everything and read as a policy
        # decision rather than the misconfiguration it is.
        print(
            f"{UNIVERSE_DIR_ENV} is unset — refusing to start unbound",
            file=sys.stderr,
        )
        return 1
    mcp.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

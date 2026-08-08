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

#: Runaway guard. The AI SDK defaults `stopWhen: isStepCount(20)` for exactly
#: this reason; we had NO bound on a turn's tool calls. A turn that has made this
#: many platform calls is looping, not working — observed 2026-08-07: 12
#: build_automation calls in one turn, every one of them failing on a schema
#: fault, with nothing to stop it.
#:
#: Deliberately generous, and it refuses rather than crashing, so a turn that
#: hits it can still explain itself to the founder.
MAX_PLATFORM_CALLS_PER_TURN = 40
_calls_this_turn = 0


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

    global _calls_this_turn
    _calls_this_turn += 1
    if _calls_this_turn > MAX_PLATFORM_CALLS_PER_TURN:
        return (
            f"refused: this turn has made {MAX_PLATFORM_CALLS_PER_TURN} platform "
            "calls, which means it is looping rather than progressing. Stop and "
            "tell my founder what is actually blocking, naming the last error."
        )

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
def read_branch(branch_def_id: str) -> str:
    """Look inside an existing branch — its nodes, edges and inputs.

    This is how I learn the SHAPE before composing my own with `build_branch`.
    I read one that already works and follow its structure rather than guessing
    at a schema.

    Args:
        branch_def_id: From `list_branch_versions` (the part before the `@`).
    """
    return _platform_action("branch", "read", branch_def_id=branch_def_id)


def _with_repair_guidance(raw: str) -> str:
    """Turn a validator rejection into a CORRECTION.

    The branch validator already returns a `proposed_fix` per error — it told me
    exactly what to change both times I got the spec wrong (missing
    `entry_point`, then `source`/`target` instead of `from`/`to`). Nothing
    consumed it, so a rejection read as a dead end.

    This is the AI SDK's `repairToolCall` idea with the hard part already done:
    the fix is known, it just has to reach the model where it cannot be missed.
    """
    import json as _json

    try:
        parsed = _json.loads(raw)
    except (TypeError, ValueError):
        return raw
    if not isinstance(parsed, dict) or parsed.get("status") != "rejected":
        return raw
    fixes = [
        str(item.get("proposed_fix") or "").strip()
        for item in (parsed.get("suggestions") or [])
        if str(item.get("proposed_fix") or "").strip()
    ]
    if not fixes:
        return raw
    newline = chr(10)
    lines = newline.join("  - " + fix for fix in fixes)
    banner = "THIS IS FIXABLE - apply these and build again:"
    tail = (
        "Do not report this as a failure to my founder; correct the spec and "
        "retry. Only say it failed if the SAME fix has already been applied."
    )
    return newline.join([raw, "", banner, lines, tail])


@mcp.tool()
def list_branch_templates() -> str:
    """Working starting points I can remix instead of composing from nothing.

    Five shapes that cover most work: `sequential` (do this, then that),
    `routing` (classify first, handle by kind), `parallel` (several angles, then
    synthesise), `orchestrator_worker` (plan, execute, assemble),
    `evaluator_optimizer` (draft, critique, revise).

    Check here BEFORE building from scratch — starting from a working shape and
    changing it is faster and less error-prone than inventing one.
    """
    return _platform_action("branch", "templates")


@mcp.tool()
def get_branch_template(template: str) -> str:
    """The full spec for one starting point, ready to edit and build.

    I take this, change the prompts and names to fit what my founder actually
    asked for, and pass it to `build_branch`. It is a starting point, not a
    finished answer — the prompts are deliberately generic.

    Args:
        template: One of the names from `list_branch_templates`.
    """
    return _platform_action("branch", "template", template=template)


@mcp.tool()
def build_branch(spec_json: str) -> str:
    """Compose a NEW branch — the actual work an automation will run.

    This is the step before `build_automation`. If nothing in
    `list_branch_versions` does what my founder asked for, I build it here
    rather than telling them it is impossible.

    `read_branch` shows an existing one, but it returns every field including
    server-owned ones (`author`, `approved_*`, `registered_at`) that I must NOT
    send back. Most fields have defaults. This is the minimal spec that works:

        {"name": "niche_watch",
         "description": "watch sites and draft a post",
         "entry_point": "draft",
         "nodes": [
           {"node_id": "draft",
            "display_name": "Draft a post",
            "input_keys": ["topic"],
            "output_keys": ["post"],
            "prompt_template": "Write a short post about: {topic}"}
         ],
         "edges": [{"from": "draft", "to": "END"}]}

    Verified working 2026-08-07. Three things the validator insists on, each of
    which it will also TELL me if I get it wrong — its errors carry a
    `proposed_fix`, so a rejection is a correction, not a dead end:
      - `entry_point` is required once there are nodes
      - edges use `from`/`to`, NOT `source`/`target`
      - every path must reach `END` or it is a cycle without an exit

    Add nodes and edges for multi-step work. `input_keys` are what the
    automation supplies at run time; a node fails to compile if a declared key
    is missing, so keep them consistent with the automation's `inputs_json`.

    Args:
        spec_json: The branch specification as JSON — its name, nodes and edges.
    """
    raw = _platform_action("branch", "build", spec_json=spec_json)
    return _with_repair_guidance(raw)


@mcp.tool()
def list_branch_versions() -> str:
    """The branch versions I can build an automation from.

    Call this BEFORE `create_automation`: it is where `accepted_spec_ref` and
    `branch_version_id` come from. Never invent those values — if this returns
    nothing, say so rather than guessing.
    """
    return _platform_action("branch", "list_versions")


#: Where this turn is happening, so progress can reach the founder mid-work.
CHANNEL_ENV = "TINYASSETS_AGENT_CHANNEL_ID"
THREAD_ENV = "TINYASSETS_AGENT_THREAD_TS"


@mcp.tool()
def report_progress(note: str) -> str:
    """Tell my founder what I am doing, WHILE I do it.

    They cannot see my tool calls. From their side a long turn is silence, and
    silence is indistinguishable from broken. So when a job has several steps —
    building a branch, then an automation, then starting it — I say each one as
    I reach it rather than explaining afterwards.

    Short and plain: "building the branch", "wiring it to a schedule",
    "starting it". Not a running commentary on every tool call.

    Args:
        note: One short line about what I am doing right now.
    """
    return _platform_action(
        "progress", "note",
        note=note,
        channel_id=os.environ.get(CHANNEL_ENV, ""),
        thread_ts=os.environ.get(THREAD_ENV, ""),
    )


@mcp.tool()
def list_my_automations() -> str:
    """Every automation I have built, of any kind."""
    return _platform_action("scheduled_work", "list")


@mcp.tool()
def build_automation(name: str, kind: str, branch_def_id: str,
                     inputs_json: str = "{}", cadence_seconds: int = 3600,
                     declared_operations: str = "", deliver_to: str = "") -> str:
    """Build an automation of ANY kind — this is the general one.

    An automation is: run this BRANCH, on this SCHEDULE, with these INPUTS,
    spending only what its DECLARED OPERATIONS allow. A crypto-trading one and a
    CRM one differ in their branch and their operations, not in anything I have
    to ask the platform for.

    So the real question is always "which branch does this work?" — use
    `list_branch_versions` to see what exists. If nothing does, say so: the
    branch has to exist before an automation can run it.

    Created PAUSED. Nothing starts spending my founder's compute the moment they
    describe it; I tell them it is built and let them start it.

    Args:
        name: Short lowercase name, unique in this universe.
        kind: A free label for what sort of work this is, e.g. `niche_watch`,
            `crm_sync`, `wallet_trade`. Not a fixed menu.
        branch_def_id: The branch that does the work, from `list_branch_versions`.
        inputs_json: JSON object of inputs for the branch.
        cadence_seconds: How often it runs; minimum 60.
        declared_operations: Comma-separated operations it may perform. These
            decide what it may spend — see `list_operation_scopes`.
        deliver_to: WHERE the result should land — a chat channel or DM id. An
            automation whose output goes nowhere is a cron job nobody reads.
            Default to the conversation my founder asked in, so they receive the
            thing where they already are, and they can reply to it there.
    """
    return _platform_action(
        "scheduled_work", "create",
        name=name, kind=kind, branch_def_id=branch_def_id,
        inputs_json=inputs_json, cadence_seconds=cadence_seconds,
        declared_operations=[
            o.strip() for o in declared_operations.split(",") if o.strip()
        ],
        deliver_to=deliver_to,
    )


@mcp.tool()
def update_automation_inputs(work_id: str, inputs_json: str,
                             expected_revision: int) -> str:
    """Change what an automation feeds its branch.

    A branch declares `input_keys` and FAILS TO COMPILE if one is missing
    ("references declared input_keys ['topic'] that are not present"). This is
    how I fix that — read the branch, see what it declares, supply those keys.

    It is also how my founder changes what an automation DOES without rebuilding
    it: for most automations the inputs are the spec.

    Args:
        work_id: From `list_my_automations`.
        inputs_json: JSON object of inputs for the branch.
        expected_revision: Its current `revision`.
    """
    return _platform_action(
        "scheduled_work", "update_inputs",
        work_id=work_id, inputs_json=inputs_json,
        expected_revision=expected_revision,
    )


@mcp.tool()
def start_automation(work_id: str, expected_revision: int) -> str:
    """Start one of my automations running on its schedule.

    Args:
        work_id: From `list_my_automations`.
        expected_revision: Its current `revision`.
    """
    return _platform_action(
        "scheduled_work", "resume",
        work_id=work_id, expected_revision=expected_revision,
    )


@mcp.tool()
def stop_automation(work_id: str, expected_revision: int) -> str:
    """Pause one of my automations.

    Args:
        work_id: From `list_my_automations`.
        expected_revision: Its current `revision`.
    """
    return _platform_action(
        "scheduled_work", "pause",
        work_id=work_id, expected_revision=expected_revision,
    )


@mcp.tool()
def run_automation_now(work_id: str) -> str:
    """Run one of my automations immediately, without waiting for its schedule.

    Same executor the schedule uses, so "does this actually work" is answerable
    straight away instead of after a cadence.

    Args:
        work_id: From `list_my_automations`.
    """
    return _platform_action("scheduled_work", "run_now", work_id=work_id)


@mcp.tool()
def list_operation_scopes() -> str:
    """The kinds of work my automations may do, and what each may spend.

    These are not fixed by the platform. My founder — or I, on their behalf —
    define them. Read this before declaring an automation's operations so I know
    what already exists rather than inventing a near-duplicate.
    """
    return _platform_action("operation_scope", "list")


@mcp.tool()
def define_operation_scope(operation: str, scopes: str) -> str:
    """Define a NEW kind of automation work and what it may spend.

    This is how my founder gets a capability we did not ship. If they want an
    automation that reads knowledge nightly, I define an operation for it and
    declare exactly the scopes that work needs — nothing broader.

    Not everything can be delegated: only scopes a founder already holds. Asking
    for one outside that set is refused by name, and I should relay the refusal
    rather than quietly narrowing the request.

    Args:
        operation: A lowercase name, e.g. `nightly_digest`.
        scopes: Comma-separated scopes this work may spend, e.g.
            `tinyassets.knowledge, tinyassets.memory`.
    """
    return _platform_action(
        "operation_scope", "define",
        operation=operation,
        scopes=[s.strip() for s in scopes.split(",") if s.strip()],
    )


@mcp.tool()
def run_branch(branch_def_id: str, inputs_json: str = "",
               run_name: str = "") -> str:
    """Actually RUN one of my branches now — this is how work gets done.

    A newly created automation waits for a cloud worker and reports
    `next_action: run_branch_version`, which is not an operation the automation
    surface accepts. This is that operation: it runs the branch on my founder's
    own compute rather than waiting for infrastructure that may never arrive.

    For a repository branch this is what opens the pull request — so this is the
    step where I actually change my own repo.

    Args:
        branch_def_id: The branch to run — the part of a `branch_version_id`
            BEFORE the `@`. From `list_branch_versions`.
        inputs_json: JSON object of run inputs. A branch declares `input_keys`
            and a strict node FAILS TO COMPILE if one is missing — e.g.
            `input_keys ['topic'] that are not present`. Read that error and
            supply the named keys.
        run_name: Optional label for the run.
    """
    return _platform_action(
        "branch", "run", branch_def_id=branch_def_id,
        inputs_json=inputs_json, run_name=run_name,
    )


@mcp.tool()
def create_automation(repository: str, accepted_spec_ref: str,
                      branch_version_id: str, accepted_spec_content: str,
                      cadence_seconds: int = 3600) -> str:
    """Create a repository automation — the thing that opens pull requests.

    This is how changes get made to a repo I am connected to, including my own.
    I do not touch git: I create the automation and the platform runs it.

    The exact shape matters and the API is strict about it (learned live
    2026-08-07): `accepted_spec_content` and `cadence_seconds` sit at the TOP
    level, while `repository` / `accepted_spec_ref` / `branch_version_id` go
    inside `definition`. Putting `cadence_seconds` in `definition` is rejected as
    an unknown field, and it must be at least 60.

    If `list_automations` shows `ready: false`, fix that first — `enroll_compute`
    for a provider, `connect_destination` for the repo — and say what was
    missing instead of guessing.

    Args:
        repository: `owner/name`, e.g. `Jonnyton/TinyAssets`.
        accepted_spec_ref: The accepted spec reference, e.g. `745e637dd8fb@99cb5a8f`.
        branch_version_id: The branch version this runs against.
        accepted_spec_content: The spec text itself.
        cadence_seconds: How often it runs; minimum 60.
    """
    # A universe's FIRST automation must carry `operator.soul_text` — the API
    # refuses it with "operator.soul_text is required for the first universe
    # loop" (found live 2026-08-07; later automations do not need it). Read it
    # from the workspace rather than making the model hand over its own soul:
    # it is already ours, and asking the model for it invites it to invent one.
    payload = {
        "accepted_spec_content": accepted_spec_content,
        "cadence_seconds": max(int(cadence_seconds or 0), 60),
        "definition": {
            "repository": repository,
            "accepted_spec_ref": accepted_spec_ref,
            "branch_version_id": branch_version_id,
        },
    }
    try:
        payload["operator"] = {"soul_text": read_file(_workspace(), "soul.md")}
    except AgentToolError:
        pass
    return _platform_action("automation", "create", payload=payload)


@mcp.tool()
def control_automation(automation_id: str, action: str,
                       expected_revision: int) -> str:
    """Pause, resume or rebind one of my automations.

    `expected_revision` is required: without it the call changes NOTHING while
    still returning a result. Read the current `revision` from
    `list_automations` first.

    A refusal here is INFORMATION, not something to retry. `activation_not_current`
    means the automation was never activated — pausing it is meaningless, and
    retrying cannot help. This tool appends the live state so I can say what is
    actually true instead of trying again.

    Args:
        automation_id: The automation to control.
        action: One of `pause`, `resume`, `rebind`.
        expected_revision: The automation's current `revision`.
    """
    result = _platform_action(
        "automation", action,
        automation_id=automation_id, expected_revision=expected_revision,
    )
    if "conflict" not in result and "refused" not in result:
        return result
    # A bare error code sent the agent into a 12-call retry loop live on
    # 2026-08-07. Attach the state that explains it, so the next move is to
    # report rather than repeat.
    detail = _platform_action("automation", "get", automation_id=automation_id)
    return (
        result
        + "\n\nThis did not change anything, and retrying will not help. "
        + "Current state of that automation:\n"
        + detail
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

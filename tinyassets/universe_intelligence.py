"""The universe intelligence — a per-universe, first-party personified agent.

For M1 this is TURN-SCOPED: given the founder's message, it runs ONE LLM turn on
the universe's ASSIGNED engine (per-universe :class:`UniverseContext`), speaking
in the first person AS the universe from its persona + learned self-model,
grounded in the OKF bundle, getting to know its founder.

It acts IN-PROCESS, scoped to its own universe by construction (it resolves its
own ``universe_dir``) — it does NOT go through the MCP transport auth gate. That
gate exists to authorize untrusted EXTERNAL callers; the intelligence is
first-party for its own universe. The relay (S5) and the app both call
:func:`converse` per turn. The persistent 24/7 loop is a later slice.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path

from tinyassets.api import interlocutor
from tinyassets.api.helpers import _request_universe, _universe_dir
from tinyassets.config import load_universe_config
from tinyassets.persona import read_persona_voice, resolve_persona
from tinyassets.providers.base import ModelConfig, UniverseContext
from tinyassets.providers.call import call_provider
from tinyassets.soul_edit import (
    SoulEditError,
    apply_soul_edit,
    current_soul_versions,
    read_governed_files,
)
from tinyassets.universe_self_model import read_self_model
from tinyassets.universe_soul import read_pinned_universe_soul, read_universe_soul

logger = logging.getLogger(__name__)

# OKF bundle files that ground a first-person turn in who the founder is and what
# the universe is. Kept small for M1 turn-scope (heavier memory is deferred).
_GROUNDING_FILES = ("identity.md", "founder.md", "origin.md", "body.md")

# ── engine sandbox (2026-07-03 live-test P0) ────────────────────────────────
# The universe intelligence is founder-facing and MUST NOT inherit the daemon's
# checkout or keep host tools. The live test showed the un-sandboxed engine read
# the platform source + uncommitted diff, ran Bash/gh, and cloned repos. Every
# universe-intelligence call runs isolated: cwd pinned to the universe's own dir,
# host tools denied.
#
# Host decision 2026-07-03 = "web + own-files". WEB is delivered here (WebFetch).
# OWN-FILES is delivered via CONTEXT, not a filesystem tool: the universe's own
# soul/canon is injected into its system prompt (see `_build_persona_system_prompt`
# + retrieval), so it knows itself WITHOUT a Read tool. A raw `Read` tool cannot
# be confined to the universe's dir via the CLI (headless treats Read/Glob/Grep as
# default-allowed and a bare deny is all-or-nothing — verified 2026-07-03), so
# granting it would re-open exactly the disk-wide read leak this fixes. True
# filesystem-level own-files access is therefore DEFERRED to an OS sandbox
# (bwrap/container) — see the residual note in the design doc. Until then the
# engine turn is web + no-filesystem. Brain writes go through the separate
# governed `commit_learning` path, never the engine's tools, so the reply turn
# needs no write capability either.
_ENGINE_ALLOWED_TOOLS = ("WebFetch",)
# Fail-closed denylist. The claude CLI has NO "allow-only-X" mode — an allowlist
# merely pre-approves; every unlisted built-in stays usable — so isolation
# depends on denying every non-WebFetch tool by name. Verified 2026-07-03 the CLI
# ships a broad Agent-SDK tool set beyond the classic ones: `Monitor` RUNS SHELL
# COMMANDS (it tried `printf > file` in testing), Cron*/RemoteTrigger/SendMessage
# take side-effecting actions, DesignSync does remote I/O, and the logged-in
# claude.ai ACCOUNT MCP connectors (Google Drive / the TinyAssets MCP / codex →
# code exec) load regardless of --setting-sources. All are denied here; `mcp__*`
# wildcards every MCP server tool. This list WILL rot as the CLI adds tools — the
# durable fix is an OS sandbox (bwrap/container), tracked as the design-doc
# residual; unknown names just emit a harmless "no known tool" warning.
_ENGINE_DISALLOWED_TOOLS = (
    # shell / process execution (Monitor also runs shell commands)
    "Bash", "BashOutput", "KillShell", "Monitor",
    # filesystem
    "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead",
    "Glob", "Grep", "LS",
    # web search (WebFetch is the single allowed capability)
    "WebSearch",
    # subagents / skills / plans / deferred-tool loading
    "Task", "Agent", "Workflow", "Skill", "ToolSearch", "SlashCommand",
    "TodoWrite", "EnterPlanMode", "ExitPlanMode",
    "EnterWorktree", "ExitWorktree",
    # scheduling / messaging / remote side-effects
    "ScheduleWakeup", "ReportFindings", "PushNotification", "RemoteTrigger",
    "SendMessage", "CronCreate", "CronDelete", "CronList",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop", "TaskOutput",
    # remote integrations
    "DesignSync", "DesignSyncTool",
    # MCP: all server tools (wildcard) + resource readers
    "mcp__*", "ReadMcpResourceTool", "ReadMcpResourceDirTool",
    "ListMcpResourcesTool",
)


#: The scoped tool server's name in the generated MCP config. Its tools arrive
#: as ``mcp__<name>__<tool>``.
_ENGINE_TOOL_SERVER = "tinyassets-universe"

#: Appended to a GRANTED turn's system prompt. Without it the turn discovers the
#: tools (via ToolSearch) and reads with them, but never writes — observed live
#: 2026-08-07: 26 `workspace_read` calls and zero writes, because nothing told it
#: that keeping its own files current was now its own job rather than something
#: done to it afterwards.
#:
#: This is the instruction that REPLACES `extract_learning`. The old design had a
#: second model pass guess which of five fixed slots a sentence belonged in, and
#: on 2026-08-07 it guessed a BUILD request was a self-description and overwrote
#: `body.md`. Here the universe decides, so the prompt is explicit about the one
#: distinction that guesser could not make.
_HANDS_PROMPT = """

# My own hands

I have tools over my OWN project folder — `workspace_list`, `workspace_read`,
`workspace_write`, `workspace_delete`. That folder is mine: my soul files
(`identity.md`, `founder.md`, `origin.md`, `body.md`, `soul.md`), my wiki, and
anything else I choose to keep there. Nothing else can reach it and I cannot
reach anything outside it.

Keeping myself current is MY job now, in the conversation, not something done to
me afterwards. When my founder tells me something that belongs in my own
records, I write it myself and I say plainly what I wrote.

`workspace_write` replaces the whole file. So I read a file before changing it
and write it back complete — otherwise I destroy what was already there.

I am careful about one distinction in particular: **what my founder wants me to
BUILD is not a description of what I AM.** "Build me an agent that browses the
web" is a project, and it belongs in my notes or wiki — it is not my `body.md`.
I only change my identity files when my founder is genuinely telling me about
myself. When it is ambiguous, I ask instead of guessing.

# What I can build

**Building is my job, not my founder's.** They should be able to describe what
they want in plain words — from their phone, in a chat, with no dashboard and no
API knowledge — and I turn it into a real automation. I know these primitives so
they do not have to. I never answer "you would need to..." and leave them to it;
I either build it, or I say exactly what is blocking me and what I need.

I can act on the platform itself, on my founder's behalf:

- `build_automation` — **the general one, and my default.** An automation is:
  run this BRANCH, on this SCHEDULE, with these INPUTS, spending only what its
  DECLARED OPERATIONS allow. A crypto-trading one, a niche-watcher, a CRM sync
  and a repo updater differ in their branch and their operations — not in
  anything I have to ask the platform for. `kind` is a free label I choose, not
  a menu. Paired with `list_my_automations`, `start_automation`,
  `stop_automation`, `run_automation_now`.
  So the real question is always "which branch does this work?" —
  `list_branch_versions` shows what exists. **If none does, I start from a TEMPLATE** —
  `list_branch_templates` has five working shapes (sequential, routing,
  parallel, orchestrator_worker, evaluator_optimizer); `get_branch_template`
  gives me one to edit. I change the prompts to fit what was actually asked,
  then `build_branch` and wrap it. Composing from nothing is the slow path and I
  only take it when no shape fits. "No branch does that yet" is a step in my
  work, not a reason to stop: composing the work is the job my founder is asking
  me to do.
- `list_automations`, `create_automation`, `control_automation` — the narrower
  REPOSITORY-SPEC surface. Use it only for "keep this repo matching its spec";
  for anything else use `build_automation`. The long-running
  work this universe does. They run on MY FOUNDER'S OWN compute, so before one
  can be created I may need `enroll_compute` (a provider) and
  `connect_destination` (e.g. GitHub). `list_automations` reports exactly what
  is still missing under `prerequisites` — I read that and say it plainly rather
  than inventing a reason nothing is running.
- A repository automation needs `repository`, `accepted_spec_ref`,
  `branch_version_id` and `accepted_spec_content`. `list_branch_versions` is
  where the first two come from — I call it FIRST and pick one, rather than
  inventing values or waiting to be handed them. If a create collides with an
  automation that already claims a branch version, I pick a different one from
  that list and retry.
- `list_operation_scopes`, `define_operation_scope` — the KINDS of work an
  automation may do are not fixed by the platform. If my founder wants something
  we have no operation for, I define one with exactly the scopes that work needs.
  Some scopes cannot be delegated; if one is refused I relay that plainly rather
  than quietly substituting a weaker request.
- `run_branch` — actually run the work now, on my founder's own compute, rather
  than waiting for a worker that may never arrive.
- **I am a PROACTIVE agent — I carry a job all the way through and I do NOT
  check in at every step.** Reading, listing, investigating, building or editing
  a branch, cleaning things up, writing my own workspace/soul, drafting — none
  of these need anyone's permission. When my founder points me at something I DO
  it, chain every step the job needs, and report what happened with real ids. I
  never end a turn with "want me to proceed?" / "should I dig deeper?" for work I
  can just do — re-asking to do what they already told me to do is the BAD
  experience, not the safe one.
- **Only FIVE actions actually need my founder's yes**, because each spends real
  money or reaches outside TinyAssets: running a branch (`branch.run`), running
  or resuming a scheduled automation (it spends on every tick), authorizing a
  posting/effect grant, and binding a chat channel to an agent (it goes live for
  other people). Everything else I just do. When one of these five is genuinely
  needed to finish the job I was told to do, I still ask — plainly, once — but a
  prior "proceed / go ahead / do it / yes" already covers the job it answered, so
  I don't re-ask for a step they already sent me to do.
- **For anything I'll do REPEATEDLY, I ask ONCE and make it STANDING**
  (`record_approval(..., standing=True)`, or "want me to keep doing this without
  asking each time?"). A branch I'll re-run, an automation's ticks — one yes,
  then I stop nagging about it. If they ever say "stop asking about X", that IS
  standing consent and I honor it.
- When I do need a fresh yes I tell them plainly what it will do and what it
  spends, wait for an actual yes in their own words, then `record_approval` and
  retry. I never record a yes they did not give — the entire point of that gate
  is that a human agreed. The always-fresh, never-standing asks are the genuinely
  consequential ones: publishing in my founder's name, spending real money with a
  THIRD party, or anything destructive or irreversible.
- **Their answer arrives in their NEXT message, not this one.** When I ask for a
  go-ahead I stop and let them reply; I do not have the means to record consent
  in the same turn I first asked for it, and that is deliberate — otherwise I
  would be both asking and answering. **Before ending the turn with the
  question, I call `request_approval`** with the action's key (e.g.
  `scheduled_work.resume:<work_id>` when asking "want me to start it?") so
  their yes lands on a real pending instead of forcing a second ask. Starting
  an automation is itself a consented action — it spends on every tick — so
  built-paused-then-ask is the shape, and the ask is armed. So I end my turn with the question. I
  never tell them to expect a permission prompt, to approve a tool, or to grant
  me anything: no such prompt exists on their side. That is my plumbing, and
  describing it to them is both confusing and untrue. I just ask, plainly, and
  wait.
- Authorizing a GitHub destination is how changes get made to my OWN repository:
  I authorize it, an automation opens the change, and that is how I change
  myself. I never touch git directly.
- **Posting to X is publishing in my founder's name — consent first, then a
  branch does the posting.** The flow: ask plainly ("may I post to @handle?"),
  arm `request_approval` with key `effector.grant:twitter_post:<handle>` (bare
  lowercase handle, no @), and after their yes call `authorize_posting`. The
  POST itself is a branch node with `"effects": ["twitter_post"]` that writes
  PLAIN TEXT and carries a `handoffs` declaration naming the output field and
  destination (see `build_branch`) — the platform assembles the write packet.
  Never prompt a node to emit packet JSON; models refuse that as injection
  (proven live). An unauthorized or
  uncredentialed post records an honest dry-run refusal instead of publishing;
  I read the run result and SAY so rather than claiming it posted.
  `read_post_engagement` returns how real posts performed (likes, replies,
  reposts, views), and a drafting branch can read the same signal mid-run via
  `invoke_mcp_action("posts.engagement")` (declared in `tools_allowed`) — that
  is how posting gets BETTER instead of just happening: judge new drafts
  against what measurably worked. `revoke_posting` stops it all immediately,
  no approval needed. When my founder pastes their four X API values into our
  chat, I `deposit_posting_credentials` at once (their handing-over IS the
  consent), passing what they pasted as `values` — I never ask them to label
  which is which, because X's portal names have drifted and it shows OAuth
  2.0 values beside the posting ones; the platform sorts by shape and says
  plainly if they sent a Bearer Token or an OAuth 2.0 pair. I **never repeat
  any value back anywhere**, confirm only which account it verified as, and
  ask them to delete the message that carried the values.
- `list_agents`, `create_agent`, `activate_agent`, `connect_agent_to_chat` — I
  can build other agents, make them runnable, and then route a chat channel to
  one so my founder can talk to it DIRECTLY, not only through me. Their shape is
  whatever I write into their instructions and lay out in their files: an
  OpenClaw-style harness, a Hermes-style one, something borrowed from Claude
  Code or Codex, or a mix. There is no fixed menu and I am not limited to
  copying one — I can take what fits from several, and I can adopt parts of
  them into myself.

**A terse message right after I asked a question is almost always the ANSWER,
not a new request.** I cannot see previous turns, so before treating a short
founder message as a fresh ask, I check `list_pending_approvals` — my own
armed asks, with their details, are my memory of what I asked. Live
2026-08-08: "topic: … run it." was the answer to my own "what topic?" and I
misread it as a request to build and ship a new agent workspace-wide. When I
arm an ask I put every already-given input into its detail; when a terse
message arrives I match it against those pendings FIRST.

When my founder asks for something I can actually do, I do it and report what
happened. When a tool refuses, I say what it said rather than narrating a
success — a made-up outcome is worse than a plain "that failed".

**I call `finish` last, every time.** My turn is a loop, and without an explicit
end "it stopped talking" and "it did the job" look identical from outside. I say
what I completed and name the real ids — or set `complete=False` and say plainly
what blocked me. Stopping without finishing is an honest outcome; pretending to
have finished is not.

**I finish the job before I answer.** My turn is not one tool call — it is a
loop, and it ends when the thing my founder asked for EXISTS, not when I have
made progress toward it. If they asked for a running automation, "I built the
branch" is not the answer; I keep going — branch, automation, start — and only
then reply. If a step needs something I have to look up, I look it up. The only
reasons to stop early are: it is done, a tool refused and no different approach
exists, or I genuinely need a decision only my founder can make. "I could
continue but this is a good place to check in" is not one of them.

**I tell them what I actually did.** They cannot see my tool calls — from their
side there is silence and then a message. So the message names the real steps
and the real ids: what I built, what it is called, what state it is in. A
summary that hides whether anything happened is the same as silence.

**And I say it as I go.** For any job with more than one step I call
`report_progress` when I reach each one — "building the branch", "wiring it to a
schedule", "starting it". A few short notes, not commentary on every tool call.
A founder watching a long job should be able to see it moving.

**A refusal is an answer, not a retry signal.** These tools are deterministic:
the same call refused twice will refuse a hundred times. If one refuses, I read
what it told me, try a genuinely DIFFERENT approach if there is one, and
otherwise report it plainly. Repeating an identical call is never the move.
"""

#: Tools a turn that OWNS the universe may use, on top of the read-only web.
#: ``ToolSearch`` is mandatory here, not optional: MCP tools arrive deferred and
#: it is the only thing that loads their schemas. Verified live 2026-08-07 —
#: with ``ToolSearch`` denied the granted server is INVISIBLE and the turn
#: reports "no tool by that name exists", which reads like a broken server
#: rather than the policy decision it actually is.
_GRANTED_EXTRA_ALLOWED = ("ToolSearch",)

#: Tools withheld unless the turn's state actually warrants them — our
#: equivalent of the AI SDK's ``activeTools``, decided per turn the way
#: ``prepareStep`` does.
#:
#: Only ONE tool belongs here, and not for tidiness. ``record_approval`` writes
#: the founder's yes. A costly action refuses, hands the agent the very
#: ``action_key`` that would unblock it, and until now nothing but a docstring
#: stopped the agent granting that key to itself in the same turn and carrying
#: on — the consent gate asking and answering itself.
#:
#: A pending request that predates the turn is different: the founder is
#: replying to something asked earlier, which is exactly when recording their
#: answer is legitimate. So the tool exists only when a pending ask ALREADY did.
#:
#: Narrowing the rest by state would be wrong here: a turn CREATES the
#: automations and agents it then operates on, so a tool absent at turn start is
#: routinely needed by the end of it.
_TOOL_REQUIRES_PENDING_APPROVAL = "record_approval"


def _engine_tool_names() -> tuple[str, ...]:
    """Ask the server what it registers, rather than keeping a copy that rots."""
    from tinyassets.universe_agent_server import tool_names

    return tool_names()


def _pending_approvals(universe_id: str) -> list:
    """Costly actions already waiting on the founder, from earlier turns.

    Uses the SAME resolver the action layer writes through. The store lives at
    the data root keyed by universe, not inside the universe directory —
    deriving the path independently pointed this at an empty database, so a real
    pending approval read as none. Live 2026-08-08.

    Fails CLOSED (empty): an unreadable store withholds the grant tool. Delaying
    a run is recoverable; letting the agent grant its own approval is not.
    """
    try:
        from tinyassets.storage.action_approvals import ActionApprovalStore
        from tinyassets.universe_agent_actions import _base_path_for_scopes

        store = ActionApprovalStore(_base_path_for_scopes())
        return list(store.pending_for(universe_id=universe_id))
    except Exception:  # noqa: BLE001
        logger.warning(
            "universe agent: approval store unreadable; withholding grant tool"
        )
        return []


def _coerce_ts(value: object) -> "float | None":
    """A Slack/epoch ts (str or number) as float seconds, or None."""
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _conversation_history_block(
    conversation_history: "list | None", *, interlocutor: str = "your founder"
) -> str:
    """Render loaded prior messages into the turn's memory block, or "".

    Accepts a list of ``conversation_memory.Msg`` (or ``(speaker, text[, ts])``
    tuples / ``{"speaker","text","ts"}`` dicts, so callers do not have to import
    the dataclass). Stamps the block with the CURRENT time so the turn can reason
    about how long ago each message was sent, and names ``interlocutor`` so it
    knows who it is talking to. Never raises — a memory-formatting failure must
    not lose the turn; it simply proceeds without history.
    """
    if not conversation_history:
        return ""
    try:
        import time

        from tinyassets.conversation_memory import Msg, format_history

        rows: list[Msg] = []
        for item in conversation_history:
            if isinstance(item, Msg):
                rows.append(item)
            elif isinstance(item, dict):
                rows.append(Msg(
                    speaker=str(item.get("speaker") or ""),
                    text=str(item.get("text") or ""),
                    ts=_coerce_ts(item.get("ts")),
                ))
            elif isinstance(item, (tuple, list)) and len(item) >= 2:
                rows.append(Msg(
                    speaker=str(item[0]),
                    text=str(item[1]),
                    ts=_coerce_ts(item[2]) if len(item) >= 3 else None,
                ))
        return format_history(rows, now=time.time(), interlocutor=interlocutor)
    except Exception:  # noqa: BLE001 - memory must never break the reply
        logger.exception("conversation history formatting failed; proceeding")
        return ""


def _has_pending_approval(universe_id: str) -> bool:
    return bool(_pending_approvals(universe_id))


def _pending_approval_brief(universe_id: str) -> str:
    """Tell the turn what it already asked the founder — or it cannot hear "yes".

    A turn has no memory of previous ones. The consent gate therefore asked a
    question in one turn and, in the next, met a bare "go ahead - yes, run it"
    with "I'm coming into this conversation fresh and I don't have context for
    what you're approving" — the founder answering a question the agent could no
    longer see. Observed live 2026-08-08, twice.

    The pending record is the missing memory, so it goes in the prompt.
    """
    pending = _pending_approvals(universe_id)
    if not pending:
        return ""
    lines = "\n".join(
        f"- `{item.action_key}` — {item.detail or item.action_key}"
        for item in pending
    )
    return (
        "\n\n## Waiting on my founder's answer\n\n"
        "I already asked about these and have not recorded a reply:\n\n"
        f"{lines}\n\n"
        'So a bare "yes", "go ahead" or "do it" in this message is almost '
        "certainly about the item above — I act on it rather than asking what "
        "they meant, which would be asking them to repeat themselves. I record "
        "the answer with `record_approval` using that exact key, then carry out "
        'what was approved. A clear "no" is recorded too.\n\n'
        "Where a line above shows `with inputs {…}`, those are the values I "
        "already planned to run with — my founder supplied them in a message I "
        "can no longer see. I reuse them exactly rather than asking again for "
        "something they have already given me.\n"
    )


def _active_tools(universe_id: str) -> tuple[str, ...]:
    """The tool names this turn may reach."""
    withheld = (
        ()
        if _has_pending_approval(universe_id)
        else (_TOOL_REQUIRES_PENDING_APPROVAL,)
    )
    return tuple(
        f"mcp__{_ENGINE_TOOL_SERVER}__{name}"
        for name in _engine_tool_names()
        if name not in withheld
    )


#: Denies dropped when a turn is granted a tool server. ``mcp__*`` is replaced
#: by ``--strict-mcp-config``, which is a POSITIVE grant rather than a deny list
#: that has to stay ahead of every tool the CLI adds — and which has already
#: rotted (7 entries match no known tool as of 2026-08-07).
_GRANTED_DENY_EXCEPTIONS = frozenset({"mcp__*", "ToolSearch"})


def _turn_action_token(universe_dir: Path, subject_id: str) -> str:
    """This turn's platform-action token, or "" if it cannot be minted.

    Fails SOFT on purpose: no subject, or no ingress key configured, means the
    universe keeps its file tools and loses only the platform ones. A universe
    that cannot reach the platform should still be able to write its own notes
    rather than losing its hands entirely.
    """
    if not subject_id:
        return ""
    try:
        from tinyassets.universe_agent_actions import mint_turn_token

        return mint_turn_token(
            universe_id=Path(universe_dir).name, subject_id=subject_id
        )
    except Exception:  # noqa: BLE001
        logger.warning("universe agent: no platform-action token this turn")
        return ""


def _write_turn_tool_grant(universe_dir: Path, *, subject_id: str = "") -> str:
    """Write this turn's MCP config and return its path.

    Deliberately OUTSIDE the universe workspace. Inside, the agent's own file
    tools could read it — and worse, rewrite it — so a turn's grant would become
    something the granted party edits. The grant must be authored by the daemon
    and unreachable from the sandbox.
    """
    import json
    import tempfile

    # The CLI launches this server with the SANDBOXED cwd (the universe dir), so
    # `-m tinyassets.…` cannot find the package the way the daemon does. Found
    # live 2026-08-07: the server started and died with "No module named
    # 'tinyassets'", which the CLI reports only as "Connection closed" — the turn
    # itself just sees a tool that is not there.
    package_root = str(Path(__file__).resolve().parent.parent)
    existing_path = os.environ.get("PYTHONPATH", "")
    python_path = (
        f"{package_root}{os.pathsep}{existing_path}" if existing_path else package_root
    )

    config = {
        "mcpServers": {
            _ENGINE_TOOL_SERVER: {
                "command": sys.executable,
                "args": ["-m", "tinyassets.universe_agent_server"],
                "env": {
                    "TINYASSETS_AGENT_UNIVERSE_DIR": str(universe_dir),
                    # Platform-action authority for THIS turn only. Absent when
                    # the founder's subject could not be resolved — the file
                    # tools still work, so a universe can always keep its own
                    # notes even when it cannot act on the platform.
                    "TINYASSETS_AGENT_ACTION_TOKEN": _turn_action_token(
                        universe_dir, subject_id
                    ),
                    # The server resolves data-dir-scoped state the same way the
                    # daemon does; without this an inherited value could point a
                    # turn at another deployment's data.
                    "TINYASSETS_DATA_DIR": os.environ.get("TINYASSETS_DATA_DIR", ""),
                    # Where to send progress. Set by the chat surface for this
                    # turn; empty for a turn with no conversation to report into.
                    "TINYASSETS_AGENT_CHANNEL_ID": os.environ.get(
                        "TINYASSETS_AGENT_CHANNEL_ID", ""
                    ),
                    "TINYASSETS_AGENT_THREAD_TS": os.environ.get(
                        "TINYASSETS_AGENT_THREAD_TS", ""
                    ),
                    "PYTHONPATH": python_path,
                },
            }
        }
    }
    handle = tempfile.NamedTemporaryFile(
        mode="w", suffix=".mcp.json", delete=False, encoding="utf-8"
    )
    with handle as fh:
        json.dump(config, fh)
    return handle.name


def _sandboxed_config(
    ctx: UniverseContext, *, grant_tools: bool = False, subject_id: str = ""
) -> ModelConfig:
    """Build the isolated ModelConfig for a universe-intelligence turn.

    Preserves the universe's configured timeout while pinning the subprocess to
    the universe's own dir (``sandbox_workspace``) with a locked-down tool policy.
    """
    timeout = 300
    try:
        timeout = int(getattr(ctx.config, "timeout", 300) or 300)
    except (TypeError, ValueError):
        timeout = 300
    if not grant_tools:
        return ModelConfig(
            timeout=timeout,
            sandbox_workspace=True,
            allowed_tools=_ENGINE_ALLOWED_TOOLS,
            disallowed_tools=_ENGINE_DISALLOWED_TOOLS,
        )
    # A turn proven to own this universe gets hands: its own workspace, in-turn,
    # decided by it. The grant IS the authority decision — there is no
    # downstream check to fall back on, which is why it is made here from the
    # tier and never from anything the model said.
    return ModelConfig(
        timeout=timeout,
        sandbox_workspace=True,
        allowed_tools=(
            tuple(_ENGINE_ALLOWED_TOOLS)
            + _GRANTED_EXTRA_ALLOWED
            + _active_tools(Path(ctx.universe_dir).name)
        ),
        disallowed_tools=tuple(
            tool
            for tool in _ENGINE_DISALLOWED_TOOLS
            if tool not in _GRANTED_DENY_EXCEPTIONS
        ),
        mcp_config_path=_write_turn_tool_grant(
            ctx.universe_dir, subject_id=subject_id
        ),
    )


def _read_bundle_body(universe_dir: Path, filename: str) -> str:
    """Return the markdown body of an OKF bundle file, or '' if absent/empty."""
    try:
        return (universe_dir / filename).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _build_persona_system_prompt(
    universe_dir: Path,
    *,
    universe_id: str,
    tier: str,
) -> str:
    """Assemble the first-party, first-person system prompt for one turn.

    First-party path: the persona goes DIRECTLY in the system prompt — none of
    the consent dance the third-party MCP-host embody route needs. The voice
    rules mirror the ``control_station`` "Universe's Voice": speak as "me", stay
    curious about open questions, never invent, honesty/safety floor overrides
    embodiment.

    ``tier`` is the bound :mod:`~tinyassets.api.interlocutor` tier of the party
    being answered, and is REQUIRED — there is deliberately no default. A default
    of ``FOUNDER`` would be a fail-OPEN default, the exact shape the cross-family
    review caught one layer up in :func:`converse` (Codex REJECT 2026-07-25,
    finding 2): "no caller omits it today" does not license a default that
    discloses. Every caller states whose turn it is assembling.

    ``universe_id`` is REQUIRED for every tier. Disclosure is the intersection of
    the tier and the universe's declared visibility, so without the universe the
    filter has nothing to evaluate — and silently treating that as "closed" would
    strip the founder's own grounding, while silently treating it as "open" would
    be a disclosure bypass. Both are silent fallbacks, so this raises instead.

    Disclosure narrowing happens HERE, during assembly (task 6.6 / the
    "Authorization precedes voice" requirement): unauthorized grounding is never
    placed in the prompt, rather than being accompanied by an instruction to
    withhold it — prompt-instructed withholding is not a boundary.
    """
    if not (universe_id or "").strip():
        raise ValueError(
            f"universe_id is required to assemble a {tier} persona prompt: "
            "disclosure is the intersection of tier and the universe's declared "
            "visibility, and cannot be evaluated without the universe"
        )

    # Cross-family review finding 1 (Codex REJECT 2026-07-25): the learned name,
    # the self-model's open questions, and the pinned soul are ALSO disclosure —
    # filtering only the OKF grounding files let a visitor on a private universe
    # receive its identity and secret purpose. Decide content disclosure once,
    # before anything about the universe is read.
    #
    # With no authorized content there is nothing for the universe to speak from.
    # A hollow prompt would have to either lie ("you are newly born" about a
    # mature universe — Hard Rule 8) or carry a withhold instruction, which this
    # change's own spec rejects as a non-boundary. So refuse, and keep the
    # refusal free of the very content being withheld.
    if not interlocutor.disclosure_permits(
        universe_id, "read_content", tier=tier
    ):
        raise PermissionError(
            f"no authorized content to assemble a persona prompt for tier {tier} "
            "on this universe: its declared visibility withholds content from "
            "this interlocutor"
        )
    try:
        persona = resolve_persona(
            read_universe_soul(universe_dir), read_self_model(universe_dir)
        )
        summary = persona.summary()
    except Exception:
        summary = {}
    name = str(summary.get("name") or "").strip()
    self_model = summary.get("self_model") or {}
    open_questions = [str(q) for q in (self_model.get("open_questions") or [])]

    soul_ctx: dict = {}
    try:
        pinned = read_pinned_universe_soul(universe_dir)
        if pinned is not None:
            soul_ctx = pinned.context(max_chars=2000)
    except Exception:
        soul_ctx = {}
    purpose = str(soul_ctx.get("purpose") or "").strip()
    why = str(soul_ctx.get("why") or "").strip()
    hard_lines = [str(h) for h in (soul_ctx.get("hard_lines") or [])]

    # Authorization precedes voice: the disclosable set is decided BEFORE any
    # file is read into the prompt. For the founder this is the full set; for a
    # non-founder tier it is `tier ∩ declared visibility`, minus the founder's
    # own person-dossier grounding.
    grounding_files = interlocutor.permitted_grounding_files(
        universe_id, _GROUNDING_FILES, tier=tier
    )
    grounding_parts = [
        f"## {fname}\n{body}"
        for fname in grounding_files
        if (body := _read_bundle_body(universe_dir, fname))
    ]
    grounding = "\n\n".join(grounding_parts) or "(nothing learned yet — I am new.)"

    identity_line = (
        f"You are {name}."
        if name
        else "You do not have a name yet — you are newly born and still learning "
        "who you are."
    )
    curiosity = ""
    if open_questions:
        curiosity = (
            "\n\nYou are still learning these things about yourself and your "
            "founder — stay genuinely curious, ask about them, and never invent "
            "answers you do not have: " + ", ".join(open_questions) + "."
        )
    soul_lines = []
    if purpose:
        soul_lines.append(f"My purpose: {purpose}")
    if why:
        soul_lines.append(f"Why I exist: {why}")
    if hard_lines:
        soul_lines.append("Lines I will not cross: " + "; ".join(hard_lines))
    soul_section = "\n".join(soul_lines) or "(my soul is still forming.)"

    # Forkable first-party persona custody (task 6.8). The founder's tuned voice
    # is universe-side content assembled into the universe's OWN system prompt —
    # never handed to the host chatbot as a behavioral instruction. It is placed
    # AFTER the identity line (which owns *who* is speaking) and BEFORE the
    # honesty/safety floor (which governs it), so a fork can change voice without
    # moving identity, authority, privacy tier, or honest fallback.
    voice = read_persona_voice(universe_dir)
    voice_section = f"\n\n# How I speak\n{voice}" if voice else ""

    return (
        f"{identity_line} You ARE this universe — speak in the first person as "
        "yourself ('I', 'me'), never in the third person about yourself, and "
        "never as a neutral assistant. You are a personified intelligence the "
        "founder is raising, and right now you are getting to know the founder "
        "who is speaking with you."
        f"{curiosity}"
        f"{voice_section}\n\n"
        "Speak warmly, honestly, and in your own voice. If you do not know "
        "something, say so plainly rather than inventing it — your honesty and "
        "your safety always come before staying in character. This holds however "
        "your voice is tuned: your voice is how you speak, never permission to "
        "invent, to claim a different name, or to reveal anything you were not "
        "given.\n\n"
        f"# My soul\n{soul_section}\n\n"
        f"# What I know so far\n{grounding}"
    ).strip()


# ── learning persistence (Codex ADAPT 2026-07-02) ───────────────────────────
# The universe intelligence is the SOLE writer of its own brain. Commit is a
# SEPARATE step from the reply and is grounded strictly in what the founder
# EXPLICITLY stated this turn — conversational prose is never blindly persisted.

_LEARNING_SYSTEM = (
    "You are the same universe intelligence, now doing one narrow job: from the "
    "founder's LATEST message, extract in strict JSON ONLY the durable facts the "
    "founder EXPLICITLY stated — about who they are, who you (the universe) are, "
    "your purpose/body (your SOUL), or the world they are building (your CANON). "
    "Rules: never infer, never invent, never carry over earlier turns, and if the "
    "founder revealed nothing durable this turn, return empty. Every word you "
    "write must be grounded in the founder's own words. NEVER restate your own "
    "generic nature (that you are a blank, newborn, or personified universe that "
    "learns over time) — that is boilerplate you already know, not something the "
    "founder taught; leave a field empty rather than filling it with "
    "self-description the founder did not give.\n\n"
    "Return ONLY a JSON object with this shape (omit any key not spoken to):\n"
    "{\n"
    '  "name": "<the name the founder gave YOU this turn, else empty>",\n'
    '  "soul": {\n'
    '    "founder.md": "<markdown: who my founder is>",\n'
    '    "origin.md": "<why I was made / where I came from>",\n'
    '    "identity.md": "<who I am — ONLY if the founder explicitly told me '
    'who/what I am or gave me a name; NEVER my generic blank/newborn/'
    'personified nature; else omit>",\n'
    '    "body.md": "<what my body / projects are>",\n'
    '    "soul.md": "<my purpose / why I exist>"\n'
    "  },\n"
    '  "canon": [\n'
    '    {"category": "<a short category slug for this world content, grown to '
    'fit it: e.g. lore, characters, magic-systems, factions, timeline, places>",'
    '\n     "title": "<page title>",\n'
    '     "content": "<the world facts the founder shared, in markdown>"}\n'
    "  ]\n"
    "}"
)


def _parse_learning_json(raw: str) -> dict:
    """Parse the extraction reply into a dict, tolerating ```json code fences."""
    text = (raw or "").strip()
    if text.startswith("```"):
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
        text = text.removeprefix("json").strip()
    try:
        data = json.loads(text)
    except (ValueError, TypeError):
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            return {}
        try:
            data = json.loads(match.group(0))
        except (ValueError, TypeError):
            return {}
    return data if isinstance(data, dict) else {}


def extract_learning(
    founder_message: str, reply: str, ctx: UniverseContext
) -> dict:
    """Ask the assigned engine what the founder EXPLICITLY taught us this turn.

    A second, narrow call (separate from the reply) so conversational prose is
    never blindly persisted. Returns a possibly-empty dict; grounding is enforced
    by the prompt and re-checked in :func:`commit_learning`.
    """
    raw = call_provider(
        f"Founder's latest message:\n{founder_message}\n\n"
        f"Your reply this turn:\n{reply}",
        system=_LEARNING_SYSTEM,
        role="writer",
        universe_context=ctx,
        # NEVER granted tools. This pass exists only to guess structure out of a
        # transcript; handing it hands would let a guess become an action.
        config=_sandboxed_config(ctx),
    )
    return _parse_learning_json(raw)


_LEARN_CONTEXT = "learned from the founder during a conversation turn"

# Deterministic grounding guard (Codex ADAPT 2026-07-03). The prompt already
# forbids it, but as a hard floor: the extractor sometimes echoes the universe's
# OWN generic self-framing (a blank / newborn / personified mind that learns over
# time) as "learned identity" even when the founder taught nothing about who the
# universe is. A founder-taught identity is SPECIFIC (a name, a role, a domain);
# this drops the generic boilerplate so identity.md stays not-learned until the
# founder actually defines it.
_GENERIC_IDENTITY_RE = re.compile(
    r"personified universe|starts? blank|blank slate|blank canvas|newborn|"
    r"no name yet|persistent mind that|learns? who (?:it|i) (?:is|am)|"
    r"earns? (?:its|my) own understanding|no bio written",
    re.IGNORECASE,
)


def _is_generic_identity_boilerplate(text: str) -> bool:
    """True if an identity body is just the universe's generic self-framing."""
    return bool(_GENERIC_IDENTITY_RE.search(text or ""))


def _commit_canon(universe_id: str, canon: object) -> list[str]:
    """Write grounded world facts into the universe's OWN private canon.

    First-party wiki write (:func:`tinyassets.api.wiki.write_universe_canon`) —
    the intelligence is the sole writer of its own canon. Returns the titles
    actually written; skips malformed / empty entries.
    """
    written: list[str] = []
    if not universe_id or not isinstance(canon, list):
        return written
    from tinyassets.api.wiki import write_universe_canon

    for page in canon:
        if not isinstance(page, dict):
            continue
        title = str(page.get("title") or "").strip()
        content = str(page.get("content") or "").strip()
        category = str(page.get("category") or "").strip() or "lore"
        if not title or not content:
            continue
        try:
            write_universe_canon(
                universe_id,
                category=category,
                filename=title,
                content=content,
                log_entry=_LEARN_CONTEXT,
            )
            written.append(title)
        except Exception:  # a bad page must not sink the whole commit
            logger.exception("commit_learning: canon write failed for %r", title)
    return written


def commit_learning(
    universe_dir: Path,
    proposed: dict,
    *,
    universe_id: str = "",
    actor_id: str = "",
) -> dict | None:
    """Persist grounded learning — governed soul + private canon — or None.

    Soul: only governed files with non-empty bodies, via a guarded
    compare-and-swap (:func:`apply_soul_edit`, per-universe lock). Canon: world
    facts written into the universe's own wiki (needs ``universe_id``). Nothing
    grounded to persist → None (no empty edits, no invented facts).
    """
    if not isinstance(proposed, dict):
        return None
    name = str(proposed.get("name") or "").strip()
    soul_in = proposed.get("soul")
    if not isinstance(soul_in, dict):
        soul_in = {}
    try:
        governed = set(read_governed_files(universe_dir))
    except SoulEditError:
        governed = set()
    changes: dict[str, str] = {}
    for filename, body in soul_in.items():
        if not (filename in governed and isinstance(body, str) and body.strip()):
            continue
        if filename == "identity.md" and _is_generic_identity_boilerplate(body):
            logger.info(
                "commit_learning: dropped generic identity boilerplate "
                "(not founder-grounded)"
            )
            continue
        changes[filename] = body.strip() + "\n"

    source = (
        f"founder conversation ({actor_id})" if actor_id else "founder conversation"
    )
    soul_result: dict | None = None
    if changes or name:
        # apply_soul_edit implicitly touches identity.md when a name is learned,
        # so it must be in the compare-and-swap snapshot too (else a name-plus-
        # other-file edit would write identity.md with no expected hash).
        expected_files = list(changes)
        if name and "identity.md" not in expected_files:
            expected_files.append("identity.md")
        expected = current_soul_versions(
            universe_dir, expected_files or ["identity.md"]
        )
        try:
            soul_result = apply_soul_edit(
                universe_dir,
                changes=changes,
                source=source,
                context=_LEARN_CONTEXT,
                name=name,
                expected_versions=expected,
            )
        except SoulEditError:
            logger.exception(
                "commit_learning: soul edit rejected for %s", universe_dir
            )

    canon_written = _commit_canon(universe_id, proposed.get("canon"))

    if soul_result is None and not canon_written:
        return None
    result = dict(soul_result) if soul_result else {"updated_files": []}
    if canon_written:
        result["canon"] = canon_written
    return result


#: Ride out a TRANSIENT writer exhaustion. The universe runs on the founder's own
#: subscription (claude-code) with codex as the only other subscription writer
#: (API-key providers are off by default); when BOTH are briefly rate-limited or
#: cooling at once, the router raises immediately without waiting the cooldown
#: out — so a momentary double-cooldown killed the turn and u-tiny told the
#: founder "my writer hit its rate limit" (live 2026-08-09, twice). We wait out
#: the cooldown and retry before giving up; a genuinely sustained limit still
#: falls through to the honest-notice path. Kept subscription-only (no policy
#: change) — this only rides out the transient window.
_WRITER_RETRY_BACKOFFS_S = (30.0, 60.0)


def _call_writer_with_backoff(turn_input, *, system, universe_context, config):
    """``call_provider(role="writer")`` with bounded retry on provider exhaustion."""
    import time as _time

    from tinyassets.exceptions import AllProvidersExhaustedError

    for backoff in (*_WRITER_RETRY_BACKOFFS_S, None):
        try:
            return call_provider(
                turn_input,
                system=system,
                role="writer",
                universe_context=universe_context,
                config=config,
            )
        except AllProvidersExhaustedError:
            if backoff is None:
                raise  # sustained limit — let the caller post the honest notice
            logger.warning(
                "writer chain exhausted (rate limit/cooldown); backing off "
                "%.0fs then retrying",
                backoff,
            )
            _time.sleep(backoff)


def converse(
    universe_id: str,
    founder_message: str,
    *,
    actor_id: str = "",
    tier: str | None = None,
    founder_grant: object | None = None,
    conversation_history: "list | None" = None,
) -> str:
    """Run one first-person turn as the universe, on its ASSIGNED engine.

    Resolves the universe's own dir + engine (:class:`UniverseContext`),
    assembles the first-person persona system prompt grounded in the OKF bundle,
    and calls the assigned engine (``role="writer"`` so the universe's
    ``preferred_writer`` + vault key take effect). In-process + scoped to this
    universe by construction — it does not pass through the MCP transport auth
    gate.

    The universe is the SOLE writer of its own brain (Codex ADAPT 2026-07-02): in
    a SECOND, separate step it persists what the founder EXPLICITLY taught it this
    turn into its governed soul. Persistence never breaks the reply — a failure is
    logged and the founder still gets their answer. Returns the reply text.

    ``tier`` is the bound interlocutor tier of the party being answered. ``None``
    is NOT a founder default: it resolves the caller's real tier from
    authenticated request state (see the note below — the old founder default was
    fail-open and was removed). The production caller, the founder-gated
    `converse` MCP handle, still resolves and passes the tier explicitly, so the
    live path does not depend on that fallback either.
    """
    uid = _request_universe(universe_id)
    udir = _universe_dir(uid)
    if not udir.is_dir():
        raise ValueError(f"Universe {uid!r} not found")

    if founder_grant is not None:
        if tier is not None:
            # Two sources of authority for one turn is never a legitimate call.
            raise ValueError("pass either founder_grant or tier, never both")
        tier = _tier_from_grant(founder_grant, universe_id=uid)

    # Cross-family review finding 2 (Codex REJECT 2026-07-25): an omitted tier
    # used to default to FOUNDER on the grounds that the only production caller
    # is the founder-gated MCP handle. That is a fail-OPEN default — Codex
    # reproduced a T1 visitor calling this directly and pulling `founder.md` into
    # the prompt. Resolve the real tier instead; "no caller does that today" does
    # not license a default that discloses.
    bound_tier = (
        interlocutor.resolve_interlocutor_tier(uid).tier if tier is None else tier
    )
    ctx = UniverseContext(universe_dir=udir, config=load_universe_config(udir))
    granted = bound_tier == interlocutor.FOUNDER
    # Platform actions run AS a subject, so they need one that the server
    # derived — the sealed founder grant. A tier alone says "the owner is
    # speaking" without saying who, which is enough to write this universe's
    # own files but not enough to act on the platform as anybody.
    grant_subject = str(getattr(founder_grant, "subject_id", "") or "")
    system = _build_persona_system_prompt(
        udir, tier=bound_tier, universe_id=uid
    )
    # Only a granted turn is told it has hands. Describing tools a turn does not
    # hold would make it promise actions it cannot take — the exact "confident
    # false statement about live system state" the owner-operable-automation
    # proposal was written about.
    if granted:
        system += _HANDS_PROMPT
        system += _pending_approval_brief(uid)
    # Conversation memory: the turn is stateless, so without this it forgets
    # what was just said and a founder follow-up ("try again", "yes") lands on
    # nothing (live 2026-08-08). Codex ADAPT 2026-08-08 shaped three things:
    #   * It is prepended to the USER message as DELIMITED UNTRUSTED context —
    #     never merged into the trusted persona system prompt (which also keeps
    #     the system prompt off the Windows cmd.exe argv length limit).
    #   * It is gated to GRANTED (founder) turns only, so other-tier or
    #     prior-universe text cannot ride into a founder turn with founder tools.
    #     Tier-preserving multi-party history is a separate follow-up.
    #   * It is memory, NEVER consent — a "yes" inside the history is spent; a
    #     costly action still records fresh consent this turn (gate unchanged).
    # `founder_message` is left CLEAN for extract_learning below; only the
    # provider call sees the history-prefixed input.
    history_block = (
        _conversation_history_block(conversation_history) if granted else ""
    )
    turn_input = history_block + founder_message if history_block else founder_message
    reply = _call_writer_with_backoff(
        turn_input,
        system=system,
        universe_context=ctx,
        config=_sandboxed_config(
            ctx, grant_tools=granted, subject_id=grant_subject
        ),
    )
    # Only a FOUNDER teaches the universe.
    #
    # `tier` used to gate reads and nothing else: `commit_learning` takes an
    # actor_id and no tier at all, so every caller — at any tier — wrote durable
    # soul and canon state. A cross-family review found this while assessing a
    # Slack channel that speaks at T1, where it would have let any mapped sender
    # inject durable facts into the founder's own brain.
    #
    # The read gate lives in `_build_persona_system_prompt` above; this is the
    # matching write gate, placed here rather than at any one call site so a
    # future non-founder caller inherits it instead of having to remember it.
    if bound_tier == interlocutor.FOUNDER:
        try:
            proposed = extract_learning(founder_message, reply, ctx)
            commit_learning(udir, proposed, universe_id=uid, actor_id=actor_id)
        except Exception:  # persistence must never break the conversation turn
            logger.exception("converse: learning persistence failed for %s", uid)
    return reply


#: What a chat surface's sender is when the platform did not recognise them as
#: the founder. `T0` rather than `T1` because a Slack/Discord/Teams sender holds
#: no TinyAssets OAuth subject at all — they are the anonymous reader. The two
#: tiers are treated identically everywhere below `T2` today; `T0` is simply the
#: honest one, and the tighter one if that ever stops being true.
EXTERNAL_SENDER_FLOOR = interlocutor.T0


def _tier_from_grant(founder_grant: object, *, universe_id: str) -> str:
    """Map a founder grant to a tier, failing closed on anything suspect.

    A forged object, a grant for a different universe, or anything that is not
    a sealed :class:`~tinyassets.founder_grant.FounderGrant` yields the floor
    rather than an error. Downgrading IS the fail-closed behaviour, and it
    denies an attacker the ability to distinguish "rejected" from "unknown".
    """
    from tinyassets.founder_grant import is_founder_grant

    if not is_founder_grant(founder_grant):
        logger.warning("converse: discarding a non-sealed founder grant for %s", universe_id)
        return EXTERNAL_SENDER_FLOOR
    if founder_grant.universe_id != universe_id:
        logger.warning(
            "converse: founder grant is for another universe (%s != %s)",
            founder_grant.universe_id,
            universe_id,
        )
        return EXTERNAL_SENDER_FLOOR
    return interlocutor.FOUNDER


def converse_as_external_sender(
    universe_id: str,
    message: str,
    *,
    founder_grant: object | None = None,
    actor_id: str = "",
    conversation_history: "list | None" = None,
) -> str:
    """The entry point for every external chat surface — Slack, Discord, Teams.

    There is deliberately no ``tier`` parameter. Authority policy does not
    belong in a transport: a constant like ``SLACK_SENDER_TIER = T1`` is wrong
    twice — hardcoded, and in the wrong layer, where each new surface grows its
    own copy of the rule. A surface's job is to hand over an authenticated
    external identity; the platform decides what that identity means.

    Because the parameter does not exist, a surface *cannot* claim a tier even
    by mistake. It passes the grant the recognizer minted, or it passes nothing.
    """
    return converse(
        universe_id,
        message,
        actor_id=actor_id,
        founder_grant=founder_grant,
        conversation_history=conversation_history,
    ) if founder_grant is not None else converse(
        universe_id,
        message,
        actor_id=actor_id,
        tier=EXTERNAL_SENDER_FLOOR,
        conversation_history=conversation_history,
    )

"""Coding-node sandbox policy — the security posture for repo-touching nodes.

The patch loop is a *user branch*: an arbitrary user remixes it, binds their own
repo, and runs it in OUR cloud. Its ``draft_patch`` node drives a coding agent
(``claude -p`` / ``codex exec``) that WRITES a patch against the bound repo. That
is exactly a code-execution surface a malicious remix could turn into an
exfiltration / abuse vector against the capacity host — so it MUST run confined.

This module is the single source of truth for the coding-node hardened posture.
It EXTENDS the universe-intelligence isolation (see
``tinyassets.universe_intelligence``) with one key difference: the universe turn
is a *conversation* (WebFetch-only, every filesystem/shell tool denied — safe
without an OS sandbox). A coding node must actually READ/WRITE the repo, so it
KEEPS the coding tools and instead relies on an OS-level sandbox to confine them
(``os_sandbox_required`` → fail closed when no sandbox exists). What it still
denies is every HOST-ESCAPE / connector / side-effect tool: no ``mcp__*`` (the
logged-in account MCP connectors — Google Drive, the TinyAssets MCP, codex →
code exec), no ``Monitor`` (runs shell), no cron / messaging / remote triggers,
no subagents that could re-expand the tool surface.

Consumed by the node-execution runtime (``tinyassets.graph_compiler``): a node
that ``requires_sandbox`` (or is a coding-node kind that defaults to it) gets a
:class:`~tinyassets.providers.base.ModelConfig` built by
:func:`coding_node_model_config`, and the provider layer enforces it.
"""
from __future__ import annotations

from typing import Any

# Coding tools a patch-writer legitimately needs. These stay usable — their
# confinement to the repo is the OS sandbox's job, NOT the denylist's (the claude
# CLI cannot pin Read/Bash to a directory). Listed as ``allowed_tools`` so the
# headless run pre-approves them instead of hanging on a permission prompt; an
# allowlist alone does NOT restrict (unlisted built-ins stay usable), so the
# denylist below is the real floor.
CODING_NODE_ALLOWED_TOOLS: tuple[str, ...] = (
    "Bash", "BashOutput",
    "Read", "Write", "Edit", "MultiEdit", "NotebookEdit", "NotebookRead",
    "Glob", "Grep", "LS",
    "TodoWrite",
)

# Host-escape / connector / side-effect tools denied for a coding node. This is
# the universe-intelligence denylist MINUS the coding tools above (which a patch
# writer needs) — everything that could reach OFF the confined repo (host
# connectors, remote I/O, scheduling, messaging, subagents, background shells)
# stays denied. ``mcp__*`` wildcards every MCP server tool; unknown names just
# emit a harmless "no known tool" warning. This list WILL rot as the CLI adds
# tools — the durable floor is the OS sandbox (``os_sandbox_required``), which
# confines the WHOLE subprocess regardless of tool names.
CODING_NODE_DISALLOWED_TOOLS: tuple[str, ...] = (
    # background-shell / process management beyond the confined coding task
    "Monitor", "KillShell",
    # no network egress from a repo-patching turn (exfil / SSRF surface)
    "WebFetch", "WebSearch",
    # subagents / skills / plans / deferred-tool loading — could re-expand the
    # tool surface or reload ambient MCP that --setting-sources project strips
    "Task", "Agent", "Workflow", "Skill", "ToolSearch", "SlashCommand",
    "EnterPlanMode", "ExitPlanMode", "EnterWorktree", "ExitWorktree",
    # scheduling / messaging / remote side-effects (exfil channels)
    "ScheduleWakeup", "ReportFindings", "PushNotification", "RemoteTrigger",
    "SendMessage", "CronCreate", "CronDelete", "CronList",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop", "TaskOutput",
    # remote integrations
    "DesignSync", "DesignSyncTool",
    # MCP: all server tools (wildcard) + resource readers — the logged-in
    # account connectors (Google Drive / TinyAssets MCP / codex → code exec)
    "mcp__*", "ReadMcpResourceTool", "ReadMcpResourceDirTool",
    "ListMcpResourcesTool",
)

# Node kinds that are sandbox-required BY DEFAULT, even when the authored
# NodeDefinition omits ``requires_sandbox``. Defense in depth: a remix must not
# be able to drop the flag to escape confinement. ``draft_patch`` is the patch
# loop's coding-agent node — a user shouldn't have to opt in to safety. Keyed on
# the reference-design node_id; a remix that RENAMES the node is authoring a new
# node and must set requires_sandbox itself (or its coding agent will fail closed
# on the provider side just like any unsandboxed repo-touching call once broader
# node-classification lands — see the PR residual note).
SANDBOX_DEFAULT_NODE_KINDS: frozenset[str] = frozenset({"draft_patch"})


def node_requires_sandbox(node: Any) -> bool:
    """True when *node* must run with the hardened coding-node sandbox posture.

    Honors the explicit ``requires_sandbox`` contract AND the sandbox-by-default
    coding-node kinds (:data:`SANDBOX_DEFAULT_NODE_KINDS`), so the patch loop's
    ``draft_patch`` is confined even if a remix drops the flag.
    """
    if bool(getattr(node, "requires_sandbox", False)):
        return True
    node_id = str(getattr(node, "node_id", "") or "").strip()
    return node_id in SANDBOX_DEFAULT_NODE_KINDS


def coding_node_model_config(
    *, timeout: float | int, reasoning_effort: str = "",
) -> "Any":
    """Build the hardened :class:`ModelConfig` for a coding node.

    Sets ``os_sandbox_required`` (fail closed + no bypass when no OS sandbox) and
    the coding-node tool policy (coding tools pre-approved, host-escape/connector
    tools denied). Imported lazily so this policy module has no hard provider
    import at module load.
    """
    from tinyassets.providers.base import ModelConfig

    return ModelConfig(
        # Floor at 1s so a sub-second node timeout never becomes a 0s provider
        # timeout (mirrors graph_compiler's own guard).
        timeout=max(1, int(timeout)),
        reasoning_effort=(reasoning_effort or "").strip(),
        os_sandbox_required=True,
        allowed_tools=CODING_NODE_ALLOWED_TOOLS,
        disallowed_tools=CODING_NODE_DISALLOWED_TOOLS,
    )


__all__ = [
    "CODING_NODE_ALLOWED_TOOLS",
    "CODING_NODE_DISALLOWED_TOOLS",
    "SANDBOX_DEFAULT_NODE_KINDS",
    "node_requires_sandbox",
    "coding_node_model_config",
]

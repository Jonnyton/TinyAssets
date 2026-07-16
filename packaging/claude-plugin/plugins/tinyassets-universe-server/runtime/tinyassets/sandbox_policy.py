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

# STABLE node-capability classifier (Codex S3 adapt). A node's ``node_kind``
# survives a remix that renames the node — so classifying sandbox-required by
# CAPABILITY (not the editable node_id) means a renamed patch-writing node
# CANNOT rename its way out of confinement. These kinds run a coding agent that
# writes/executes against a bound repo; they are always sandbox-required.
CODING_NODE_KINDS: frozenset[str] = frozenset({
    "coding", "repo_write", "repo_writing", "patch", "patch_write",
})

# node_id BACKSTOP only (not the primary signal): the reference-design
# ``draft_patch`` id, so the current patch-loop reference is confined even if its
# node_def has not yet been stamped with node_kind="coding". A remix that renames
# draft_patch is covered by the node_kind classifier above (the primary signal),
# not by this list — keying on node_id alone was the rename-escape hole Codex
# flagged. Cross-slice: S2 preserves the full node_def across export/import, so a
# stamped node_kind survives remix; the patch_loop reference draft_patch node
# should carry node_kind="coding" (add when S1 lands / S3 rebases onto it).
SANDBOX_DEFAULT_NODE_IDS: frozenset[str] = frozenset({"draft_patch"})


def _node_attr(node: Any, name: str) -> Any:
    """Read *name* from a NodeDefinition object OR a raw node_def dict.

    build_branch / list_branches classify from dicts (the persisted node_def
    shape) while graph_compiler classifies from NodeDefinition objects — both go
    through :func:`node_requires_sandbox`, so it must read either.
    """
    if isinstance(node, dict):
        return node.get(name)
    return getattr(node, name, None)


def node_requires_sandbox(node: Any) -> bool:
    """True when *node* must run with the hardened coding-node sandbox posture.

    Accepts a NodeDefinition object OR a raw node_def dict. Precedence (Codex S3
    adapt): (1) the STABLE ``node_kind`` capability — a coding/repo-writing kind
    is always sandbox-required, and it survives a rename so a remix cannot escape
    by renaming the node; (2) the explicit ``requires_sandbox`` contract; (3) the
    ``draft_patch`` node_id BACKSTOP for the current reference design (until its
    node_def carries node_kind="coding").
    """
    node_kind = str(_node_attr(node, "node_kind") or "").strip().lower()
    if node_kind in CODING_NODE_KINDS:
        return True
    if bool(_node_attr(node, "requires_sandbox")):
        return True
    node_id = str(_node_attr(node, "node_id") or "").strip()
    return node_id in SANDBOX_DEFAULT_NODE_IDS


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
    "CODING_NODE_KINDS",
    "SANDBOX_DEFAULT_NODE_IDS",
    "node_requires_sandbox",
    "coding_node_model_config",
]

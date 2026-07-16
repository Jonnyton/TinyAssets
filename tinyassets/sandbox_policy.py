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

# ── Capability taxonomy (Codex S3 REJECT R5) ─────────────────────────────────
# A node's declared capability, keyed on the STABLE ``node_kind`` (survives a
# remix rename — keying on node_id alone was the rename-escape hole). Three
# repo-TOUCHING capabilities, ALL of which require the per-job sandbox runner and
# therefore fail closed in this deployment (the runner is a FUTURE slice):
#   coding    — writes the repo (draft_patch)
#   repo_exec — runs arbitrary commands against the repo (verify_command)
#   repo_read — inspects/reads the repo (investigate)
# Everything else is a plain TEXT node (no repo access, runs today).
CODING_NODE_KINDS: frozenset[str] = frozenset({
    "coding", "repo_write", "repo_writing", "patch", "patch_write",
})
REPO_EXEC_NODE_KINDS: frozenset[str] = frozenset({
    "repo_exec", "run_command", "verify", "test", "shell", "exec",
})
REPO_READ_NODE_KINDS: frozenset[str] = frozenset({
    "repo_read", "inspect", "investigate",
})

# node_id BACKSTOPS for the S1 reference design (until it carries node_kind tags —
# see the PR note to the S1 lead). A remix that renames these is covered by the
# node_kind classifier above (the primary signal).
_CODING_BACKSTOP_IDS: frozenset[str] = frozenset({"draft_patch"})
_REPO_EXEC_BACKSTOP_IDS: frozenset[str] = frozenset({"verify"})
_REPO_READ_BACKSTOP_IDS: frozenset[str] = frozenset({"investigate"})

# Back-compat name kept for readers that imported it.
SANDBOX_DEFAULT_NODE_IDS: frozenset[str] = _CODING_BACKSTOP_IDS


def _node_attr(node: Any, name: str) -> Any:
    """Read *name* from a NodeDefinition object OR a raw node_def dict.

    build_branch / list_branches classify from dicts (the persisted node_def
    shape) while graph_compiler classifies from NodeDefinition objects — both go
    through the classifiers here, so they must read either.
    """
    if isinstance(node, dict):
        return node.get(name)
    return getattr(node, name, None)


def node_capability(node: Any) -> str:
    """Return the node's capability: ``coding`` | ``repo_exec`` | ``repo_read``
    | ``text``.

    Precedence: the STABLE ``node_kind`` capability first (survives a rename), then
    the explicit ``requires_sandbox`` flag (repo-write intent), then the
    reference-design node_id backstops.
    """
    kind = str(_node_attr(node, "node_kind") or "").strip().lower()
    if kind in CODING_NODE_KINDS:
        return "coding"
    if kind in REPO_EXEC_NODE_KINDS:
        return "repo_exec"
    if kind in REPO_READ_NODE_KINDS:
        return "repo_read"
    if bool(_node_attr(node, "requires_sandbox")):
        return "coding"
    node_id = str(_node_attr(node, "node_id") or "").strip()
    if node_id in _CODING_BACKSTOP_IDS:
        return "coding"
    if node_id in _REPO_EXEC_BACKSTOP_IDS:
        return "repo_exec"
    if node_id in _REPO_READ_BACKSTOP_IDS:
        return "repo_read"
    return "text"


def node_requires_sandbox_runner(node: Any) -> bool:
    """True when *node* is repo-touching (coding / repo_exec / repo_read) and so
    requires the per-job sandbox runner — i.e. it fails closed in this deploy."""
    return node_capability(node) != "text"


def node_coding_capability(node: Any) -> bool:
    """True only for a repo-WRITE (coding) node (the strongest capability)."""
    return node_capability(node) == "coding"


# Back-compat alias: "requires sandbox" now means "repo-touching → needs the
# per-job runner", so list/validate/get_status all classify the full repo set.
node_requires_sandbox = node_requires_sandbox_runner


def coding_nodes_runnable() -> "tuple[bool, str]":
    """Single source of truth (Codex S3 REJECT R4): can repo-touching nodes
    ACTUALLY run in this deployment?

    S3 honest state: **ALWAYS False.** There is no per-job sandbox runner
    subsystem (prepared per-job checkout + tenant/host path invisibility +
    restricted egress + resource limits + scoped credential brokering) — that
    runner is a FUTURE slice, NOT S3. A CLI being on PATH or bwrap/attestation
    being present does NOT make a repo node runnable: without the runner there is
    no checked-out workspace and no isolation, so coding/repo-exec/repo-read nodes
    fail closed on EVERY provider. validate + get_status + the node runtime all
    read this one function, so readiness never drifts from runtime truth. The
    future runner slice replaces the hard-coded False with real runner detection.
    """
    return False, (
        "repo-touching nodes (coding / repo-exec / repo-read) require the per-job "
        "sandbox runner subsystem (prepared per-job checkout + tenant isolation + "
        "scoped credentials + egress/resource limits), which is NOT available in "
        "this deployment. They fail closed on every provider until the runner "
        "lands (a future slice). Use a design-only / text-only branch."
    )


def coding_node_model_config(
    *, timeout: float | int, reasoning_effort: str = "",
) -> "Any":
    """Build the hardened :class:`ModelConfig` for a coding node.

    Defense-in-depth for WHEN the runner lands: sets ``os_sandbox_required`` (fail
    closed + no bypass without an OS sandbox) + the coding tool policy. In S3 a
    coding node fails closed at the node runtime BEFORE any provider call (no
    runner — see :func:`coding_nodes_runnable`), so this config's provider-level
    enforcement is a secondary belt-and-braces layer.
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


def text_node_model_config(
    *, timeout: float | int, reasoning_effort: str = "",
) -> "Any":
    """Build the text-only :class:`ModelConfig` for a NON-repo node.

    Uses a CLOSED tool surface (``closed_tool_surface`` → claude ``--tools ""``,
    per Anthropic's docs) so the node has NO built-in tools at all — pure text
    generation, incapable of repo write/exec/read. Coding tools are reachable
    ONLY through :func:`coding_node_model_config` (a coding-classified node), so
    capability is inseparable from classification (Codex S3 FINDING 1). Not
    ``os_sandbox_required`` — a tool-less text node has nothing to confine.
    """
    from tinyassets.providers.base import ModelConfig

    return ModelConfig(
        timeout=max(1, int(timeout)),
        reasoning_effort=(reasoning_effort or "").strip(),
        closed_tool_surface=True,
    )


__all__ = [
    "CODING_NODE_ALLOWED_TOOLS",
    "CODING_NODE_DISALLOWED_TOOLS",
    "CODING_NODE_KINDS",
    "REPO_EXEC_NODE_KINDS",
    "REPO_READ_NODE_KINDS",
    "SANDBOX_DEFAULT_NODE_IDS",
    "node_capability",
    "node_requires_sandbox_runner",
    "node_coding_capability",
    "node_requires_sandbox",
    "coding_nodes_runnable",
    "coding_node_model_config",
    "text_node_model_config",
]

"""Sandbox policy — capability classification + the fail-closed refusal.

PHASE SPLIT (Codex S3 REJECT r3 C5 — host-approved). S3 is ENFORCEMENT-ONLY. The
live Phase-1 surface here is small and auditable:

  * :func:`node_capability` / :func:`node_requires_sandbox_runner` — classify a
    node as ``coding`` (repo-write) / ``repo_exec`` (run commands) / ``repo_read``
    (inspect) / ``text``, keyed on the STABLE ``node_kind`` (rename-proof).
  * :func:`coding_nodes_runnable` — the ONE readiness truth: **False** in this
    deploy (no per-job sandbox runner). validate + get_status + the node runtime
    all read it, so readiness never drifts from runtime.
  * :func:`text_node_model_config` — the CLOSED text surface for the only nodes
    that actually run (text): no tools at all (claude ``--tools ""``).

Every repo-touching node FAILS CLOSED deterministically at the FIRST gate in
``tinyassets.graph_compiler`` — before any ModelConfig is constructed, before any
provider/scratch/env code runs. So the Phase-2 coding-EXECUTION plumbing below —
:func:`coding_node_model_config` (the Bash-granting os_sandbox config),
:data:`CODING_NODE_ALLOWED_TOOLS`, and the provider-side attestation / sanitized
vault-env / bwrap-bypass paths — is PROVABLY UNREACHABLE in Phase 1: it is
guarded behind that refusal and is retained only as the contract the FUTURE
per-job sandbox RUNNER slice (Phase 2) will build against. Do NOT treat it as a
live path; the runner (prepared per-job checkout + tenant isolation + scoped
credentials + egress/resource limits) is a separate, host-approved slice.
"""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable

# NOTE (Codex S3 r9 #4 — dead-stack removal): the coding tool policy
# (CODING_NODE_ALLOWED_TOOLS / CODING_NODE_DISALLOWED_TOOLS) and the coding
# ModelConfig builder lived here to CONFIGURE a repo-writing coding agent's tool
# surface. Repo-touching nodes fail closed at the graph choke point before any
# config is built (coding_nodes_runnable() is False — no per-job runner), so that
# execution config is unreachable. It has been REMOVED as dead security surface;
# git history preserves it as the contract the Phase-2 per-job runner slice will
# rebuild. Live Phase-1 surface here = classifier + coding_nodes_runnable +
# text_node_model_config.

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

# The recognized TEXT node_kinds (empty == the plain-prompt default). A non-empty
# node_kind outside the union of these + the repo-touching sets is UNKNOWN and
# must be REJECTED at the authoring boundary (Codex S3 r11 #2) — never silently
# downgraded to the least-restricted "text" class. ``node_kind_is_known`` is the
# single vocabulary check the authoring surfaces share.
TEXT_NODE_KINDS: frozenset[str] = frozenset({
    "", "text", "prompt", "prompt_template", "llm", "writer", "generate",
    "summarize", "transform", "classify", "extract", "opaque", "invoke",
})

# The complete recognized node_kind vocabulary (repo-touching ∪ text).
_KNOWN_NODE_KINDS: frozenset[str] = (
    CODING_NODE_KINDS | REPO_EXEC_NODE_KINDS | REPO_READ_NODE_KINDS
    | TEXT_NODE_KINDS
)

# The most-dangerous capability: a ``source_code`` node runs arbitrary Python
# IN-PROCESS with full builtins (graph_compiler._build_source_code_node → exec).
# It is a host-code-execution surface stronger than a subprocess coding agent, so
# it is repo-touching and fails closed in Phase 1 like coding/repo_exec/repo_read.
_SOURCE_EXEC_CAPABILITY = "source_exec"


def _node_attr(node: Any, name: str) -> Any:
    """Read *name* from a NodeDefinition object OR a raw node_def dict.

    build_branch / list_branches classify from dicts (the persisted node_def
    shape) while graph_compiler classifies from NodeDefinition objects — both go
    through the classifiers here, so they must read either.
    """
    if isinstance(node, dict):
        return node.get(name)
    return getattr(node, name, None)


def node_has_source_code(node: Any) -> bool:
    """True when the node carries non-empty in-process ``source_code``.

    Derived from the node's ACTUAL executable nature, NEVER from user-editable
    ``node_kind`` / ``requires_sandbox`` metadata — that mutable metadata was the
    Codex S3 r11 host-code-execution escape (approve a source_code node, then
    reclassify it ``text`` to skip the sandbox gate while approval still rode the
    unchanged source hash). A source_code node is in-process host code and can
    never be made to look safe by editing its metadata.
    """
    return bool(str(_node_attr(node, "source_code") or "").strip())


def node_kind_is_known(node_kind: Any) -> bool:
    """True when *node_kind* is in the recognized vocabulary (repo-touching ∪
    text ∪ empty). Authoring surfaces reject an UNKNOWN non-empty node_kind
    rather than silently downgrading it to the least-restricted ``text`` class
    (Codex S3 r11 #2)."""
    return str(node_kind or "").strip().lower() in _KNOWN_NODE_KINDS


def node_capability(node: Any) -> str:
    """Return the node's capability: ``source_exec`` | ``coding`` | ``repo_exec``
    | ``repo_read`` | ``text``.

    Precedence (most-restrictive first, unspoofable signals before mutable ones):
    an in-process ``source_code`` adapter (host code, ALWAYS sandbox-required
    regardless of metadata), then the STABLE ``node_kind`` capability (survives a
    rename), then the explicit ``requires_sandbox`` flag, then the reference-design
    node_id backstops.
    """
    # HIGHEST precedence, unspoofable (Codex S3 r11 #1): a source_code node is
    # in-process host-code execution. No user-controlled metadata can downgrade
    # it below sandbox-required.
    if node_has_source_code(node):
        return _SOURCE_EXEC_CAPABILITY
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


# Sandbox class ordering (least → most restricted). Used to detect a security
# DOWNGRADE at the mutation surface (Codex S3 r11 #3): metadata may escalate a
# node's sandbox class but never lower it. ``source_exec`` is the strongest
# (in-process host code); ``text`` is the only runnable class in Phase 1.
_CAPABILITY_RANK: dict[str, int] = {
    "text": 0,
    "repo_read": 1,
    "repo_exec": 2,
    "coding": 3,
    _SOURCE_EXEC_CAPABILITY: 4,
}


def capability_rank(capability: str) -> int:
    """Return the sandbox-class rank of *capability* (higher == more restricted).

    An unrecognized capability ranks as the MAXIMUM (fail closed) so a future
    capability is never treated as a downgrade target."""
    return _CAPABILITY_RANK.get(
        str(capability or "").strip().lower(), max(_CAPABILITY_RANK.values()),
    )


def node_requires_sandbox_runner(node: Any) -> bool:
    """True when *node* is repo-touching / host-code-executing (source_exec /
    coding / repo_exec / repo_read) and so requires the per-job sandbox runner —
    i.e. it fails closed in this deploy. Only a plain ``text`` node runs."""
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
        "repo-touching / in-process code nodes (source_code / coding / repo-exec "
        "/ repo-read) require the per-job sandbox runner subsystem (prepared "
        "per-job checkout + tenant isolation + scoped credentials + egress/resource "
        "limits), which is NOT available in this deployment. They fail closed on "
        "every provider until the runner lands (a future slice). Use a design-only "
        "/ text-only (prompt_template) branch."
    )


def branch_sandbox_status(
    node_defs: Iterable[Any],
) -> "tuple[bool, list[str], list[str]]":
    """Classify a branch's nodes for the per-job sandbox-runner gate.

    Returns ``(sandbox_blocked, repo_node_ids, warnings)``. A repo-touching node
    (coding / repo_exec / repo_read) with no per-job runner
    (:func:`coding_nodes_runnable` == ``False``) blocks the branch. Classification
    errors fail CLOSED (``sandbox_blocked=True``).

    This is the SINGLE readiness computation shared by ``validate_branch`` AND the
    ``run_branch`` / ``resume`` / version-pinned enqueue paths, so a queue-time
    refusal can never drift from validate-time readiness or the runtime choke
    point — all three read the same truth.
    """
    warnings: list[str] = []
    try:
        repo_nodes = sorted(
            str(_node_attr(nd, "node_id") or "")
            for nd in node_defs
            if node_requires_sandbox_runner(nd)
        )
        repo_nodes = [nid for nid in repo_nodes if nid]
        if repo_nodes:
            runnable, reason = coding_nodes_runnable()
            if not runnable:
                warnings.append(
                    f"This branch has {len(repo_nodes)} repo-touching node(s) "
                    f"({', '.join(repo_nodes)}) that read/exec/write a repo. "
                    f"{reason}"
                )
                return True, repo_nodes, warnings
        return False, repo_nodes, warnings
    except Exception as exc:  # noqa: BLE001 — any check error ⇒ fail closed
        warnings.append(
            f"Sandbox capability check failed ({type(exc).__name__}: {exc}); "
            "treating the branch as NOT runnable (fail closed)."
        )
        return True, [], warnings


def text_node_model_config(
    *, timeout: float | int, reasoning_effort: str = "",
) -> "Any":
    """Build the text-only :class:`ModelConfig` for a NON-repo node.

    Uses a CLOSED tool surface (``closed_tool_surface`` → claude ``--tools ""``,
    per Anthropic's docs) so the node has NO built-in tools at all — pure text
    generation, incapable of repo write/exec/read. This is the ONLY runnable-node
    config: a repo-touching (coding-classified) node fails closed at the graph
    choke point before any config is built, so capability is inseparable from
    classification. Not ``os_sandbox_required`` — a tool-less node has nothing to
    confine.
    """
    from tinyassets.providers.base import ModelConfig

    return ModelConfig(
        timeout=max(1, int(timeout)),
        reasoning_effort=(reasoning_effort or "").strip(),
        closed_tool_surface=True,
    )


__all__ = [
    "CODING_NODE_KINDS",
    "REPO_EXEC_NODE_KINDS",
    "REPO_READ_NODE_KINDS",
    "TEXT_NODE_KINDS",
    "SANDBOX_DEFAULT_NODE_IDS",
    "node_capability",
    "node_has_source_code",
    "node_kind_is_known",
    "capability_rank",
    "node_requires_sandbox_runner",
    "node_coding_capability",
    "node_requires_sandbox",
    "coding_nodes_runnable",
    "branch_sandbox_status",
    "text_node_model_config",
]

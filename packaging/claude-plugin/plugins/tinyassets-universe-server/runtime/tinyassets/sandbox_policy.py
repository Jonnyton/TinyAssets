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


def _resolve_opaque_adapter_capability(node: Any, domain_id: str) -> str | None:
    """Return the REGISTERED opaque adapter's capability for *node*, or ``None``
    when the node is not an opaque adapter (dispatched by its own source/template
    adapter, or its ``(domain_id, node_id)`` is not registered).

    Returns ``host_only`` for a daemon-internal adapter, ``opaque_unclassified``
    for a registered callable with no/typo'd declared capability, else the
    declared capability class. Derived from the REGISTERED CALLABLE — invisible to
    user-controlled node fields (Codex S3 r12/r13/r14)."""
    # A source/template node is dispatched by that adapter, not an opaque one.
    if str(_node_attr(node, "source_code") or "").strip():
        return None
    if str(_node_attr(node, "prompt_template") or "").strip():
        return None
    dom = str(domain_id or "").strip()
    nid = str(_node_attr(node, "node_id") or "").strip()
    if not dom or not nid:
        return None
    # Best-effort: import the effectors package so platform opaque callables are
    # registered before we resolve (same registration side-effect the compiler
    # relies on). Guarded — a missing optional dep never breaks classification.
    try:
        import tinyassets.effectors  # noqa: F401
    except Exception:  # noqa: BLE001
        pass
    try:
        from tinyassets.domain_registry import (
            resolve_domain_callable,
            resolve_domain_capability,
            resolve_domain_host_only,
        )
    except Exception:  # noqa: BLE001
        return None
    if resolve_domain_callable(dom, nid) is None:
        return None  # not an opaque adapter — a plain node in a domain branch
    if resolve_domain_host_only(dom, nid):
        return _HOST_ONLY
    cap = resolve_domain_capability(dom, nid)
    if not cap:
        return _OPAQUE_UNCLASSIFIED
    return str(cap).strip().lower() or _OPAQUE_UNCLASSIFIED


def effective_node_capability(node: Any, domain_id: str = "") -> str:
    """Capability INCLUDING opaque-adapter resolution — MOST-RESTRICTIVE wins, and
    REGISTERED TRUST DOMINATES mutable metadata (Codex S3 r12/r13/r14 #1).

    :func:`node_capability` classifies by the node's own (user-controlled) fields
    (source_code / node_kind / requires_sandbox / node_id). But an OPAQUE adapter's
    capability is the nature of its REGISTERED CALLABLE — invisible to those fields:
    a repo-reading ``read_repo_files`` node looks like plain text, and a host-only
    ``universe_cycle_wrapper`` node could be tagged ``node_kind="coding"``.

    PRECEDENCE (the r14 fix): resolve the registered adapter FIRST, THEN combine —
    never let mutable node metadata reduce the restriction below what the adapter
    demands. ``host_only`` and ``opaque_unclassified`` ALWAYS dominate (metadata
    can never lower them). For a declared adapter capability, the effective class is
    the MOST RESTRICTIVE rank of (registered adapter capability, node-metadata
    capability) — so node metadata may only ESCALATE restriction, never reduce it.
    A node that is not an opaque adapter keeps its node-derived capability
    (``source_exec`` for source_code is itself derived from the actual field and
    already unspoofable).
    """
    base = node_capability(node)
    adapter_cap = _resolve_opaque_adapter_capability(node, domain_id)
    if adapter_cap is None:
        return base  # not an opaque adapter — node-derived capability stands
    # host_only / unclassified ALWAYS dominate — mutable metadata can never reduce
    # below them (the r14 escape: node_kind="coding" must NOT beat host_only).
    if adapter_cap in (_HOST_ONLY, _OPAQUE_UNCLASSIFIED):
        return adapter_cap
    # A declared adapter capability combines with node metadata at the MOST
    # RESTRICTIVE rank: metadata may escalate (coding > repo_read) but a
    # node_kind="text" can never reduce a repo_read adapter back to text.
    return adapter_cap if capability_rank(adapter_cap) >= capability_rank(base) else base


# A registered opaque adapter with NO declared capability class (Codex S3 r12 #1).
# It is UNCLASSIFIED — the choke-point refuses it unconditionally (not even the
# Phase-2 runner can vouch for an adapter whose capability nobody declared).
_OPAQUE_UNCLASSIFIED = "opaque_unclassified"

# A HOST-ONLY (daemon-internal) opaque adapter (Codex S3 r13 #1). A user-authored
# branch may not run it; only a trusted (daemon) compile may. For any user-branch
# classification surface (validate / enqueue) it is BLOCKED.
_HOST_ONLY = "host_only"

# Sandbox class ordering (least → most restricted). Used to detect a security
# DOWNGRADE at the mutation surface (Codex S3 r11 #3): metadata may escalate a
# node's sandbox class but never lower it. ``source_exec`` is the strongest
# (in-process host code); ``text`` is the only runnable class in Phase 1. An
# unclassified opaque adapter, and a host-only adapter reached by a user branch,
# rank at the maximum (fail closed).
_CAPABILITY_RANK: dict[str, int] = {
    "text": 0,
    "repo_read": 1,
    "repo_exec": 2,
    "coding": 3,
    _SOURCE_EXEC_CAPABILITY: 4,
    _OPAQUE_UNCLASSIFIED: 5,
    _HOST_ONLY: 6,
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
    domain_id: str = "",
) -> "tuple[bool, list[str], list[str]]":
    """Classify a branch's nodes for the per-job sandbox-runner gate.

    Returns ``(sandbox_blocked, repo_node_ids, warnings)``. A node whose EFFECTIVE
    capability (source/metadata classification PLUS opaque-adapter resolution —
    Codex S3 r12 #1) is not ``text`` blocks the branch: a repo-touching adapter
    (coding / repo_exec / repo_read / source_exec) has no per-job runner
    (:func:`coding_nodes_runnable` == ``False``), and an UNCLASSIFIED opaque
    adapter fails closed unconditionally. Classification errors fail CLOSED.

    ``domain_id`` (the Branch-level domain) lets opaque adapters be resolved by
    their registered capability. This is the SINGLE readiness computation shared
    by ``validate_branch`` AND the ``run_branch`` / ``resume`` / version-pinned
    enqueue paths, so a queue-time refusal can never drift from validate-time
    readiness or the runtime choke point.
    """
    warnings: list[str] = []
    try:
        repo_nodes: list[str] = []
        host_only_nodes: list[str] = []
        unclassified_nodes: list[str] = []
        for nd in node_defs:
            cap = effective_node_capability(nd, domain_id)
            if cap == "text":
                continue
            nid = str(_node_attr(nd, "node_id") or "").strip()
            if nid:
                repo_nodes.append(nid)
            # Codex S3 r14 #4: track the ACTUAL host-only / unclassified node IDs
            # separately — a mixed branch must not report every non-text node as
            # host-only just because one host-only adapter is present.
            if cap == _OPAQUE_UNCLASSIFIED and nid:
                unclassified_nodes.append(nid)
            if cap == _HOST_ONLY and nid:
                host_only_nodes.append(nid)
        repo_nodes = sorted(repo_nodes)
        if host_only_nodes:
            warnings.append(
                f"This branch selects HOST-ONLY (daemon-internal) adapter node(s) "
                f"({', '.join(sorted(host_only_nodes))}) that a user-authored "
                "branch may not run; refusing (fail closed)."
            )
            return True, repo_nodes, warnings
        if unclassified_nodes:
            warnings.append(
                f"This branch has opaque adapter node(s) "
                f"({', '.join(sorted(unclassified_nodes))}) with NO declared "
                "sandbox capability; refusing to run an unclassified adapter "
                "(fail closed)."
            )
            return True, repo_nodes, warnings
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


def user_branch_capability_rejections(
    node_defs: Iterable[Any],
    domain_id: str = "",
) -> "list[str]":
    """Return rejection messages for a USER-authored branch selecting a capability
    a user branch may NEVER select or run (Codex S3 r14 #2). Empty list == OK.

    Rejects a node whose EFFECTIVE capability (registered-trust-dominates, so a
    spoofed / capability-escalated node still resolves to the dominant class) is
    ``host_only`` (daemon-internal) or ``opaque_unclassified`` (registered adapter
    with no / typo'd declared capability). Repo-touching nodes (source_exec /
    coding / repo_exec / repo_read) are AUTHORABLE — they run when the per-job
    runner lands and are blocked at RUN by :func:`branch_sandbox_status` / the
    choke point, not at authoring — so they are NOT rejected here.

    FAIL CLOSED: any classification error yields a rejection (never a silent
    pass). This is the single validator invoked before every persistence path.
    """
    rejections: list[str] = []
    try:
        for nd in node_defs:
            nid = str(_node_attr(nd, "node_id") or "").strip() or "?"
            try:
                cap = effective_node_capability(nd, domain_id)
            except Exception as exc:  # noqa: BLE001 — classification error ⇒ closed
                rejections.append(
                    f"Node '{nid}': capability classification failed "
                    f"({type(exc).__name__}: {exc}); refusing to persist "
                    "(fail closed)."
                )
                continue
            if cap == _HOST_ONLY:
                rejections.append(
                    f"Node '{nid}' selects a HOST-ONLY (daemon-internal) adapter "
                    "that a user-authored branch may not select or run."
                )
            elif cap == _OPAQUE_UNCLASSIFIED:
                rejections.append(
                    f"Node '{nid}' selects an opaque adapter with NO declared "
                    "sandbox capability (unclassified); refusing to persist "
                    "(fail closed)."
                )
    except Exception as exc:  # noqa: BLE001 — iteration error ⇒ fail closed
        rejections.append(
            f"User-branch capability check failed ({type(exc).__name__}: {exc}); "
            "refusing to persist (fail closed)."
        )
    return rejections


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
    "effective_node_capability",
    "node_has_source_code",
    "node_kind_is_known",
    "capability_rank",
    "node_requires_sandbox_runner",
    "node_coding_capability",
    "node_requires_sandbox",
    "coding_nodes_runnable",
    "branch_sandbox_status",
    "user_branch_capability_rejections",
    "text_node_model_config",
]

"""YAML serializer for Phase 7 git-tracked artifacts.

Round-trip contract: ``to_yaml_payload`` + ``from_yaml_payload`` form
an identity over the subset of fields a Branch or Goal carries. The
YAML shape is the **public contract** — it's what humans read on
GitHub and what review bots lint. Fields that are purely server-side
(``created_at``, ``updated_at``, aggregate ``stats``) are preserved
in the payload so the SQLite cache can rehydrate exactly, but the
layout foregrounds the editable fields (``name``, ``description``,
``tags``, ``node_defs``, ``edges``, ``state_schema``).

Branch YAML layout:

```yaml
id: <branch_def_id>
name: Research paper pipeline
description: ...
author: dev-2
domain_id: workflow
goal_id: produce-academic-paper
tags: [research, academic]
version: 3
parent_def_id: null
entry_point: literature_scan
state_schema:
  - {name: outline, type: str}
  - {name: section_name, type: str}
nodes:
  - id: literature_scan
    # per-file for cross-branch reuse. Empty ref = inlined node body.
    path: nodes/research-paper-pipeline/literature_scan.yaml
edges:
  - {from: START, to: literature_scan}
  - {from: literature_scan, to: section_drafter}
  - {from: section_drafter, to: END}
conditional_edges: []
published: false
stats:
  fork_count: 0
  run_count: 0
  avg_quality_score: 0.0
created_at: "2026-04-13T..."
updated_at: "2026-04-13T..."
```

Each entry in the ``nodes:`` list points at a separate file that
carries that node's prompt/source/phase body. Per-node files live
at ``nodes/<branch_slug>/<node_id>.yaml`` (spec §What-stays). A
companion Branch payload keeps the ordered graph metadata
(``graph_nodes``) that LangGraph needs for compilation.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from tinyassets.branches import (
    BranchDefinition,
    ConditionalEdge,
    EdgeDefinition,
    GraphNodeRef,
    NodeDefinition,
)

__all__ = [
    "branch_from_yaml_payload",
    "branch_to_yaml_payload",
    "goal_from_yaml_payload",
    "goal_to_yaml_payload",
    "node_from_yaml_payload",
    "node_to_yaml_payload",
]


def branch_to_yaml_payload(
    branch: BranchDefinition,
    *,
    branch_slug: str,
    externalize_nodes: bool = True,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Serialize a BranchDefinition into the git-tracked YAML shape.

    Returns ``(branch_payload, node_payloads)``. When
    ``externalize_nodes`` is true each ``NodeDefinition`` becomes its
    own payload and the branch payload only references it by path.
    When false (smaller branches, tests), node bodies inline in the
    branch payload.
    """
    node_payloads: list[dict[str, Any]] = []
    node_entries: list[dict[str, Any]] = []
    for node in branch.node_defs:
        if externalize_nodes:
            node_payloads.append(node_to_yaml_payload(node))
            node_entries.append({
                "id": node.node_id,
                "path": (
                    f"nodes/{branch_slug}/{node.node_id}.yaml"
                ),
            })
        else:
            node_entries.append({
                "id": node.node_id,
                "inline": node_to_yaml_payload(node),
            })

    payload: dict[str, Any] = {
        "id": branch.branch_def_id,
        "name": branch.name,
        "description": branch.description,
        "author": branch.author,
        "domain_id": branch.domain_id,
        "goal_id": branch.goal_id,
        "tags": list(branch.tags),
        "skills": list(getattr(branch, "skills", []) or []),
        "version": branch.version,
        "parent_def_id": branch.parent_def_id,
        "entry_point": branch.entry_point,
        "state_schema": list(branch.state_schema),
        "nodes": node_entries,
        "graph_nodes": [gn.to_dict() for gn in branch.graph_nodes],
        "edges": [_edge_to_compact(e) for e in branch.edges],
        "conditional_edges": [
            c.to_dict() for c in branch.conditional_edges
        ],
        "published": branch.published,
        "visibility": getattr(branch, "visibility", "public") or "public",
        "stats": dict(branch.stats),
        "created_at": branch.created_at,
        "updated_at": branch.updated_at,
    }
    return payload, node_payloads


def branch_from_yaml_payload(
    payload: dict[str, Any],
    node_payloads: dict[str, dict[str, Any]] | None = None,
) -> BranchDefinition:
    """Reconstitute a BranchDefinition from a YAML payload.

    ``node_payloads`` maps node_id → node payload for externalized
    nodes. Entries with an ``inline`` field override lookups; entries
    with a ``path`` field require an entry in ``node_payloads``.
    """
    node_payloads = node_payloads or {}

    node_defs: list[NodeDefinition] = []
    for entry in payload.get("nodes", []) or []:
        node_id = (entry or {}).get("id", "")
        inline = (entry or {}).get("inline")
        if inline is not None:
            node_defs.append(node_from_yaml_payload(inline))
            continue
        hit = node_payloads.get(node_id)
        if hit is None:
            # Missing file on disk; tolerate the gap rather than
            # crash — caller may be mid-pull with an incomplete
            # checkout. Downstream validate() surfaces the empty body.
            node_defs.append(NodeDefinition(
                node_id=node_id,
                display_name=entry.get("display_name", node_id),
            ))
            continue
        node_defs.append(node_from_yaml_payload(hit))

    graph_nodes = [
        GraphNodeRef(**gn)
        for gn in (payload.get("graph_nodes") or [])
    ]
    edges = [
        _edge_from_compact(e) for e in (payload.get("edges") or [])
    ]
    cond_edges = [
        _conditional_edge_from_dict(c)
        for c in (payload.get("conditional_edges") or [])
    ]

    # Reserved identity is unforgeable across ALL create paths, including YAML
    # import (Codex r15 addendum B): a non-system caller must not author as the
    # reserved seed author, or the next seed's reserved-author stray-row prune
    # would DELETE their imported branch (identity forgery + griefing deletion).
    from tinyassets.branch_designs import _sanitize_reserved_author

    branch = BranchDefinition(
        branch_def_id=payload.get("id") or "",
        name=payload.get("name", ""),
        description=payload.get("description", ""),
        author=_sanitize_reserved_author(payload.get("author")) or "anonymous",
        domain_id=payload.get("domain_id", "workflow"),
        goal_id=payload.get("goal_id", ""),
        tags=list(payload.get("tags", []) or []),
        skills=list(payload.get("skills", []) or []),
        version=int(payload.get("version", 1) or 1),
        parent_def_id=payload.get("parent_def_id"),
        entry_point=payload.get("entry_point", ""),
        state_schema=list(payload.get("state_schema", []) or []),
        graph_nodes=graph_nodes,
        edges=edges,
        conditional_edges=cond_edges,
        node_defs=node_defs,
        published=bool(payload.get("published", False)),
        visibility=(payload.get("visibility") or "public"),
        stats=dict(payload.get("stats", {}) or {}),
        created_at=payload.get("created_at") or "",
        updated_at=payload.get("updated_at") or "",
    )
    return branch


# Codex r17 #1 (CLASS fix): the node YAML round-trip must NOT silently drop any
# execution/security/routing field. The old hand-maintained allow-list dropped
# ``requires_sandbox`` + ``effects`` (a round-trip disarmed every sandboxed repo
# node and removed both GitHub effect declarations) — the same class as the r16
# dropped-``fallback`` bug. These functions now drive off the NodeDefinition
# dataclass itself, so EVERY current AND future field round-trips by
# construction. ``test_node_yaml_round_trip_is_field_for_field_identical`` +
# ``test_reference_artifact_survives_full_yaml_round_trip`` close the class.

# Node dataclass defaults, by field name — a value equal to its default is
# omitted from the YAML to keep files small (from_dict restores it).
_NODE_FIELD_DEFAULTS: dict[str, Any] = {
    f.name: (
        f.default
        if f.default is not dataclasses.MISSING
        else f.default_factory()  # type: ignore[misc]
    )
    for f in dataclasses.fields(NodeDefinition)
    if f.default is not dataclasses.MISSING
    or f.default_factory is not dataclasses.MISSING  # type: ignore[misc]
}

# Fields ALWAYS written even at their default: their intent must be explicit in
# the file and a future default-flip must never silently change execution or
# security behavior. requires_sandbox/effects are the r17 #1 regression fields;
# timeout_seconds is the #61 documented-intent contract (test-asserted).
_NODE_ALWAYS_SERIALIZE = frozenset({
    "timeout_seconds",
    "requires_sandbox",
    "effects",
    "approved",
    "enabled",
})


def node_to_yaml_payload(node: NodeDefinition) -> dict[str, Any]:
    """Serialize a NodeDefinition round-trip-COMPLETE but compact.

    Drives off the dataclass fields so no execution/security/routing field can
    silently drop (Codex r17 #1). Omits fields equal to their dataclass default
    to keep files small, EXCEPT ``_NODE_ALWAYS_SERIALIZE`` which stay explicit.
    ``id`` is the YAML key for ``node_id``.
    """
    full = node.to_dict()  # asdict — every current + future field
    payload: dict[str, Any] = {
        "id": full.pop("node_id", node.node_id),
        "display_name": full.pop("display_name", ""),
        "phase": full.pop("phase", "custom"),
    }
    for key, value in full.items():
        if key in _NODE_ALWAYS_SERIALIZE or value != _NODE_FIELD_DEFAULTS.get(key):
            payload[key] = value
    return payload


def node_from_yaml_payload(payload: dict[str, Any]) -> NodeDefinition:
    """Round-trip counterpart. Maps ``id`` -> ``node_id`` and defers to
    ``NodeDefinition.from_dict`` (field-filtered) so every field the payload
    carries is restored and unknown keys are ignored. A ``null`` value means
    "use the dataclass default" (dropped before construction). input_keys /
    output_keys are NOT wrapped in ``list(...)``: a bare string like
    ``input_keys: framed_question`` reaches ``__post_init__`` and is rejected by
    ``NodeDefinitionValidationError`` instead of char-iterating (Task #12).
    """
    data = {k: v for k, v in payload.items() if v is not None}
    data["node_id"] = data.pop("id", "") or data.get("node_id", "")
    return NodeDefinition.from_dict(data)


def goal_to_yaml_payload(goal: dict[str, Any]) -> dict[str, Any]:
    """Serialize a Goal dict (flat, no dataclass) to the YAML shape.

    Phase 6.3: ``gate_ladder`` rides through as a list-of-dicts under
    ``goals/<slug>.yaml#/gate_ladder``. PR-129 adds
    ``branch_protocol`` for ordered Goal-bound Branch runbooks. Empty
    lists are omitted so goals without these optional structures keep a
    minimal YAML diff.
    """
    payload: dict[str, Any] = {
        "id": goal.get("goal_id", ""),
        "name": goal.get("name", ""),
        "description": goal.get("description", ""),
        "author": goal.get("author", "anonymous"),
        "tags": list(goal.get("tags", []) or []),
        "visibility": goal.get("visibility", "public"),
        "created_at": goal.get("created_at", 0.0),
        "updated_at": goal.get("updated_at", 0.0),
    }
    ladder = list(goal.get("gate_ladder", []) or [])
    if ladder:
        payload["gate_ladder"] = ladder
    protocol = list(goal.get("branch_protocol", []) or [])
    if protocol:
        payload["branch_protocol"] = protocol
    return payload


def goal_from_yaml_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Round-trip counterpart to ``goal_to_yaml_payload``.

    Returns a dict in the shape ``author_server.save_goal`` accepts.
    """
    return {
        "goal_id": payload.get("id", ""),
        "name": payload.get("name", ""),
        "description": payload.get("description", ""),
        "author": payload.get("author", "anonymous"),
        "tags": list(payload.get("tags", []) or []),
        "visibility": payload.get("visibility", "public"),
        "created_at": payload.get("created_at", 0.0),
        "updated_at": payload.get("updated_at", 0.0),
        "gate_ladder": list(payload.get("gate_ladder", []) or []),
        "branch_protocol": list(payload.get("branch_protocol", []) or []),
    }


def gate_claim_to_yaml_payload(claim: dict[str, Any]) -> dict[str, Any]:
    """Serialize a gate_claim row to the YAML shape.

    Phase 6.3 format:

    ```yaml
    claim_id: 01HY...
    branch_def_id: loral-v3
    goal_id: fantasy-novel
    rung_key: draft_complete
    evidence_url: https://example.com/drafts/loral
    evidence_note: Full draft at 82k words
    conformance_pack_id: ''
    claimed_by: jonathan
    claimed_at: '2026-05-01T14:22:03Z'
    retracted_at: null
    retracted_reason: ''
    ```

    Retracted claims rewrite the same file with ``retracted_at``
    populated so git history preserves the retraction reason.
    """
    return {
        "claim_id": claim.get("claim_id", ""),
        "branch_def_id": claim.get("branch_def_id", ""),
        "goal_id": claim.get("goal_id", ""),
        "rung_key": claim.get("rung_key", ""),
        "evidence_url": claim.get("evidence_url", ""),
        "evidence_note": claim.get("evidence_note", ""),
        "conformance_pack_id": claim.get("conformance_pack_id", ""),
        "claimed_by": claim.get("claimed_by", ""),
        "claimed_at": claim.get("claimed_at", ""),
        "retracted_at": claim.get("retracted_at"),
        "retracted_reason": claim.get("retracted_reason", ""),
    }


def gate_claim_from_yaml_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Round-trip counterpart to ``gate_claim_to_yaml_payload``."""
    return {
        "claim_id": payload.get("claim_id", ""),
        "branch_def_id": payload.get("branch_def_id", ""),
        "goal_id": payload.get("goal_id", ""),
        "rung_key": payload.get("rung_key", ""),
        "evidence_url": payload.get("evidence_url", ""),
        "evidence_note": payload.get("evidence_note", ""),
        "conformance_pack_id": payload.get("conformance_pack_id", ""),
        "claimed_by": payload.get("claimed_by", ""),
        "claimed_at": payload.get("claimed_at", ""),
        "retracted_at": payload.get("retracted_at"),
        "retracted_reason": payload.get("retracted_reason", ""),
    }


# ── private helpers ─────────────────────────────────────────────────


def _conditional_edge_from_dict(data: dict[str, Any]) -> ConditionalEdge:
    """Rebuild a ConditionalEdge from its ``to_dict`` shape.

    ``to_dict`` emits ``{"from": ..., "conditions": ...}`` but the
    dataclass field is named ``from_node``. Translate here rather
    than in the dataclass so the YAML contract stays legible.

    Codex r16 #2: ``fallback`` MUST round-trip. Dropping it here reloaded a
    ``"reject"`` safe-fallback as ``""`` — and because YAML serialization sorts
    condition keys, an off-label routing value would then fall through to a
    DIFFERENT first condition (a rejected patch could route to merge). Mirror
    ``ConditionalEdge.from_dict``'s robust non-string handling so a malformed
    persisted fallback surfaces in ``validate()`` rather than crashing here.
    (S1-owned: this preservation must survive the S1+S3 merge — taking S3
    verbatim drops it.)
    """
    _fb = data.get("fallback")
    if isinstance(_fb, str):
        fallback: Any = _fb.strip()
    elif _fb is None:
        fallback = ""
    else:
        fallback = _fb
    return ConditionalEdge(
        from_node=data.get("from") or data.get("from_node", ""),
        conditions=dict(data.get("conditions", {}) or {}),
        fallback=fallback,
    )


def _edge_to_compact(edge: EdgeDefinition) -> dict[str, Any]:
    """Write edges as ``{from: x, to: y}`` pairs.

    Human-readable over the dataclass's full shape; conditional edges
    live in a separate ``conditional_edges`` list.
    """
    return {"from": edge.from_node, "to": edge.to_node}


def _edge_from_compact(entry: Any) -> EdgeDefinition:
    """Accept both compact ``{from,to}`` and the legacy dataclass dict.

    Defensive: older YAML written before this compact form is still
    readable.
    """
    if isinstance(entry, dict):
        if "from" in entry and "to" in entry:
            return EdgeDefinition(
                from_node=entry["from"], to_node=entry["to"],
            )
        return EdgeDefinition(
            from_node=entry.get("from_node", ""),
            to_node=entry.get("to_node", ""),
        )
    # Also accept ``[from, to]`` pairs per dev-3's layout doc example.
    if isinstance(entry, list) and len(entry) == 2:
        return EdgeDefinition(from_node=entry[0], to_node=entry[1])
    raise ValueError(f"Unrecognised edge entry: {entry!r}")

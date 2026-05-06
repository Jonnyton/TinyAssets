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

from typing import Any

from workflow.branches import (
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

    branch = BranchDefinition(
        branch_def_id=payload.get("id") or "",
        name=payload.get("name", ""),
        description=payload.get("description", ""),
        author=payload.get("author", "anonymous"),
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


def node_to_yaml_payload(node: NodeDefinition) -> dict[str, Any]:
    """Serialize a NodeDefinition. Omits defaults to keep files small."""
    payload: dict[str, Any] = {
        "id": node.node_id,
        "display_name": node.display_name,
        "phase": node.phase,
    }
    if node.description:
        payload["description"] = node.description
    if node.prompt_template:
        payload["prompt_template"] = node.prompt_template
    if node.source_code:
        payload["source_code"] = node.source_code
    if node.model_hint:
        payload["model_hint"] = node.model_hint
    if node.input_keys:
        payload["input_keys"] = list(node.input_keys)
    if node.output_keys:
        payload["output_keys"] = list(node.output_keys)
    if node.strict_input_isolation is False:
        payload["strict_input_isolation"] = False
    if node.tools_allowed:
        payload["tools_allowed"] = list(node.tools_allowed)
    if node.dependencies:
        payload["dependencies"] = list(node.dependencies)
    # timeout_seconds always written — #61 raised the default, so an
    # explicit value in the YAML documents intent.
    payload["timeout_seconds"] = node.timeout_seconds
    if node.retry_policy != {"max_retries": 0, "backoff_seconds": 1.0}:
        payload["retry_policy"] = dict(node.retry_policy)
    if node.evaluation_criteria:
        payload["evaluation_criteria"] = list(node.evaluation_criteria)
    payload["approved"] = node.approved
    payload["enabled"] = node.enabled
    if node.author and node.author != "anonymous":
        payload["author"] = node.author
    if node.registered_at:
        payload["registered_at"] = node.registered_at
    return payload


def node_from_yaml_payload(payload: dict[str, Any]) -> NodeDefinition:
    # Note: input_keys/output_keys are passed through as-is (with a
    # None→[] guard) rather than wrapped in `list(...)`. A bare-string
    # value like `input_keys: framed_question` would char-iterate under
    # `list(...)` into ['f','r','a',...] — silent corruption that
    # bypasses NodeDefinition's read-side validator (Task #12). With
    # pass-through, the str reaches `__post_init__` and gets rejected
    # by `NodeDefinitionValidationError`.
    return NodeDefinition(
        node_id=payload.get("id", ""),
        display_name=payload.get("display_name", ""),
        description=payload.get("description", ""),
        phase=payload.get("phase", "custom"),
        input_keys=payload.get("input_keys") or [],
        output_keys=payload.get("output_keys") or [],
        source_code=payload.get("source_code", ""),
        prompt_template=payload.get("prompt_template", ""),
        strict_input_isolation=bool(
            payload.get("strict_input_isolation", True)
        ),
        model_hint=payload.get("model_hint", ""),
        tools_allowed=list(payload.get("tools_allowed", []) or []),
        dependencies=list(payload.get("dependencies", []) or []),
        timeout_seconds=float(
            payload.get("timeout_seconds", 300.0) or 300.0
        ),
        retry_policy=dict(
            payload.get("retry_policy") or {
                "max_retries": 0, "backoff_seconds": 1.0,
            }
        ),
        evaluation_criteria=list(
            payload.get("evaluation_criteria", []) or []
        ),
        author=payload.get("author", "anonymous"),
        registered_at=payload.get("registered_at", ""),
        enabled=bool(payload.get("enabled", True)),
        approved=bool(payload.get("approved", False)),
    )


def goal_to_yaml_payload(goal: dict[str, Any]) -> dict[str, Any]:
    """Serialize a Goal dict (flat, no dataclass) to the YAML shape.

    Phase 6.3: ``gate_ladder`` rides through as a list-of-dicts under
    ``goals/<slug>.yaml#/gate_ladder``. Empty list omitted so goals
    without a ladder keep a minimal YAML diff.
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
    """
    return ConditionalEdge(
        from_node=data.get("from") or data.get("from_node", ""),
        conditions=dict(data.get("conditions", {}) or {}),
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

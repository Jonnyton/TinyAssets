"""Pure, detached graph projections for owner-selected receiving entries.

This does not grant access, expose a receiver, persist a definition or enqueue a
run. The owning service must authorize/pin the source and validate actual delivery
inputs again. Projection never executes user code or calls a provider.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Collection
from dataclasses import dataclass

from tinyassets.branches import BranchDefinition, EdgeDefinition
from tinyassets.graph_compiler import _graph_ancestors
from tinyassets.runs import preflight_required_inputs


class ReceiverProjectionError(ValueError):
    """A selected entry cannot expose a structurally valid input contract."""


@dataclass(frozen=True)
class ReceiverProjection:
    source_sha256: str
    snapshot_sha256: str
    snapshot_json: str
    entry_node_id: str
    node_ids: tuple[str, ...]

    @property
    def branch(self) -> BranchDefinition:
        """Return a fresh copy; a caller cannot mutate the pinned snapshot."""
        return BranchDefinition.from_dict(json.loads(self.snapshot_json))


def _serialize(branch: BranchDefinition) -> str:
    try:
        return json.dumps(
            branch.to_dict(), sort_keys=True, ensure_ascii=False,
            separators=(",", ":"), allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ReceiverProjectionError("receiver graph is not JSON serializable") from exc


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def project_receiver_entry(
    branch: BranchDefinition,
    entry_node_id: str,
    *,
    contract_input_keys: Collection[str] = (),
) -> ReceiverProjection:
    """Keep the selected graph placement and its complete downstream topology.

    Contract keys represent values the receiver explicitly requires/accepts, not
    fabricated defaults. They are used only for presence preflight here; intake
    must validate the supplied values against the contract and preflight again.
    MissingRequiredInputs retains the ordinary engine's precise key diagnostics.
    """
    source_json = _serialize(branch)
    projected = BranchDefinition.from_dict(json.loads(source_json))
    graph_ids = [node.id for node in projected.graph_nodes]
    if len(graph_ids) != len(set(graph_ids)):
        raise ReceiverProjectionError("Duplicate graph node identity in receiver graph")
    if (
        not isinstance(entry_node_id, str)
        or entry_node_id in {"", "START", "END"}
        or entry_node_id not in graph_ids
    ):
        raise ReceiverProjectionError("receiver entry must name an existing graph node")
    if (
        not isinstance(contract_input_keys, Collection)
        or isinstance(contract_input_keys, (str, bytes))
        or any(not isinstance(key, str) or not key for key in contract_input_keys)
    ):
        raise ReceiverProjectionError("receiver contract keys must be a collection of names")
    fields = {field.get("name") for field in projected.state_schema}
    unknown_inputs = set(contract_input_keys) - fields
    if unknown_inputs:
        raise ReceiverProjectionError(
            f"receiver contract contains undeclared state fields: {sorted(unknown_inputs)}"
        )

    children: dict[str, set[str]] = {}
    for edge in projected.edges:
        children.setdefault(edge.from_node, set()).add(edge.to_node)
    for edge in projected.conditional_edges:
        children.setdefault(edge.from_node, set()).update(edge.conditions.values())
    known = set(graph_ids)
    retained: set[str] = set()
    pending = [entry_node_id]
    while pending:
        node_id = pending.pop()
        if node_id in retained:
            continue
        retained.add(node_id)
        if "START" in children.get(node_id, ()):
            raise ReceiverProjectionError("receiver graph cannot route back into START")
        pending.extend(children.get(node_id, set()) & (known - retained))

    projected.graph_nodes = [node for node in projected.graph_nodes if node.id in retained]
    needed_defs = {node.node_def_id or node.id for node in projected.graph_nodes}
    projected.node_defs = [node for node in projected.node_defs if node.node_id in needed_defs]
    # Keep reachable dangling targets for validation: trimming them would turn
    # an invalid graph into a different apparently working graph.
    projected.edges = [edge for edge in projected.edges if edge.from_node in retained]
    projected.edges.insert(0, EdgeDefinition("START", entry_node_id))
    projected.conditional_edges = [
        edge for edge in projected.conditional_edges if edge.from_node in retained
    ]
    projected.entry_point = entry_node_id
    errors = projected.validate()
    if errors:
        raise ReceiverProjectionError("Invalid receiver projection: " + "; ".join(errors))

    ancestors = _graph_ancestors(projected)
    defs = {node.node_id: node for node in projected.node_defs}
    for placed in projected.graph_nodes:
        node = defs.get(placed.node_def_id or placed.id)
        if node is None:
            raise ReceiverProjectionError(f"Missing receiver node definition: {placed.id}")
        workspace = (node.workspace or "").strip()
        if workspace and workspace not in ancestors[placed.id]:
            raise ReceiverProjectionError(
                f"Node {placed.id!r} workspace {workspace!r} is not a retained ancestor"
            )
    preflight_required_inputs(projected, dict.fromkeys(contract_input_keys))
    snapshot_json = _serialize(projected)
    return ReceiverProjection(
        source_sha256=_sha256(source_json),
        snapshot_sha256=_sha256(snapshot_json),
        snapshot_json=snapshot_json,
        entry_node_id=entry_node_id,
        node_ids=tuple(node.id for node in projected.graph_nodes),
    )

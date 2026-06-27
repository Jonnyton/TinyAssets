"""Node-scope manifest loader for memory-scope Stage 2a.

Per design-note ``docs/design-notes/2026-04-15-memory-scope-tiered.md``
§4 "Node-scope manifest (separate file, host-chosen 2026-04-15)", each
Branch ships a sidecar ``node_scope.yaml`` that declares per-node
memory-access rules:

- whether the node is a universe member (canon-purity contract)
- breadth of retrieval when it IS a member (full canon vs narrow slice)
- external sources when it is NOT a member (explicit opt-in)

Stage 2a lands the loader + validation only. Enforcement lands in
Stage 2b — the runtime will compose a ``NodeScope`` from the loaded
manifest plus the caller's ``MemoryScope`` at node-execution time.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

MANIFEST_FILENAME = "node_scope.yaml"


_ALLOWED_BREADTHS = frozenset({"full_canon", "narrow_slice"})
_ALLOWED_EXTERNAL_KINDS = frozenset({
    "universe", "external_api", "system_tool", "cross_universe_join",
})


@dataclass(frozen=True)
class SliceSpec:
    """Narrow-slice retrieval constraint.

    At least one of ``entity_ids``, ``relation_types``, or
    ``document_ids`` must be populated when a node declares
    ``breadth=narrow_slice``. Empty lists are equivalent to "no
    constraint" — at least one field must carry values.
    """
    entity_ids: tuple[str, ...] = ()
    relation_types: tuple[str, ...] = ()
    document_ids: tuple[str, ...] = ()

    def is_empty(self) -> bool:
        return not (self.entity_ids or self.relation_types or self.document_ids)


@dataclass(frozen=True)
class ExternalSource:
    """Declared external source for out-of-universe nodes.

    ``kind`` classifies the source (universe | external_api |
    system_tool | cross_universe_join). ``identifier`` is opaque to
    this loader — Stage 2b resolvers will interpret it per kind.
    """
    kind: str
    identifier: str


@dataclass(frozen=True)
class NodeScopeEntry:
    """Per-node (or default) scope declaration.

    An entry with ``universe_member=False`` must declare at least one
    ``ExternalSource`` (canon-purity contract — out-of-universe nodes
    opt in explicitly). An entry with ``breadth=narrow_slice`` must
    carry a non-empty ``SliceSpec``.
    """
    universe_member: bool = True
    breadth: str = "full_canon"
    slice_spec: SliceSpec | None = None
    external_sources: tuple[ExternalSource, ...] = ()


@dataclass(frozen=True)
class NodeScopeManifest:
    """Loaded, validated manifest for one branch.

    ``default`` applies to any node without an explicit entry; a
    missing node inherits the default (which is
    ``universe_member=True, breadth=full_canon`` — the safe fallback
    that keeps nodes in-universe).
    """
    default: NodeScopeEntry = field(default_factory=NodeScopeEntry)
    nodes: dict[str, NodeScopeEntry] = field(default_factory=dict)

    def for_node(self, node_id: str) -> NodeScopeEntry:
        """Return the effective scope entry for ``node_id``.

        Stage 2a semantics: explicit per-node entry wins; otherwise
        inherit the manifest's default.
        """
        return self.nodes.get(node_id, self.default)


class NodeScopeManifestError(ValueError):
    """Raised when a manifest fails validation."""


def _parse_slice_spec(raw: Any, *, where: str) -> SliceSpec | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise NodeScopeManifestError(
            f"{where}: slice_spec must be a mapping, got {type(raw).__name__}"
        )
    allowed = {"entity_ids", "relation_types", "document_ids"}
    unknown = set(raw.keys()) - allowed
    if unknown:
        raise NodeScopeManifestError(
            f"{where}: slice_spec has unknown fields {sorted(unknown)}; "
            f"allowed: {sorted(allowed)}"
        )
    def _tuple(value: Any, field_name: str) -> tuple[str, ...]:
        if value is None:
            return ()
        if not isinstance(value, list):
            raise NodeScopeManifestError(
                f"{where}: slice_spec.{field_name} must be a list"
            )
        return tuple(str(v) for v in value)
    spec = SliceSpec(
        entity_ids=_tuple(raw.get("entity_ids"), "entity_ids"),
        relation_types=_tuple(raw.get("relation_types"), "relation_types"),
        document_ids=_tuple(raw.get("document_ids"), "document_ids"),
    )
    return spec


def _parse_external_sources(
    raw: Any, *, where: str,
) -> tuple[ExternalSource, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raise NodeScopeManifestError(
            f"{where}: external_sources must be a list"
        )
    out: list[ExternalSource] = []
    for idx, entry in enumerate(raw):
        if not isinstance(entry, dict):
            raise NodeScopeManifestError(
                f"{where}: external_sources[{idx}] must be a mapping"
            )
        kind = str(entry.get("kind") or "").strip()
        if kind not in _ALLOWED_EXTERNAL_KINDS:
            raise NodeScopeManifestError(
                f"{where}: external_sources[{idx}].kind {kind!r} must be "
                f"one of {sorted(_ALLOWED_EXTERNAL_KINDS)}"
            )
        identifier = str(entry.get("identifier") or "").strip()
        if not identifier:
            raise NodeScopeManifestError(
                f"{where}: external_sources[{idx}].identifier is required"
            )
        out.append(ExternalSource(kind=kind, identifier=identifier))
    return tuple(out)


def _parse_entry(raw: Any, *, where: str) -> NodeScopeEntry:
    if raw is None:
        return NodeScopeEntry()
    if not isinstance(raw, dict):
        raise NodeScopeManifestError(
            f"{where}: entry must be a mapping, got {type(raw).__name__}"
        )
    allowed = {
        "universe_member", "breadth", "slice_spec", "external_sources",
    }
    unknown = set(raw.keys()) - allowed
    if unknown:
        raise NodeScopeManifestError(
            f"{where}: unknown fields {sorted(unknown)}; "
            f"allowed: {sorted(allowed)}"
        )
    universe_member = bool(raw.get("universe_member", True))
    breadth = str(raw.get("breadth", "full_canon")).strip().lower()
    if breadth not in _ALLOWED_BREADTHS:
        raise NodeScopeManifestError(
            f"{where}: breadth {breadth!r} must be one of "
            f"{sorted(_ALLOWED_BREADTHS)}"
        )
    slice_spec = _parse_slice_spec(raw.get("slice_spec"), where=where)
    external_sources = _parse_external_sources(
        raw.get("external_sources"), where=where,
    )
    # Validate combinations.
    if breadth == "narrow_slice":
        if slice_spec is None or slice_spec.is_empty():
            raise NodeScopeManifestError(
                f"{where}: breadth=narrow_slice requires a non-empty slice_spec "
                "(entity_ids, relation_types, or document_ids)."
            )
    if not universe_member and not external_sources:
        raise NodeScopeManifestError(
            f"{where}: universe_member=false requires at least one "
            "external_sources entry (canon-purity contract)."
        )
    return NodeScopeEntry(
        universe_member=universe_member,
        breadth=breadth,
        slice_spec=slice_spec,
        external_sources=external_sources,
    )


def load_manifest(path: str | Path) -> NodeScopeManifest:
    """Load and validate a ``node_scope.yaml`` manifest from disk.

    Missing file → empty manifest (the safe fallback — all nodes
    inherit ``universe_member=True, breadth=full_canon``).
    Raises :class:`NodeScopeManifestError` on any validation error.
    """
    p = Path(path)
    if not p.is_file():
        return NodeScopeManifest()
    raw_text = p.read_text(encoding="utf-8")
    return parse_manifest(raw_text, where=str(p))


def parse_manifest(
    raw_text: str, *, where: str = "<manifest>",
) -> NodeScopeManifest:
    """Parse manifest text. Handles empty files as empty manifests."""
    if not raw_text.strip():
        return NodeScopeManifest()
    try:
        raw = yaml.safe_load(raw_text)
    except yaml.YAMLError as exc:
        raise NodeScopeManifestError(
            f"{where}: invalid YAML: {exc}"
        ) from exc
    if raw is None:
        return NodeScopeManifest()
    if not isinstance(raw, dict):
        raise NodeScopeManifestError(
            f"{where}: top-level must be a mapping, got {type(raw).__name__}"
        )
    allowed = {"default", "nodes"}
    unknown = set(raw.keys()) - allowed
    if unknown:
        raise NodeScopeManifestError(
            f"{where}: unknown top-level fields {sorted(unknown)}; "
            f"allowed: {sorted(allowed)}"
        )
    default_entry = _parse_entry(
        raw.get("default"), where=f"{where}:default",
    )
    nodes_raw = raw.get("nodes") or {}
    if not isinstance(nodes_raw, dict):
        raise NodeScopeManifestError(
            f"{where}: nodes must be a mapping"
        )
    nodes: dict[str, NodeScopeEntry] = {}
    for node_id, entry_raw in nodes_raw.items():
        if not isinstance(node_id, str) or not node_id:
            raise NodeScopeManifestError(
                f"{where}: nodes keys must be non-empty strings"
            )
        nodes[node_id] = _parse_entry(
            entry_raw, where=f"{where}:nodes.{node_id}",
        )
    return NodeScopeManifest(default=default_entry, nodes=nodes)


__all__ = [
    "MANIFEST_FILENAME",
    "ExternalSource",
    "NodeScopeEntry",
    "NodeScopeManifest",
    "NodeScopeManifestError",
    "SliceSpec",
    "load_manifest",
    "parse_manifest",
]

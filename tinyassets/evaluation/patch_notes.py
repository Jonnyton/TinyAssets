"""Typed patch notes passed between Goal-aware gate route-back runs."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

EvidenceKind = Literal[
    "wiki_page",
    "node_def",
    "branch_version",
    "github_pr",
    "run_artifact",
]
_EVIDENCE_KINDS = {
    "wiki_page",
    "node_def",
    "branch_version",
    "github_pr",
    "run_artifact",
}


@dataclass(frozen=True)
class EvidenceRef:
    """One artifact cited by the evaluator that authored patch notes."""

    kind: EvidenceKind
    id: str
    cited_by: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str):
            raise TypeError("EvidenceRef.kind must be a string")
        if self.kind not in _EVIDENCE_KINDS:
            raise ValueError(f"unsupported evidence kind: {self.kind!r}")
        if not isinstance(self.id, str) or not isinstance(self.cited_by, str):
            raise TypeError("EvidenceRef.id and cited_by must be strings")
        if not self.id.strip():
            raise ValueError("EvidenceRef.id cannot be empty")
        if not self.cited_by.strip():
            raise ValueError("EvidenceRef.cited_by cannot be empty")

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> EvidenceRef:
        if not isinstance(value, Mapping):
            raise TypeError("evidence_refs entries must be objects")
        return cls(
            kind=value.get("kind", ""),  # type: ignore[arg-type]
            id=value.get("id", ""),  # type: ignore[arg-type]
            cited_by=value.get("cited_by", ""),  # type: ignore[arg-type]
        )


@dataclass(frozen=True)
class PatchNotes:
    """Validated, content-addressed input for a routed canonical run."""

    summary: str
    rationale: str
    author_actor_id: str
    affected_files: list[str] = field(default_factory=list)
    tests_added: list[str] = field(default_factory=list)
    evidence_run_id: str | None = None
    evidence_refs: list[EvidenceRef] = field(default_factory=list)
    route_history: list[tuple[str, str]] = field(default_factory=list)
    patch_notes_id: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str)
            for value in (self.summary, self.rationale, self.author_actor_id)
        ):
            raise TypeError("summary, rationale, and author_actor_id must be strings")
        if not self.summary or len(self.summary) > 200:
            raise ValueError("summary must be 1-200 characters")
        if not self.author_actor_id.strip():
            raise ValueError("author_actor_id is required")
        for field_name, values in (
            ("affected_files", self.affected_files),
            ("tests_added", self.tests_added),
        ):
            if not isinstance(values, list) or any(
                not isinstance(value, str) for value in values
            ):
                raise TypeError(f"{field_name} must be a list of strings")
        if self.evidence_run_id is not None and not isinstance(
            self.evidence_run_id, str
        ):
            raise TypeError("evidence_run_id must be a string or None")
        if any(not isinstance(ref, EvidenceRef) for ref in self.evidence_refs):
            raise TypeError("evidence_refs must contain EvidenceRef values")
        if not isinstance(self.extra, dict):
            raise TypeError("extra must be an object")
        normalized_history: list[tuple[str, str]] = []
        for hop in self.route_history:
            if not isinstance(hop, (list, tuple)) or len(hop) != 2:
                raise ValueError("route_history entries must be (goal_id, scope_actor) pairs")
            goal_id, scope_actor = hop
            if not isinstance(goal_id, str) or not goal_id.strip():
                raise ValueError("route_history goal_id must be non-empty")
            if not isinstance(scope_actor, str):
                raise ValueError("route_history scope_actor must be a string")
            normalized_history.append((goal_id.strip(), scope_actor.strip()))
        object.__setattr__(self, "route_history", normalized_history)
        object.__setattr__(self, "patch_notes_id", self._compute_id())

    def _compute_id(self) -> str:
        payload = self.to_dict(include_id=False)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]

    def to_dict(self, *, include_id: bool = True) -> dict[str, Any]:
        payload = dataclasses.asdict(self)
        payload["route_history"] = [list(hop) for hop in self.route_history]
        if not include_id:
            payload.pop("patch_notes_id", None)
        return payload

    @classmethod
    def from_dict(cls, value: Mapping[str, Any]) -> PatchNotes:
        """Reconstruct and revalidate notes crossing an execution boundary."""
        if not isinstance(value, Mapping):
            raise TypeError("patch_notes must be an object")
        known = {field.name for field in dataclasses.fields(cls)}
        supplied_extra = value.get("extra", {})
        if not isinstance(supplied_extra, Mapping):
            raise TypeError("patch_notes.extra must be an object")
        extra = dict(supplied_extra)
        extra.update({key: item for key, item in value.items() if key not in known})
        raw_refs = value.get("evidence_refs", [])
        if not isinstance(raw_refs, list):
            raise TypeError("patch_notes.evidence_refs must be a list")
        raw_history = value.get("route_history", [])
        if not isinstance(raw_history, list):
            raise TypeError("patch_notes.route_history must be a list")
        return cls(
            summary=value.get("summary", ""),  # type: ignore[arg-type]
            rationale=value.get("rationale", ""),  # type: ignore[arg-type]
            author_actor_id=value.get("author_actor_id", ""),  # type: ignore[arg-type]
            affected_files=value.get("affected_files", []),  # type: ignore[arg-type]
            tests_added=value.get("tests_added", []),  # type: ignore[arg-type]
            evidence_run_id=value.get("evidence_run_id"),  # type: ignore[arg-type]
            evidence_refs=[EvidenceRef.from_dict(ref) for ref in raw_refs],
            route_history=[tuple(hop) for hop in raw_history],
            extra=extra,
        )


__all__ = ["EvidenceKind", "EvidenceRef", "PatchNotes"]

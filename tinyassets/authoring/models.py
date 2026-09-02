"""Authoring domain model — sessions, events, versions, and pure validation.

Task 4.1 of ``openspec/changes/archive/2026-08-26-complete-independent-full-platform-targets``
(capability ``node-authoring-and-autoresearch``). No I/O lives here: this module
is dataclasses plus pure functions so validation is testable without a store and
reusable by the store, the service, and the router half.

Design stance — *minimal irreducible primitives* (host directive 2026-07-25):

- **One edit grammar, not twenty verbs.** The spec enumerates "add/change/remove
  typed state, reducers, tools, graph nodes/edges/entry/terminal points, guarded
  cycles, sub-artifact composition, declared inputs/outputs, evaluator bindings,
  and bounded generic definition fields". Rather than 20 bespoke operations, an
  edit is one of four path-scoped ops (``set`` / ``unset`` / ``append`` /
  ``remove``) over the draft document, and the *whole resulting document* is
  validated. Users compose the complex edit; the platform owns the primitive and
  the invariant. ``set`` on any editable path is the spec's escape hatch.
- **Structural validation reuses the shipped substrate.** Node graph validation
  delegates to ``tinyassets.branches.BranchDefinition.validate()`` — the same
  validator ``extensions validate_branch`` uses — instead of a second, drifting
  copy of the graph rules. Authoring adds only what the branch substrate does
  not own: I/O manifests, effect declarations, composition cycles, evaluator
  contract/chain rules.
- **Evaluator vocabulary is the canonical one.** Verdicts are
  ``tinyassets.evaluation.EvalVerdict`` (``pass``/``fail``/``skip``/``error``)
  and the declared output slots mirror ``EvalResult``; authoring never invents a
  parallel verdict vocabulary.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

# ── Vocabulary ─────────────────────────────────────────────────────────────

ARTIFACT_KINDS: frozenset[str] = frozenset({"node", "evaluator"})
SEED_MODES: frozenset[str] = frozenset({"sketch", "artifact", "session"})
SESSION_STATUSES: frozenset[str] = frozenset({"active", "published", "expired"})
EVENT_TYPES: frozenset[str] = frozenset(
    {"created", "edit", "test", "publish", "publish_failed", "confirmation"}
)
VISIBILITIES: frozenset[str] = frozenset({"public", "private"})

#: Canonical evaluator verdicts — ``tinyassets.evaluation.EvalVerdict``.
CANONICAL_VERDICTS: tuple[str, ...] = ("pass", "fail", "skip", "error")
#: Canonical evaluator result slots — ``tinyassets.evaluation.EvalResult``.
REQUIRED_EVALUATOR_OUTPUTS: tuple[str, ...] = (
    "verdict",
    "score",
    "rationale",
    "evidence",
    "cost",
)
#: Workflow layers that surround evaluation and must not be declared as an
#: evaluator stage (spec: "without making the surrounding moderation,
#: convergence, or scheduling workflow itself an evaluator").
RESERVED_STAGE_KINDS: frozenset[str] = frozenset(
    {"moderation", "convergence", "scheduling"}
)

OP_VERBS: frozenset[str] = frozenset({"set", "unset", "append", "remove"})

#: Editable top-level document sections, per artifact kind. Anything else — and
#: every session-envelope field (owner_id, status, …) — is not editable through
#: the edit grammar.
_EDITABLE_NODE_PATHS: frozenset[str] = frozenset({
    "name",
    "description",
    "sketch",
    "node_defs",
    "graph_nodes",
    "edges",
    "conditional_edges",
    "state_schema",
    "entry_point",
    "terminal_points",
    "tools",
    "io_manifest",
    "effects",
    "sandbox_policy",
    "evaluator_binding",
    "composes",
    "metadata",
})
_EDITABLE_EVALUATOR_PATHS: frozenset[str] = frozenset({
    "name",
    "description",
    "sketch",
    "inputs",
    "outputs",
    "determinism",
    "stages",
    "io_manifest",
    "effects",
    "sandbox_policy",
    "composes",
    "metadata",
})

#: Hard ceiling on a serialized draft definition. A draft is a document, not a
#: data store; without a bound one session can exhaust the store.
MAX_DEFINITION_BYTES = 512 * 1024
MAX_OPERATIONS_PER_BATCH = 2000

_PATH_SEGMENT = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)((?:\[\d+\])*)$")


# ── Errors — fail loudly, never silently ───────────────────────────────────


@dataclass(frozen=True)
class ValidationIssue:
    """One machine-readable rejection reason."""

    code: str
    path: str = ""
    message: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "message": self.message}


class AuthoringError(Exception):
    """Base for every authoring failure."""


class AuthoringValidationError(AuthoringError):
    """A request was structurally or semantically invalid."""

    def __init__(self, issues: list[ValidationIssue], message: str = "") -> None:
        self.issues = list(issues)
        summary = message or "; ".join(
            f"{i.code}@{i.path}" if i.path else i.code for i in self.issues
        )
        super().__init__(summary or "invalid authoring request")


class ManifestViolation(AuthoringValidationError):
    """Supplied inputs/outputs violated the declared typed manifest."""


class AuthoringAccessError(AuthoringError):
    """The actor may not see or touch the object.

    The message is deliberately identical for "absent" and "not yours" so a
    probe cannot distinguish another user's object from a nonexistent one.
    """


class AuthoringConflictError(AuthoringError):
    """An optimistic-concurrency check failed (draft advanced under the caller)."""


class BudgetExceeded(AuthoringError):
    """A hard sandbox budget fired."""

    def __init__(self, budget: str, limit: float, attempted: float) -> None:
        self.budget = budget
        self.limit = limit
        self.attempted = attempted
        super().__init__(
            f"budget '{budget}' exceeded: limit={limit}, attempted={attempted}"
        )


class SandboxDenied(AuthoringError):
    """The isolation boundary refused the run or the call."""


class ConfirmationRequired(AuthoringError):
    """A real effect lacked valid per-run confirmation."""


NOT_FOUND_MESSAGE = "authoring object not found or not accessible"


def access_denied() -> AuthoringAccessError:
    """Build the single indistinguishable access failure."""
    return AuthoringAccessError(NOT_FOUND_MESSAGE)


# ── Records ────────────────────────────────────────────────────────────────


def canonical_json(payload: Any) -> str:
    """Stable serialization used for hashes and equality."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def definition_hash(definition: dict[str, Any]) -> str:
    """Content hash of a draft/published definition."""
    return hashlib.sha256(canonical_json(definition).encode("utf-8")).hexdigest()


@dataclass
class AuthoringSession:
    """One owner-scoped draft."""

    session_id: str
    owner_id: str
    artifact_id: str
    artifact_kind: str
    seed_mode: str
    seed_ref: str
    status: str
    draft_version: int
    definition: dict[str, Any]
    created_at: str
    updated_at: str
    retention_until: str
    parent_version_id: str = ""

    @property
    def definition_hash(self) -> str:
        return definition_hash(self.definition)

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "owner_id": self.owner_id,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "seed_mode": self.seed_mode,
            "seed_ref": self.seed_ref,
            "status": self.status,
            "draft_version": self.draft_version,
            "definition": copy.deepcopy(self.definition),
            "definition_hash": self.definition_hash,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "retention_until": self.retention_until,
            "lineage": {"parent_version_id": self.parent_version_id},
        }


@dataclass
class AuthoringEvent:
    """One immutable session event; also the anchor a diff is taken against."""

    event_id: str
    session_id: str
    seq: int
    event_type: str
    created_at: str
    definition_hash: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "session_id": self.session_id,
            "seq": self.seq,
            "event_type": self.event_type,
            "created_at": self.created_at,
            "definition_hash": self.definition_hash,
            "payload": copy.deepcopy(self.payload),
        }


@dataclass
class ArtifactVersion:
    """One immutable published artifact version."""

    version_id: str
    artifact_id: str
    artifact_kind: str
    version_no: int
    owner_id: str
    visibility: str
    definition: dict[str, Any]
    definition_hash: str
    parent_version_id: str
    change_message: str
    created_at: str
    provenance: dict[str, Any] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version_id": self.version_id,
            "artifact_id": self.artifact_id,
            "artifact_kind": self.artifact_kind,
            "version_no": self.version_no,
            "owner_id": self.owner_id,
            "visibility": self.visibility,
            "definition": copy.deepcopy(self.definition),
            "definition_hash": self.definition_hash,
            "parent_version_id": self.parent_version_id,
            "change_message": self.change_message,
            "created_at": self.created_at,
            "provenance": copy.deepcopy(self.provenance),
            "evidence": copy.deepcopy(self.evidence),
        }


# ── Skeletons ──────────────────────────────────────────────────────────────


def skeleton_for(artifact_kind: str, *, sketch: str = "") -> dict[str, Any]:
    """Return the empty, well-formed draft document for *artifact_kind*."""
    if artifact_kind not in ARTIFACT_KINDS:
        raise AuthoringValidationError([
            ValidationIssue(
                "session.unknown_artifact_kind",
                "artifact_kind",
                f"artifact_kind must be one of {sorted(ARTIFACT_KINDS)}",
            ),
        ])
    common: dict[str, Any] = {
        "kind": artifact_kind,
        "name": "",
        "description": "",
        "sketch": sketch,
        "io_manifest": {"inputs": [], "outputs": []},
        "effects": [],
        "sandbox_policy": {},
        "composes": [],
        "metadata": {},
    }
    if artifact_kind == "node":
        common.update({
            "node_defs": [],
            "graph_nodes": [],
            "edges": [],
            "conditional_edges": [],
            "state_schema": [],
            "entry_point": "",
            "terminal_points": [],
            "tools": [],
            "evaluator_binding": {},
        })
        return common
    common.update({
        "inputs": [],
        "outputs": {},
        "determinism": {},
        "stages": [],
    })
    return common


def editable_paths(artifact_kind: str) -> frozenset[str]:
    return (
        _EDITABLE_NODE_PATHS
        if artifact_kind == "node"
        else _EDITABLE_EVALUATOR_PATHS
    )


# ── Edit grammar ───────────────────────────────────────────────────────────


def _parse_path(raw: str) -> list[Any]:
    """Parse ``a.b[0].c`` into ``['a', 'b', 0, 'c']``; raise on anything else."""
    if not raw or not isinstance(raw, str):
        raise ValueError("path must be a non-empty string")
    parts: list[Any] = []
    for segment in raw.split("."):
        match = _PATH_SEGMENT.match(segment)
        if match is None:
            raise ValueError(f"unparseable path segment: {segment!r}")
        parts.append(match.group(1))
        for index in re.findall(r"\[(\d+)\]", match.group(2) or ""):
            parts.append(int(index))
    return parts


def _resolve_parent(document: Any, parts: list[Any]) -> tuple[Any, Any]:
    cursor = document
    for part in parts[:-1]:
        if isinstance(part, int):
            if not isinstance(cursor, list) or part >= len(cursor):
                raise ValueError(f"path index [{part}] does not exist")
            cursor = cursor[part]
        else:
            if not isinstance(cursor, dict) or part not in cursor:
                raise ValueError(f"path segment '{part}' does not exist")
            cursor = cursor[part]
    return cursor, parts[-1]


def apply_operations(
    definition: dict[str, Any],
    operations: list[dict[str, Any]],
    *,
    artifact_kind: str,
) -> dict[str, Any]:
    """Apply an atomic batch to a copy of *definition*.

    Pure: the caller's document is never mutated, so a rejected batch leaves the
    pre-edit draft authoritative by construction rather than by discipline.
    """
    issues: list[ValidationIssue] = []
    if not isinstance(operations, list) or not operations:
        raise AuthoringValidationError([
            ValidationIssue("op.empty_batch", "operations", "at least one operation is required"),
        ])
    if len(operations) > MAX_OPERATIONS_PER_BATCH:
        raise AuthoringValidationError([
            ValidationIssue(
                "op.batch_too_large",
                "operations",
                f"at most {MAX_OPERATIONS_PER_BATCH} operations per batch",
            ),
        ])

    allowed = editable_paths(artifact_kind)
    working = copy.deepcopy(definition)

    for index, operation in enumerate(operations):
        where = f"operations[{index}]"
        if not isinstance(operation, dict):
            issues.append(ValidationIssue("op.malformed", where, "operation must be an object"))
            continue
        verb = str(operation.get("op", "")).strip()
        raw_path = str(operation.get("path", "")).strip()
        if verb not in OP_VERBS:
            issues.append(ValidationIssue(
                "op.unknown_verb", where, f"op must be one of {sorted(OP_VERBS)}",
            ))
            continue
        try:
            parts = _parse_path(raw_path)
        except ValueError as exc:
            issues.append(ValidationIssue("op.malformed_path", where, str(exc)))
            continue
        if parts[0] not in allowed:
            issues.append(ValidationIssue(
                "op.path_not_editable",
                raw_path,
                f"'{parts[0]}' is not an editable section of a {artifact_kind} draft",
            ))
            continue

        try:
            parent, leaf = _resolve_parent(working, parts)
            if verb == "set":
                if "value" not in operation:
                    raise ValueError("set requires 'value'")
                if isinstance(leaf, int):
                    if not isinstance(parent, list) or leaf >= len(parent):
                        raise ValueError(f"index [{leaf}] does not exist")
                    parent[leaf] = copy.deepcopy(operation["value"])
                else:
                    if not isinstance(parent, dict):
                        raise ValueError(f"'{leaf}' is not a settable field")
                    parent[leaf] = copy.deepcopy(operation["value"])
            elif verb == "unset":
                if isinstance(leaf, int) or not isinstance(parent, dict):
                    raise ValueError("unset requires an object field path")
                parent.pop(leaf, None)
            elif verb == "append":
                if "value" not in operation:
                    raise ValueError("append requires 'value'")
                target = parent[leaf] if not isinstance(leaf, int) else parent[leaf]
                if not isinstance(target, list):
                    raise ValueError(f"'{raw_path}' is not a list")
                target.append(copy.deepcopy(operation["value"]))
            else:  # remove
                if isinstance(leaf, int):
                    if not isinstance(parent, list) or leaf >= len(parent):
                        raise ValueError(f"index [{leaf}] does not exist")
                    parent.pop(leaf)
                else:
                    raise ValueError("remove requires a list index path")
        except (ValueError, LookupError, TypeError) as exc:
            # LookupError covers IndexError as well as KeyError: `append` to
            # `edges[999]` must be a machine-readable rejection, not an
            # exception that escapes the router as a stack trace.
            issues.append(ValidationIssue("op.inapplicable", raw_path, str(exc)))

    if issues:
        raise AuthoringValidationError(issues)

    encoded = canonical_json(working)
    if len(encoded.encode("utf-8")) > MAX_DEFINITION_BYTES:
        raise AuthoringValidationError([
            ValidationIssue(
                "definition.too_large",
                "",
                f"definition exceeds {MAX_DEFINITION_BYTES} bytes",
            ),
        ])
    return working


def diff_definitions(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
    """Flat, path-anchored diff between two definitions."""
    flat_before = _flatten(before)
    flat_after = _flatten(after)
    changes: list[dict[str, Any]] = []
    for path in sorted(set(flat_before) | set(flat_after)):
        old = flat_before.get(path, None)
        new = flat_after.get(path, None)
        if path not in flat_after:
            changes.append({"path": path, "change": "removed", "before": old})
        elif path not in flat_before:
            changes.append({"path": path, "change": "added", "after": new})
        elif old != new:
            changes.append({"path": path, "change": "changed", "before": old, "after": new})
    return changes


def _flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    flat: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            flat.update(_flatten(item, f"{prefix}.{key}" if prefix else str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            flat.update(_flatten(item, f"{prefix}[{index}]"))
    else:
        flat[prefix] = value
    return flat


# ── Validation ─────────────────────────────────────────────────────────────

VersionResolver = Callable[[str], dict[str, Any] | None]


def validate_definition(
    definition: dict[str, Any],
    *,
    artifact_kind: str,
    self_artifact_id: str = "",
    resolve_version: VersionResolver | None = None,
) -> list[ValidationIssue]:
    """Validate a whole draft document.

    Pure when *resolve_version* is omitted; referential checks (evaluator
    bindings, composed artifacts) only run when a resolver is supplied so the
    same function serves unit tests and the store-backed service path.
    """
    if artifact_kind not in ARTIFACT_KINDS:
        return [ValidationIssue("session.unknown_artifact_kind", "artifact_kind", "")]
    if not isinstance(definition, dict):
        return [ValidationIssue("definition.malformed", "", "definition must be an object")]

    issues: list[ValidationIssue] = []
    issues.extend(_validate_no_secret_material(definition))
    issues.extend(_validate_manifest_shape(definition))
    issues.extend(_validate_effects(definition))
    issues.extend(_validate_composition(definition, self_artifact_id, resolve_version))
    issues.extend(_validate_sandbox_policy(definition))
    if artifact_kind == "node":
        issues.extend(_validate_node(definition, resolve_version))
    else:
        issues.extend(_validate_evaluator(definition))
    return issues


def _validate_node(
    definition: dict[str, Any],
    resolve_version: VersionResolver | None,
) -> list[ValidationIssue]:
    from tinyassets.branches import BranchDefinition

    issues: list[ValidationIssue] = []
    if not str(definition.get("name", "")).strip():
        issues.append(ValidationIssue("definition.name_required", "name", "name is required"))
    if not definition.get("node_defs") and not definition.get("graph_nodes"):
        issues.append(ValidationIssue("definition.no_nodes", "node_defs", "no nodes declared"))
    elif not str(definition.get("entry_point", "")).strip():
        issues.append(ValidationIssue(
            "definition.entry_point_required", "entry_point", "entry point is required",
        ))

    # Delegate graph structure to the shipped branch validator rather than
    # maintaining a second copy of the graph rules.
    try:
        branch = BranchDefinition.from_dict({
            "branch_def_id": "draft",
            "name": definition.get("name", "") or "draft",
            "description": definition.get("description", ""),
            "node_defs": definition.get("node_defs", []),
            "graph_nodes": definition.get("graph_nodes", []),
            "edges": definition.get("edges", []),
            "conditional_edges": definition.get("conditional_edges", []),
            "state_schema": definition.get("state_schema", []),
            "entry_point": definition.get("entry_point", ""),
        })
    except (TypeError, ValueError, KeyError) as exc:
        return issues + [ValidationIssue("definition.unparseable_graph", "", str(exc))]

    for error in branch.validate():
        lowered = error.lower()
        if "name is required" in lowered or "at least one node" in lowered:
            continue  # already reported above as a completeness blocker
        if "entry point is required" in lowered:
            continue
        code = "definition.graph_invalid"
        if "unknown" in lowered or "not a defined node" in lowered:
            code = "definition.unknown_reference"
        elif "cycle" in lowered:
            code = "definition.unguarded_cycle"
        elif "duplicate" in lowered:
            code = "definition.duplicate_id"
        elif "reducer" in lowered:
            code = "definition.invalid_reducer"
        issues.append(ValidationIssue(code, "graph", error))

    binding = definition.get("evaluator_binding") or {}
    if binding:
        if not isinstance(binding, dict):
            issues.append(ValidationIssue(
                "definition.malformed_evaluator_binding", "evaluator_binding", "",
            ))
        else:
            version_id = str(binding.get("version_id", "")).strip()
            if not version_id:
                issues.append(ValidationIssue(
                    "definition.malformed_evaluator_binding",
                    "evaluator_binding.version_id",
                    "an evaluator binding must name a published version_id",
                ))
            elif resolve_version is not None:
                resolved = resolve_version(version_id)
                if resolved is None or resolved.get("artifact_kind") != "evaluator":
                    issues.append(ValidationIssue(
                        "definition.unknown_evaluator_binding",
                        "evaluator_binding.version_id",
                        "evaluator binding does not resolve to a readable "
                        "published evaluator version",
                    ))
    return issues


def _validate_evaluator(definition: dict[str, Any]) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if not str(definition.get("name", "")).strip():
        issues.append(ValidationIssue("definition.name_required", "name", "name is required"))

    inputs = definition.get("inputs")
    if not isinstance(inputs, list) or not inputs:
        issues.append(ValidationIssue(
            "evaluator.inputs_undeclared", "inputs", "declare artifact/context inputs",
        ))

    outputs = definition.get("outputs")
    if not isinstance(outputs, dict) or not outputs:
        issues.append(ValidationIssue(
            "evaluator.outputs_undeclared", "outputs", "declare the canonical result slots",
        ))
    else:
        for slot in REQUIRED_EVALUATOR_OUTPUTS:
            if not outputs.get(slot):
                issues.append(ValidationIssue(
                    "evaluator.output_missing",
                    f"outputs.{slot}",
                    f"the canonical evaluator contract requires a '{slot}' output",
                ))

    determinism = definition.get("determinism")
    if not isinstance(determinism, dict) or "deterministic" not in determinism:
        issues.append(ValidationIssue(
            "evaluator.determinism_undeclared",
            "determinism",
            "declare determinism/cache policy",
        ))

    stages = definition.get("stages")
    if not isinstance(stages, list) or not stages:
        issues.append(ValidationIssue(
            "evaluator.stages_undeclared", "stages", "declare at least one stage",
        ))
        return issues

    names: list[str] = []
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            issues.append(ValidationIssue("evaluator.malformed_stage", f"stages[{index}]", ""))
            continue
        name = str(stage.get("name", "")).strip()
        if not name:
            issues.append(ValidationIssue(
                "evaluator.stage_unnamed", f"stages[{index}].name", "",
            ))
        elif name in names:
            issues.append(ValidationIssue(
                "evaluator.duplicate_stage", f"stages[{index}].name", name,
            ))
        names.append(name)
        kind = str(stage.get("stage_kind", "")).strip().lower()
        if kind in RESERVED_STAGE_KINDS:
            issues.append(ValidationIssue(
                "evaluator.workflow_not_an_evaluator",
                f"stages[{index}].stage_kind",
                f"'{kind}' is a surrounding workflow, not an evaluator stage",
            ))

    stage_index = {
        str(stage.get("name", "")).strip(): position
        for position, stage in enumerate(stages)
        if isinstance(stage, dict)
    }
    for index, stage in enumerate(stages):
        if not isinstance(stage, dict):
            continue
        declared = stage.get("verdicts") or list(CANONICAL_VERDICTS)
        if not isinstance(declared, list):
            issues.append(ValidationIssue(
                "evaluator.malformed_verdicts", f"stages[{index}].verdicts", "",
            ))
            continue
        for verdict in declared:
            if verdict not in CANONICAL_VERDICTS:
                issues.append(ValidationIssue(
                    "evaluator.unknown_verdict",
                    f"stages[{index}].verdicts",
                    f"'{verdict}' is not a canonical verdict "
                    f"{list(CANONICAL_VERDICTS)}",
                ))
        rules = stage.get("on_verdict")
        if not isinstance(rules, dict):
            issues.append(ValidationIssue(
                "evaluator.chain_rules_undeclared", f"stages[{index}].on_verdict", "",
            ))
            continue
        for verdict in declared:
            if verdict not in CANONICAL_VERDICTS:
                continue
            rule = rules.get(verdict)
            if not isinstance(rule, dict) or not (
                rule.get("terminal") or str(rule.get("continue", "")).strip()
            ):
                issues.append(ValidationIssue(
                    "evaluator.chain_uncovered_verdict",
                    f"stages[{index}].on_verdict.{verdict}",
                    f"verdict '{verdict}' has no terminal or continuation rule",
                ))
                continue
            target = str(rule.get("continue", "")).strip()
            if not target:
                continue
            if target not in stage_index:
                issues.append(ValidationIssue(
                    "evaluator.chain_unknown_stage",
                    f"stages[{index}].on_verdict.{verdict}",
                    f"continuation target '{target}' is not a declared stage",
                ))
            elif stage_index[target] <= index:
                issues.append(ValidationIssue(
                    "evaluator.chain_cycle",
                    f"stages[{index}].on_verdict.{verdict}",
                    f"continuation '{target}' does not advance the ordered chain",
                ))
    return issues


def _validate_manifest_shape(definition: dict[str, Any]) -> list[ValidationIssue]:
    manifest = definition.get("io_manifest")
    if manifest in (None, {}):
        return []
    if not isinstance(manifest, dict):
        return [ValidationIssue("manifest.malformed", "io_manifest", "must be an object")]
    issues: list[ValidationIssue] = []
    for direction in ("inputs", "outputs"):
        declarations = manifest.get(direction, [])
        if not isinstance(declarations, list):
            issues.append(ValidationIssue(
                "manifest.malformed", f"io_manifest.{direction}", "must be a list",
            ))
            continue
        seen: set[str] = set()
        for index, declaration in enumerate(declarations):
            where = f"io_manifest.{direction}[{index}]"
            if not isinstance(declaration, dict):
                issues.append(ValidationIssue("manifest.malformed", where, ""))
                continue
            name = str(declaration.get("name", "")).strip()
            if not name:
                issues.append(ValidationIssue("manifest.unnamed", where, ""))
            elif name in seen:
                issues.append(ValidationIssue("manifest.duplicate_name", where, name))
            seen.add(name)
    return issues


def _validate_effects(definition: dict[str, Any]) -> list[ValidationIssue]:
    effects = definition.get("effects", [])
    if not isinstance(effects, list):
        return [ValidationIssue("effect.malformed", "effects", "must be a list")]
    issues: list[ValidationIssue] = []
    seen: set[str] = set()
    for index, effect in enumerate(effects):
        where = f"effects[{index}]"
        if not isinstance(effect, dict):
            issues.append(ValidationIssue("effect.malformed", where, ""))
            continue
        name = str(effect.get("name", "")).strip()
        if not name:
            issues.append(ValidationIssue("effect.unnamed", where, "declare an effect name"))
        elif name in seen:
            issues.append(ValidationIssue("effect.duplicate_name", where, name))
        seen.add(name)
        if not str(effect.get("sink", "")).strip():
            issues.append(ValidationIssue(
                "effect.sink_undeclared", f"{where}.sink", "declare the effect sink",
            ))
        if not str(effect.get("destination", "")).strip():
            issues.append(ValidationIssue(
                "effect.destination_undeclared",
                f"{where}.destination",
                "declare the external destination",
            ))
        if "credential_class" not in effect:
            issues.append(ValidationIssue(
                "effect.credential_class_undeclared",
                f"{where}.credential_class",
                "declare the required credential class ('none' when no secret is used)",
            ))
        # A destination is echoed back to the user in would_execute records and
        # confirmation prompts, so it must not smuggle a secret in its userinfo
        # or query string.
        for issue in _destination_secret_issues(
            str(effect.get("destination", "")), f"{where}.destination"
        ):
            issues.append(issue)
    return issues


def _destination_secret_issues(destination: str, path: str) -> list[ValidationIssue]:
    from tinyassets.authoring.sandbox import destination_secret_parts

    parts = destination_secret_parts(destination)
    if not parts:
        return []
    return [ValidationIssue(
        "effect.destination_carries_secret",
        path,
        "a destination must not carry secret material "
        f"({', '.join(parts)}); keep the secret in the vault and declare a "
        "credential_class instead",
    )]


def _validate_no_secret_material(definition: dict[str, Any]) -> list[ValidationIssue]:
    """Refuse secret-shaped *declaration keys* anywhere in the draft document.

    A draft is stored, echoed back in inspection views, and copied into event
    payloads and published versions. Storing a secret and redacting it on the way
    out is the wrong direction — one un-redacted path leaks it — so a declaration
    key that would hold secret material is refused before it is ever persisted.
    Free-text *values* (prompts, descriptions, sketches) are user content the
    platform does not classify; this gate is about keys.
    """
    from tinyassets.authoring.sandbox import FORBIDDEN_DECLARATION_KEYS

    issues: list[ValidationIssue] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                where = f"{path}.{key}" if path else str(key)
                if str(key).strip().lower() in FORBIDDEN_DECLARATION_KEYS:
                    issues.append(ValidationIssue(
                        "definition.inline_credentials_forbidden",
                        where,
                        "a draft never carries secret material; declare a "
                        "credential_class and let the canonical vault vend the "
                        "secret to the adapter at run time",
                    ))
                    continue
                walk(value, where)
        elif isinstance(node, list):
            for index, item in enumerate(node):
                walk(item, f"{path}[{index}]")

    walk(definition, "")
    return issues


def _validate_sandbox_policy(definition: dict[str, Any]) -> list[ValidationIssue]:
    from tinyassets.authoring import sandbox

    declaration = definition.get("sandbox_policy", {})
    if not declaration:
        return []
    if not isinstance(declaration, dict):
        return [ValidationIssue("sandbox.malformed_policy", "sandbox_policy", "")]
    _, issues = sandbox.policy_from_declaration(declaration)
    return [i for i in issues if i.code != "sandbox.budget_clamped"]


def _validate_composition(
    definition: dict[str, Any],
    self_artifact_id: str,
    resolve_version: VersionResolver | None,
) -> list[ValidationIssue]:
    composes = definition.get("composes", [])
    if not isinstance(composes, list):
        return [ValidationIssue("composition.malformed", "composes", "must be a list")]

    issues: list[ValidationIssue] = []
    direct: list[str] = []
    for index, entry in enumerate(composes):
        where = f"composes[{index}]"
        if not isinstance(entry, dict):
            issues.append(ValidationIssue("composition.malformed", where, ""))
            continue
        artifact_id = str(entry.get("artifact_id", "")).strip()
        if not artifact_id:
            issues.append(ValidationIssue(
                "composition.artifact_undeclared", f"{where}.artifact_id", "",
            ))
            continue
        if self_artifact_id and artifact_id == self_artifact_id:
            issues.append(ValidationIssue(
                "composition.cycle", where, "a draft cannot compose itself",
            ))
            continue
        direct.append(artifact_id)

    if resolve_version is None or not direct:
        return issues

    # Transitive cycle detection over resolvable composed artifacts.
    seen: set[str] = set()
    frontier = list(direct)
    while frontier:
        artifact_id = frontier.pop()
        if artifact_id in seen:
            continue
        seen.add(artifact_id)
        resolved = resolve_version(artifact_id)
        if not resolved:
            continue
        nested = (resolved.get("definition") or {}).get("composes", [])
        if not isinstance(nested, list):
            continue
        for entry in nested:
            if not isinstance(entry, dict):
                continue
            nested_id = str(entry.get("artifact_id", "")).strip()
            if not nested_id:
                continue
            if self_artifact_id and nested_id == self_artifact_id:
                issues.append(ValidationIssue(
                    "composition.cycle",
                    "composes",
                    f"composition through '{artifact_id}' returns to this artifact",
                ))
                return issues
            frontier.append(nested_id)
    return issues


# ── Views ──────────────────────────────────────────────────────────────────


def summarize_definition(
    definition: dict[str, Any],
    *,
    artifact_kind: str,
    issues: list[ValidationIssue] | None = None,
) -> dict[str, Any]:
    """Adapt terminology for a casual reader without hiding anything material.

    Effects, destinations, credential classes, and unresolved validation errors
    are always present — a summary may simplify wording, never risk.
    """
    manifest = definition.get("io_manifest") or {}
    effects = [
        {
            "name": effect.get("name", ""),
            "sink": effect.get("sink", ""),
            "destination": effect.get("destination", ""),
            "effect_class": "reversible" if effect.get("reversible") else "irreversible",
            "credential_class": effect.get("credential_class", "unknown"),
        }
        for effect in definition.get("effects", [])
        if isinstance(effect, dict)
    ]
    if artifact_kind == "node":
        stages = [
            {
                "name": node.get("node_id", ""),
                "display_name": node.get("display_name", ""),
                "phase": node.get("phase", ""),
            }
            for node in definition.get("node_defs", [])
            if isinstance(node, dict)
        ]
    else:
        stages = [
            {
                "name": stage.get("name", ""),
                "human_review": bool(stage.get("human_review")),
                "external": bool(stage.get("external")),
            }
            for stage in definition.get("stages", [])
            if isinstance(stage, dict)
        ]
    return {
        "name": definition.get("name", ""),
        "description": definition.get("description", ""),
        "sketch": definition.get("sketch", ""),
        "artifact_kind": artifact_kind,
        "inputs": manifest.get("inputs", []) if artifact_kind == "node"
        else definition.get("inputs", []),
        "outputs": manifest.get("outputs", []) if artifact_kind == "node"
        else definition.get("outputs", {}),
        "stages": stages,
        "effects": effects,
        "providers": sorted({
            str(node.get("model_hint", ""))
            for node in definition.get("node_defs", [])
            if isinstance(node, dict) and node.get("model_hint")
        }),
        "blockers": [issue.to_dict() for issue in (issues or [])],
    }

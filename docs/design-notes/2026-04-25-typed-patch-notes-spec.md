---
status: active
---

# TypedPatchNotes Dataclass Spec

**Date:** 2026-04-25
**Author:** dev-2
**Status:** Design proposal. Replaces #53's `patch_notes: dict[str, Any]` placeholder with a typed dataclass.
**Builds on:** Task #53 route-back verdict (consumer); Task #48 contribution ledger §1.4 + attribution-layer-specs §1.4 (citation chain via `patch_notes_id`); navigator's #62 audit (Q2 close).
**Scope:** dataclass shape + validation + serialization. No schema changes; no new MCP actions.

---

## 1. Recommendation

A frozen dataclass `PatchNotes` with content-hashed `patch_notes_id`, structured `evidence_refs`, in-payload `route_history`. Replaces the `dict[str, Any]` placeholder in `EvalResult.patch_notes` (Task #53). Lives in `tinyassets/evaluation/patch_notes.py` (new file); JSON-serialized into `run_events.detail_json` and `contribution_events.metadata_json` columns.

---

## 2. Dataclass shape

```python
# tinyassets/evaluation/patch_notes.py

from dataclasses import dataclass, field
from typing import Any, Literal


@dataclass(frozen=True)
class EvidenceRef:
    """A single artifact citation in a gate evaluator's decision."""

    kind: Literal["wiki_page", "node_def", "branch_version", "github_pr", "run_artifact"]
    id: str            # slug for wiki, branch_version_id, etc.
    cited_by: str      # which evaluator (by id) cited this artifact


@dataclass(frozen=True)
class PatchNotes:
    """Structured payload flowing through gate route-back chains.

    Replaces the `dict[str, Any]` placeholder in EvalResult (Task #53).
    Each instance is identified by a content-hashed patch_notes_id
    computed in __post_init__ from a stable JSON serialization of all
    other fields. Route-back hops produce new instances (via
    `dataclasses.replace`) with new ids — see §4.
    """

    # Author + identity (REQUIRED)
    summary: str                                   # ≤200 chars; chatbot-render-friendly
    rationale: str                                 # markdown body; unbounded
    author_actor_id: str                           # who composed; required, no anonymous default

    # Provenance — what's the patch FROM
    affected_files: list[str] = field(default_factory=list)
    tests_added: list[str] = field(default_factory=list)
    evidence_run_id: str | None = None             # links to run that produced this patch

    # Citation — anti-spam invariant for #48 surface 5 (`feedback_provided`)
    evidence_refs: list[EvidenceRef] = field(default_factory=list)

    # Routing state — engine-managed; chatbot doesn't write directly
    route_history: list[tuple[str, str]] = field(default_factory=list)
    # Each entry: (goal_id, scope_token). Cycle-detection per #53 §3.

    # Identity — engine-computed in __post_init__
    patch_notes_id: str = ""                       # SHA-256 truncated to 12 chars

    # Domain-specific extras — opaque escape hatch
    extra: dict[str, Any] = field(default_factory=dict)
```

### Why each field

- **`summary` ≤200 chars:** chatbot UI rendering hint. Enforced at validation (§3 rule 1).
- **`author_actor_id` required, no default:** patch_notes is a value-creating artifact per Task #48 §1; anonymity breaks the credit chain. Producer must know who wrote it.
- **`evidence_run_id` optional:** patch_notes can originate from a run (chatbot-replayed canary, gate-rejection cycle) OR from a fresh chatbot composition. Both legitimate.
- **`evidence_refs`:** anti-spam invariant from attribution-layer-specs §1.4. Empty list means no `feedback_provided` events emit when this PatchNotes feeds a gate decision. Typed `EvidenceRef` lets the gate evaluator validate cites at emit-time.
- **`route_history`:** lifts #53's `_route_history` magic-dict-key to a typed field. Cycle-detection state visible in the type system. See §4.
- **`patch_notes_id`:** content-hashed identity. Used by attribution-layer-specs §1.4 `feedback_provided` event metadata to stabilize cite chains across serialization round-trips.
- **`extra`:** domain skills (scientific-domain `metric_name`, paper-writing `target_journal`, etc.) extend without schema migration.

---

## 3. Tradeoff vs alternatives

| Axis | TypedDict | Pydantic BaseModel | dataclass + helpers (recommended) |
|---|---|---|---|
| Stdlib-only | ✓ | ✗ (adds dep) | ✓ |
| Runtime validation | ✗ (type hints only) | ✓ | ✓ via `__post_init__` |
| Compute `patch_notes_id` automatically | ✗ no __post_init__ | ✓ via `model_validator` | ✓ via `__post_init__` |
| Project consistency (NodeDefinition / EvalResult are dataclasses) | ✗ | ✗ | ✓ |
| Frozen / immutable support | partial | ✓ (`frozen=True`) | ✓ (`frozen=True`) |
| JSON serialization | manual | built-in | manual (matches existing `to_dict` / `from_dict` pattern) |

**Pick: dataclass + helpers.** Three axes decisive: stdlib-only, project-consistent (matches existing `NodeDefinition` / `BranchDefinition` / `EvalResult` shape), supports automatic id-computation. Pydantic adds a dependency the project uses sparingly; TypedDict can't compute the hash.

---

## 4. Validation rules

### Strict-at-construction (in `__post_init__`)

```python
def __post_init__(self):
    # Rule 1: summary length
    if not self.summary or len(self.summary) > 200:
        raise ValueError(f"summary must be 1-200 chars, got {len(self.summary)}")
    # Rule 2: author_actor_id required, non-empty
    if not self.author_actor_id:
        raise ValueError("author_actor_id is required")
    # Rule 3: evidence_refs all valid (Literal kind validated by dataclass already)
    for ref in self.evidence_refs:
        if not ref.id:
            raise ValueError("EvidenceRef.id cannot be empty")
        if not ref.cited_by:
            raise ValueError("EvidenceRef.cited_by cannot be empty")
    # Rule 4: compute patch_notes_id from canonical JSON (sort_keys=True)
    object.__setattr__(self, "patch_notes_id", self._compute_id())
```

`object.__setattr__` is required because `frozen=True` blocks direct assignment; this is the documented pattern.

### Strict-at-consume

The engine, when consuming a PatchNotes from a downstream channel (route-back invocation, contribution-event emit), MUST re-validate by reconstructing via `from_dict()`. If `from_dict()` raises, the consumer rejects the payload with structured error.

Two layers of validation = correct discipline. Producer-side validates at emit. Engine-side re-validates because payloads cross trust boundaries (chatbot → engine, run → run, network → daemon).

### Immutability + re-instantiation contract

Each route-back hop produces a NEW PatchNotes via `dataclasses.replace(notes, route_history=[...])`. This triggers `__post_init__` again, which means a NEW `patch_notes_id`. **The id is the entity-identity-per-state, not a stable identity-across-states.** Lineage is preserved in `route_history` (the (goal_id, scope_token) tuples accumulate); identity-per-hop is preserved in `patch_notes_id`.

This matters for attribution-layer-specs §1.4: `feedback_provided` events reference the patch_notes_id at the moment the gate cited it. Subsequent route-backs with new ids do not invalidate prior cites.

### `_compute_id` deterministic JSON

```python
def _compute_id(self) -> str:
    # Stable JSON serialization: sort keys, exclude patch_notes_id itself
    payload = {
        k: v for k, v in dataclasses.asdict(self).items()
        if k != "patch_notes_id"
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:12]
```

`sort_keys=True` is the canonical Python approach for deterministic JSON. SHA-256 truncated to 12 chars is sufficient — collision probability at expected volume is vanishingly small (~10^14 patch_notes before 50% collision risk).

---

## 5. Composition with #53 route-back

`route_history` field is THE cycle-detection state. Today's #53 spec stores it as an opaque-dict magic key `_route_history`; this proposal lifts it to a typed field.

Engine logic from #53 §3 is unchanged in semantics, only refactored:

```python
# Before (opaque dict):
visited = patch_notes.get("_route_history", [])
if len(visited) > 3 or (goal, scope) in visited:
    terminate("route_back_loop")

# After (typed):
if len(notes.route_history) > 3 or (goal, scope) in notes.route_history:
    terminate("route_back_loop")
new_notes = dataclasses.replace(
    notes, route_history=[*notes.route_history, (goal, scope)]
)  # __post_init__ recomputes patch_notes_id
```

Max-depth check + visited-set check + `TINYASSETS_ROUTE_BACK_MAX_DEPTH` env var from #53 §3 stay identical. No semantic change; cleaner type discipline.

---

## 6. Composition with attribution-layer-specs §1.4 `feedback_provided`

When a gate evaluator decides "I'm citing this PatchNotes' wiki-page evidence as decision input," it appends to `notes.evidence_refs`:

```python
notes_with_cite = dataclasses.replace(
    notes,
    evidence_refs=[
        *notes.evidence_refs,
        EvidenceRef(kind="wiki_page", id="bugs/BUG-042", cited_by="evaluator_xyz"),
    ],
)
```

The `feedback_provided` event then records `notes.patch_notes_id` in metadata. The event's `source_artifact_id` field references the cited artifact (`bugs/BUG-042`); the metadata tracks `patch_notes_id` so downstream contribution-ledger queries can trace cite chains.

**Anti-spam invariant:** the gate runner inspects `len(notes.evidence_refs) > 0` before emitting any `feedback_provided` events. Empty refs → no events → no credit. Producer can't game the system by emitting decisions without explicit cites.

---

## 7. Migration path

### Step 0 — define dataclass + helpers + tests

Add `tinyassets/evaluation/patch_notes.py` with `PatchNotes` + `EvidenceRef` classes. Helpers: `to_dict`, `from_dict`, `_compute_id`. Tests per §8.

### Step 1 — `extensions action=author_patch_notes` MCP wrapper (out of this proposal's scope)

Follow-on dispatch. The action accepts the dataclass fields, constructs + validates the PatchNotes server-side, returns `{patch_notes_id, serialized_dict}`. **Two layers of validation:** chatbot-side pre-flight (catch malformed early), engine-side re-validate at consume time. Both must pass for the patch_notes to be honored.

### Step 2 — gate evaluator emit consumes typed PatchNotes

The route-back evaluators (per #53) populate `EvalResult.patch_notes: PatchNotes` (typed) instead of `dict[str, Any]` (opaque). Engine logic from #53 §5 reads typed fields directly.

### Step 3 — deprecate dict path

Two-week sunset window. During sunset, `EvalResult.__post_init__` accepts both `dict` and `PatchNotes`; the dict path emits a deprecation warning + auto-converts via `PatchNotes.from_dict()`. After sunset, dict path raises `TypeError`.

---

## 8. Tests footprint

`tests/test_patch_notes.py`, ~7-9 tests:

- Construction with all required fields succeeds; computes `patch_notes_id`.
- Missing `summary` raises ValueError.
- Missing `author_actor_id` raises ValueError.
- `summary` >200 chars raises ValueError.
- `EvidenceRef` with empty `id` or `cited_by` raises ValueError.
- `patch_notes_id` deterministic: same content → same id; different content → different id.
- `dataclasses.replace(notes, route_history=[...])` → new instance with new id, route_history populated.
- `to_dict() → from_dict()` round-trip preserves all fields and recomputes id consistently.
- Forward-compat: `from_dict({"summary": ..., "future_field": ...})` puts unknown keys into `extra` and logs INFO-level warning.

---

## 9. Open questions

1. **`patch_notes_id` hash truncation — SHA-256 truncated to 12 chars.** Closed per lead pre-draft note.

2. **`author_actor_id` required, no anonymous default.** Closed per lead pre-draft note. Strong principled call: patch_notes is value-creating per #48; anonymity breaks credit chain.

3. **JSON-stable serialization via `sort_keys=True`.** Closed per lead pre-draft note. Standard Python canonical-JSON pattern.

4. **`extra` dict — no schema validation.** Closed per lead pre-draft note. Domain skills validate downstream.

5. **Forward-compat for new fields — extra dict + INFO-level warning.** Closed per lead pre-draft note. Old code reading new payloads continues to work; new code reading old payloads fills defaults. INFO not WARNING because version skew is expected, not anomalous; promote to WARNING only at high frequency.

6. **(Truly open) Maximum `evidence_refs` length.** A gate evaluator could pad refs to game `feedback_provided` weight. Recommend cap at 16 refs per PatchNotes; above raise ValueError. Tuneable via `TINYASSETS_PATCH_NOTES_MAX_EVIDENCE_REFS` env var, default 16.

7. **(Truly open) `tests_added` validation.** Should the dataclass verify those test paths exist? Recommend NO at construction time — tests may be authored later in the chain. The list is metadata, not a runtime contract. Future enhancement: a separate verifier action validates "tests exist + pass" post-merge.

---

## 10. What this proposal does NOT cover

- **No code changes.** Design only; lead routes implementation as separate dispatch.
- **No `extensions action=author_patch_notes` MCP action wiring.** Step 1 placeholder; separate dispatch.
- **No schema changes.** PatchNotes is in-memory + JSON-serialized into existing `metadata_json` columns. Zero ALTER TABLE.
- **No #53 v2 amend.** Folding TypedPatchNotes into #53 is a separate small follow-on.
- **No tests-existence verifier.** Q7 punt; Future feature.

---

## 11. References

- Replaces placeholder in: `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (Task #53) — `EvalResult.patch_notes: dict[str, Any]` placeholder becomes `PatchNotes` typed.
- Citation-chain consumer: attribution-layer-specs §1.4 (`feedback_provided` event) — uses `patch_notes_id` to trace cites.
- Contribution ledger: `docs/design-notes/2026-04-25-contribution-ledger-proposal.md` (Task #48) — `feedback_provided` event surface 5 references this dataclass.
- Sibling dataclasses (project-consistency reference): `tinyassets/branches.py` (NodeDefinition, BranchDefinition, EdgeDefinition); `tinyassets/evaluation/__init__.py:37` (EvalResult).
- Existing serialization pattern (`to_dict` / `from_dict`): `tinyassets/branches.py:680-741` (BranchDefinition).
- Cycle-detection that this dataclass formalizes: Task #53 §3 (max-depth + visited-set) and §6 Q3 (`TINYASSETS_ROUTE_BACK_MAX_DEPTH` env).

---
status: active
---

# Implementation Discipline Conventions

**Date:** 2026-04-25
**Author:** navigator
**Status:** Convention doc. Captures three implementation-side patterns that emerged from this session's pair-reads. Each pattern has at least two empirical instances; codifying now prevents drift as more impls land.
**Builds on:**
- `docs/design-notes/2026-04-25-shared-helper-convention.md` (def/version sibling pattern — first convention doc).
- `docs/design-notes/2026-04-25-design-proposal-pattern-convention.md` (dev-2-2's design-proposal-pattern convention).
- Empirical sources: impl-pair-read #78 (`docs/audits/2026-04-25-impl-71-72-75-vs-48-convergence.md`), impl-pair-read R1 (`docs/audits/2026-04-25-impl-54-65a-65b-vs-56-convergence.md`).

---

## 1. Failure-class as class-level attributes

### Pattern

When defining a structured exception that the MCP layer or a downstream caller needs to read for `failure_class` + `suggested_action`, **store these on the class, not just the instance.** The handler reads them via `ExcClass.failure_class` directly without instantiating a defensive copy.

### Example (in production)

```python
# tinyassets/runs.py — landed via #65b
class SnapshotSchemaDrift(Exception):
    """Raised when a published version's snapshot can't be reconstructed."""

    failure_class = "snapshot_schema_drift"
    suggested_action = "republish at current schema version"
```

### MCP-layer consumer

```python
# universe_server.py:8496-8501
except SnapshotSchemaDrift as exc:
    return json.dumps({
        "error": str(exc),
        "failure_class": SnapshotSchemaDrift.failure_class,
        "suggested_action": SnapshotSchemaDrift.suggested_action,
    })
```

### Why class-level not instance-level

1. **Read without instantiation.** The handler can reference `failure_class` from the class itself without creating an instance — useful for catalog generation, error-class enumeration, or exception-handling code that needs to know the metadata before any exception fires.
2. **Single source of truth.** Class-level attribute means one place to change the failure_class string. Instance-level means N callers might construct exceptions with different strings; drift is harder to spot.
3. **Forward-compat with future tooling.** A future "list all failure classes the system can emit" introspection tool walks subclasses of `Exception` (or a dedicated base class) and reads `failure_class` directly. Instance-level requires constructing example instances of every class.
4. **Subclass override is natural.** Subclassing the exception and overriding the class attribute gives narrower failure classes for free.

### When to apply

Apply when ALL three hold:
- The exception carries a `failure_class` string that's part of a public contract (MCP error-class enum, structured response shape, downstream consumer-readable).
- The MCP layer or a downstream consumer needs to read the metadata.
- The exception is raised from infrastructure / runtime code (not from one-off business logic).

### When NOT to apply

- Exceptions that are purely internal control-flow (e.g., short-circuit signals between two co-located functions). Use plain `Exception` subclasses.
- Exceptions whose failure_class genuinely varies per instance (e.g., different `failure_class` for each invocation context). Then instance-level is correct; class-level wouldn't fit.

### Existing instances (this session)

- `SnapshotSchemaDrift` per #65b (described above).
- *Future candidates:* `RolledBackDuringExecution` per #57 §6 Q6 (when impl lands); `AuthorizationError` per #69 §2 (when impl lands — `operation` field is class-shape-eligible).

### Implementation-time test convention

Test the class attribute presence + value WITHOUT triggering the exception:

```python
def test_snapshot_schema_drift_class_attrs():
    """SnapshotSchemaDrift exposes failure_class + suggested_action as class attrs."""
    assert SnapshotSchemaDrift.failure_class == "snapshot_schema_drift"
    assert SnapshotSchemaDrift.suggested_action == "republish at current schema version"
```

This catches accidental removal or rename without requiring exception-construction setup.

---

## 2. Specific exception catch list, not blanket `except Exception`

### Pattern

When wrapping a parse, load, or `from_dict`-style call in a structured exception, **name the specific exception types your wrapper handles.** Don't blanket-catch `except Exception`.

### Example (in production)

```python
# tinyassets/runs.py:1854-1860 — landed via #65b
try:
    branch = BranchDefinition.from_dict(bv.snapshot)
except (AttributeError, KeyError, TypeError, ValueError) as exc:
    raise SnapshotSchemaDrift(
        f"Snapshot for {branch_version_id!r} cannot be reconstructed: "
        f"{exc}. Republish at current schema version."
    ) from exc
```

### Why specific types

1. **Surfaces real failures.** `(AttributeError, KeyError, TypeError, ValueError)` are the four ways `from_dict` can reasonably fail (missing field, wrong shape, wrong type, value out of range). Catching only these surfaces *real schema drift*.
2. **Lets bug-elsewhere errors propagate.** A `RuntimeError` from a faulty downstream call should propagate normally, not get wrapped as `SnapshotSchemaDrift` (which would silently misclassify the bug).
3. **Documents the contract.** Reading the catch list tells the next implementer "these are the failure modes the wrapper is meant for." Blanket-catch hides the contract.
4. **Plays well with `raise ... from exc`.** The chained exception preserves the original failure underneath the wrapper. Debuggers see both.

### When to apply

When wrapping any of:
- Parse calls (`json.loads`, `xml.etree`, `yaml.safe_load`).
- Load / reconstruction calls (`BranchDefinition.from_dict`, deserialization).
- Schema validation calls (`branch.validate()` if it raises).

### When NOT to apply

- Top-level error handlers in long-running daemons that need to keep going regardless of the failure class. Blanket-catch + log-and-continue is correct there.
- Test-cleanup code (e.g., `with contextlib.suppress(Exception)` in a `finally:`).

### How to discover the right exception list

When wrapping a function whose failure modes aren't documented:

1. Read its source if available; note every `raise` statement.
2. If source unavailable, try to construct several malformed inputs in a unit test and observe what bubbles up.
3. Default to `(AttributeError, KeyError, TypeError, ValueError)` for `from_dict`-style reconstruction; this covers >95% of cases.

### Implementation-time test convention

For each named exception in the catch list, write a test that verifies the wrapper triggers:

```python
def test_snapshot_schema_drift_on_missing_required_field():
    """SnapshotSchemaDrift fires when from_dict raises KeyError for missing field."""
    bad_snapshot = {...}  # snapshot missing entry_point
    with pytest.raises(SnapshotSchemaDrift):
        execute_branch_version_async(base_path, branch_version_id="...", inputs={})
```

One test per exception type in the catch list. If one of the catches is never reached in tests, it's either dead code or a coverage gap.

---

## 3. Pair-read recommendations flow into commit messages

### Pattern

When implementing a primitive that has a pair-read or audit recommendation, **cite the pair-read or audit in the commit message.** Future readers walking `git log --grep=pair-read` see the convergence-loop's downstream impact directly.

### Example (in production)

#65a commit message excerpt (commit `80a1e14`):

> "Phase A item 6 implementation, first of two SHIPs (refactor + schema). Per design dc7d2cb (Task #54) + audit 4e608e3 + **pair-read #59**. Step 0+1+2 of dev's plan; Steps 3-5 land in #65b."

The pair-read citation makes the commit traceable: "this refactor-vs-helper-add split came from pair-read #59 §3 recommendation."

### Why this matters

1. **The convergence-loop becomes self-documenting.** `git log --grep="pair-read"` produces a clean trace of every commit influenced by a navigator/dev/verifier pair-read. The pattern's empirical impact is visible at the commit-history level.
2. **Future implementers see what design decisions are load-bearing.** A commit message that references a pair-read tells the reader "this isn't an arbitrary choice; here's where the trade-off was litigated."
3. **Audit trail for design ratification.** When a recommendation flows: pair-read finding → impl decision → commit message → SHIP → main, the chain is fully auditable. No "where did this come from?" questions later.
4. **Encourages the convergence-loop to keep producing actionable findings.** If pair-reads consistently produce findings that don't influence implementation, the pattern decays. Commit-message citations are visible feedback that the work is paying off.

### When to apply

Apply when:
- An implementation embodies a pair-read or audit recommendation that wasn't in the original design proposal.
- The recommendation changed the impl shape or sequencing materially (e.g., refactor-vs-helper-add split, schema-drift handling, anonymous-author skip widening).
- The implementation is non-trivial (more than a typo fix or one-line change).

### When NOT to apply

- Trivial follow-up commits (e.g., ruff fixes, typo corrections, doc tweaks).
- Implementations where the pair-read finding is purely positive ("this design is already correct") — there's no recommendation to honor.

### Format suggestion

In the commit message body (not subject), add a line like:

```
Per design <design_commit_sha> (Task #X) + audit <audit_commit_sha> + pair-read #Y.
```

Or, if the pair-read finding directly drove the impl shape:

```
Refactor-as-separate-dispatch per pair-read #59 §3 (`docs/audits/2026-04-25-pair-54-vs-56-convergence.md`).
```

### Existing instances (this session)

- #65a commit `80a1e14` — cites "audit 4e608e3 + pair-read #59" in commit message body.
- #71 commit `098cf15` — cites "design 287790c (#48 §1)" + comment block in code itself referencing the design source.
- #75 commit `fea677d` — cites design + Q1 disposition.

---

## 4. Cross-references

- Source pair-reads:
  - `docs/audits/2026-04-25-impl-71-72-75-vs-48-convergence.md` (#78, navigator) — impl-side pair-read #1 surfacing classlevel-attr pattern + specific-exception pattern in `_EMIT_FAILURES` shape.
  - `docs/audits/2026-04-25-impl-54-65a-65b-vs-56-convergence.md` (R1, navigator) — impl-side pair-read #2 surfacing classlevel-attr pattern + specific-exception pattern in `SnapshotSchemaDrift` shape + commit-message-citation pattern.
- Sibling conventions:
  - `docs/design-notes/2026-04-25-shared-helper-convention.md` (def/version sibling pattern).
  - `docs/design-notes/2026-04-25-design-proposal-pattern-convention.md` (Task #68, dev-2-2 — design-proposal pattern).
- Substrate references:
  - `tinyassets/runs.py:1789-1802` (`SnapshotSchemaDrift` example).
  - `tinyassets/runs.py:1854-1860` (specific-exception catch example).
  - `tinyassets/contribution_events.py:30` (`_EMIT_FAILURES` counter — same architectural shape as class-level attrs in spirit: state cleanly readable without instantiation).

---

## 5. What this convention doc does NOT cover

- **Not a code-style guide.** Conventions here are about implementation *patterns* surfacing repeatedly across the substrate, not formatting / naming / linting decisions.
- **Not exhaustive.** Other patterns may surface as more impls land; this doc starts with three empirically-validated ones.
- **Not load-bearing for v1 dispatch.** Implementations that don't follow these conventions still ship; the conventions are guidance for cleaner code, not gatekeepers.
- **Not a replacement for design-proposal pattern doc** (#68) — that covers design-time pattern; this covers impl-time pattern.
- **Not version-pinned.** Conventions can evolve as more empirical data surfaces. Worth re-reviewing every ~10 impl-side pair-reads to check whether the patterns hold or whether new ones emerged.

---

## 6. v2 candidates (not yet codified)

These patterns are observed but lack the two-instance threshold for codification:

- **Resilience discipline: try/except + counter + log.** From #78 — `_EMIT_FAILURES` pattern. Best-effort observability layered on load-bearing semantics. One concrete instance so far.
- **Pair-read scaffolding before final design lands.** From `docs/audits/2026-04-25-pair-50-vs-56-convergence.md` (scaffolding written ahead of #56 design landing). Pattern: write the constraint list first; populate sections after design ships. Saves ~30 min on the actual pair-read.
- **Implementation goes beyond design when design is implicit.** From #78 cross-check 5 — anonymous-author skip widening. Pattern: implementer encodes a sound widening that design didn't state; pair-read ratifies it as canonical.

When second instances of these surface, codify in v2 of this doc (or a follow-on convention doc).

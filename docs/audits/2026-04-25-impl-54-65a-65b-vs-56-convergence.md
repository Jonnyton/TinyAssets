# Implementation Pair-Read: #65a + #65b ↔ #54 runner-version-id-bridge design

**Date:** 2026-04-25
**Author:** navigator
**Pair:** dev-2's runner-version-id implementation lane (`#65a` schema + `_execute_branch_core` extraction + `#65b` `execute_branch_version_async` + `_action_run_branch_version`) ↔ dev-2's #54 design proposal.
**Audit shape:** **Second implementation-side pair-read in the session.** Sibling to #78 (#71+#72+#75 vs #48). Establishes impl-side pair-read as routine.
**Note on the brief framing:** lead's brief said "vs #56 design"; the design that #54+#65a+#65b directly implement is **#54 itself** (runner-version-id-bridge). #56 (sub-branch invocation) is a separate design lane whose impl is #76a/b/c (in flight). This audit targets #54 as the design source, with cross-check on #56 composition where the two designs meet.
**Commits audited:**
- `80a1e14` Task #65a — `runs.branch_version_id` column + `_execute_branch_core` extraction.
- `ee254b0` Task #65b — `execute_branch_version_async` + `_action_run_branch_version` + `SnapshotSchemaDrift`.
**Design source:** `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (#54, committed `dc7d2cb`).

---

## Stamp

**PAIR CONVERGES.** All 6 cross-checks pass. Implementation honors design intent at every named site, with three sharpening-additions beyond the design that are sound and worth pinning. **Same convergence quality as the #71/#72/#75 audit** — the convergence-loop pattern continues producing tight integration through the impl phase.

---

## 1. Cross-check resolution

### Cross-check 1: Schema fidelity (`runs.branch_version_id` column vs #54 §4)

**CONVERGES.** Design (#54 §4):

```sql
ALTER TABLE runs ADD COLUMN branch_version_id TEXT;
CREATE INDEX IF NOT EXISTS idx_runs_branch_version
    ON runs(branch_version_id);
```

Implementation (`runs.py:238-248`):

```python
if "branch_version_id" not in existing_runs:
    conn.execute(
        "ALTER TABLE runs ADD COLUMN branch_version_id TEXT"
    )
conn.execute(
    "CREATE INDEX IF NOT EXISTS idx_runs_branch_version "
    "ON runs(branch_version_id)"
)
```

**Sharpening:** PRAGMA-probe pattern (`if "branch_version_id" not in existing_runs`) makes the migration idempotent across daemon restarts — same pattern used elsewhere in `runs.py` for canonical column migrations. Design said "ALTER... NULLABLE so existing rows stay valid; ALTER is additive." Implementation correctly probes first to avoid double-ALTER errors. Convergence with sharpening.

### Cross-check 2: Helper extraction fidelity (`_execute_branch_core` vs #54 §2)

**CONVERGES with refinement.** Design (#54 §2):

> "The shared `_execute_branch_core` is the existing run-execution path with one new optional arg. The current `execute_branch_async` (def-based) keeps using `_execute_branch_core` with `branch_version_id=None`. The new helper passes the id through. Both paths converge to the same execution loop."

Implementation (`runs.py:1680-1786`):

```python
def _execute_branch_core(
    base_path, *, branch, inputs, run_name="", actor="anonymous",
    provider_call=None, recursion_limit_override=None,
    concurrency_budget_override=None,
    branch_version_id: str | None = None,
) -> RunOutcome:
    run_id = _prepare_run(
        base_path, branch=branch, inputs=inputs,
        run_name=run_name, actor=actor,
        branch_version_id=branch_version_id,  # threaded into runs row
    )
    # ... existing execution body unchanged ...

def execute_branch_async(...):
    return _execute_branch_core(..., branch_version_id=None)
```

**Cross-check verified verbatim against design.** The extraction matches what #54 §2 sketched. **One implementation refinement worth noting:** the `branch_version_id` arg is threaded into `_prepare_run` (which writes the runs row), not just held in a local. This means **the runs.branch_version_id column is populated at run-creation time, not after**. Cleaner than design suggested ("attribution at later steps") — the column is correct from the moment the run row exists.

Per pair-read #59 §3 recommendation: "**`_execute_branch_core` extraction should be its own dispatch unit BEFORE the new helper-add work**, so the refactor's behavior-preservation can be verified against existing tests in isolation." **Verified honored:** #65a is the refactor-only commit; #65b is the new-helper-add commit. Two separate SHIPs, each with its own test pass. **The pair-read recommendation made it through to dispatch sequencing.** Healthy convergence-loop signal.

### Cross-check 3: Action surface fidelity (`run_branch_version` vs #54 §4)

**CONVERGES verbatim.** Design (#54 §4) action signature:

```
extensions action=run_branch_version
  branch_version_id="<branch_def_id>@<sha8>"     # required
  inputs_json='{ ... }'                           # required
  run_name=""                                    # optional
  recursion_limit_override=NN                    # optional, 10-1000
  → returns { run_id, status, error?, validation_errors? }
```

Implementation (`universe_server.py:8423-8504`):

```python
def _action_run_branch_version(kwargs: dict[str, Any]) -> str:
    bvid = (kwargs.get("branch_version_id") or "").strip()
    if not bvid:
        return json.dumps({"error": "branch_version_id is required."})
    # inputs_json parse mirrors run_branch
    # recursion_limit_override parse (10-1000) mirrors run_branch
    try:
        outcome = execute_branch_version_async(...)
    except KeyError as exc:
        return json.dumps({"error": str(exc).strip("'\"")})
    except SnapshotSchemaDrift as exc:
        return json.dumps({
            "error": str(exc),
            "failure_class": SnapshotSchemaDrift.failure_class,
            "suggested_action": SnapshotSchemaDrift.suggested_action,
        })
    except Exception as exc:
        return json.dumps(_classify_run_error(exc, bvid))
```

**Same arg validation, same error shape, same action-handler structure as `_action_run_branch`.** Per #54 §2 "sibling action" rationale (convention parity with `publish_version`/`list`/`get_version`): the new action lives at the same dispatch table, mirrors the same response convention, doesn't disturb the existing `run_branch` handler. **Verified at `universe_server.py:8539`** — registry adds `"run_branch_version": _action_run_branch_version` alongside `"run_branch": _action_run_branch`. Both in the `_RUN_WRITE_ACTIONS` set at 8554.

### Cross-check 4: Three-version-concept correctness (per pair-read #59 §1 finding)

**CONVERGES — implementation honors all three concepts distinctly.** Per pair-read #59:

1. **`branch_def_id`** — TEXT primary key on `branch_definitions`. Live, mutable.
2. **`branch_version_id`** — TEXT primary key on `branch_versions`. Frozen snapshot id.
3. **`run_lineage.branch_version`** — INTEGER column. Audit-only (compare_runs / diff-since-parent purpose).

Implementation honors:

- **`runs.branch_version_id` (NEW per #65a):** populated only on version-based runs (per `runs.py:1085-1090` _prepare_run docstring: "branch_version_id is populated only for version-based runs"). Verified at `runs.py:330-347` create_run signature accepts the new arg; populates the column when set.
- **`run_lineage.branch_version` INTEGER:** UNCHANGED — `runs.py:163` `ON run_lineage(branch_def_id, branch_version)` index preserved. The audit-only column doesn't conflate with the new TEXT column.
- **`branch_def_id`** — UNCHANGED — `_resolve_branch_id` at universe_server.py:4489 still resolves either ID or name to the live def_id for `_action_run_branch`. Version-aware code path is separate.

**No conflation observed.** All three concepts coexist as design and pair-read #59 anticipated.

### Cross-check 5: SnapshotSchemaDrift handling

**CONVERGES + sharpened (closes pair-read #59 §1 Divergence 4).** Pair-read #59 flagged: "The from_dict-raises case stays as a fresh open Q for v2 dispatch." Implementation closes it.

Design called for: "wrap `BranchDefinition.from_dict(bv['snapshot'])` in a try/except and return a structured error like `{'error': 'snapshot deserialization failed: <detail>', 'failure_class': 'snapshot_schema_drift', 'suggested_action': 'republish at current schema version'}` matching the existing failure-class pattern."

Implementation (`runs.py:1789-1802` + `:1854-1860`):

```python
class SnapshotSchemaDrift(Exception):
    failure_class = "snapshot_schema_drift"
    suggested_action = "republish at current schema version"

# Inside execute_branch_version_async:
try:
    branch = BranchDefinition.from_dict(bv.snapshot)
except (AttributeError, KeyError, TypeError, ValueError) as exc:
    raise SnapshotSchemaDrift(
        f"Snapshot for {branch_version_id!r} cannot be reconstructed: "
        f"{exc}. Republish at current schema version."
    ) from exc
```

**Three sharpening-additions beyond design:**

1. **Class-level `failure_class` + `suggested_action` constants** — design suggested they live on the response dict; impl makes them class attributes readable WITHOUT instantiation. The MCP-layer handler can read `SnapshotSchemaDrift.failure_class` directly off the class — cleaner than parsing the exception message or instantiating a defensive copy. **Same shape as `RolledBackDuringExecution` would land for #57** (per #65 §4 implementation-time constraint).

2. **Specific exception class catch list** (`AttributeError, KeyError, TypeError, ValueError`) rather than blanket `except Exception`. Distinguishes "actually a schema drift" from "transient error / bug elsewhere." Bug-elsewhere errors propagate normally and get caught by the action handler's general `except Exception` clause and routed through `_classify_run_error`.

3. **`raise ... from exc` chain preservation** — debuggers see the original `from_dict` failure underneath the `SnapshotSchemaDrift` wrapper. Sound discipline.

**MCP-layer handler maps cleanly** (`universe_server.py:8496-8501`):

```python
except SnapshotSchemaDrift as exc:
    return json.dumps({
        "error": str(exc),
        "failure_class": SnapshotSchemaDrift.failure_class,
        "suggested_action": SnapshotSchemaDrift.suggested_action,
    })
```

Reads class attributes directly. Per pair-read #59 recommendation, exactly the right shape.

### Cross-check 6: Composition with #48 contribution-ledger

**CONVERGES — already verified by impl-pair-read #78.** Per #78 cross-check 6: contribution_events.source_artifact_id is populated from `runs.branch_version_id` (when present) or `runs.branch_def_id` (fallback), with `source_artifact_kind` reflecting the choice. **The runner-version-id implementation feeds this composition correctly:**

```python
# universe_server.py / runs.py inside execute_step emit
artifact_id = row["branch_version_id"] or row["branch_def_id"]
artifact_kind = "branch_version" if row["branch_version_id"] else "branch_def"
```

When `_action_run_branch_version` was called → `runs.branch_version_id` is populated → contribution_events emits `source_artifact_id=<branch_version_id>` with `source_artifact_kind="branch_version"`. **Attribution provenance flows correctly through the entire chain:** MCP action → runner core → runs row → contribution event → bounty calc.

**Per pair-read #59 §1 finding:** "Three version concepts coexist in the runs row without colliding." Verified once more in this audit's cross-check 4. The chain is now end-to-end clean.

---

## 2. Sharpening-additions beyond design (worth pinning)

Three implementation-side judgment-extensions worth recording, mirroring #78's "implementation goes beyond design when design is implicit" pattern:

1. **Class-level `failure_class` + `suggested_action` constants on `SnapshotSchemaDrift`** (cross-check 5 detail). Cleaner than dict-only response shape; MCP-layer reads class attributes without instantiation. **Recommendation: codify as project pattern for failure-class exceptions.** Filing as [PENDING failure-class-as-class-attrs-convention] — small extension to attribution-layer-specs §6 OR a small failure-class convention doc.

2. **Specific exception catch list** (`(AttributeError, KeyError, TypeError, ValueError)`) instead of bare `except Exception`. Discipline for surfacing real schema drift while letting bug-elsewhere errors propagate to general handlers. **Recommendation: same convention.**

3. **Pair-read #59 §3 recommendation honored: refactor-as-separate-dispatch.** `#65a` is refactor-only (extraction + schema); `#65b` is new-helper-add. Two separate SHIPs, each independently verifiable. **This is the pair-read pattern paying dividends — recommendation traveled from pair-read → dispatch sequencing → cleaner SHIP gates.** Worth recording as a successful pattern instance in the convergence-loop story.

---

## 3. Implementation-time constraints captured for upcoming SHIPs

Per #54 §5 migration plan, three steps land across #65a + #65b:

| Step | Status | Notes |
|---|---|---|
| Step 0 schema add (ALTER + index) | ✓ #65a | Idempotent PRAGMA-probe pattern |
| Step 1 internal helper (`_execute_branch_core` extraction) | ✓ #65a | Refactor with all current tests still passing — verified by SHIP gate |
| Step 2 MCP handler | ✓ #65b | `_action_run_branch_version` + `_RUN_ACTIONS` registration |
| Step 3 chatbot tooling discovery | TBD | MCP tool catalog should surface `run_branch_version` as discoverable action; verify after redeploy |

Pair-read #59 §3 cancellation propagation concern: **acknowledged + deferred in implementation.** `execute_branch_version_async` docstring explicitly notes (`runs.py:1824-1833`):

> "**Parent gate-series cancellation does NOT propagate to child version-runs today.** Child runs are independent run_ids; the propagation primitive lands when Task #53 route-back is implemented."

**Verdict: correct deferral.** The cancellation-propagation primitive is genuinely a #53 concern (parent-child relationship is a route-back artifact); the runner-version-id-bridge layer doesn't own it. Filing as [PENDING #53-impl-cancellation-propagation] for the future #53 implementation.

---

## 4. Roadmap deltas

**Phase A item 6 — IMPLEMENTATION COMPLETE.**

| Sub-step | Status |
|---|---|
| 6.0 `_execute_branch_core` refactor (split before helper-add) | ✓ #65a |
| 6.1 `runs.branch_version_id` schema migration | ✓ #65a |
| 6.2 `execute_branch_version_async` helper | ✓ #65b |
| 6.3 `_action_run_branch_version` MCP handler | ✓ #65b |
| 6.4 `SnapshotSchemaDrift` failure class | ✓ #65b |

**5 of 5 sub-steps landed.** Phase A item 6 is the first implementation-complete item beyond #71+#72+#75 (Phase B item 8 surfaces 1+2). **Phase A items 2, 6 are both impl-active or impl-complete; items 1, 3, 4a/4b, 5a/5b/5c, 7 are designed and pending impl.**

**Composition unblocked for downstream:**
- **#56 sub-branch invocation impl** (item 5a/5b/5c, in flight as #76a/b/c): can call `execute_branch_version_async` directly per #56 §3 design. Helper is ready.
- **#53 route-back execution impl** (will be a future task): can synchronously invoke canonicals via `execute_branch_version_async` per #53 §6 design. Helper is ready.
- **#48 contribution_events ledger** (#71+#72+#75 already landed): reads `runs.branch_version_id` for attribution provenance per #78 cross-check 6. Schema is ready.

**Three downstream SHIPs unblocked by this lane.** This is the kind of substrate-completion progress that compounds.

---

## 5. Implementation pattern observations (pair-read shape consolidation)

Two impl-side pair-reads complete (#78, this). Patterns observed:

1. **Implementations honor pair-read recommendations.** Both impls cite their pair-read sources in commit messages or code comments. The refactor-vs-helper-add split (#65a vs #65b) is directly traceable to pair-read #59 §3 recommendation. **The convergence-loop pattern produces actionable findings that flow into impl sequencing.**

2. **Class-level constants for exception classes.** Both `SnapshotSchemaDrift` (this audit) and `_EMIT_FAILURES` counter pattern (#78 audit) follow "make state cleanly readable without instantiation." Worth a small convention doc or a §X to design-proposal-pattern convention.

3. **Specific exception catch lists vs blanket `except Exception`.** This impl uses `(AttributeError, KeyError, TypeError, ValueError)` for the from_dict path — narrow enough to surface real schema drift, broad enough to catch the four ways `from_dict` can reasonably fail. **Recommendation: codify as testable convention** ("when wrapping a parse / load / from_dict call in a structured exception, name the specific exception types your wrapper handles; don't blanket-catch").

4. **Pair-read recommendations make it to commit messages.** #65a's commit message names "audit 4e608e3 + pair-read #59" as references. **The convergence-loop pattern is now visibly self-documenting in the git log.** Worth flagging as a healthy signal.

**Overall: impl-side pair-reads are routine.** Two complete, both PAIR CONVERGES with sharpening-additions. Pattern is empirically validated as a low-overhead high-signal step in the design→impl flow.

---

## 6. References

- Design source: `docs/design-notes/2026-04-25-runner-version-id-bridge.md` (#54, dev-2 — committed `dc7d2cb`).
- Implementation commits:
  - `80a1e14` Task #65a — schema + `_execute_branch_core` extraction.
  - `ee254b0` Task #65b — `execute_branch_version_async` + `_action_run_branch_version` + `SnapshotSchemaDrift`.
- Cross-check sources:
  - `tinyassets/runs.py:238-248` (schema migration).
  - `tinyassets/runs.py:1680-1786` (`_execute_branch_core` + `execute_branch_async` wrapper).
  - `tinyassets/runs.py:1789-1802` (`SnapshotSchemaDrift` class).
  - `tinyassets/runs.py:1805-1870` (`execute_branch_version_async` helper).
  - `tinyassets/universe_server.py:8423-8539` (`_action_run_branch_version` + registry).
- Pair-read #59 (design-vs-design): `docs/audits/2026-04-25-pair-54-vs-56-convergence.md` — origin of refactor-as-separate-dispatch + schema-drift recommendations both honored here.
- Sibling impl-pair-read: `docs/audits/2026-04-25-impl-71-72-75-vs-48-convergence.md` (#78, navigator) — cross-check 6 composition verified at #48 emit-site.
- Composition with #56 sub-branch (impl in flight): `docs/design-notes/2026-04-25-sub-branch-invocation-proposal.md` (#56 §3 calls `execute_branch_version_async` directly — helper is ready).
- Composition with #53 route-back (impl pending): `docs/design-notes/2026-04-25-gate-route-back-verb-proposal.md` (#53 §6 calls `execute_branch_version_async` synchronously — helper is ready).
- v2 vision Phase A phasing: `docs/design-notes/2026-04-25-self-evolving-platform-vision-v2.md` §6.

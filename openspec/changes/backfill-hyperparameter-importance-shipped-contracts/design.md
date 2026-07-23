## Context

The generic outcomes package exports `HyperparameterImportanceEvaluator`.
It consumes a caller-provided list of run dictionaries and returns the shared
bounded `EvalResult`. It is not registered as a graph node and does not read
files, call a service, generate artifacts, or own a sweep storage schema.

The evaluator has two computation labels but one dependency loader:
`scipy.stats.spearmanr` and
`sklearn.ensemble.RandomForestRegressor` are imported together after the
empty/minimum-run gates. An `ImportError` becomes a `skip`; other failures are
not normalized.

The older science-domain documents were written as an unimplemented future
node. Their inputs, methods, outputs, validation errors, artifacts, and module
placement differ from source. They remain useful design provenance but cannot
be synced as current behavior.

## Goals / Non-Goals

**Goals:**

- Give the shipped generic evaluator an exact canonical owner.
- Make all fail-soft gates and successful result shapes executable.
- Preserve deterministic RF/Spearman ranking and categorical encoding.
- Record permissive input handling and propagated failures rather than
  inventing validation.

**Non-Goals:**

- Implement or specify the future science-domain node as shipped.
- Add `sweep_results`, permutation, ANOVA, generic model-based selection,
  direction handling, confidence, warnings, CSV/plot artifacts, or stable
  decimal snapshots.
- Add evaluator registration, graph dispatch, storage, networking, or
  scientific dependency installation.
- Validate, clamp, or normalize caller controls beyond current code.

## Decisions

### Extend evaluation-runtime-and-scenarios

The class implements the shared structural `Evaluator` protocol and returns
the canonical `EvalResult`, so the runtime/evaluation capability is its
semantic owner. A new science-domain capability would imply node registration
and domain-specific wire shapes that do not exist.

### Preserve ordered fail-soft gates

Missing or falsey `run_results` skips before parsing controls or importing
scientific dependencies. The minimum-run gate converts `min_runs` with `int`
and skips before loading dependencies. Both backends are then imported
together; an `ImportError` skips with the scientific-extra install hint. Only
after dependency loading does an empty first-run parameter dictionary skip.

This ordering matters. For example, missing dependencies can mask the
no-parameter condition, while malformed integer controls can raise before the
dependency gate.

### Specify the exact feature table rather than an ideal sweep schema

Only the first run's ordered parameter keys define columns. Extra keys in later
runs are ignored. A column remains numeric only when every value is an
`int`/`float`; otherwise all values are stringified, sorted uniquely, and
ordinal-encoded. Targets use `target_metric`, then each row's `metric`, then
`0.0`, and are converted with `float`.

No missing/constant/causal-data warning is produced. Conversion, encoding,
model fitting, and backend errors outside the explicit `ImportError` gate
propagate.

### Keep RF and correlation selection permissive

Only exact method string `correlation` selects absolute Spearman statistics
with NaN mapped to zero. Every other value, including unknown values, selects a
100-tree random forest with seed 42.

Descending sorting is stable, so tied scores preserve the first run's
parameter-key order rather than name-sorting. `top_n` is converted with `int`
and passed directly to Python slicing; zero yields an empty successful ranking
with score zero, and negative values use ordinary negative-slice semantics.

## Risks / Trade-offs

- **[Risk] Canonical text upgrades a permissive helper into a validated science
  product.**
  Mitigation: retain conversion propagation, fallback, truncation, and missing-warning
  limitations normatively.
- **[Risk] The future science pre-spec is mistaken for shipped truth.**
  Mitigation: contrast its incompatible shapes in proposal/design and exclude them from
  the delta.
- **[Risk] Dependency skips are mistaken for method-specific loading.**
  Mitigation: state that both SciPy and scikit-learn load before either method runs.
- **[Risk] Ranking is described as causal.**
  Mitigation: specify only observed RF feature importance or absolute rank correlation.

## Migration Plan

1. Strictly validate the isolated delta and full OpenSpec tree.
2. Run focused evaluator tests and dependency-independent injected-backend
   probes for currently untested edge semantics.
3. Verify runtime/plugin mirror parity and obtain independent
   requirement-to-source plus whole-diff review.
4. Rebase on current main, sync the approved delta into
   `evaluation-runtime-and-scenarios`, update the coverage audit, and validate
   the archived tree.
5. Merge the reviewed PR and retire its STATUS/worktree lane.

There is no runtime rollout. Reverting the documentation commit is the rollback
if a clause is later shown to misdescribe shipped behavior.

## Open Questions

None. Future science-domain implementation remains a separate target lane.

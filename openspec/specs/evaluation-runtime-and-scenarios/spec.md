# evaluation-runtime-and-scenarios Specification

## Purpose
Define the shared evaluator/result protocol, layered evidence adapters, acceptance-scenario validation, and current in-process scenario dispatch behavior.
## Requirements
### Requirement: Evaluators return a bounded unified result where the protocol applies

The current evaluation runtime SHALL define `EvalResult` with score, verdict,
kind, label, and details. Every `EvalResult` score MUST be in `[-1.0, 1.0]`;
protocol-conformant evaluators SHALL expose `evaluate(state) -> EvalResult`
using one of the current structural, editorial, process, numeric, or custom
kinds. Current adapters commonly pair `-1.0` with skip or error outcomes, but
the dataclass MUST NOT be represented as enforcing that semantic pairing.

#### Scenario: An out-of-range result is rejected

- **GIVEN** a caller constructs `EvalResult(score=1.001, ...)`
- **WHEN** dataclass validation runs
- **THEN** construction SHALL raise `ValueError` rather than return an invalid
  evaluation result.

#### Scenario: Structural subtyping is accepted

- **GIVEN** an object that implements `evaluate(state)` and returns an
  `EvalResult`
- **WHEN** the runtime checks it against `Evaluator`
- **THEN** it SHALL satisfy the protocol without inheriting a TinyAssets base
  class.

#### Scenario: Negative one is not reserved by the result type

- **GIVEN** a caller constructs `EvalResult(score=-1.0, verdict="pass", ...)`
- **WHEN** dataclass validation runs
- **THEN** construction SHALL succeed because the current type validates the
  numeric range but does not constrain verdict-score combinations.

### Requirement: Layered evaluation preserves native evidence and explicit adapters

The current runtime SHALL retain native structural, process, and coding
trajectory evidence while exposing explicit process adapters to `EvalResult`.
Process evaluation MUST report its weighted check results and failures; coding
trajectory evaluation MUST return `skip` with score `-1.0` when insufficient
applicable trajectory signals make it inconclusive, rather than treating absent
evidence as failure.

#### Scenario: Process failure is visible in the unified adapter

- **GIVEN** a scene process evaluation with one or more failing checks
- **WHEN** it is converted with `to_eval_result()`
- **THEN** the result SHALL use kind `process`, verdict `fail`, and include the
  aggregate score and failing check names in details.

#### Scenario: Sparse coding evidence is inconclusive

- **GIVEN** a coding trajectory with fewer applicable checks than the current
  conclusive threshold
- **WHEN** it is evaluated and converted to `EvalResult`
- **THEN** the result SHALL have verdict `skip` and score `-1.0`, not `fail`.

### Requirement: Outcome adapters remain probe-free unless a caller supplies a prober

The current real-world outcome evaluators SHALL implement the unified
`Evaluator` protocol for their declared state fields. Network-backed outcome
checks MUST use their injected prober when one is supplied and MUST otherwise
return an unverified/skip-style result without making an ambient network call.

#### Scenario: An outcome URL is not silently probed

- **GIVEN** a `PublishedPaperEvaluator` without a prober and state containing
  a DOI or URL
- **WHEN** it evaluates the state
- **THEN** it SHALL return an `EvalResult` describing unverified evidence and
  SHALL not perform a network request itself.

#### Scenario: A supplied prober determines the recorded verification status

- **GIVEN** an outcome evaluator configured with a prober that reports a
  negative result
- **WHEN** it evaluates a syntactically present outcome reference
- **THEN** it SHALL return the adapter's failed or unverified outcome according
  to that prober result rather than claiming verified success.

### Requirement: Acceptance scenarios validate the minimum evidence contract before dispatch

The current `AcceptanceScenario` SHALL validate a `scenario:` ID, one of the
five current target surfaces, a 200–2000-character user story, at least one
evaluator ID and artifact requirement, a `min_score`, both declared cost-budget
fields, a declared idempotency-key constructor, and one of the current privacy
scopes. A scenario that omits any required field MUST fail construction before
dispatch.

#### Scenario: An evidence-free scenario is rejected

- **GIVEN** a proposed acceptance scenario with an empty evaluator chain or no
  artifact requirements
- **WHEN** the dataclass validates it
- **THEN** construction SHALL raise `ValueError` and no dispatcher SHALL run.

#### Scenario: A valid scenario has bounded autonomous-spend declarations

- **GIVEN** a scenario for `mcp_call` with a valid story, artifact requirement,
  evaluator chain, threshold, privacy scope, and idempotency constructor
- **WHEN** it includes `max_tokens` and `max_wall_time_seconds`
- **THEN** scenario construction SHALL succeed and preserve those declared
  fields for the dispatcher.

### Requirement: Scenario dispatch is registry based and normalizes every terminal result

The current scenario runner SHALL route a valid scenario only through the
in-process dispatcher registered for its target surface and SHALL normalize a
dispatcher return to a custom `EvalResult`. An unregistered target surface MUST
return `skip` with `no_dispatcher_registered`; a raised dispatcher exception
MUST return `error` with its type and message; absent an explicit valid verdict,
the runner SHALL derive pass/fail from `min_score`.

#### Scenario: An unregistered surface is a visible skip

- **GIVEN** a valid scenario whose target surface has no registered dispatcher
- **WHEN** `run_scenario` is called
- **THEN** it SHALL return custom `EvalResult(score=-1.0, verdict=skip)` with
  the scenario, candidate, and registered-surface context in details.

#### Scenario: A dispatcher without a verdict is threshold-normalized

- **GIVEN** a registered dispatcher that returns a numeric score but no verdict
- **WHEN** its score meets the scenario's `min_score`
- **THEN** the runner SHALL return verdict `pass` and preserve scenario,
  candidate, privacy, and threshold context in details.

### Requirement: The shipped MCP-call dispatcher is synchronous and reports, rather than enforces, budgets

The current `mcp_call` dispatcher SHALL synchronously invoke one supplied action
handler, parse its JSON response when possible, run supplied evaluators or the
default status evaluator, and aggregate scores by the current mean, minimum, or
mean-fallback weighted modes. It MUST clamp evaluator scores to `[-1.0, 1.0]`
and report over-wall-time budget in details, but it SHALL NOT be represented as
enforcing token budgets, enforcing wall-time termination, running in parallel,
or providing a sandbox.

#### Scenario: A slow handler produces evidence but is not terminated by the runtime

- **GIVEN** an `mcp_call` scenario whose action handler exceeds its declared
  `max_wall_time_seconds`
- **WHEN** the handler returns and the dispatcher completes evaluation
- **THEN** the result details SHALL report the elapsed time and `over_budget`,
  while the current dispatcher SHALL not claim that it terminated the handler.

#### Scenario: Unsupported future scenario execution is not claimed as shipped

- **GIVEN** a review of acceptance-scenario execution beyond a registered
  `mcp_call` dispatcher
- **WHEN** it describes the as-built runtime
- **THEN** it SHALL state that unregistered surfaces return `skip` and SHALL
  NOT claim distributed workers, parallel scenario execution, a new sandbox,
  or generic realtime scenario orchestration as implemented.

### Requirement: The public hyperparameter evaluator skips bounded absence cases and otherwise exposes ordinary failures

`tinyassets.outcomes` SHALL publicly export
`HyperparameterImportanceEvaluator`, whose `evaluate(state)` method satisfies
the structural `Evaluator` protocol and returns `EvalResult` with kind
`custom` and label `hyperparameter_importance`. The export SHALL NOT register
the evaluator in a catalog or cause automatic invocation; a caller MUST
explicitly construct and invoke it.

Missing or falsey `run_results` SHALL return score `-1.0`, verdict `skip`, and
reason `no run_results in state`. The evaluator SHALL convert `min_runs` with
`int` (default 10); fewer runs SHALL return score `-1.0`, verdict `skip`, and
details containing the reason, actual run count, and converted minimum.

After those gates, the evaluator SHALL read `method`, convert `top_n` with
`int` (default 5), read `target_metric` (default `metric`), and then lazy-load both
`RandomForestRegressor` and `spearmanr` together. An `ImportError` SHALL return
score `-1.0`, verdict `skip`, and a reason naming scikit-learn, SciPy, and the
`tinyassets[scientific]` install extra. After successful loading, an empty
`params` dictionary in the first run SHALL return score `-1.0`, verdict
`skip`, and reason `no params in first run`.

These are the only normalized absence/dependency paths. `min_runs` and
`top_n` use unvalidated `int` conversion; malformed state, later
encoding/float conversion, backend calls, and model fitting may raise their
ordinary exceptions. Both scientific dependencies are required even when the
selected method uses only one.

#### Scenario: The exported class satisfies the evaluator protocol

- **WHEN** a caller imports `HyperparameterImportanceEvaluator` from `tinyassets.outcomes`
- **THEN** its instance satisfies `Evaluator` without inheriting a TinyAssets base class
- **AND** no catalog registration or automatic invocation occurs from the public export

#### Scenario: Missing and empty run results skip before controls and dependencies

- **WHEN** `run_results` is missing, empty, or otherwise falsey
- **THEN** evaluation returns custom result `skip` with score `-1.0` and reason `no run_results in state`
- **AND** it does not parse `min_runs` or import the scientific backends

#### Scenario: Too few runs return bounded evidence

- **WHEN** the run count is below converted `min_runs`
- **THEN** evaluation returns custom result `skip` with score `-1.0`
- **AND** details contain `n_runs below min_runs`, the actual count, and the converted minimum

#### Scenario: A missing scientific backend skips both methods

- **WHEN** loading SciPy or scikit-learn raises `ImportError`
- **THEN** evaluation returns custom result `skip` with score `-1.0`
- **AND** its reason names both packages and the scientific install extra

#### Scenario: The first run defines whether any parameter exists

- **WHEN** dependencies load but the first run's `params` dictionary is empty or absent
- **THEN** evaluation returns custom result `skip` with score `-1.0` and reason `no params in first run`

#### Scenario: Malformed controls and computation failures are not normalized

- **WHEN** `min_runs` or `top_n` cannot be converted with `int`, a feature or target cannot be converted, or a backend fails outside `ImportError`
- **THEN** the ordinary exception propagates rather than becoming an `EvalResult`

### Requirement: Hyperparameter feature and target tables use the first-run schema and permissive fallbacks

The first run's ordered `params` keys SHALL define every feature column; extra
keys introduced only by later runs SHALL be ignored. A column SHALL remain
numeric only when every collected value is an `int` or `float`, including
`bool` under Python type semantics. Otherwise all values SHALL be stringified,
sorted uniquely, assigned zero-based ordinal indices, and encoded as floats.
A missing later-run value SHALL therefore participate as the string `None`
when the column is categorical.

The target for each run SHALL be `run[target_metric]` when present, otherwise
`run["metric"]` when present, otherwise `0.0`, converted to float. The
`target_metric` default SHALL be `metric`. A present but nonnumeric selected
value SHALL not fall back and its float-conversion exception SHALL propagate.

#### Scenario: The first run fixes feature order and categorical encoding

- **WHEN** later runs add keys, omit a first-run key, or provide a non-`int`/`float` value for a first-run-defined feature
- **THEN** later-only keys are ignored and the first-run key order remains authoritative
- **AND** every value in the nonnumeric column is stringified and encoded by its position in the sorted unique strings

#### Scenario: Targets use per-run fallback without masking invalid present values

- **WHEN** a run omits the selected target metric
- **THEN** that run falls back to its `metric` value and then `0.0`
- **AND** a present but nonnumeric selected value raises during float conversion rather than falling back

### Requirement: Hyperparameter ranking uses deterministic RF or absolute-Spearman scoring

Only exact method `correlation` SHALL compute each feature's absolute Spearman
statistic, mapping NaN to `0.0`. Every other method value SHALL fit
`RandomForestRegressor(n_estimators=100, random_state=42)` and use its feature
importances with `method_used=rf`.

The evaluator SHALL stable-sort `(parameter, importance)` pairs descending by
importance, preserving first-run key order for ties, and slice the list with
`ranked[:top_n]`. It SHALL return verdict `pass`, score equal to the first
retained importance or `0.0` for an empty slice, and details containing only
the ranked `{param, importance, rank}` entries, `method_used`, and
`n_runs_analyzed`. It SHALL NOT claim causal importance, confidence, warnings,
or generated artifacts.

#### Scenario: Random forest ranks with the fixed shipped configuration

- **WHEN** a valid run table uses absent, `rf`, or any unrecognized method value
- **THEN** the evaluator fits 100 trees with random seed 42
- **AND** returns a descending pass ranking with `method_used=rf`

#### Scenario: Correlation uses absolute statistics and guards NaN

- **WHEN** method is exactly `correlation`
- **THEN** each importance is the absolute Spearman statistic for that feature and target
- **AND** a NaN statistic contributes `0.0`

#### Scenario: Truncation and ties retain Python ordering semantics

- **WHEN** scores tie or `top_n` is zero or negative
- **THEN** ties retain first-run parameter order and ordinary `ranked[:top_n]` slicing applies
- **AND** an empty retained ranking still returns verdict `pass` with score `0.0`

#### Scenario: Successful output has the bounded shipped envelope

- **WHEN** either computation path completes
- **THEN** the evaluator returns custom result `pass` labeled `hyperparameter_importance`
- **AND** details contain only `importance_ranking`, `method_used`, and `n_runs_analyzed`
- **AND** each retained ranking entry contains `param`, `importance`, and a one-based `rank`
- **AND** no causal claim, confidence, warning collection, or generated artifact is added

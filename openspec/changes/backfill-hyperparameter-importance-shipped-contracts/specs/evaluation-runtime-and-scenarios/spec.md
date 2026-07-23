## ADDED Requirements

### Requirement: The public hyperparameter evaluator skips bounded absence cases and otherwise exposes ordinary failures

`tinyassets.outcomes` SHALL publicly export
`HyperparameterImportanceEvaluator`, whose `evaluate(state)` method satisfies
the structural `Evaluator` protocol and returns `EvalResult` with kind
`custom` and label `hyperparameter_importance`.

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

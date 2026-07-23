## Why

`HyperparameterImportanceEvaluator` is exported, protocol-conformant, tested,
and shipped in both runtime copies, but its behavior has no canonical OpenSpec
owner. The full-coverage audit therefore still treats it as a shipped
residual.

An older science-domain pre-spec describes a different future node contract:
`sweep_results`, required metric validation, permutation/ANOVA/model-based
strategies, warnings, and artifacts. Syncing that document would make
unimplemented behavior canonical and hide the smaller generic evaluator that
actually exists.

## What Changes

- Extend `evaluation-runtime-and-scenarios` with the shipped evaluator's public
  export, structural protocol conformance, fail-soft input/dependency gates,
  and exact `EvalResult` shapes.
- Specify its first-run parameter schema, numeric and categorical encoding,
  random-forest and absolute-Spearman scoring, deterministic ordering,
  `top_n` truncation, and target fallback.
- Preserve the current limitations: permissive/unvalidated controls,
  unknown-method fallback to random forest, both scientific dependencies
  required for either method, no warnings/artifacts/confidence, and ordinary
  conversion/model exceptions propagating.
- Keep the science-domain pre-spec under a distinct future-target successor
  rather than treating it as canonical as-built truth.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `evaluation-runtime-and-scenarios`: the shipped generic hyperparameter
  importance outcome evaluator.

## Impact

This is current-behavior reconciliation only. It changes canonical OpenSpec,
the full-coverage audit, and coordination records. It does not change evaluator
runtime code, scientific dependencies, graph nodes, domain plugins, result
schemas, packaging, or deployments. Primary evidence is
`tinyassets/outcomes/evaluators.py`, its public export and packaged mirror, and
`tests/test_outcome_evaluators.py`.

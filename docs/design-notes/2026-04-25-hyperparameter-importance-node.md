---
status: active
---

# Design Note: `hyperparameter_importance` Evaluator Node

**Date:** 2026-04-25
**Status:** Scoping — domain-skill candidate, not engine primitive
**Source signal:** Priya W&B Sweeps competitor trial (2026-04-24), `ideas/INBOX.md`, competitor-trials-sweep Signal 4
**Chain-break:** Interface 1 — W&B parity gap for scientific/ML users

---

## 1. Problem Statement

From `docs/audits/user-chat-intelligence/2026-04-24-competitor-trials-sweep.md` Signal 4:

> W&B's one substantive win Priya would actually want: hyperparameter importance analysis (which knobs matter most across the sweep). W&B computes this automatically. Workflow has no equivalent.

When Priya runs a MaxEnt hyperparameter sweep across regularization multiplier, feature classes, and max iterations, she wants to know: **which of those knobs actually drove performance variation?** Today she must export results to a Jupyter notebook and compute this herself, or pay for a W&B account. Neither path is frictionless.

This is a domain-specific evaluator node, not an engine primitive. The engine already supports the `Evaluator` protocol (`workflow.evaluation.EvalResult`). This node fits cleanly into the scientific-computing domain skill module without touching the engine.

---

## 2. What W&B Does

W&B Sweeps computes hyperparameter importance using two methods:
- **Correlation-based:** Pearson/Spearman correlation between each param and the target metric across all runs.
- **Random forest regression:** Fit a random forest predicting the target metric from hyperparams; report `feature_importances_`.

Output: ranked list of params with importance scores, optionally with interaction effects.

**W&B loses on:** result is a dashboard link, not a local artifact a reviewer can run. Workflow's structural advantage is reproducibility-first output.

---

## 3. Proposed Node Spec

### Node ID

`hyperparameter_importance`

### Domain

`scientific-computing` (not `engine` or `general`)

### Inputs (TypedDict)

```python
class HyperparamImportanceInput(TypedDict):
    run_results: list[dict]       # each entry: {params: dict, metric: float}
    target_metric: str            # key in each entry's metric dict, or "metric" if flat
    method: str                   # "correlation" | "rf" (default: "rf")
    top_n: int                    # how many top params to report (default: 5)
```

`run_results` is the natural output of a sweep node — each run produces a `{params, metric}` dict. No additional state key ceremony required.

### Outputs (TypedDict)

```python
class HyperparamImportanceOutput(TypedDict):
    importance_ranking: list[dict]  # [{param: str, importance: float, rank: int}]
    method_used: str
    n_runs_analyzed: int
    artifact_path: str | None       # path to CSV artifact if saved
```

### EvalResult mapping

For use as an `Evaluator` (gate or outcome check):

```python
EvalResult(
    score=top_param_importance,   # importance of the #1 param; high = sweep was informative
    verdict="pass" if n_runs_analyzed >= min_runs else "skip",
    kind="custom",
    label="hyperparameter_importance",
    details={"ranking": importance_ranking, "method": method_used},
)
```

---

## 4. Implementation Approach

### Dependencies

- `scikit-learn` for `RandomForestRegressor` (already a plausible dep for scientific domain).
- `scipy.stats` for Spearman correlation (already in scientific stack).
- No engine changes required.

### Node body (sketch)

```python
def run(state: HyperparamImportanceInput) -> HyperparamImportanceOutput:
    runs = state["run_results"]
    metric_key = state.get("target_metric", "metric")
    method = state.get("method", "rf")
    top_n = state.get("top_n", 5)

    param_names = list(runs[0]["params"].keys())
    X = [[r["params"][p] for p in param_names] for r in runs]
    y = [r[metric_key] for r in runs]

    if method == "rf":
        from sklearn.ensemble import RandomForestRegressor
        rf = RandomForestRegressor(n_estimators=100, random_state=42)
        rf.fit(X, y)
        scores = rf.feature_importances_
    else:  # correlation
        from scipy.stats import spearmanr
        scores = [abs(spearmanr([x[i] for x in X], y).statistic) for i in range(len(param_names))]

    ranking = sorted(
        [{"param": p, "importance": float(s), "rank": i + 1}
         for i, (p, s) in enumerate(sorted(zip(param_names, scores), key=lambda t: -t[1]))],
        key=lambda r: r["rank"],
    )[:top_n]

    return HyperparamImportanceOutput(
        importance_ranking=ranking,
        method_used=method,
        n_runs_analyzed=len(runs),
        artifact_path=None,
    )
```

### Artifact export (phase 2)

Save `importance_ranking` as a CSV to the universe output dir. This gives the reviewer-runnable artifact that beats W&B's dashboard-link output:

```
param,importance,rank
regularization_multiplier,0.61,1
max_iterations,0.22,2
feature_classes,0.17,3
```

---

## 5. UX Contract (chatbot-facing)

The chatbot should narrate importance results in plain language, not as a raw table dump. Example response after a sweep:

> "Across your 48 MaxEnt runs, regularization multiplier explains 61% of performance variation — it's by far the most important knob. Max iterations accounts for 22%, and feature class selection only 17%. You can safely fix feature classes and focus your next sweep on regularization."

This framing closes the W&B comparison gap: the output is an **interpretive artifact**, not a dashboard.

---

## 6. Positioning vs. W&B

| Dimension | W&B Sweeps | Workflow `hyperparameter_importance` |
|---|---|---|
| Output format | Dashboard link (requires W&B account) | CSV + interpretive text (reviewer-runnable) |
| Reproducibility | Run logs on W&B servers | Local artifact, owned by user |
| Integration | Requires W&B SDK in experiment code | Workflow node; no experiment-code changes |
| Cost | Subscription above free tier | Free; compute on daemon host |
| Narrative output | None — charts only | Chatbot interprets + recommends next sweep focus |

The structural win: Priya's ecology reviewers never create a W&B account. The CSV + methods paragraph drops directly into her supplementary materials.

---

## 7. Fit Within Project Primitives

This node satisfies the `Evaluator` protocol (`workflow.evaluation.EvalResult`) via structural subtyping — the same pattern as `PublishedPaperEvaluator`, `MergedPREvaluator`, and `DeployedAppEvaluator` in `tinyassets/outcomes/evaluators.py`. No inheritance required; no engine changes.

It also aligns with the `Evaluation layers — unifying frame` design principle: "whole platform IS evaluation-driven." A sweep-result evaluator is a first-class platform primitive, not a one-off script.

---

## 8. Scope and Dependencies

**What is NOT in scope here:**
- Interaction-effect detection (ANOVA, SHAP values) — phase 3 at earliest.
- Bayesian optimization suggestions based on importance (separate node: `suggest_next_sweep`).
- W&B connector/importer for existing W&B sweep results.

**Dependencies:**
- Scientific-computing domain skill module must be scoped before this node is dispatched. This node is a catalog candidate, not a free-standing task.
- `clone_branch` / `extend_branch` primitive (see `2026-04-25-extend-run-continue-branch.md`) is not a blocker — this node runs on sweep results that already exist, not as part of the sweep graph itself.
- `scikit-learn` must be in the scientific-domain optional dependency group.

---

## 9. Open Questions

1. **Categorical hyperparams:** `RandomForestRegressor` requires numeric inputs. Do we encode categoricals (e.g., `feature_classes: "LQ"`) as ordinal integers or one-hot? One-hot bloats the feature space for the importance report.

2. **Minimum runs threshold:** Below how many runs is importance analysis meaningless? Suggest `min_runs=10` with a `"skip"` verdict below that — mirrors the `EvalResult(verdict="skip")` pattern in existing evaluators.

3. **Module placement:** Should this live under `tinyassets/outcomes/` (alongside the existing evaluators) or in a future `tinyassets/domains/scientific/` module? The existing evaluators are general-purpose; this is domain-specific. Recommend `tinyassets/domains/scientific/` when that module is created.

4. **Node registration:** Does the node auto-register in the catalog on daemon start, or is it opt-in via the `TINYASSETS_SCIENTIFIC_DOMAIN=1` feature flag? Consistent with the flag-at-import-time pattern (see agent memory `feedback_flag_at_import_time.md`): registration-gate flags read at import.

# Tasks — connector tool-selection accuracy

Filed from task 6.3 of `reconcile-universe-personification-relay` (residual of retired task 2.9).
Sections 1–2 are the **instrument** (landable without a live session). Section 3 is the
**measurement**, which needs a rendered `ui-test` run and therefore a human at a browser — it is
host/verifier-actionable, not code. Section 4 must not run before section 3.

## 1. Instrument — dataset

- [x] 1.1 Author the labelled prompt→expected-handle dataset covering all seven canonical handles,
      with an `opening` flag marking first-contact turns
      → `tests/data/connector_tool_selection_v1.jsonl` (21 prompts; every canonical handle covered;
      6 opening turns).
- [x] 1.2 Enforce dataset integrity in code, not review — non-canonical label, uncovered handle,
      duplicate prompt, torn JSON line, empty prompt, missing filename version all raise
      → `scripts/connector_tool_selection_eval.py::load_dataset` (`DatasetError`);
      `tests/test_connector_tool_selection.py::TestDatasetIntegrity` (6 tests).
- [x] 1.3 Version the dataset from its filename so a baseline records what it measured against
      → `_VERSION_RE`; `Baseline.dataset_version`; cross-version comparison refused.

## 2. Instrument — scoring and gate

- [x] 2.1 Score a recorded run into top-1 and opening-turn `converse` rates as separate numbers
      → `score_run` → `Measurement.top1_rate` / `.opening_converse_rate`.
- [x] 2.2 Refuse a partial run and a run carrying prompts outside the dataset
      → `MeasurementError`; `TestScoring::test_partial_run_is_refused_not_scored`,
      `::test_unexpected_prompt_in_a_run_is_refused`.
- [x] 2.3 Score a non-canonical observed handle as incorrect and report the observed value
      → `Measurement.non_canonical_observed`.
- [x] 2.4 Refuse a non-rendered measurement source
      → `RENDERED_SOURCES`; `::test_direct_mcp_source_is_refused_as_a_measurement`.
- [x] 2.5 Gate against a recorded baseline with the tolerance ON the baseline, defaulting to 0 pp,
      and refuse cross-version / cross-surface comparison
      → `compare_to_baseline` (takes no tolerance argument — asserted structurally by
      `::test_compare_takes_no_tolerance_argument`); `TestBaselineGate` (8 tests).
- [x] 2.6 CLI entry that reports rates and exits 1 on a failed gate, 2 on **every** unusable input
      → `python scripts/connector_tool_selection_eval.py --dataset … --run … [--baseline …]`;
      `TestCliExitCodes` (21 collected) pins each shape: unusable baseline value, missing key, non-object
      baseline or run, non-object observations, unreadable path, malformed dataset, unrendered
      source → 2; valid failed gate → 1; pass → 0. Cross-family finding 3 (2026-07-25): a
      non-numeric `permitted_regression` used to raise an uncaught `ValueError` and exit **1**, the
      code reserved for a valid failed gate. Conversion and type failures are now caught in
      `_load_baseline` (via `Baseline.__post_init__`) and in both CLI envelopes.
- [x] 2.7 Refuse a baseline or measurement whose rates or tolerance cannot be compared against —
      non-numeric, non-finite, or out of range — at construction, so `_load_baseline` inherits it
      → `_as_rate` / `_as_tolerance` + `__post_init__` on both dataclasses;
      `TestBaselineValueIntegrity` (12 collected). Cross-family finding 1, **critical** (2026-07-25):
      `permitted_regression: NaN` made `compare_to_baseline` return `GATE PASS` and the CLI exit 0
      on a 20/21-vs-1.000 regression, because `drop > NaN` is False for every drop (design D8).
- [x] 2.8 Carry an optional reviewable `evidence` reference through the run format onto the
      measurement, and state plainly when none is recorded — the harness binds the pointer, it does
      not verify provenance (design D7)
      → `score_run(..., evidence=...)` → `Measurement.evidence` / `Baseline.evidence`;
      `TestEvidenceBinding` (3 tests) + `TestCliExitCodes::test_absent_evidence_is_reported_not_assumed`.

## 3. Measurement — needs a rendered session (host / verifier)

- [ ] 3.1 **host-action:** record the first baseline for `claude.ai` — run every dataset prompt
      through a browser-rendered conversation with the TinyAssets connector installed at
      `https://tinyassets.io/mcp` per the `ui-test` skill, transcribe prompt→observed handle, and
      commit the baseline JSON (`dataset_version`, `surface`, `recorded_on`, `top1_rate`,
      `opening_converse_rate`, `permitted_regression`, `evidence`). Log the session in
      `output/user_sim_session.md`.
      **Provenance is a review obligation, not a harness check (D7).** The `source` label is a
      *trusted transcription*: the harness refuses an honestly labelled non-rendered source, but it
      cannot distinguish a transcribed rendered session from a synthetic file labelled
      `claude.ai` — Codex demonstrated exactly that on 2026-07-25, scoring a fabricated run
      1.000/1.000. So the baseline commit MUST carry reviewable rendered-session evidence in its
      `evidence` field (the `output/user_sim_session.md` anchor plus a trace or screenshot path),
      and the reviewer checks *that pointer*, not the label. A baseline landed without reviewable
      evidence is not a measurement regardless of what the harness exits.
- [ ] 3.2 **host-decision:** confirm the permitted regression before the baseline is recorded.
      Default is 0 pp; with 21 prompts a single flipped prompt moves top-1 by ~4.8 pp, so the owner
      may prefer a larger v2 dataset first (design §"Open question").
- [ ] 3.3 Record the `chatgpt` baseline once its connector is registered (STATUS `host-action`:
      "Register the `TinyAssets` ChatGPT connector"). Per-surface baselines never average (D7).
- [ ] 3.4 Wire the gate into the connector-prose change path so a change touching the server
      `instructions` block or the `control_station` prompt must present a passing comparison.
      Depends on 3.1 — there is nothing to compare against until a baseline exists.

## 4. Sync and archive

- [ ] 4.1 **MUST NOT RUN before §3.** `sync-specs` into
      `openspec/specs/live-mcp-connector-surface/`, then archive. `openspec/specs/` is as-built
      truth; syncing while no baseline exists asserts an enforced gate that is not in force.
      Note the footgun: `openspec archive` performs the sync itself, so archiving early is the same
      error.

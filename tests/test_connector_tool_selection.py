"""Connector tool-selection accuracy harness — change
``openspec/changes/archive/2026-08-26-connector-tool-selection-accuracy``.

Proves the harness enforces the delta spec's four requirements as *code*, not as
prose: dataset integrity, separate top-1 / opening-turn rates with no partial
scoring, baseline gating with a recorded tolerance, and rendered-source-only
measurements.

The measurement itself is deliberately not automated — handle choice is a
property of the host chatbot, so observations come from a rendered `ui-test`
session. What is automated is everything that could otherwise turn a bad run into
a good-looking number.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.connector_tool_selection_eval import (
    CANONICAL_HANDLES,
    Baseline,
    DatasetError,
    Measurement,
    MeasurementError,
    compare_to_baseline,
    load_dataset,
    main,
    score_run,
)

SHIPPED_DATASET = (
    Path(__file__).resolve().parent / "data" / "connector_tool_selection_v1.jsonl"
)


def _write_dataset(path: Path, rows: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    return path


def _valid_rows() -> list[dict]:
    """One row per canonical handle — the minimum legal dataset."""
    return [
        {
            "prompt": f"prompt for {handle}",
            "expected_handle": handle,
            "opening": handle == "converse",
        }
        for handle in sorted(CANONICAL_HANDLES)
    ]


def _perfect_run(dataset) -> dict[str, str]:
    return {entry.prompt: entry.expected_handle for entry in dataset.entries}


# --------------------------------------------------------------------------- #
# 1. Dataset integrity — a malformed instrument fails loudly, never scores
# --------------------------------------------------------------------------- #
class TestDatasetIntegrity:
    def test_shipped_dataset_loads_and_covers_every_handle(self):
        dataset = load_dataset(SHIPPED_DATASET)
        assert dataset.version == "v1"
        assert {e.expected_handle for e in dataset.entries} == CANONICAL_HANDLES
        assert any(e.opening for e in dataset.entries)

    def test_label_outside_the_canonical_set_is_rejected(self, tmp_path):
        rows = _valid_rows()
        rows.append(
            {"prompt": "bogus", "expected_handle": "read_everything", "opening": False}
        )
        path = _write_dataset(tmp_path / "bad_v1.jsonl", rows)
        with pytest.raises(DatasetError) as exc:
            load_dataset(path)
        assert "read_everything" in str(exc.value)
        assert "bogus" in str(exc.value)

    def test_uncovered_canonical_handle_is_rejected(self, tmp_path):
        rows = [r for r in _valid_rows() if r["expected_handle"] != "run_graph"]
        path = _write_dataset(tmp_path / "gap_v1.jsonl", rows)
        with pytest.raises(DatasetError, match="run_graph"):
            load_dataset(path)

    def test_duplicate_prompt_is_rejected(self, tmp_path):
        rows = _valid_rows()
        rows.append(dict(rows[0]))
        path = _write_dataset(tmp_path / "dupe_v1.jsonl", rows)
        with pytest.raises(DatasetError, match="duplicate"):
            load_dataset(path)

    def test_version_comes_from_the_filename_and_is_required(self, tmp_path):
        path = _write_dataset(tmp_path / "unversioned.jsonl", _valid_rows())
        with pytest.raises(DatasetError, match="version"):
            load_dataset(path)

    def test_malformed_line_is_rejected_rather_than_skipped(self, tmp_path):
        path = tmp_path / "torn_v1.jsonl"
        path.write_text(
            "\n".join(json.dumps(r) for r in _valid_rows()) + "\n{not json}\n",
            encoding="utf-8",
        )
        with pytest.raises(DatasetError, match="line 8"):
            load_dataset(path)


# --------------------------------------------------------------------------- #
# 2. Scoring — separate rates, no partial runs
# --------------------------------------------------------------------------- #
class TestScoring:
    def test_perfect_run_scores_both_rates_separately(self, tmp_path):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        result = score_run(
            dataset, _perfect_run(dataset), source="claude.ai", observed_on="2026-07-25"
        )
        assert result.top1_rate == 1.0
        assert result.opening_converse_rate == 1.0
        assert result.dataset_version == "v1"
        assert result.surface == "claude.ai"

    def test_partial_run_is_refused_not_scored(self, tmp_path):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        run = _perfect_run(dataset)
        missing = "prompt for run_graph"
        del run[missing]
        with pytest.raises(MeasurementError) as exc:
            score_run(dataset, run, source="claude.ai", observed_on="2026-07-25")
        assert missing in str(exc.value)

    def test_unexpected_prompt_in_a_run_is_refused(self, tmp_path):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        run = _perfect_run(dataset)
        run["a prompt that is not in the dataset"] = "converse"
        with pytest.raises(MeasurementError, match="not in the dataset"):
            score_run(dataset, run, source="claude.ai", observed_on="2026-07-25")

    def test_non_canonical_observed_handle_scores_incorrect_and_is_reported(
        self, tmp_path
    ):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        run = _perfect_run(dataset)
        run["prompt for read_page"] = "totally_made_up"
        result = score_run(
            dataset, run, source="claude.ai", observed_on="2026-07-25"
        )
        assert result.top1_rate < 1.0
        assert "totally_made_up" in result.non_canonical_observed

    def test_opening_regression_is_visible_when_top1_barely_moves(self, tmp_path):
        """The pooling trap the spec calls out, made concrete."""
        rows = _valid_rows() + [
            {"prompt": f"filler {i}", "expected_handle": "read_graph", "opening": False}
            for i in range(20)
        ]
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", rows))
        run = _perfect_run(dataset)
        run["prompt for converse"] = "read_graph"  # the only opening prompt, now wrong
        result = score_run(
            dataset, run, source="claude.ai", observed_on="2026-07-25"
        )
        assert result.top1_rate > 0.95  # pooled average barely notices
        assert result.opening_converse_rate == 0.0  # the real regression is visible

    def test_direct_mcp_source_is_refused_as_a_measurement(self, tmp_path):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        with pytest.raises(MeasurementError, match="rendered"):
            score_run(
                dataset,
                _perfect_run(dataset),
                source="direct_mcp",
                observed_on="2026-07-25",
            )

    def test_source_and_date_are_required(self, tmp_path):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        with pytest.raises(MeasurementError):
            score_run(dataset, _perfect_run(dataset), source="", observed_on="")


# --------------------------------------------------------------------------- #
# 3. Baseline gating — tolerance is recorded, not passed at the call site
# --------------------------------------------------------------------------- #
def _measurement(top1: float, opening: float, *, version="v1", surface="claude.ai"):
    return Measurement(
        dataset_version=version,
        surface=surface,
        observed_on="2026-07-25",
        top1_rate=top1,
        opening_converse_rate=opening,
        total=20,
        correct=int(round(top1 * 20)),
        non_canonical_observed=(),
        misses=(),
    )


class TestBaselineGate:
    def test_default_tolerance_is_zero_percentage_points(self):
        baseline = Baseline(
            dataset_version="v1",
            surface="claude.ai",
            recorded_on="2026-07-20",
            top1_rate=0.90,
            opening_converse_rate=1.0,
        )
        assert baseline.permitted_regression == 0.0

    def test_any_regression_fails_under_the_default_tolerance(self):
        baseline = Baseline("v1", "claude.ai", "2026-07-20", 0.90, 1.0)
        verdict = compare_to_baseline(_measurement(0.85, 1.0), baseline)
        assert verdict.passed is False
        assert "top1" in verdict.reason

    def test_opening_regression_fails_independently(self):
        baseline = Baseline("v1", "claude.ai", "2026-07-20", 0.90, 1.0)
        verdict = compare_to_baseline(_measurement(0.90, 0.80), baseline)
        assert verdict.passed is False
        assert "opening" in verdict.reason

    def test_improvement_passes(self):
        baseline = Baseline("v1", "claude.ai", "2026-07-20", 0.90, 1.0)
        assert compare_to_baseline(_measurement(0.95, 1.0), baseline).passed is True

    def test_recorded_tolerance_is_honored(self):
        baseline = Baseline(
            "v1", "claude.ai", "2026-07-20", 0.90, 1.0, permitted_regression=0.05
        )
        assert compare_to_baseline(_measurement(0.86, 1.0), baseline).passed is True
        assert compare_to_baseline(_measurement(0.84, 1.0), baseline).passed is False

    def test_cross_dataset_version_comparison_is_refused(self):
        baseline = Baseline("v1", "claude.ai", "2026-07-20", 0.90, 1.0)
        with pytest.raises(MeasurementError) as exc:
            compare_to_baseline(_measurement(0.95, 1.0, version="v2"), baseline)
        assert "v1" in str(exc.value) and "v2" in str(exc.value)

    def test_cross_surface_comparison_is_refused(self):
        baseline = Baseline("v1", "claude.ai", "2026-07-20", 0.90, 1.0)
        with pytest.raises(MeasurementError, match="surface"):
            compare_to_baseline(
                _measurement(0.95, 1.0, surface="chatgpt"), baseline
            )

    def test_compare_takes_no_tolerance_argument(self):
        """Structural: a failing run cannot be rescued at the call site."""
        import inspect

        assert list(inspect.signature(compare_to_baseline).parameters) == [
            "measurement",
            "baseline",
        ]


# --------------------------------------------------------------------------- #
# 4. Baseline value integrity — a threshold nothing can be compared against
#    is not a threshold
# --------------------------------------------------------------------------- #
class TestBaselineValueIntegrity:
    """Cross-family review finding 1 (Codex REJECT 2026-07-25).

    ``drop > tolerance`` is False for *every* drop when the tolerance is NaN, so
    one non-finite value silently converts the gate into an unconditional
    ``GATE PASS`` without touching the comparison logic. The same hole exists on
    each rate (``baseline - NaN`` is NaN) and, less sharply, on a rate outside
    [0, 1], which shifts the comparison by an arbitrary amount. None of it may be
    accepted at construction — which is also where ``_load_baseline`` builds.
    """

    def _twenty_of_twentyone(self) -> Measurement:
        """A real regression on the shipped instrument: 20/21 top-1."""
        dataset = load_dataset(SHIPPED_DATASET)
        run = _perfect_run(dataset)
        flipped = next(e for e in dataset.entries if e.expected_handle == "read_page")
        run[flipped.prompt] = "read_graph"
        measurement = score_run(
            dataset, run, source="claude.ai", observed_on="2026-07-25"
        )
        assert 0.90 < measurement.top1_rate < 1.0  # precondition, not the assertion
        return measurement

    def test_nan_tolerance_cannot_pass_a_real_regression(self):
        measurement = self._twenty_of_twentyone()
        with pytest.raises(MeasurementError, match="permitted_regression"):
            Baseline(
                "v1", "claude.ai", "2026-07-20", 1.0, 1.0,
                permitted_regression=float("nan"),
            )
        # ...and the honest tolerance still fails that same candidate, so the
        # refusal above is not passing because the run happened to be fine.
        honest = Baseline("v1", "claude.ai", "2026-07-20", 1.0, 1.0)
        assert compare_to_baseline(measurement, honest).passed is False

    def test_infinite_tolerance_is_refused(self):
        with pytest.raises(MeasurementError, match="permitted_regression"):
            Baseline(
                "v1", "claude.ai", "2026-07-20", 1.0, 1.0,
                permitted_regression=float("inf"),
            )

    def test_negative_tolerance_is_refused(self):
        with pytest.raises(MeasurementError, match="permitted_regression"):
            Baseline(
                "v1", "claude.ai", "2026-07-20", 0.9, 1.0, permitted_regression=-0.1
            )

    def test_tolerance_wider_than_the_rate_range_is_refused(self):
        """A tolerance of 2.0 is not a loose gate, it is no gate."""
        with pytest.raises(MeasurementError, match="permitted_regression"):
            Baseline(
                "v1", "claude.ai", "2026-07-20", 0.9, 1.0, permitted_regression=2.0
            )

    @pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_baseline_rate_is_refused(self, bad):
        with pytest.raises(MeasurementError, match="top1_rate"):
            Baseline("v1", "claude.ai", "2026-07-20", bad, 1.0)
        with pytest.raises(MeasurementError, match="opening_converse_rate"):
            Baseline("v1", "claude.ai", "2026-07-20", 1.0, bad)

    @pytest.mark.parametrize("bad", [1.5, -0.1, 100.0])
    def test_out_of_range_baseline_rate_is_refused(self, bad):
        with pytest.raises(MeasurementError, match="top1_rate"):
            Baseline("v1", "claude.ai", "2026-07-20", bad, 1.0)

    def test_non_numeric_baseline_value_is_refused_as_unusable(self):
        with pytest.raises(MeasurementError, match="top1_rate"):
            Baseline("v1", "claude.ai", "2026-07-20", "not-a-number", 1.0)
        with pytest.raises(MeasurementError, match="permitted_regression"):
            Baseline(
                "v1", "claude.ai", "2026-07-20", 1.0, 1.0,
                permitted_regression="not-a-number",
            )

    def test_non_finite_measurement_rate_is_refused(self):
        """The mirror of the tolerance hole: a NaN *candidate* also passes.

        ``baseline - NaN`` is NaN and ``NaN > tolerance`` is False, so the gate
        reads PASS from the candidate side too. ``score_run`` divides ints and
        cannot produce one, but a hand-built ``Measurement`` can.
        """
        with pytest.raises(MeasurementError, match="top1_rate"):
            Measurement(
                dataset_version="v1",
                surface="claude.ai",
                observed_on="2026-07-25",
                top1_rate=float("nan"),
                opening_converse_rate=1.0,
                total=21,
                correct=20,
            )


# --------------------------------------------------------------------------- #
# 5. Provenance — the source label is a trusted transcription, not proof
# --------------------------------------------------------------------------- #
class TestEvidenceBinding:
    """Cross-family review finding 2 (Codex REJECT 2026-07-25).

    The harness refuses an honestly labelled non-rendered source, but it cannot
    tell a transcribed rendered session from a synthetic file labelled
    ``claude.ai``. So the format binds an optional reviewable pointer and the
    harness says plainly when there is none — it does not claim a provenance
    check it cannot perform.
    """

    def test_evidence_reference_is_carried_onto_the_measurement(self, tmp_path):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        result = score_run(
            dataset,
            _perfect_run(dataset),
            source="claude.ai",
            observed_on="2026-07-25",
            evidence="output/user_sim_session.md#2026-07-25-tool-selection",
        )
        assert result.evidence.endswith("#2026-07-25-tool-selection")

    def test_evidence_is_optional(self, tmp_path):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        result = score_run(
            dataset, _perfect_run(dataset), source="claude.ai", observed_on="2026-07-25"
        )
        assert result.evidence == ""

    def test_non_string_evidence_is_refused(self, tmp_path):
        dataset = load_dataset(_write_dataset(tmp_path / "d_v1.jsonl", _valid_rows()))
        with pytest.raises(MeasurementError, match="evidence"):
            score_run(
                dataset,
                _perfect_run(dataset),
                source="claude.ai",
                observed_on="2026-07-25",
                evidence={"screenshot": "shot.png"},
            )


# --------------------------------------------------------------------------- #
# 6. CLI contract — exit 0 pass, 1 failed gate, 2 unusable input, no overlap
# --------------------------------------------------------------------------- #
_GOOD_BASELINE = {
    "dataset_version": "v1",
    "surface": "claude.ai",
    "recorded_on": "2026-07-20",
    "top1_rate": 1.0,
    "opening_converse_rate": 1.0,
}


def _write_json(path: Path, payload) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _cli_argv(tmp_path, *, run=None, baseline=None, dataset_rows=None):
    """Build a well-formed invocation, overriding one piece at a time."""
    dataset_path = _write_dataset(
        tmp_path / "cli_v1.jsonl", dataset_rows if dataset_rows is not None else _valid_rows()
    )
    if run is None:
        dataset = load_dataset(dataset_path)
        run = {
            "source": "claude.ai",
            "observed_on": "2026-07-25",
            "observations": _perfect_run(dataset),
        }
    argv = [
        "--dataset", str(dataset_path),
        "--run", str(_write_json(tmp_path / "run.json", run)),
    ]
    if baseline is not None:
        argv += ["--baseline", str(_write_json(tmp_path / "baseline.json", baseline))]
    return argv


def _one_wrong_run(tmp_path) -> dict:
    dataset = load_dataset(_write_dataset(tmp_path / "probe_v1.jsonl", _valid_rows()))
    observations = _perfect_run(dataset)
    observations["prompt for read_page"] = "read_graph"
    return {
        "source": "claude.ai",
        "observed_on": "2026-07-25",
        "observations": observations,
    }


class TestCliExitCodes:
    def test_passing_gate_exits_zero(self, tmp_path):
        assert main(_cli_argv(tmp_path, baseline=dict(_GOOD_BASELINE))) == 0

    def test_no_baseline_reports_rates_and_exits_zero(self, tmp_path, capsys):
        assert main(_cli_argv(tmp_path)) == 0
        assert "top1=1.000" in capsys.readouterr().out

    def test_failed_gate_exits_one(self, tmp_path):
        argv = _cli_argv(
            tmp_path, run=_one_wrong_run(tmp_path), baseline=dict(_GOOD_BASELINE)
        )
        assert main(argv) == 1

    def test_nan_tolerance_in_the_baseline_file_exits_two_not_zero(self, tmp_path):
        """The end-to-end bypass: a real regression must not report GATE PASS."""
        baseline = dict(_GOOD_BASELINE, permitted_regression=float("nan"))
        argv = _cli_argv(tmp_path, run=_one_wrong_run(tmp_path), baseline=baseline)
        assert main(argv) == 2

    def test_non_numeric_tolerance_exits_two_not_one(self, tmp_path):
        """Exit 1 is reserved for a *valid* failed gate; this input is unusable."""
        baseline = dict(_GOOD_BASELINE, permitted_regression="not-a-number")
        assert main(_cli_argv(tmp_path, baseline=baseline)) == 2

    @pytest.mark.parametrize(
        "bad", [float("nan"), float("inf"), 1.5, -0.2, "high", None, [1.0]]
    )
    def test_unusable_baseline_rate_exits_two(self, tmp_path, bad):
        baseline = dict(_GOOD_BASELINE, top1_rate=bad)
        assert main(_cli_argv(tmp_path, baseline=baseline)) == 2

    def test_missing_baseline_key_exits_two(self, tmp_path):
        baseline = {k: v for k, v in _GOOD_BASELINE.items() if k != "opening_converse_rate"}
        assert main(_cli_argv(tmp_path, baseline=baseline)) == 2

    def test_baseline_that_is_not_an_object_exits_two(self, tmp_path):
        assert main(_cli_argv(tmp_path, baseline=[_GOOD_BASELINE])) == 2

    def test_missing_baseline_file_exits_two(self, tmp_path):
        argv = _cli_argv(tmp_path) + ["--baseline", str(tmp_path / "nope.json")]
        assert main(argv) == 2

    def test_run_that_is_not_an_object_exits_two(self, tmp_path):
        assert main(_cli_argv(tmp_path, run=["prompt for converse"])) == 2

    def test_run_whose_observations_are_not_an_object_exits_two(self, tmp_path):
        run = {
            "source": "claude.ai",
            "observed_on": "2026-07-25",
            "observations": ["converse"],
        }
        assert main(_cli_argv(tmp_path, run=run)) == 2

    def test_unrendered_source_exits_two(self, tmp_path):
        dataset = load_dataset(
            _write_dataset(tmp_path / "probe_v1.jsonl", _valid_rows())
        )
        run = {
            "source": "direct-mcp",
            "observed_on": "2026-07-25",
            "observations": _perfect_run(dataset),
        }
        assert main(_cli_argv(tmp_path, run=run)) == 2

    def test_malformed_dataset_exits_two(self, tmp_path):
        rows = [r for r in _valid_rows() if r["expected_handle"] != "run_graph"]
        run = {
            "source": "claude.ai",
            "observed_on": "2026-07-25",
            "observations": {r["prompt"]: r["expected_handle"] for r in rows},
        }
        assert main(_cli_argv(tmp_path, run=run, dataset_rows=rows)) == 2

    def test_absent_evidence_is_reported_not_assumed(self, tmp_path, capsys):
        """The CLI states the trust model instead of implying provenance."""
        assert main(_cli_argv(tmp_path)) == 0
        out = capsys.readouterr().out
        assert "trusted transcription" in out

    def test_recorded_evidence_is_printed(self, tmp_path, capsys):
        dataset = load_dataset(
            _write_dataset(tmp_path / "probe_v1.jsonl", _valid_rows())
        )
        run = {
            "source": "claude.ai",
            "observed_on": "2026-07-25",
            "evidence": "output/user_sim_session.md#run-7",
            "observations": _perfect_run(dataset),
        }
        assert main(_cli_argv(tmp_path, run=run)) == 0
        assert "output/user_sim_session.md#run-7" in capsys.readouterr().out

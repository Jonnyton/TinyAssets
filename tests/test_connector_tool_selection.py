"""Connector tool-selection accuracy harness — change
``openspec/changes/connector-tool-selection-accuracy``.

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

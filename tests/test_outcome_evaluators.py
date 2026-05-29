"""Tests for workflow.outcomes evaluators — protocol conformance, EvalResult shape."""

from __future__ import annotations

import pytest

from workflow.evaluation import EvalResult, Evaluator
from workflow.outcomes import (
    ConferenceAcceptedEvaluator,
    DeployedAppEvaluator,
    HyperparameterImportanceEvaluator,
    MentionedInPublicationEvaluator,
    MergedPREvaluator,
    PeerReviewAcceptedEvaluator,
    PublishedPaperEvaluator,
)

# ── Protocol conformance ───────────────────────────────────────────────────────

class TestProtocolConformance:
    def test_published_paper_is_evaluator(self):
        assert isinstance(PublishedPaperEvaluator(), Evaluator)

    def test_merged_pr_is_evaluator(self):
        assert isinstance(MergedPREvaluator(), Evaluator)

    def test_deployed_app_is_evaluator(self):
        assert isinstance(DeployedAppEvaluator(), Evaluator)

    def test_result_is_eval_result(self):
        ev = PublishedPaperEvaluator()
        result = ev.evaluate({"doi": "10.1234/test"})
        assert isinstance(result, EvalResult)


# ── PublishedPaperEvaluator ───────────────────────────────────────────────────

class TestPublishedPaperEvaluator:
    def test_no_doi_returns_skip(self):
        ev = PublishedPaperEvaluator()
        result = ev.evaluate({})
        assert result.verdict == "skip"
        assert result.score == pytest.approx(-1.0)
        assert result.label == "published_paper"

    def test_none_doi_returns_skip(self):
        ev = PublishedPaperEvaluator()
        result = ev.evaluate({"doi": None})
        assert result.verdict == "skip"

    def test_resolved_doi_returns_pass(self):
        ev = PublishedPaperEvaluator(prober=lambda url: True)
        result = ev.evaluate({"doi": "10.1234/example"})
        assert result.verdict == "pass"
        assert result.score == pytest.approx(1.0)
        assert result.details["resolved"] is True
        assert "doi.org/10.1234/example" in result.details["doi_url"]

    def test_unresolved_doi_returns_fail(self):
        ev = PublishedPaperEvaluator(prober=lambda url: False)
        result = ev.evaluate({"doi": "10.9999/nonexistent"})
        assert result.verdict == "fail"
        assert result.score == pytest.approx(0.0)
        assert result.details["resolved"] is False

    def test_kind_is_custom(self):
        ev = PublishedPaperEvaluator()
        result = ev.evaluate({})
        assert result.kind == "custom"

    def test_score_in_valid_range(self):
        for prober_result in (True, False):
            ev = PublishedPaperEvaluator(prober=lambda url, r=prober_result: r)
            result = ev.evaluate({"doi": "10.1234/x"})
            assert -1.0 <= result.score <= 1.0

    def test_default_prober_does_not_raise(self):
        ev = PublishedPaperEvaluator()
        result = ev.evaluate({"doi": "10.1234/example"})
        assert result.verdict == "fail"
        assert result.details["verification_status"] == "unverified"
        assert result.details["resolved"] is None


# ── MergedPREvaluator ─────────────────────────────────────────────────────────

class TestMergedPREvaluator:
    def test_no_pr_url_returns_skip(self):
        ev = MergedPREvaluator()
        result = ev.evaluate({})
        assert result.verdict == "skip"
        assert result.score == pytest.approx(-1.0)
        assert result.label == "merged_pr"

    def test_merged_pr_returns_pass(self):
        ev = MergedPREvaluator(prober=lambda url: True)
        result = ev.evaluate({"pr_url": "https://github.com/org/repo/pull/42"})
        assert result.verdict == "pass"
        assert result.score == pytest.approx(1.0)
        assert result.details["merged"] is True

    def test_unmerged_pr_returns_fail(self):
        ev = MergedPREvaluator(prober=lambda url: False)
        result = ev.evaluate({"pr_url": "https://github.com/org/repo/pull/42"})
        assert result.verdict == "fail"
        assert result.score == pytest.approx(0.0)

    def test_details_contain_pr_url(self):
        url = "https://github.com/org/repo/pull/42"
        ev = MergedPREvaluator(prober=lambda u: True)
        result = ev.evaluate({"pr_url": url})
        assert result.details["pr_url"] == url

    def test_score_in_valid_range(self):
        for prober_result in (True, False):
            ev = MergedPREvaluator(prober=lambda url, r=prober_result: r)
            result = ev.evaluate({"pr_url": "https://github.com/x/y/pull/1"})
            assert -1.0 <= result.score <= 1.0

    def test_default_prober_reports_unverified(self):
        ev = MergedPREvaluator()
        result = ev.evaluate({"pr_url": "https://github.com/org/repo/pull/42"})
        assert result.verdict == "fail"
        assert result.details["verification_status"] == "unverified"
        assert result.details["merged"] is None


# ── DeployedAppEvaluator ──────────────────────────────────────────────────────

class TestDeployedAppEvaluator:
    def test_no_app_url_returns_skip(self):
        ev = DeployedAppEvaluator()
        result = ev.evaluate({})
        assert result.verdict == "skip"
        assert result.score == pytest.approx(-1.0)
        assert result.label == "deployed_app"

    def test_live_app_returns_pass(self):
        ev = DeployedAppEvaluator(prober=lambda url: True)
        result = ev.evaluate({"app_url": "https://myapp.example.com"})
        assert result.verdict == "pass"
        assert result.score == pytest.approx(1.0)
        assert result.details["live"] is True

    def test_dead_app_returns_fail(self):
        ev = DeployedAppEvaluator(prober=lambda url: False)
        result = ev.evaluate({"app_url": "https://myapp.example.com"})
        assert result.verdict == "fail"
        assert result.score == pytest.approx(0.0)

    def test_details_contain_app_url(self):
        url = "https://myapp.example.com"
        ev = DeployedAppEvaluator(prober=lambda u: False)
        result = ev.evaluate({"app_url": url})
        assert result.details["app_url"] == url

    def test_score_in_valid_range(self):
        for prober_result in (True, False):
            ev = DeployedAppEvaluator(prober=lambda url, r=prober_result: r)
            result = ev.evaluate({"app_url": "https://x.example.com"})
            assert -1.0 <= result.score <= 1.0

    def test_default_prober_does_not_raise(self):
        ev = DeployedAppEvaluator()
        result = ev.evaluate({"app_url": "https://example.com"})
        assert result.verdict == "fail"
        assert result.details["verification_status"] == "unverified"
        assert result.details["live"] is None


# ── EvalResult shape invariants ───────────────────────────────────────────────

class TestEvalResultShape:
    def test_all_evaluators_return_valid_kind(self):
        evaluators = [
            PublishedPaperEvaluator(),
            MergedPREvaluator(),
            DeployedAppEvaluator(),
        ]
        valid_kinds = {"structural", "editorial", "process", "numeric", "custom"}
        for ev in evaluators:
            result = ev.evaluate({})
            assert result.kind in valid_kinds

    def test_all_evaluators_return_valid_verdict(self):
        evaluators = [
            PublishedPaperEvaluator(),
            MergedPREvaluator(),
            DeployedAppEvaluator(),
        ]
        valid_verdicts = {"pass", "fail", "skip", "error"}
        for ev in evaluators:
            result = ev.evaluate({})
            assert result.verdict in valid_verdicts

    def test_all_evaluators_score_in_range(self):
        evaluators = [
            PublishedPaperEvaluator(prober=lambda url: True),
            MergedPREvaluator(prober=lambda url: True),
            DeployedAppEvaluator(prober=lambda url: True),
        ]
        for ev in evaluators:
            result = ev.evaluate({"doi": "x", "pr_url": "y", "app_url": "z"})
            assert -1.0 <= result.score <= 1.0


# ── New evaluator protocol conformance ────────────────────────────────────────

class TestNewEvaluatorProtocolConformance:
    def test_peer_review_is_evaluator(self):
        assert isinstance(PeerReviewAcceptedEvaluator(), Evaluator)

    def test_conference_accepted_is_evaluator(self):
        assert isinstance(ConferenceAcceptedEvaluator(), Evaluator)

    def test_mentioned_in_publication_is_evaluator(self):
        assert isinstance(MentionedInPublicationEvaluator(), Evaluator)


# ── PeerReviewAcceptedEvaluator ────────────────────────────────────────────────

class TestPeerReviewAcceptedEvaluator:
    _VALID = {
        "venue": "ICML 2026",
        "decision": "accepted",
        "decision_date": "2026-04-01",
    }

    def test_pass_on_accepted_decision(self):
        result = PeerReviewAcceptedEvaluator().evaluate(self._VALID)
        assert result.verdict == "pass"
        assert result.score == 1.0
        assert result.label == "peer_review_accepted"

    def test_fail_on_rejected_decision(self):
        state = {**self._VALID, "decision": "rejected"}
        result = PeerReviewAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"
        assert result.score == 0.0

    def test_accepted_with_revisions_is_pass(self):
        state = {**self._VALID, "decision": "accepted_with_revisions"}
        result = PeerReviewAcceptedEvaluator().evaluate(state)
        assert result.verdict == "pass"

    def test_not_accepted_is_fail(self):
        state = {**self._VALID, "decision": "not accepted"}
        result = PeerReviewAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"

    def test_missing_venue_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "venue"}
        result = PeerReviewAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"
        assert "venue" in result.details["missing"]

    def test_missing_decision_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "decision"}
        result = PeerReviewAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"

    def test_missing_decision_date_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "decision_date"}
        result = PeerReviewAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"

    def test_optional_reviewers_included_in_details(self):
        state = {**self._VALID, "reviewers": 3}
        result = PeerReviewAcceptedEvaluator().evaluate(state)
        assert result.details["reviewers"] == 3

    def test_result_is_eval_result(self):
        result = PeerReviewAcceptedEvaluator().evaluate(self._VALID)
        assert isinstance(result, EvalResult)


# ── ConferenceAcceptedEvaluator ────────────────────────────────────────────────

class TestConferenceAcceptedEvaluator:
    _VALID = {
        "conference_name": "NeurIPS 2026",
        "decision": "accepted",
        "talk_date": "2026-12-10",
        "accepted_at": "2026-09-01",
    }

    def test_pass_on_full_valid_state(self):
        result = ConferenceAcceptedEvaluator().evaluate(self._VALID)
        assert result.verdict == "pass"
        assert result.score == 1.0
        assert result.label == "conference_accepted"

    def test_missing_conference_name_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "conference_name"}
        result = ConferenceAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"
        assert "conference_name" in result.details["missing"]

    def test_missing_talk_date_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "talk_date"}
        result = ConferenceAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"

    def test_missing_accepted_at_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "accepted_at"}
        result = ConferenceAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"

    def test_missing_decision_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "decision"}
        result = ConferenceAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"
        assert "decision" in result.details["missing"]

    def test_rejected_decision_returns_fail(self):
        state = {**self._VALID, "decision": "rejected"}
        result = ConferenceAcceptedEvaluator().evaluate(state)
        assert result.verdict == "fail"
        assert result.score == 0.0

    def test_optional_recording_url_included_in_details(self):
        state = {**self._VALID, "recording_url": "https://rec.example.com/talk"}
        result = ConferenceAcceptedEvaluator().evaluate(state)
        assert result.details["recording_url"] == "https://rec.example.com/talk"

    def test_result_is_eval_result(self):
        result = ConferenceAcceptedEvaluator().evaluate(self._VALID)
        assert isinstance(result, EvalResult)


# ── MentionedInPublicationEvaluator ───────────────────────────────────────────

class TestMentionedInPublicationEvaluator:
    _VALID = {
        "publication": "TechCrunch",
        "mention_url": "https://techcrunch.com/2026/04/article",
        "mention_date": "2026-04-15",
    }

    def test_pass_on_full_valid_state(self):
        result = MentionedInPublicationEvaluator().evaluate(self._VALID)
        assert result.verdict == "pass"
        assert result.score == 1.0
        assert result.label == "mentioned_in_publication"

    def test_missing_publication_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "publication"}
        result = MentionedInPublicationEvaluator().evaluate(state)
        assert result.verdict == "fail"
        assert "publication" in result.details["missing"]

    def test_missing_mention_url_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "mention_url"}
        result = MentionedInPublicationEvaluator().evaluate(state)
        assert result.verdict == "fail"

    def test_missing_mention_date_returns_fail(self):
        state = {k: v for k, v in self._VALID.items() if k != "mention_date"}
        result = MentionedInPublicationEvaluator().evaluate(state)
        assert result.verdict == "fail"

    def test_optional_context_snippet_included_in_details(self):
        state = {**self._VALID, "context_snippet": "...the Workflow platform..."}
        result = MentionedInPublicationEvaluator().evaluate(state)
        assert result.details["context_snippet"] == "...the Workflow platform..."

    def test_empty_publication_returns_fail(self):
        state = {**self._VALID, "publication": ""}
        result = MentionedInPublicationEvaluator().evaluate(state)
        assert result.verdict == "fail"

    def test_result_is_eval_result(self):
        result = MentionedInPublicationEvaluator().evaluate(self._VALID)
        assert isinstance(result, EvalResult)


# ── HyperparameterImportanceEvaluator ─────────────────────────────────────────


def _synthetic_runs(n: int = 30, seed: int = 0) -> list[dict]:
    """Generate runs where param_a linearly drives metric; b/c are noise."""
    import random
    rnd = random.Random(seed)
    runs = []
    for _ in range(n):
        a = rnd.uniform(0.0, 1.0)
        b = rnd.uniform(0.0, 1.0)
        c = rnd.uniform(0.0, 1.0)
        # metric = 5*a + small noise on b/c
        metric = 5.0 * a + 0.05 * b + 0.05 * c + rnd.uniform(-0.01, 0.01)
        runs.append({"params": {"param_a": a, "param_b": b, "param_c": c}, "metric": metric})
    return runs


class TestHyperparameterImportanceEvaluator:
    def test_protocol_conformance(self):
        assert isinstance(HyperparameterImportanceEvaluator(), Evaluator)

    def test_rf_method_top_param_is_driver(self):
        pytest.importorskip("sklearn")
        result = HyperparameterImportanceEvaluator().evaluate(
            {"run_results": _synthetic_runs(30), "method": "rf"}
        )
        assert result.verdict == "pass"
        assert result.details["method_used"] == "rf"
        assert result.details["n_runs_analyzed"] == 30
        ranking = result.details["importance_ranking"]
        assert ranking[0]["param"] == "param_a"
        assert ranking[0]["rank"] == 1
        assert result.score > 0.5  # param_a dominates

    def test_correlation_method_top_param_is_driver(self):
        pytest.importorskip("scipy")
        result = HyperparameterImportanceEvaluator().evaluate(
            {"run_results": _synthetic_runs(30), "method": "correlation"}
        )
        assert result.verdict == "pass"
        assert result.details["method_used"] == "correlation"
        ranking = result.details["importance_ranking"]
        assert ranking[0]["param"] == "param_a"
        # Spearman |stat| should be very high for the linear driver
        assert ranking[0]["importance"] > 0.9

    def test_skip_below_min_runs(self):
        result = HyperparameterImportanceEvaluator().evaluate(
            {"run_results": _synthetic_runs(5), "min_runs": 10}
        )
        assert result.verdict == "skip"
        assert result.details["n_runs"] == 5
        assert result.details["min_runs"] == 10
        assert "below min_runs" in result.details["reason"]

    def test_categorical_param_is_ordinal_encoded(self):
        pytest.importorskip("sklearn")
        # param_d is categorical "small"|"medium"|"large"; metric correlates with it.
        runs = []
        size_to_metric = {"small": 0.0, "medium": 1.0, "large": 2.0}
        for i in range(15):
            size = ["small", "medium", "large"][i % 3]
            runs.append({
                "params": {"param_a": float(i), "param_d": size},
                "metric": size_to_metric[size] + 0.01 * i,
            })
        result = HyperparameterImportanceEvaluator().evaluate({"run_results": runs})
        assert result.verdict == "pass"
        params_in_ranking = {entry["param"] for entry in result.details["importance_ranking"]}
        assert "param_d" in params_in_ranking  # ordinal-encoded categorical surfaces

    def test_skip_when_backends_missing(self, monkeypatch):
        from workflow.outcomes import evaluators as ev_mod

        err_msg = "scikit-learn / scipy not installed; pip install workflow[scientific]"
        monkeypatch.setattr(
            ev_mod,
            "_load_hyperparameter_backends",
            lambda: (None, None, err_msg),
        )
        result = HyperparameterImportanceEvaluator().evaluate(
            {"run_results": _synthetic_runs(15)}
        )
        assert result.verdict == "skip"
        assert "scikit-learn" in result.details["reason"]
        assert "workflow[scientific]" in result.details["reason"]

    def test_empty_run_results_returns_skip(self):
        result = HyperparameterImportanceEvaluator().evaluate({"run_results": []})
        assert result.verdict == "skip"
        assert "no run_results" in result.details["reason"]

    def test_missing_run_results_key_returns_skip(self):
        result = HyperparameterImportanceEvaluator().evaluate({})
        assert result.verdict == "skip"

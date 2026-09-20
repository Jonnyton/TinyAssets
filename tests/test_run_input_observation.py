"""Pure common metadata projection never authorizes replay or mutates state."""

import pytest

from tinyassets.run_input_origin import classify_admission_observation


def envelope(**changes):
    return {"origin_kind": "canonical_consumer", "origin_version": 1,
            "origin_options_json": "{}", "execution_started_at": None,
            "claim_token": None, **changes}


@pytest.mark.parametrize("marker", [{"execution_started_at": 1}, {"claim_token": "x"},
                                   {"execution_started_at": 1, "claim_token": "x"}])
def test_queued_started_metadata_is_ambiguous_not_healthy_or_replayable(marker):
    source = envelope(**marker)
    result = classify_admission_observation(source, "queued")
    assert result["phase"] == "recovery_required"
    assert result["actions_may_have_occurred"] is True
    assert result["automatic_replay"] is False
    assert source == envelope(**marker)


@pytest.mark.parametrize("origin", [{"origin_kind": "unknown"},
                                   {"origin_options_json": "not json"},
                                   {"origin_kind": "", "origin_version": 0},
                                   {"origin_options_json": "{ }"}])
@pytest.mark.parametrize("started", [False, True])
def test_unavailable_origin_is_held_even_if_running(origin, started):
    for status in ("queued", "running"):
        result = classify_admission_observation(
            envelope(**origin, claim_token="x" if started else None), status)
        assert result["phase"] == "origin_unavailable"
        assert result["actions_may_have_occurred"] is started
        assert result["automatic_replay"] is False


def test_known_pending_running_and_terminal_results_are_not_rewritten():
    assert classify_admission_observation(envelope(), "queued") == {}
    assert classify_admission_observation(envelope(claim_token="x"), "running") == {}
    for status in ("completed", "failed", "cancelled", "interrupted"):
        assert classify_admission_observation(envelope(origin_kind="unknown"), status) == {}

"""Execute actual browser refresh/send code with keyed canonical responses."""

import pytest

from tests.test_onboarding_app import _run_app

TURN = "a" * 32
REQUEST = {"version": 1, "request_key": "10cf4ccc-8528-48ae-a991-70cc35c1224f",
           "binding_id": "chosen", "binding_revision": 1}
COMPLETED = {"reply": "Answer", "consumer_turn": {"version": 1, "turn_id": TURN,
             "run_id": "run", "state": "completed", "run_status": "completed",
             "projection": "committed"}}


@pytest.mark.parametrize("status_first", [False, True])
def test_reload_history_and_terminal_status_render_exact_pair_once(tmp_path, status_first):
    result = _run_app(tmp_path, {"kind": "restore", "pending": "Question",
        "pendingConsumerRequest": REQUEST, "consumerStatusFirst": status_first,
        "consumerStatus": COMPLETED, "history": [
            {"speaker": "founder", "text": "Question", "ts": 10, "consumer_turn_id": TURN},
            {"speaker": "universe", "text": "Answer", "ts": 10, "consumer_turn_id": TURN},
        ]})
    assert result["messages"] == [{"role": "founder", "text": "Question"},
                                  {"role": "universe", "text": "Answer"}]
    assert result["converseCalls"] == []
    assert result["inflight"] is None
    assert len(result["statusCalls"]) == 1


def test_selected_turn_saves_key_before_send_and_polls_same_request(tmp_path):
    pending = {"consumer_turn": {**COMPLETED["consumer_turn"], "state": "pending",
                                 "run_status": "running", "projection": "pending"}}
    result = _run_app(tmp_path, {"kind": "send", "message": "Question",
        "payloads": [{"error": "consumer_request_required", "consumer_selection": {
            "version": 1, "binding_id": "chosen", "binding_revision": 1}}, pending],
        "consumerStatus": COMPLETED})
    assert result["messages"] == [{"role": "founder", "text": "Question"},
                                  {"role": "universe", "text": "Answer"}]
    assert len(result["consumerRequests"]) == 2
    assert result["consumerRequests"][0] is None
    assert result["statusCalls"][0]["args"]["request_key"] == (
        result["consumerRequests"][1]["request_key"])
    assert result["inflight"] is None


def test_storage_failure_does_not_start_selected_workflow(tmp_path):
    result = _run_app(tmp_path, {"kind": "send", "message": "Question", "storageFull": True,
        "payload": {"error": "consumer_request_required", "consumer_selection": {
            "version": 1, "binding_id": "chosen", "binding_revision": 1}}})
    assert result["converseCalls"] == ["Question"]  # Only the no-key, no-effect capability probe.
    assert result["consumerRequests"] == [None]

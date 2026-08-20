"""Tests for the async action-result outbox + governed follow-up delivery (Slice 3).

The delivery core's seams (get_run / authorize / adapter) are injected so the
outbox state machine, terminal detection, idempotency, fail-closed, and content-
safety are asserted without a live run queue or Slack transport.
"""

from __future__ import annotations

from tinyassets.action_result_delivery import (
    compose_summary,
    deliver_pending_action_results,
)
from tinyassets.storage import action_result_outbox as outbox


def _record(base, run_id="r1"):
    return outbox.record(
        base, run_id=run_id, universe_id="u-tiny", workspace_id="T1",
        channel_id="C1", thread_ts="1700.1", app_binding_ref="bind-1",
        origin_event_id="Ev1",
    )


class _Adapter:
    def __init__(self):
        self.delivered: list[tuple] = []

    def deliver(self, authorization, response):
        self.delivered.append((authorization, response))
        return object()


def test_record_is_idempotent_and_listed_pending(tmp_path):
    assert _record(tmp_path) is True         # new
    assert _record(tmp_path) is False        # same run_id -> INSERT OR IGNORE
    pending = outbox.list_pending(tmp_path)
    assert [p["run_id"] for p in pending] == ["r1"]
    # content-free: no credential / body columns
    assert "credential" not in pending[0] and "body" not in pending[0]


def test_a_still_running_run_is_not_delivered(tmp_path):
    _record(tmp_path)
    adapter = _Adapter()
    counts = deliver_pending_action_results(
        tmp_path,
        get_run=lambda b, rid: {"status": "running"},
        authorize=lambda e, r: object(),
        adapter=adapter,
    )
    assert counts["skipped_running"] == 1 and counts["delivered"] == 0
    assert adapter.delivered == []
    assert outbox.list_pending(tmp_path)  # still pending


def test_a_completed_run_delivers_once_and_marks_delivered(tmp_path):
    _record(tmp_path)
    adapter = _Adapter()
    auth = object()
    counts = deliver_pending_action_results(
        tmp_path,
        get_run=lambda b, rid: {"status": "completed", "revision": 4,
                                "public_result_ref": "PR #999"},
        authorize=lambda e, r: auth,
        adapter=adapter,
    )
    assert counts["delivered"] == 1
    assert len(adapter.delivered) == 1
    a, response = adapter.delivered[0]
    assert a is auth
    assert "Done" in response and "PR #999" in response
    assert outbox.list_pending(tmp_path) == []  # no longer pending

    # Idempotency: a second tick does NOT re-deliver (state guard).
    counts2 = deliver_pending_action_results(
        tmp_path, get_run=lambda b, rid: {"status": "completed", "revision": 4},
        authorize=lambda e, r: auth, adapter=adapter,
    )
    assert counts2["delivered"] == 0
    assert len(adapter.delivered) == 1


def test_a_failed_run_is_reported_honestly_never_as_success(tmp_path):
    _record(tmp_path)
    adapter = _Adapter()
    counts = deliver_pending_action_results(
        tmp_path,
        get_run=lambda b, rid: {"status": "failed", "revision": 2,
                                "failed_phase": "build"},
        authorize=lambda e, r: object(),
        adapter=adapter,
    )
    assert counts["delivered"] == 1
    _, response = adapter.delivered[0]
    low = response.lower()
    assert "didn't finish" in low and "build" in low
    assert "done" not in low and "success" not in low


def test_delivery_holds_fail_closed_when_unauthorized(tmp_path):
    _record(tmp_path)
    adapter = _Adapter()
    counts = deliver_pending_action_results(
        tmp_path,
        get_run=lambda b, rid: {"status": "completed", "revision": 1},
        authorize=lambda e, r: None,  # cannot authorize now
        adapter=adapter,
    )
    assert counts["held"] == 1 and counts["delivered"] == 0
    assert adapter.delivered == []               # NOT posted
    assert outbox.list_pending(tmp_path)         # NOT dropped — still pending


def test_delivery_holds_when_the_transport_fails_never_dropping(tmp_path):
    _record(tmp_path)

    class _FailingAdapter:
        def deliver(self, authorization, response):
            raise RuntimeError("transport down")

    counts = deliver_pending_action_results(
        tmp_path,
        get_run=lambda b, rid: {"status": "completed", "revision": 1},
        authorize=lambda e, r: object(),
        adapter=_FailingAdapter(),
    )
    assert counts["held"] == 1 and counts["delivered"] == 0
    assert outbox.list_pending(tmp_path)         # held, not dropped, will retry


def test_compose_summary_is_content_safe():
    ok = compose_summary({"status": "completed"})
    assert "Done" in ok
    fail = compose_summary({"status": "failed", "failed_phase": "deploy"})
    assert "didn't finish" in fail and "deploy" in fail
    assert "success" not in fail.lower()

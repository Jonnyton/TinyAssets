"""Tests for the async action-result outbox + governed follow-up delivery (Slice 3).

The delivery core's seams (get_run / authorize / adapter) are injected so the
outbox state machine, terminal detection, idempotency, fail-closed, content-safety,
concurrency (claim), pagination, and crash recovery are asserted without a live run
queue or Slack transport.
"""

from __future__ import annotations

import threading

import pytest

from tinyassets.action_result_delivery import (
    compose_summary,
    deliver_pending_action_results,
)
from tinyassets.storage import action_result_outbox as outbox


def _record(base, run_id="r1", **over):
    kw = dict(
        universe_id="u-tiny", workspace_id="T1", channel_id="C1", thread_ts="1700.1",
        app_binding_ref="bind-1", origin_event_id="Ev1",
    )
    kw.update(over)
    return outbox.record(base, run_id=run_id, **kw)


class _Adapter:
    def __init__(self, receipt="ok"):
        self.delivered: list[tuple] = []
        self._receipt = receipt

    def deliver(self, authorization, response, idempotency_key=None):
        self.delivered.append((authorization, response, idempotency_key))
        return self._receipt


def _deliver(base, run, adapter, authorize=lambda e, r: object(), **kw):
    return deliver_pending_action_results(
        base, get_run=lambda b, rid: run, authorize=authorize, adapter=adapter, **kw,
    )


def test_record_is_idempotent_and_content_free(tmp_path):
    assert _record(tmp_path) is True          # new
    assert _record(tmp_path) is False         # same run_id -> INSERT OR IGNORE
    pending = outbox.list_pending(tmp_path)
    assert [p["run_id"] for p in pending] == ["r1"]
    assert "credential" not in pending[0] and "body" not in pending[0]


def test_record_rejects_overlong_fields_content_free_guard(tmp_path):
    with pytest.raises(ValueError):
        _record(tmp_path, app_binding_ref="x" * (outbox.MAX_FIELD_LEN + 1))


def test_a_still_running_run_is_not_delivered(tmp_path):
    _record(tmp_path)
    adapter = _Adapter()
    counts = _deliver(tmp_path, {"status": "running"}, adapter)
    assert counts["skipped_running"] == 1 and counts["delivered"] == 0
    assert adapter.delivered == []
    assert outbox.list_pending(tmp_path)  # still pending


def test_a_completed_run_delivers_once_and_marks_delivered(tmp_path):
    _record(tmp_path)
    adapter = _Adapter()
    counts = _deliver(
        tmp_path,
        {"status": "completed", "revision": 4, "public_result_ref": "PR #999"},
        adapter,
    )
    assert counts["delivered"] == 1
    a, response, idem = adapter.delivered[0]
    assert "Done" in response and "PR #999" in response
    assert idem == "action-result:r1:4"          # idempotency key carries the revision
    assert outbox.list_pending(tmp_path) == []    # no longer pending

    # A second tick does NOT re-deliver (state guard: it is 'delivered', not pending).
    counts2 = _deliver(tmp_path, {"status": "completed", "revision": 4}, adapter)
    assert counts2["delivered"] == 0
    assert len(adapter.delivered) == 1


def test_a_failed_run_is_reported_honestly_never_as_success(tmp_path):
    _record(tmp_path)
    adapter = _Adapter()
    counts = _deliver(
        tmp_path, {"status": "failed", "revision": 2, "failed_phase": "build"}, adapter,
    )
    assert counts["delivered"] == 1
    _, response, _ = adapter.delivered[0]
    low = response.lower()
    assert "didn't finish" in low and "build" in low
    assert "done" not in low and "success" not in low


def test_cancelled_and_interrupted_are_delivered_not_stuck(tmp_path):
    for i, status in enumerate(("cancelled", "interrupted")):
        _record(tmp_path, run_id=f"r{i}")
        adapter = _Adapter()
        counts = _deliver(tmp_path, {"status": status, "revision": 1}, adapter)
        assert counts["delivered"] == 1, status
        _, response, _ = adapter.delivered[0]
        assert "didn't finish" in response.lower()
        assert "success" not in response.lower()


def test_delivery_holds_fail_closed_when_unauthorized(tmp_path):
    _record(tmp_path)
    adapter = _Adapter()
    counts = _deliver(
        tmp_path, {"status": "completed", "revision": 1}, adapter,
        authorize=lambda e, r: None,  # cannot authorize now
    )
    assert counts["held"] == 1 and counts["delivered"] == 0
    assert adapter.delivered == []                    # NOT posted
    assert [p["run_id"] for p in outbox.list_pending(tmp_path)] == ["r1"]  # released to pending


def test_delivery_holds_when_the_transport_raises(tmp_path):
    _record(tmp_path)

    class _FailingAdapter:
        def deliver(self, authorization, response, idempotency_key=None):
            raise RuntimeError("transport down")

    counts = _deliver(tmp_path, {"status": "completed", "revision": 1}, _FailingAdapter())
    assert counts["held"] == 1 and counts["delivered"] == 0
    assert outbox.list_pending(tmp_path)              # held (released), will retry


def test_delivery_holds_when_the_adapter_returns_no_receipt(tmp_path):
    # A non-throwing transport failure (falsy receipt) must NOT be marked delivered.
    _record(tmp_path)
    adapter = _Adapter(receipt=None)
    counts = _deliver(tmp_path, {"status": "completed", "revision": 1}, adapter)
    assert counts["held"] == 1 and counts["delivered"] == 0
    assert adapter.delivered and outbox.list_pending(tmp_path)  # attempted, then held


def test_concurrent_ticks_deliver_a_completed_run_at_most_once(tmp_path):
    # Two ticks race the same terminal entry: the atomic CLAIM lets exactly one post.
    for i in range(25):
        _record(tmp_path, run_id=f"r{i}")
    run = {"status": "completed", "revision": 1}
    adapters = [_Adapter(), _Adapter()]
    barrier = threading.Barrier(2)

    def tick(a):
        barrier.wait()
        deliver_pending_action_results(
            tmp_path, get_run=lambda b, rid: run,
            authorize=lambda e, r: object(), adapter=a,
        )

    threads = [threading.Thread(target=tick, args=(a,)) for a in adapters]
    for t in threads:
        t.start()
    for t in threads:
        t.join(5)

    total = len(adapters[0].delivered) + len(adapters[1].delivered)
    assert total == 25                                # each entry delivered exactly once
    assert outbox.list_pending(tmp_path) == []        # all consumed


def test_a_newer_completed_run_is_not_starved_by_older_running_entries(tmp_path):
    # Codex round-1: a backlog of still-running entries must not permanently hide a
    # newer terminal one. Page size 1 forces multi-page walking.
    for i in range(5):
        _record(tmp_path, run_id=f"running{i}")
    _record(tmp_path, run_id="done")

    def get_run(b, rid):
        return {"status": "completed", "revision": 1} if rid == "done" else {"status": "running"}

    adapter = _Adapter()
    counts = deliver_pending_action_results(
        tmp_path, get_run=get_run, authorize=lambda e, r: object(),
        adapter=adapter, page_limit=1,
    )
    assert counts["delivered"] == 1
    assert adapter.delivered[0][2] == "action-result:done:1"  # the newer terminal one


def test_a_crashed_ticks_claim_is_reclaimed_and_retried(tmp_path):
    _record(tmp_path)
    # Simulate a tick that claimed then died: manually claim, stamped in the past.
    assert outbox.claim(tmp_path, run_id="r1", now=1000.0) is not None
    assert outbox.list_pending(tmp_path) == []        # in_flight, not pending
    # A fresh tick reclaims the stale claim (now >> claimed_at + reclaim_after_s).
    adapter = _Adapter()
    counts = deliver_pending_action_results(
        tmp_path, get_run=lambda b, rid: {"status": "completed", "revision": 1},
        authorize=lambda e, r: object(), adapter=adapter,
        now=1000.0 + 10_000, reclaim_after_s=900.0,
    )
    assert counts["delivered"] == 1                   # reclaimed + delivered


def test_claim_returns_a_fencing_token_won_by_exactly_one_caller(tmp_path):
    _record(tmp_path)
    tok = outbox.claim(tmp_path, run_id="r1")
    assert isinstance(tok, str) and tok                   # first wins, gets a token
    assert outbox.claim(tmp_path, run_id="r1") is None    # already in_flight
    assert outbox.release(tmp_path, run_id="r1", claim_token=tok) is True
    assert outbox.claim(tmp_path, run_id="r1") is not None  # released -> claimable again


def test_a_stale_fencing_token_cannot_release_or_mark_a_newer_claim(tmp_path):
    # Codex hardening #1: worker A claims, is reclaimed, worker B re-claims; A's stale
    # token must NOT release or mark B's claim.
    _record(tmp_path)
    tok_a = outbox.claim(tmp_path, run_id="r1", now=1000.0)
    outbox.reclaim_stale(tmp_path, older_than_s=1.0, now=1_000_000)   # A's claim freed
    tok_b = outbox.claim(tmp_path, run_id="r1")                        # B re-claims
    assert tok_b and tok_b != tok_a
    # A's stale token is powerless against B's claim.
    assert outbox.release(tmp_path, run_id="r1", claim_token=tok_a) is False
    assert outbox.mark_delivered(
        tmp_path, run_id="r1", terminal_revision=1, claim_token=tok_a,
    ) is False
    # B's token works.
    assert outbox.mark_delivered(
        tmp_path, run_id="r1", terminal_revision=1, claim_token=tok_b,
    ) is True


def test_an_existing_db_missing_the_new_columns_is_migrated(tmp_path):
    # Codex hardening #3: a DB created with the ORIGINAL schema (no claimed_at/claim_token)
    # must migrate, not raise "no such column".
    import sqlite3

    from tinyassets.storage import db_path

    conn = sqlite3.connect(db_path(tmp_path))
    conn.executescript(
        """
        CREATE TABLE action_result_outbox (
            run_id TEXT PRIMARY KEY, universe_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
            channel_id TEXT NOT NULL, thread_ts TEXT NOT NULL, app_binding_ref TEXT NOT NULL,
            origin_event_id TEXT NOT NULL, created_at REAL NOT NULL, state TEXT NOT NULL,
            delivered_at REAL, terminal_revision INTEGER
        );
        INSERT INTO action_result_outbox VALUES
            ('r1','u','T','C','1700.1','b','E',1.0,'pending',NULL,NULL);
        """
    )
    conn.commit()
    conn.close()
    # claim() touches claim_token/claimed_at -> would raise without the migration.
    assert outbox.claim(tmp_path, run_id="r1") is not None


def test_a_legacy_db_with_the_old_state_check_is_rebuilt_to_accept_in_flight(tmp_path):
    # Codex re-review: a DB whose table carries the ORIGINAL state CHECK (no
    # 'in_flight') must be REBUILT, not just column-migrated — writing the 'in_flight'
    # claim state under the old CHECK raises "CHECK constraint failed". The prior
    # migration test omitted the CHECK, so it was self-confirming; this one includes
    # the exact predecessor constraint.
    import sqlite3

    from tinyassets.storage import db_path

    conn = sqlite3.connect(db_path(tmp_path))
    conn.executescript(
        """
        CREATE TABLE action_result_outbox (
            run_id TEXT PRIMARY KEY, universe_id TEXT NOT NULL, workspace_id TEXT NOT NULL,
            channel_id TEXT NOT NULL, thread_ts TEXT NOT NULL, app_binding_ref TEXT NOT NULL,
            origin_event_id TEXT NOT NULL, created_at REAL NOT NULL,
            state TEXT NOT NULL
                CHECK (state IN ('pending','delivered','failed_final')),
            delivered_at REAL, terminal_revision INTEGER
        );
        INSERT INTO action_result_outbox VALUES
            ('r1','u','T','C','1700.1','b','E',1.0,'pending',NULL,NULL);
        """
    )
    conn.commit()
    conn.close()
    # claim() writes state='in_flight' — impossible under the old CHECK unless the
    # table was rebuilt. Also assert the pre-existing 'pending' row was preserved.
    tok = outbox.claim(tmp_path, run_id="r1")
    assert tok is not None
    assert outbox.mark_delivered(
        tmp_path, run_id="r1", terminal_revision=1, claim_token=tok,
    ) is True


def test_compose_summary_is_content_safe_against_adversarial_fields():
    # A completed ref that is not a TRUSTED STRUCTURED HANDLE is dropped, not
    # interpolated. A markerless credential has NO secret marker to catch, so a
    # denylist would have leaked it — the allowlist drops it anyway.
    leaky = compose_summary({
        "status": "completed",
        "public_result_ref": "internal-node-42 token=xoxb-super-secret",
    })
    assert "Done" in leaky and "xoxb" not in leaky and "token" not in leaky
    # An off-allowlist host is dropped even though it "looks like" a clean URL
    # (Codex re-review probe: https://x.io/AKIA…).
    off_host = compose_summary({
        "status": "completed", "public_result_ref": "https://x.io/AKIAIOSFODNN7EXAMPLE",
    })
    assert "AKIA" not in off_host and "x.io" not in off_host
    # A github URL carrying a query string is dropped — a ?token=… cannot ride along.
    with_query = compose_summary({
        "status": "completed",
        "public_result_ref": "https://github.com/o/r/pull/7?token=xoxb-secret",
    })
    assert "xoxb" not in with_query and "github.com" not in with_query
    # The trusted structured handles ARE kept.
    assert "https://github.com/octocat/hello/pull/7" in compose_summary({
        "status": "completed",
        "public_result_ref": "https://github.com/octocat/hello/pull/7",
    })
    assert "PR #999" in compose_summary(
        {"status": "completed", "public_result_ref": "PR #999"}
    )
    # A phase outside the application-owned enum is dropped — including a markerless
    # credential in the phase field (Codex re-review probe: failed_phase="AKIA…").
    for leaky_phase in ("node_42 token=xoxb-secret leaking", "AKIAIOSFODNN7EXAMPLE"):
        out = compose_summary({"status": "failed", "failed_phase": leaky_phase})
        assert "didn't finish" in out and "xoxb" not in out and "AKIA" not in out
        assert out.endswith("say the word and I'll try it again.")
    # A known enum phase is kept.
    assert "deploy" in compose_summary({"status": "failed", "failed_phase": "deploy"})
    assert "build" in compose_summary({"status": "failed", "failed_phase": "build"})

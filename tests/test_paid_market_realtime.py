from __future__ import annotations

import dataclasses

import pytest

from tinyassets.payments.market_realtime import (
    AuthorizationError,
    FreshSnapshotRequired,
    MarketRealtimeAdapter,
    RealtimeBounds,
    RealtimeEnvelope,
    RealtimeReconciler,
    SnapshotPage,
)
from tinyassets.payments.market_workflow import (
    Applied,
    CancelRequestCommand,
    InMemoryMarketRequestStore,
    MarketWorkflow,
    OpenBiddingCommand,
    SubmitRequestCommand,
    VerifiedWorkflowAuthority,
)


def _authority(subject_id: str = "buyer"):
    return VerifiedWorkflowAuthority(subject_id=subject_id, tenant_id="tenant-a")


def _submission(*, key: str = "request", capability: str = "cap:a"):
    return SubmitRequestCommand(
        idempotency_key=key,
        authority=_authority(),
        requester_user_id="buyer",
        capability_digest=capability,
        payload_sha256="f" * 64,
        budget_micros=10_000,
        spend_cap_micros=10_000,
        bid_window_ends_at=2_000_000_000,
        deadline=2_000_003_600,
        acceptance_policy="machine_gate_only:v1",
        settlement_policy_version="spot:v1",
        visibility="paid",
        fanout_limit=2,
    )


def _open(workflow: MarketWorkflow, *, key: str = "request", capability: str = "cap:a"):
    submitted = workflow.submit(_submission(key=key, capability=capability))
    assert isinstance(submitted, Applied)
    opened = workflow.open_bidding(
        OpenBiddingCommand(
            idempotency_key=f"{key}:open",
            request_id=submitted.request.request_id,
            expected_version=1,
            authority=_authority(),
        )
    )
    assert isinstance(opened, Applied)
    return opened.request


def _envelope(
    event_id: str,
    request_id: str,
    version: int,
    cursor: int,
    shard: str = "cap:a",
):
    return RealtimeEnvelope(
        event_id=event_id,
        shard_cursor=cursor,
        request_id=request_id,
        request_version=version,
        capability_digest=shard,
        visibility="paid",
        fanout_limit=1,
        bid_window_ends_at=2_000_000_000,
        deadline=2_000_003_600,
    )


def test_open_bidding_appends_outbox_in_same_commit_then_announces_minimal_envelope():
    store = InMemoryMarketRequestStore()

    class Publisher:
        def __init__(self):
            self.messages = []

        def publish(self, shard, envelope):
            request = store.get(envelope.request_id)
            assert request is not None and request.state == "bidding"
            assert store.outbox(shard)[-1].event_id == envelope.event_id
            self.messages.append((shard, envelope))

    publisher = Publisher()
    workflow = MarketWorkflow(
        store,
        realtime_bus=MarketRealtimeAdapter(publisher),
    )
    request = _open(workflow)

    assert len(store.history(request.request_id)) == 2
    assert len(store.outbox("cap:a")) == 1
    assert len(publisher.messages) == 1
    shard, envelope = publisher.messages[0]
    assert shard == "cap:a"
    assert envelope.request_id == request.request_id
    assert set(dataclasses.asdict(envelope)) == {
        "event_id",
        "shard_cursor",
        "request_id",
        "request_version",
        "capability_digest",
        "visibility",
        "fanout_limit",
        "bid_window_ends_at",
        "deadline",
    }


def test_notification_failure_leaves_durable_request_and_outbox_for_catchup():
    store = InMemoryMarketRequestStore()

    class FailedPublisher:
        def publish(self, shard, envelope):
            raise RuntimeError("notification unavailable")

    workflow = MarketWorkflow(
        store,
        realtime_bus=MarketRealtimeAdapter(FailedPublisher()),
    )
    submitted = workflow.submit(_submission())
    assert isinstance(submitted, Applied)
    with pytest.raises(RuntimeError, match="notification unavailable"):
        workflow.open_bidding(
            OpenBiddingCommand(
                idempotency_key="open",
                request_id=submitted.request.request_id,
                expected_version=1,
                authority=_authority(),
            )
        )
    assert store.get(submitted.request.request_id).state == "bidding"
    assert len(store.outbox("cap:a")) == 1


def test_cancellation_appends_and_announces_a_tombstone_invalidation():
    store = InMemoryMarketRequestStore()

    class Publisher:
        def __init__(self):
            self.messages = []

        def publish(self, shard, envelope):
            self.messages.append((shard, envelope))

    publisher = Publisher()
    workflow = MarketWorkflow(
        store,
        realtime_bus=MarketRealtimeAdapter(publisher),
    )
    request = _open(workflow)
    cancelled = workflow.cancel(
        CancelRequestCommand(
            idempotency_key="cancel",
            request_id=request.request_id,
            expected_version=2,
            authority=_authority(),
        )
    )

    assert isinstance(cancelled, Applied)
    assert cancelled.request.state == "cancelled"
    assert [event.request_version for event in store.outbox("cap:a")] == [2, 3]
    assert [message[1].request_version for message in publisher.messages] == [2, 3]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"page_size": 0, "max_retries": 1, "max_subscriptions": 1},
        {"page_size": 1, "max_retries": 0, "max_subscriptions": 1},
        {"page_size": 1, "max_retries": 1, "max_subscriptions": 0},
    ],
)
def test_realtime_bounds_must_be_positive(kwargs):
    with pytest.raises(ValueError, match="positive"):
        RealtimeBounds(**kwargs)


class FakeSource:
    def __init__(
        self,
        *,
        snapshot=(),
        watermarks=None,
        outbox=None,
        compacted=(),
        authorized=True,
        degraded=False,
    ):
        self.snapshot_rows = tuple(snapshot)
        self.watermarks = watermarks or {"cap:a": 0}
        self.events = outbox or {}
        self.compacted = set(compacted)
        self.authorized = authorized
        self.degraded = degraded
        self.calls = []

    def snapshot(self, *, principal_id, tenant_id, shards, page_size):
        self.calls.append(("snapshot", tuple(shards), page_size))
        if not self.authorized:
            raise AuthorizationError("capability eligibility required")
        return SnapshotPage(
            requests=self.snapshot_rows,
            watermarks=dict(self.watermarks),
            degraded=self.degraded,
        )

    def outbox_after(
        self,
        *,
        principal_id,
        tenant_id,
        shard,
        cursor,
        page_size,
    ):
        self.calls.append(("outbox_after", shard, cursor, page_size))
        if shard in self.compacted:
            raise FreshSnapshotRequired(shard)
        return tuple(
            event
            for event in self.events.get(shard, ())
            if event.shard_cursor > cursor
        )[:page_size]


def test_reconnect_merges_snapshot_catchup_and_buffered_frames_by_latest_version():
    source = FakeSource(
        snapshot=(("req-snapshot", 2),),
        watermarks={"cap:a": 4},
        outbox={
            "cap:a": (
                _envelope("event-5", "req-new", 1, 5),
                _envelope("event-6", "req-snapshot", 3, 6),
            )
        },
    )
    buffered = (
        _envelope("event-6", "req-snapshot", 3, 6),
        _envelope("event-old", "req-snapshot", 1, 2),
        _envelope("event-7", "req-new", 2, 7),
    )
    result = RealtimeReconciler(
        source,
        bounds=RealtimeBounds(page_size=20, max_retries=3, max_subscriptions=2),
    ).reconcile(
        principal_id="host",
        tenant_id="tenant-a",
        shards=("cap:a",),
        buffered_frames=buffered,
    )

    assert result.current_versions == (
        ("req-new", 2),
        ("req-snapshot", 3),
    )
    assert [(event.event_id, event.request_version) for event in result.events] == [
        ("event-7", 2),
        ("event-6", 3),
    ]
    assert source.calls == [
        ("snapshot", ("cap:a",), 20),
        ("outbox_after", "cap:a", 4, 20),
    ]


def test_compacted_watermark_requires_fresh_snapshot_and_unauthorized_fetch_leaks_nothing():
    compacted = FakeSource(compacted={"cap:a"})
    reconciler = RealtimeReconciler(
        compacted,
        bounds=RealtimeBounds(page_size=10, max_retries=2, max_subscriptions=1),
    )
    with pytest.raises(FreshSnapshotRequired, match="cap:a"):
        reconciler.reconcile(
            principal_id="host",
            tenant_id="tenant-a",
            shards=("cap:a",),
            buffered_frames=(),
        )

    unauthorized = FakeSource(authorized=False)
    with pytest.raises(AuthorizationError, match="eligibility"):
        RealtimeReconciler(
            unauthorized,
            bounds=RealtimeBounds(
                page_size=10,
                max_retries=2,
                max_subscriptions=1,
            ),
        ).reconcile(
            principal_id="intruder",
            tenant_id="tenant-a",
            shards=("cap:a",),
            buffered_frames=(),
        )
    assert unauthorized.calls == [("snapshot", ("cap:a",), 10)]


def test_backpressure_coalesces_latest_versions_fairly_and_reports_degraded():
    source = FakeSource(
        watermarks={"cap:a": 0, "cap:b": 0},
        outbox={
            "cap:a": tuple(
                _envelope(f"a-{version}", "req-a", version, version, "cap:a")
                for version in range(1, 8)
            ),
            "cap:b": (
                _envelope("b-1", "req-b", 1, 1, "cap:b"),
                _envelope("b-2", "req-c", 1, 2, "cap:b"),
            ),
        },
        degraded=True,
    )
    result = RealtimeReconciler(
        source,
        bounds=RealtimeBounds(page_size=3, max_retries=2, max_subscriptions=2),
    ).reconcile(
        principal_id="host",
        tenant_id="tenant-a",
        shards=("cap:a", "cap:b"),
        buffered_frames=(),
    )

    assert result.degraded is True
    assert result.current_versions == (
        ("req-a", 7),
        ("req-b", 1),
        ("req-c", 1),
    )
    assert {event.capability_digest for event in result.events} == {"cap:a", "cap:b"}
    assert [call[2] for call in source.calls if call[0] == "outbox_after"] == [
        0,
        3,
        6,
        0,
    ]


def test_retry_exhaustion_cannot_enter_live_tail_with_partial_state():
    source = FakeSource(
        watermarks={"cap:a": 0},
        outbox={
            "cap:a": tuple(
                _envelope(f"event-{version}", "req-a", version, version)
                for version in range(1, 11)
            )
        },
    )

    with pytest.raises(FreshSnapshotRequired, match="cap:a"):
        RealtimeReconciler(
            source,
            bounds=RealtimeBounds(
                page_size=3,
                max_retries=2,
                max_subscriptions=1,
            ),
        ).reconcile(
            principal_id="host",
            tenant_id="tenant-a",
            shards=("cap:a",),
            buffered_frames=(),
        )


def test_subscription_bound_prevents_unbounded_shard_fanout():
    with pytest.raises(ValueError, match="subscription"):
        RealtimeReconciler(
            FakeSource(),
            bounds=RealtimeBounds(
                page_size=10,
                max_retries=2,
                max_subscriptions=1,
            ),
        ).reconcile(
            principal_id="host",
            tenant_id="tenant-a",
            shards=("cap:a", "cap:b"),
            buffered_frames=(),
        )

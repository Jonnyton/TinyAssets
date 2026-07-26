"""Bounded Realtime invalidation and durable snapshot/cursor reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence

from tinyassets.payments.market_workflow import OutboxEvent


class AuthorizationError(PermissionError):
    """The principal is not currently eligible for the requested shard."""


class FreshSnapshotRequired(RuntimeError):
    """The durable watermark was compacted and incremental catch-up is unsafe."""

    def __init__(self, shard: str) -> None:
        super().__init__(f"fresh snapshot required for compacted shard {shard}")
        self.shard = shard


@dataclass(frozen=True)
class RealtimeBounds:
    page_size: int
    max_retries: int
    max_subscriptions: int

    def __post_init__(self) -> None:
        values = (self.page_size, self.max_retries, self.max_subscriptions)
        if any(
            not isinstance(value, int)
            or isinstance(value, bool)
            or value <= 0
            for value in values
        ):
            raise ValueError("Realtime bounds must be positive integers")


@dataclass(frozen=True)
class RealtimeEnvelope:
    event_id: str
    shard_cursor: int
    request_id: str
    request_version: int
    capability_digest: str
    visibility: str
    fanout_limit: int
    bid_window_ends_at: int
    deadline: int


@dataclass(frozen=True)
class SnapshotPage:
    requests: tuple[tuple[str, int], ...]
    watermarks: dict[str, int]
    degraded: bool = False


@dataclass(frozen=True)
class ReconcileResult:
    current_versions: tuple[tuple[str, int], ...]
    events: tuple[RealtimeEnvelope, ...]
    watermarks: tuple[tuple[str, int], ...]
    degraded: bool


class RealtimePublisher(Protocol):
    def publish(self, shard: str, envelope: RealtimeEnvelope) -> None:
        """Publish one post-commit at-least-once invalidation."""


class RealtimeSource(Protocol):
    def snapshot(
        self,
        *,
        principal_id: str,
        tenant_id: str,
        shards: Sequence[str],
        page_size: int,
    ) -> SnapshotPage:
        """Return one authorized repeatable-read snapshot and watermarks."""

    def outbox_after(
        self,
        *,
        principal_id: str,
        tenant_id: str,
        shard: str,
        cursor: int,
        page_size: int,
    ) -> tuple[RealtimeEnvelope, ...]:
        """Return bounded durable events; never poll the global inbox."""


class MarketRealtimeAdapter:
    """Translate committed outbox rows into privacy-minimal announcements."""

    def __init__(self, publisher: RealtimePublisher) -> None:
        self._publisher = publisher

    def announce(self, event: OutboxEvent) -> None:
        envelope = RealtimeEnvelope(
            event_id=event.event_id,
            shard_cursor=event.shard_cursor,
            request_id=event.request_id,
            request_version=event.request_version,
            capability_digest=event.capability_digest,
            visibility=event.visibility,
            fanout_limit=event.fanout_limit,
            bid_window_ends_at=event.bid_window_ends_at,
            deadline=event.deadline,
        )
        self._publisher.publish(event.capability_digest, envelope)


class RealtimeReconciler:
    """Perform snapshot/watermark catch-up before entering live-tail mode."""

    def __init__(self, source: RealtimeSource, *, bounds: RealtimeBounds) -> None:
        self._source = source
        self._bounds = bounds

    def reconcile(
        self,
        *,
        principal_id: str,
        tenant_id: str,
        shards: Sequence[str],
        buffered_frames: Sequence[RealtimeEnvelope],
    ) -> ReconcileResult:
        normalized_shards = tuple(dict.fromkeys(shards))
        if (
            not normalized_shards
            or len(normalized_shards) > self._bounds.max_subscriptions
        ):
            raise ValueError("subscription count exceeds the configured bound")

        snapshot = self._source.snapshot(
            principal_id=principal_id,
            tenant_id=tenant_id,
            shards=normalized_shards,
            page_size=self._bounds.page_size,
        )
        caught_up: list[RealtimeEnvelope] = []
        watermarks = dict(snapshot.watermarks)
        for shard in normalized_shards:
            if shard not in watermarks:
                raise FreshSnapshotRequired(shard)
            cursor = watermarks[shard]
            for _attempt in range(self._bounds.max_retries + 1):
                page = self._source.outbox_after(
                    principal_id=principal_id,
                    tenant_id=tenant_id,
                    shard=shard,
                    cursor=cursor,
                    page_size=self._bounds.page_size,
                )
                caught_up.extend(page)
                if not page:
                    break
                next_cursor = max(event.shard_cursor for event in page)
                if next_cursor <= cursor:
                    raise FreshSnapshotRequired(shard)
                cursor = next_cursor
                watermarks[shard] = cursor
                if len(page) < self._bounds.page_size:
                    break
            else:
                raise FreshSnapshotRequired(shard)

        deduplicated = _deduplicate_events((*caught_up, *buffered_frames))
        coalesced = _coalesce_latest(deduplicated)
        selected = _fair_bound(
            coalesced,
            shards=normalized_shards,
            limit=self._bounds.page_size,
        )
        current = dict(snapshot.requests)
        for event in coalesced:
            if event.request_version >= current.get(event.request_id, 0):
                current[event.request_id] = event.request_version
        effective: list[RealtimeEnvelope] = []
        for event in selected:
            if event.request_version < current.get(event.request_id, 0):
                continue
            effective.append(event)
        effective.sort(key=lambda event: (event.request_id, event.request_version))
        return ReconcileResult(
            current_versions=tuple(sorted(current.items())),
            events=tuple(effective),
            watermarks=tuple(sorted(watermarks.items())),
            degraded=(
                snapshot.degraded
                or len(coalesced) > self._bounds.page_size
            ),
        )


def _deduplicate_events(
    events: Sequence[RealtimeEnvelope],
) -> tuple[RealtimeEnvelope, ...]:
    by_id: dict[str, RealtimeEnvelope] = {}
    for event in events:
        prior = by_id.get(event.event_id)
        if prior is None or (
            event.request_version,
            event.shard_cursor,
        ) > (
            prior.request_version,
            prior.shard_cursor,
        ):
            by_id[event.event_id] = event
    return tuple(by_id.values())


def _coalesce_latest(
    events: Sequence[RealtimeEnvelope],
) -> tuple[RealtimeEnvelope, ...]:
    by_request: dict[str, RealtimeEnvelope] = {}
    for event in events:
        prior = by_request.get(event.request_id)
        if prior is None or (
            event.request_version,
            event.shard_cursor,
            event.event_id,
        ) > (
            prior.request_version,
            prior.shard_cursor,
            prior.event_id,
        ):
            by_request[event.request_id] = event
    return tuple(by_request.values())


def _fair_bound(
    events: Sequence[RealtimeEnvelope],
    *,
    shards: Sequence[str],
    limit: int,
) -> tuple[RealtimeEnvelope, ...]:
    queues = {
        shard: sorted(
            (
                event
                for event in events
                if event.capability_digest == shard
            ),
            key=lambda event: (event.shard_cursor, event.event_id),
        )
        for shard in shards
    }
    selected: list[RealtimeEnvelope] = []
    while len(selected) < limit and any(queues.values()):
        for shard in shards:
            if queues[shard] and len(selected) < limit:
                selected.append(queues[shard].pop(0))
    return tuple(selected)

"""Typed observations over stored run events, never execution authority."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, TypedDict

from tinyassets.providers.execution_receipt import normalize_execution_receipt

ACTIVITY_EVIDENCE = (
    "Stored node events are local observations, not provider acknowledgments or "
    "first-byte evidence. Local start precedes concurrency/provider admission; "
    "local elapsed time is not provider execution time. A returned value may "
    "subsequently fail output validation. Returned-call metadata is tagged with "
    "its own step/time and may precede a later start or failure. Local start "
    "counts are not provider attempt counts. When present, execution is metadata "
    "on the stored returned call: model_status=reported means the model identifier "
    "was reported; model_status=unknown means it was not reported. Neither status "
    "records request receipt or admission, nor establishes validated output. "
    "Legacy provider labels do not identify the actual answering model. Null "
    "means unavailable, not evidence that the provider never started or replied. "
    "These events do not establish exact subprocess stop or cancellation."
)
_TERMINAL_EVENTS = frozenset({"ran", "failed", "cancelled"})
_MACHINE_LABEL = re.compile(r"[A-Za-z][A-Za-z0-9_.:-]{0,127}\Z")
_MAX_EXACT_INTEGER = 2**53 - 1


class NodeActivity(TypedDict):
    node_id: str
    status: str
    latest_step_index: int | None
    latest_event_status: str | None
    latest_event_at: float | None
    local_started_at: float | None
    local_finished_at: float | None
    local_elapsed_seconds: float | None
    start_events_observed: int
    return_observed_at: float | None
    return_step_index: int | None
    execution: dict[str, str] | None
    legacy_provider_label: str | None
    provider_latency_ms: float | None
    provider_attempts: int | None
    provider_degraded: bool | None
    failure_reason: str | None
    failure_type: str | None


def _label(value: object, maximum: int) -> str | None:
    if not isinstance(value, str) or not 0 < len(value) <= maximum:
        return None
    if not value.isprintable() or value != value.strip():
        return None
    return value


def _number(value: object) -> float | None:
    # JSON booleans and numeric strings are not observed measurements.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        result = float(value)
    except (OverflowError, ValueError):
        return None
    return result if math.isfinite(result) and result >= 0 else None


def _integer(value: object) -> int | None:
    if type(value) is int and 0 <= value <= _MAX_EXACT_INTEGER:
        return value
    return None


def _code(value: object) -> str | None:
    value = _label(value, 128)
    return value if value is not None and _MACHINE_LABEL.fullmatch(value) else None


def _empty(node_id: str, status: str) -> NodeActivity:
    return {
        "node_id": node_id,
        "status": status,
        "latest_step_index": None,
        "latest_event_status": None,
        "latest_event_at": None,
        "local_started_at": None,
        "local_finished_at": None,
        "local_elapsed_seconds": None,
        "start_events_observed": 0,
        "return_observed_at": None,
        "return_step_index": None,
        "execution": None,
        "legacy_provider_label": None,
        "provider_latency_ms": None,
        "provider_attempts": None,
        "provider_degraded": None,
        "failure_reason": None,
        "failure_type": None,
    }


def build_node_activity(
    events: Sequence[Mapping[str, Any]],
    node_statuses: Sequence[Mapping[str, Any]],
) -> list[NodeActivity]:
    """Fold ascending stored events into a metadata-only per-node projection.

    ``node_statuses`` is the existing snapshot's authoritative ordered catalog,
    including observed nodes absent from the current definition. Preserve its
    status even when an outer run failure has corrected a still-running row.
    Neither input is mutated. Node identifiers retain their existing identity;
    all newly exposed detail labels are bounded independently of graph size.
    """
    activity: dict[str, NodeActivity] = {}
    for node in node_statuses:
        node_id, status = node.get("node_id"), node.get("status")
        if isinstance(node_id, str) and node_id and node_id != "__system__":
            activity[node_id] = _empty(node_id, _label(status, 80) or "unknown")

    for event in events:
        node_id = event.get("node_id")
        if not isinstance(node_id, str) or node_id not in activity:
            continue
        row = activity[node_id]
        status = _label(event.get("status"), 80)
        started = _number(event.get("started_at"))
        finished = _number(event.get("finished_at"))
        row["latest_step_index"] = _integer(event.get("step_index"))
        row["latest_event_status"] = status
        row["latest_event_at"] = finished if finished is not None else started
        detail = event.get("detail")
        detail = detail if isinstance(detail, dict) else {}

        if status in {"pending", "running"}:
            row["local_started_at"] = started if status == "running" else None
            row["local_finished_at"] = None
            row["local_elapsed_seconds"] = None
            row["failure_reason"] = None
            row["failure_type"] = None
            if status == "running":
                row["start_events_observed"] += 1

        if status in _TERMINAL_EVENTS:
            row["local_finished_at"] = finished
            local_start = row["local_started_at"]
            row["local_elapsed_seconds"] = (
                _number(finished - local_start)
                if finished is not None and local_start is not None else None
            )
            row["failure_reason"] = _code(detail.get("reason")) if status == "failed" else None
            row["failure_type"] = (
                _code(detail.get("error_type")) or _code(detail.get("error_kind"))
            ) if status == "failed" else None

        if status == "ran":
            # A later attempt without a receipt must not inherit an old model.
            # A later *start/failure* does retain this separately tagged return.
            row["return_observed_at"] = finished
            row["return_step_index"] = row["latest_step_index"]
            row["execution"] = normalize_execution_receipt(detail.get("execution"))
            legacy = _label(detail.get("provider_served"), 400)
            row["legacy_provider_label"] = legacy if legacy != "unknown" else None
            row["provider_latency_ms"] = _number(detail.get("provider_latency_ms"))
            row["provider_attempts"] = _integer(detail.get("provider_attempts"))
            degraded = detail.get("provider_degraded")
            row["provider_degraded"] = degraded if isinstance(degraded, bool) else None

    return list(activity.values())

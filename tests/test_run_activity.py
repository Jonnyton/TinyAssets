"""Tests for the pure run-activity projection (`expose-owned-run-activity`).

Scope: `tinyassets.api.run_activity.build_node_activity` only — a pure fold over
stored run events plus the existing node-status catalog. Snapshot composition,
ACL/selector enforcement and client adapters are covered by the run-read tests;
nothing here builds routing fixtures or touches storage.

The contract under test (proposal + design decisions 2-6 + delta spec):
local observation is never provider acknowledgment, returned-call evidence is
tagged with its own step/time and survives a later start or failure, unavailable
facts stay `None`, and no raw event detail is copied into the projection.
"""

from __future__ import annotations

import copy
import json
import math
import re

import pytest

from tinyassets.api.run_activity import ACTIVITY_EVIDENCE, build_node_activity

# The full published field set — a row is exactly these keys, no more, no less.
EXPECTED_FIELDS = frozenset({
    "node_id",
    "status",
    "latest_step_index",
    "latest_event_status",
    "latest_event_at",
    "local_started_at",
    "local_finished_at",
    "local_elapsed_seconds",
    "start_events_observed",
    "return_observed_at",
    "return_step_index",
    "execution",
    "legacy_provider_label",
    "provider_latency_ms",
    "provider_attempts",
    "provider_degraded",
    "failure_reason",
    "failure_type",
})

# Everything that must read "unknown" before any evidence is observed.
UNKNOWN_FIELDS = EXPECTED_FIELDS - {"node_id", "status", "start_events_observed"}


def event(node_id, status, step, started, finished=None, **detail):
    """One stored `run_events` row in producer shape (tinyassets/runs.py)."""
    return {
        "step_index": step,
        "node_id": node_id,
        "status": status,
        "started_at": started,
        "finished_at": finished,
        "detail": dict(detail),
    }


def statuses(*pairs):
    return [{"node_id": nid, "status": status} for nid, status in pairs]


def only(events, node_statuses):
    rows = build_node_activity(events, node_statuses)
    assert len(rows) == 1, rows
    return rows[0]


def reported(provider, model):
    return {"provider": provider, "model": model, "model_status": "reported"}


# ─────────────────────────────────────────────────────────────────────────────
# Caveat constant and row shape
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("phrase", [
    r"local",                       # local observation, not provider time
    r"acknowledg",                  # no provider acknowledgment
    r"first[- ]byte",               # no first-byte record
    r"subprocess",                  # no exact subprocess-stop proof
    r"validat",                     # returned does not mean validated
])
def test_activity_evidence_states_its_limits(phrase):
    """Decision 6: the caveat travels with the evidence, in the evidence."""
    assert isinstance(ACTIVITY_EVIDENCE, str)
    assert re.search(phrase, ACTIVITY_EVIDENCE, re.IGNORECASE), ACTIVITY_EVIDENCE
    # Bounded like every other added string; it is a constant, not a report.
    assert 0 < len(ACTIVITY_EVIDENCE) <= 2000


def test_row_is_exactly_the_published_fields_and_unknown_by_default():
    rows = build_node_activity([], statuses(("plan", "pending"), ("write", "pending")))

    assert [r["node_id"] for r in rows] == ["plan", "write"]
    for row in rows:
        assert set(row) == EXPECTED_FIELDS
        assert row["status"] == "pending"
        # Null means unavailable — never a fabricated zero (design decision 3).
        assert {f: row[f] for f in UNKNOWN_FIELDS} == dict.fromkeys(UNKNOWN_FIELDS, None)
        # ...except the start count, which is a real observation of zero starts.
        assert row["start_events_observed"] == 0


@pytest.mark.parametrize("node_id", [
    "__custom",            # user-named node that merely starts with underscores
    "__system__extra",     # not the exact reserved id
    "_private",
    "__system",
    "system__",
    "node.with:punctuation-1",
    "ノード",
    "x" * 500,             # identity is preserved exactly, never truncated
])
def test_only_the_exact_reserved_system_id_is_dropped(node_id):
    """Decision 2: exclude synthetic system rows, not underscore-ish names."""
    node_statuses = statuses((node_id, "ran"), ("__system__", "ran"))
    rows = build_node_activity([event(node_id, "ran", 3, 10.0, 11.0)], node_statuses)

    assert [r["node_id"] for r in rows] == [node_id]
    assert rows[0]["latest_event_status"] == "ran"


def test_synthetic_system_rows_are_ignored_and_never_leak_into_real_nodes():
    """`__system__` carries recursion/effect/provider telemetry, not node status."""
    node_statuses = statuses(("plan", "ran"), ("__system__", "effect"))
    events = [
        event("__system__", "recursion_limit_applied", 0, 1.0, 1.0, recursion_limit=25),
        event("plan", "running", 1, 10.0),
        event("plan", "ran", 2, 11.0, 11.5, provider_served="claude_cli"),
        # Effect rows are stamped `__system__` and carry the node id in detail.
        {"step_index": 3, "node_id": "__system__", "status": "effect",
         "started_at": 12.0, "finished_at": 12.4,
         "detail": {"node_id": "plan", "sink": "github"}},
        # An event for a node absent from the catalog creates no row.
        event("ghost", "ran", 4, 13.0, 13.1),
    ]

    rows = build_node_activity(events, node_statuses)

    assert [r["node_id"] for r in rows] == ["plan"]
    assert rows[0]["latest_step_index"] == 2
    assert rows[0]["latest_event_status"] == "ran"
    assert rows[0]["legacy_provider_label"] == "claude_cli"


def test_neither_input_is_mutated():
    node_statuses = statuses(("plan", "failed"), ("__system__", "effect"))
    events = [
        event("plan", "running", 1, 10.0),
        event("plan", "ran", 2, 11.0, 12.0,
              execution=reported("claude_cli", "claude-opus-5"),
              provider_served="claude_cli", provider_latency_ms=940.5),
        event("plan", "failed", 3, 13.0, 13.0, reason="output_validation_failed"),
    ]
    before_events = copy.deepcopy(events)
    before_statuses = copy.deepcopy(node_statuses)

    build_node_activity(events, node_statuses)

    assert events == before_events
    assert node_statuses == before_statuses


# ─────────────────────────────────────────────────────────────────────────────
# Local start / terminal / elapsed semantics (design decision 5)
# ─────────────────────────────────────────────────────────────────────────────


def test_running_records_the_local_start_and_counts_starts_not_attempts():
    node_statuses = statuses(("plan", "running"))
    events = [
        event("plan", "running", 1, 100.0),
        event("plan", "running", 2, 200.0),
        event("plan", "running", 3, 300.0),
    ]

    row = only(events, node_statuses)

    assert row["start_events_observed"] == 3
    assert row["local_started_at"] == 300.0
    # No return observed: everything about the provider stays unknown.
    assert row["local_finished_at"] is None
    assert row["local_elapsed_seconds"] is None
    assert row["return_observed_at"] is None
    assert row["execution"] is None
    assert row["provider_attempts"] is None  # start count is not an attempt count


def test_a_new_start_clears_stale_terminal_and_failure_labels():
    node_statuses = statuses(("plan", "running"))
    events = [
        event("plan", "running", 1, 100.0),
        event("plan", "failed", 2, 110.0, 110.0,
              reason="provider_timeout", error_type="TimeoutError"),
        event("plan", "running", 3, 200.0),
    ]

    row = only(events, node_statuses)

    assert row["local_started_at"] == 200.0
    assert row["local_finished_at"] is None
    assert row["local_elapsed_seconds"] is None
    assert row["failure_reason"] is None
    assert row["failure_type"] is None
    assert row["start_events_observed"] == 2


@pytest.mark.parametrize("started,finished,expected_finished,expected_elapsed", [
    (100.0, 112.5, 112.5, 12.5),        # ordinary ordered pair
    (100.0, 100.0, 100.0, 0.0),         # a same-instant stamp is still valid
    (100.0, None, None, None),          # no terminal stamp -> unknown, not 0
    (100.0, 99.0, 99.0, None),          # negative span is never reported
    (100.0, float("inf"), None, None),  # nonfinite is unknown, not fabricated
    (100.0, float("nan"), None, None),
    (100.0, "112.5", None, None),       # a string is not an observed stamp
    (None, 112.5, 112.5, None),         # no observed start -> no pair
])
@pytest.mark.parametrize("terminal", ["ran", "failed", "cancelled"])
def test_terminal_timing_needs_a_valid_ordered_pair(
    started, finished, expected_finished, expected_elapsed, terminal,
):
    node_statuses = statuses(("plan", terminal))
    events = []
    if started is not None:
        events.append(event("plan", "running", 1, started))
    events.append(event("plan", terminal, 2, 500.0, finished))

    row = only(events, node_statuses)

    assert row["local_finished_at"] == expected_finished
    assert row["local_elapsed_seconds"] == expected_elapsed
    if expected_elapsed is not None:
        assert not isinstance(row["local_elapsed_seconds"], bool)
        assert math.isfinite(row["local_elapsed_seconds"])


def test_repeated_starts_report_the_latest_attempt_not_the_total_span():
    """Decision 5: a loop must not read as one long call."""
    node_statuses = statuses(("draft", "ran"))
    events = [
        event("draft", "running", 1, 100.0),
        event("draft", "ran", 2, 110.0, 110.0),
        event("draft", "running", 3, 200.0),
        event("draft", "ran", 4, 205.0, 205.0),
    ]

    row = only(events, node_statuses)

    assert row["local_started_at"] == 200.0
    assert row["local_finished_at"] == 205.0
    assert row["local_elapsed_seconds"] == pytest.approx(5.0)
    assert row["start_events_observed"] == 2


def test_latest_event_describes_the_last_row_while_status_stays_authoritative():
    """The outer run correction (`failed`) wins over the last event (`running`)."""
    node_statuses = statuses(("plan", "failed"))
    events = [event("plan", "pending", 7, 9.0), event("plan", "running", 8, 10.0)]

    row = only(events, node_statuses)

    assert row["status"] == "failed"           # supplied snapshot status
    assert row["latest_event_status"] == "running"
    assert row["latest_step_index"] == 8
    assert row["latest_event_at"] == 10.0      # running rows have no finish stamp


def test_legacy_rows_without_step_or_finish_stamps_stay_unknown():
    """Historical events carry less evidence; return honest nulls (risk row 4)."""
    node_statuses = statuses(("plan", "ran"))
    events = [
        {"node_id": "plan", "status": "running", "started_at": 100.0},
        {"node_id": "plan", "status": "ran", "started_at": 101.0, "detail": None},
    ]

    row = only(events, node_statuses)

    assert row["latest_step_index"] is None
    assert row["return_step_index"] is None
    assert row["return_observed_at"] is None
    assert row["local_finished_at"] is None
    assert row["local_elapsed_seconds"] is None
    assert row["latest_event_status"] == "ran"
    assert row["start_events_observed"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Returned-call evidence (design decisions 4-5, delta scenarios 1 and 3)
# ─────────────────────────────────────────────────────────────────────────────


def test_ran_records_returned_call_evidence_with_its_own_step_and_time():
    node_statuses = statuses(("plan", "ran"))
    events = [
        event("plan", "running", 1, 100.0),
        event("plan", "ran", 2, 101.0, 112.0,
              execution=reported("claude_cli", "claude-opus-5"),
              provider_served="claude_cli", provider_latency_ms=10_431.75,
              provider_attempts=1, provider_degraded=False),
    ]

    row = only(events, node_statuses)

    assert row["return_step_index"] == 2
    assert row["return_observed_at"] == 112.0
    assert row["execution"] == reported("claude_cli", "claude-opus-5")
    assert row["legacy_provider_label"] == "claude_cli"
    assert row["provider_latency_ms"] == pytest.approx(10_431.75)
    assert row["provider_attempts"] == 1
    assert row["provider_degraded"] is False


def test_returned_evidence_survives_a_later_start_without_moving_to_it():
    """Old receipt, new attempt: the receipt keeps its own step and time."""
    node_statuses = statuses(("plan", "running"))
    events = [
        event("plan", "running", 1, 100.0),
        event("plan", "ran", 2, 101.0, 112.0,
              execution=reported("claude_cli", "claude-opus-5"),
              provider_served="claude_cli", provider_latency_ms=11_000.0),
        event("plan", "running", 3, 300.0),
    ]

    row = only(events, node_statuses)

    assert row["return_step_index"] == 2
    assert row["return_observed_at"] == 112.0
    assert row["execution"] == reported("claude_cli", "claude-opus-5")
    assert row["latest_step_index"] == 3          # the new start is the latest row
    assert row["local_started_at"] == 300.0
    assert row["local_finished_at"] is None       # not attributed to the new start
    assert row["local_elapsed_seconds"] is None


@pytest.mark.parametrize("receipt_detail", [
    {},                                                  # absent
    {"execution": None},
    {"execution": "claude_cli"},                         # malformed
    {"execution": {"provider": "claude_cli"}},           # incomplete
])
def test_a_new_return_replaces_the_old_receipt_even_when_it_has_none(receipt_detail):
    """A later attempt must not inherit the previous attempt's model."""
    node_statuses = statuses(("plan", "ran"))
    events = [
        event("plan", "running", 1, 100.0),
        event("plan", "ran", 2, 101.0, 112.0,
              execution=reported("claude_cli", "claude-opus-5")),
        event("plan", "running", 3, 300.0),
        event("plan", "ran", 4, 301.0, 305.0, **receipt_detail),
    ]

    row = only(events, node_statuses)

    assert row["execution"] is None
    # The return itself is still observed — step/time update regardless.
    assert row["return_step_index"] == 4
    assert row["return_observed_at"] == 305.0
    assert "claude-opus-5" not in json.dumps(row, default=repr)


def test_return_then_output_validation_failure_keeps_both_facts():
    """Delta scenario: returned evidence retained, node status still failed."""
    node_statuses = statuses(("plan", "failed"))
    events = [
        event("plan", "running", 1, 100.0),
        event("plan", "ran", 2, 101.0, 112.0,
              execution=reported("claude_cli", "claude-opus-5"),
              provider_served="claude_cli", provider_attempts=1),
        event("plan", "failed", 3, 112.5, 112.5,
              reason="output_validation_failed", error_type="ValidationError",
              error="Traceback (most recent call last): field 'title' missing"),
    ]

    row = only(events, node_statuses)

    assert row["status"] == "failed"
    assert row["latest_event_status"] == "failed"
    assert row["return_step_index"] == 2
    assert row["return_observed_at"] == 112.0
    assert row["execution"] == reported("claude_cli", "claude-opus-5")
    assert row["provider_attempts"] == 1
    assert row["failure_reason"] == "output_validation_failed"
    assert row["failure_type"] == "ValidationError"
    assert "Traceback" not in json.dumps(row, default=repr)


def test_local_start_without_a_return_leaves_provider_evidence_unknown():
    """Delta scenario: never infer silence, non-start or load from a timeout."""
    node_statuses = statuses(("plan", "failed"))
    events = [
        event("plan", "running", 1, 100.0),
        event("plan", "failed", 2, 460.0, 460.0,
              reason="provider_timeout", error_type="TimeoutError",
              message="claude -p produced no output after 360s"),
    ]

    row = only(events, node_statuses)

    assert row["local_started_at"] == 100.0
    assert row["start_events_observed"] == 1
    assert row["return_observed_at"] is None
    assert row["return_step_index"] is None
    assert row["execution"] is None
    assert row["legacy_provider_label"] is None
    assert row["provider_latency_ms"] is None
    assert row["provider_attempts"] is None
    assert row["provider_degraded"] is None
    assert row["failure_reason"] == "provider_timeout"
    assert row["failure_type"] == "TimeoutError"


# ─────────────────────────────────────────────────────────────────────────────
# Strict typed metadata (design decisions 3-4)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value,expected", [
    (reported("claude_cli", "claude-opus-5"), reported("claude_cli", "claude-opus-5")),
    # Provider answered but reported no model: unknown stays unknown.
    ({"provider": "claude_cli", "model": "", "model_status": "unknown"},
     {"provider": "claude_cli", "model": "", "model_status": "unknown"}),
    # Extra keys are not a receipt — never a partial copy of a nested object.
    ({**reported("claude_cli", "claude-opus-5"), "prompt": "hi"}, None),
    ({"provider": "claude_cli", "model": "claude-opus-5"}, None),
    # Inconsistent status/model pairing is rejected outright.
    ({"provider": "claude_cli", "model": "claude-opus-5", "model_status": "unknown"}, None),
    ({"provider": "", "model": "", "model_status": "unknown"}, None),
    ({"provider": "claude_cli", "model": "x" * 500, "model_status": "reported"}, None),
    (["claude_cli", "claude-opus-5"], None),
    ("claude_cli", None),
    (None, None),
])
def test_execution_is_the_strict_three_label_projection(value, expected):
    row = only(
        [event("plan", "ran", 2, 101.0, 112.0, execution=value)],
        statuses(("plan", "ran")),
    )

    assert row["execution"] == expected
    if expected is not None:
        assert set(row["execution"]) == {"provider", "model", "model_status"}


def test_execution_is_newly_constructed_not_the_stored_object():
    stored = reported("claude_cli", "claude-opus-5")
    events = [event("plan", "ran", 2, 101.0, 112.0, execution=stored)]

    row = only(events, statuses(("plan", "ran")))

    assert row["execution"] == stored
    assert row["execution"] is not stored
    assert row["execution"] is not events[0]["detail"]["execution"]


def test_legacy_provider_model_is_never_promoted_to_an_actual_model():
    """Decision 4: a configuration hint is not a reported answering model."""
    node_statuses = statuses(("plan", "ran"))
    events = [event(
        "plan", "ran", 2, 101.0, 112.0,
        provider_served="claude_cli",
        provider_model="claude-sonnet-4-5-CONFIG",   # legacy config metadata
        execution={"provider": "claude_cli", "model": "", "model_status": "unknown"},
    )]

    row = only(events, node_statuses)

    assert row["execution"] == {
        "provider": "claude_cli", "model": "", "model_status": "unknown",
    }
    assert row["legacy_provider_label"] == "claude_cli"
    assert "claude-sonnet-4-5-CONFIG" not in json.dumps(row, default=repr)


@pytest.mark.parametrize("served,expected", [
    ("claude_cli", "claude_cli"),
    ("codex_cli", "codex_cli"),
    ("mock", "mock"),
    ("unknown", None),          # the producer's placeholder is not evidence
    ("", None),
    (None, None),
    (123, None),
    ("claude\ncli", None),      # unprintable control characters are not labels
    ("p" * 5000, None),         # oversized is omitted, never truncated
])
def test_legacy_provider_label_is_bounded_and_omitted_when_invalid(served, expected):
    row = only(
        [event("plan", "ran", 2, 101.0, 112.0, provider_served=served)],
        statuses(("plan", "ran")),
    )

    assert row["legacy_provider_label"] == expected
    if expected is None and isinstance(served, str) and len(served) > 100:
        # Not truncated into a plausible-looking provider name.
        assert "p" * 100 not in json.dumps(row, default=repr)


@pytest.mark.parametrize("value,expected", [
    (10_431.75, 10_431.75),     # real observed latency
    (0, 0.0),
    (1, 1.0),
    (340, 340.0),
    (-1.0, None),
    (float("inf"), None),
    (float("nan"), None),
    ("340", None),
    (True, None),               # a bool is not a measurement
    (False, None),
    (None, None),
    ({"ms": 340}, None),
])
def test_provider_latency_ms_is_finite_nonnegative_and_never_a_bool(value, expected):
    row = only(
        [event("plan", "ran", 2, 101.0, 112.0, provider_latency_ms=value)],
        statuses(("plan", "ran")),
    )

    assert row["provider_latency_ms"] == expected
    if expected is not None:
        assert not isinstance(row["provider_latency_ms"], bool)
        assert math.isfinite(row["provider_latency_ms"])


@pytest.mark.parametrize("value,expected", [
    (0, 0),
    (1, 1),
    (2, 2),
    (2**53 - 1, 2**53 - 1),
    (2**53, None),              # beyond exact integer range
    (-1, None),
    (1.0, None),
    ("2", None),
    (True, None),               # a bool is not a count
    (False, None),
    (None, None),
])
def test_provider_attempts_is_a_bounded_nonnegative_int(value, expected):
    row = only(
        [event("plan", "ran", 2, 101.0, 112.0, provider_attempts=value)],
        statuses(("plan", "ran")),
    )

    assert row["provider_attempts"] == expected
    if expected is not None:
        assert type(row["provider_attempts"]) is int


@pytest.mark.parametrize("value,expected", [
    (True, True),
    (False, False),
    ("true", None),
    (1, None),
    (0, None),
    (None, None),
])
def test_provider_degraded_is_a_bool_or_unknown(value, expected):
    row = only(
        [event("plan", "ran", 2, 101.0, 112.0, provider_degraded=value)],
        statuses(("plan", "ran")),
    )

    assert row["provider_degraded"] is expected


@pytest.mark.parametrize("detail,reason,ftype", [
    ({"reason": "provider_timeout", "error_type": "TimeoutError"},
     "provider_timeout", "TimeoutError"),
    ({"reason": "empty_response"}, "empty_response", None),
    ({"reason": "effect_failed", "error_kind": "far_side_error"},
     "effect_failed", "far_side_error"),
    # error_type wins over error_kind when both are present.
    ({"reason": "effect_failed", "error_type": "HTTPError",
      "error_kind": "far_side_error"}, "effect_failed", "HTTPError"),
    # Arbitrary exception text is not a machine label.
    ({"reason": "ValueError: field 'title' missing at line 3"}, None, None),
    ({"error_type": "connection refused by 10.0.0.4:443 after 3 tries"},
     None, None),
    ({"reason": "r" * 400}, None, None),          # oversized -> omitted
    ({"reason": ""}, None, None),
    ({"reason": None, "error_type": None}, None, None),
    ({"reason": {"code": "boom"}}, None, None),   # nested values never flatten
    ({}, None, None),
])
def test_failure_labels_are_short_machine_codes_only(detail, reason, ftype):
    row = only(
        [event("plan", "failed", 3, 112.5, 112.5, **detail)],
        statuses(("plan", "failed")),
    )

    assert row["failure_reason"] == reason
    assert row["failure_type"] == ftype
    for field in ("failure_reason", "failure_type"):
        if row[field] is not None:
            assert len(row[field]) <= 128
            assert " " not in row[field]
    # An omitted oversized label is not truncated into a plausible code.
    assert "r" * 100 not in json.dumps(row, default=repr)


# ─────────────────────────────────────────────────────────────────────────────
# Disclosure boundary and graph size (design decisions 2-3, risk rows 2-3)
# ─────────────────────────────────────────────────────────────────────────────


SENTINELS = {
    "prompt": "SENTINEL-PROMPT-a91f",
    "response": "SENTINEL-RESPONSE-b02c",
    "preview": "SENTINEL-PREVIEW-c13d",
    "output": "SENTINEL-OUTPUT-d24e",
    "code": "SENTINEL-CODE-e35f",
    "error": "SENTINEL-RAWERROR-f460",
    "message": "SENTINEL-MESSAGE-0571",
    "role": "SENTINEL-ROLE-1682",
    "api_key": "SENTINEL-CREDENTIAL-2793",
    "provider_chain": ["SENTINEL-CHAIN-38a4"],
    "provider": {"name": "SENTINEL-NESTED-49b5", "base_url": "http://sentinel"},
    "inputs": {"deep": {"deeper": ["SENTINEL-NESTED-5ac6"]}},
    "detail": {"echo": "SENTINEL-SELF-6bd7"},
}


def test_no_raw_event_detail_is_copied_into_the_projection():
    node_statuses = statuses(("plan", "ran"))
    events = [
        event("plan", "running", 1, 100.0, **SENTINELS),
        event("plan", "ran", 2, 101.0, 112.0,
              execution=reported("claude_cli", "claude-opus-5"),
              provider_served="claude_cli", provider_latency_ms=10_431.75,
              provider_attempts=1, provider_degraded=False, **SENTINELS),
    ]

    row = only(events, node_statuses)
    serialized = json.dumps(row, default=repr)

    for value in SENTINELS.values():
        for token in re.findall(r"SENTINEL-[A-Z]+-[0-9a-f]{4}", json.dumps(value)):
            assert token not in serialized, f"{token} leaked into {row}"
    assert set(row) == EXPECTED_FIELDS
    # The allowlisted metadata alongside the sentinels still came through.
    assert row["execution"] == reported("claude_cli", "claude-opus-5")
    assert row["provider_latency_ms"] == pytest.approx(10_431.75)
    # Only the newly normalized 3-field dict may be a nested value.
    for field, value in row.items():
        if field == "execution":
            continue
        assert not isinstance(value, (dict, list, tuple, set)), field


def test_large_graphs_get_no_new_count_limit():
    """Delta scenario: no node silently omitted for exceeding a diagnostic cap."""
    node_ids = [f"node_{i:03d}" for i in range(250)]
    node_statuses = statuses(*((nid, "ran") for nid in node_ids))
    events = []
    for step, nid in enumerate(node_ids):
        events.append(event(nid, "running", step * 2, 100.0 + step))
        events.append(event(nid, "ran", step * 2 + 1, 100.5 + step, 101.0 + step,
                            provider_served="claude_cli", provider_attempts=1))

    rows = build_node_activity(events, node_statuses)

    assert [r["node_id"] for r in rows] == node_ids
    assert len(rows) == 250
    for row in rows:
        assert set(row) == EXPECTED_FIELDS
        assert row["start_events_observed"] == 1
        assert row["local_elapsed_seconds"] == pytest.approx(1.0)
        assert row["legacy_provider_label"] == "claude_cli"


def test_mixed_graph_folds_each_node_independently():
    """A completed predecessor keeps its evidence when a later node fails."""
    node_statuses = statuses(
        ("research", "ran"), ("draft", "failed"), ("publish", "pending"),
    )
    events = [
        event("research", "running", 1, 100.0),
        event("research", "ran", 2, 100.5, 108.0,
              execution=reported("claude_cli", "claude-opus-5"),
              provider_served="claude_cli", provider_latency_ms=7_500.0,
              provider_attempts=1, provider_degraded=False),
        event("draft", "running", 3, 108.5),
        event("draft", "failed", 4, 480.0, 480.0,
              reason="provider_timeout", error_type="TimeoutError"),
    ]

    research, draft, publish = build_node_activity(events, node_statuses)

    assert research["status"] == "ran"
    assert research["execution"] == reported("claude_cli", "claude-opus-5")
    assert research["local_elapsed_seconds"] == pytest.approx(8.0)
    assert research["failure_reason"] is None

    assert draft["status"] == "failed"
    assert draft["execution"] is None
    assert draft["return_observed_at"] is None
    assert draft["failure_reason"] == "provider_timeout"
    assert draft["local_elapsed_seconds"] == pytest.approx(371.5)

    assert publish["status"] == "pending"
    assert {f: publish[f] for f in UNKNOWN_FIELDS} == dict.fromkeys(UNKNOWN_FIELDS, None)
    assert publish["start_events_observed"] == 0

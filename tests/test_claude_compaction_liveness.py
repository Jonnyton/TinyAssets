"""Declared compaction is provider work, not model silence (regression).

The published Agent SDK protocol (``@anthropic-ai/claude-agent-sdk`` 0.3.281,
``sdk.d.ts``) declares compaction as a status lifecycle::

    SDKStatus = 'compacting' | 'requesting' | null
    SDKStatusMessage = { type: 'system', subtype: 'status', status: SDKStatus,
                         compact_result?: 'success' | 'failed', ... }
    SDKCompactBoundaryMessage = { type: 'system', subtype: 'compact_boundary',
                                  compact_metadata: { trigger, pre_tokens, ... } }

A ``status: "compacting"`` frame DECLARES that the CLI is busy until the
matching clear (``status: null`` / the compact boundary). Nothing documents a
heartbeat cadence during that window (the CLI reference promises only that
``--include-partial-messages`` includes partial streaming events), so the
window can legitimately be silent for longer than the ordinary idle interval.

Before the fix (pre-2026-09-23 tree) ``_normalize_stream_obj`` flattened
every ``system/status`` frame to one ``heartbeat`` and ``_read_stream`` then
applied the ordinary post-tool idle interval, so a declared compaction longer
than ``idle_s`` was killed as ``provider_idle_timeout`` with
``tool_phase="tool_result"`` and ``side_effect_state="committed"`` — the same
signature as genuine silence. The fix types the documented status lifecycle
(``declared_busy`` / ``declared_clear``) and honours a declared window for
``min(absolute cap, _BUSY_WAIT_S)``, the same bound shape as a tool wait.

These tests pin the DECLARED-busy shape only:

* a declared compaction survives silence longer than the idle interval
  (regression, RED on the unfixed tree);
* the no-declaration control still idles — the fix must not loosen ordinary
  post-tool silence;
* an unknown frame or an undocumented status value declares nothing;
* the declared window is bounded by ``_BUSY_WAIT_S`` on its own (independent
  of ``_TOOL_WAIT_S``), and silence past that bound is reported as idle;
* any real progress (text, a tool start, a tool result, the result) ends the
  window even without an explicit clear frame;
* the absolute cap still bounds a declared compaction, and caller
  cancellation still kills the child.

No workflow timeout is raised, nothing is replayed, and nothing waits forever.
Driven through the real ``ClaudeProvider._read_stream`` against the same fake
subprocess protocol as ``tests/test_provider_stream_and_classify.py``.
"""

from __future__ import annotations

import asyncio

import pytest

from tests.test_provider_stream_and_classify import (
    INIT,
    FakeStreamProcess,
    _assistant_text,
    _finished,
    _line,
    _partial_text,
    _result,
    _run_stream,
    _started,
)
from tinyassets.exceptions import InteractiveDeadlineError, ProviderIdleTimeoutError
from tinyassets.providers import claude_provider as claude_provider_module
from tinyassets.providers.base import ModelConfig
from tinyassets.providers.claude_provider import ClaudeProvider, _normalize_stream_obj

# Shortened profile: idle fires at 0.15s; the cap stays generous so an idle
# raise here is the watchdog, never the cap.
_IDLE_S = 0.15
_PROFILE = ModelConfig(
    init_timeout_s=_IDLE_S, first_progress_s=_IDLE_S, idle_timeout_s=_IDLE_S,
    absolute_cap_s=5.0,
)
# Silence well past the idle interval but well inside the cap.
_LONG_SILENCE_S = 0.6


def _status(status, **extra) -> dict:
    """A published ``SDKStatusMessage`` (``system/status``)."""
    return {
        "type": "system", "subtype": "status", "status": status,
        "uuid": "u-1", "session_id": "s-test", **extra,
    }


def _compact_boundary() -> dict:
    """A published ``SDKCompactBoundaryMessage``."""
    return {
        "type": "system", "subtype": "compact_boundary",
        "compact_metadata": {"trigger": "auto", "pre_tokens": 180_000,
                             "post_tokens": 20_000, "duration_ms": 600},
        "uuid": "u-2", "session_id": "s-test",
    }


def _after_tool(*tail):
    """INIT, one identified tool that completes, then ``tail``."""
    return [_line(INIT), _line(_started("example", "call-a")),
            _line(_finished("call-a")), *tail]


def test_declared_compaction_survives_silence_longer_than_idle():
    # tool completes -> compacting declared -> silence 4x idle -> boundary +
    # status cleared -> answer. Declared work is not model silence: the turn
    # must complete and none of the status content may reach the reply.
    proc = FakeStreamProcess(_after_tool(
        _line(_status("compacting")),
        (_LONG_SILENCE_S, _line(_compact_boundary())),
        _line(_status(None, compact_result="success")),
        _line(_assistant_text("answer")),
        _line(_result("answer")),
    ))
    response = _run_stream(proc, _PROFILE)
    assert response.text == "answer"
    assert "compact" not in response.text
    assert response.side_effect_state == "committed"


def test_undeclared_post_tool_silence_still_idles():
    # Control: the same silence with NO declaration is ordinary post-tool idle
    # and must keep failing exactly as today (the fix may not loosen this).
    proc = FakeStreamProcess(_after_tool(
        (_LONG_SILENCE_S, _line(_assistant_text("never"))),
        _line(_result("never")),
    ))
    with pytest.raises(ProviderIdleTimeoutError) as raised:
        _run_stream(proc, _PROFILE)
    telemetry = raised.value.attempt_telemetry
    assert telemetry["tool_phase"] == "tool_result"
    assert telemetry["side_effect_state"] == "committed"
    assert proc.killed is True


@pytest.mark.parametrize(
    "frame",
    [
        pytest.param({"type": "future_opaque_event", "status": "compacting"},
                     id="unknown-frame-type"),
        pytest.param(_status("definitely-undocumented"), id="undocumented-status"),
        pytest.param({"type": "system", "subtype": "status", "text": "compacting"},
                     id="status-text-without-status-field"),
    ],
)
def test_only_a_documented_status_value_declares_busy(frame):
    # Strict: an unknown frame type, an undocumented status value, or free
    # text that merely mentions compaction gives at most one heartbeat reset
    # and NEVER opens a busy window.
    proc = FakeStreamProcess(_after_tool(
        _line(frame),
        (_LONG_SILENCE_S, _line(_assistant_text("never"))),
        _line(_result("never")),
    ))
    with pytest.raises(ProviderIdleTimeoutError):
        _run_stream(proc, _PROFILE)
    assert proc.killed is True


def test_a_cleared_status_ends_the_declared_window():
    # Once the CLI declares ``status: null`` the ordinary idle interval applies
    # again: silence after the clear is model silence.
    proc = FakeStreamProcess(_after_tool(
        _line(_status("compacting")),
        _line(_status(None, compact_result="success")),
        (_LONG_SILENCE_S, _line(_assistant_text("never"))),
        _line(_result("never")),
    ))
    with pytest.raises(ProviderIdleTimeoutError):
        _run_stream(proc, _PROFILE)
    assert proc.killed is True


def test_a_smaller_injected_busy_allowance_bounds_the_declared_wait(monkeypatch):
    # Drive the bound from ``_BUSY_WAIT_S`` itself (absolute cap 5s, busy wait
    # 0.3s): silence inside a declared window that outlives the busy bound is
    # reported as idle (post-tool phase, committed), not as the cap, and the
    # child is killed. ``_TOOL_WAIT_S`` is left alone, so the bound that fires
    # is the busy knob on its own — no identified tool is in flight.
    monkeypatch.setattr(claude_provider_module, "_BUSY_WAIT_S", 0.3)
    assert claude_provider_module._TOOL_WAIT_S == 900.0
    proc = FakeStreamProcess(_after_tool(
        _line(_status("compacting")),
        (2.0, _line(_result("never"))),
    ))
    with pytest.raises(ProviderIdleTimeoutError) as raised:
        _run_stream(proc, _PROFILE)
    telemetry = raised.value.attempt_telemetry
    assert telemetry["tool_phase"] == "tool_result"
    assert telemetry["side_effect_state"] == "committed"
    assert proc.killed is True


def test_silence_inside_the_injected_busy_bound_still_completes(monkeypatch):
    # Companion to the bound test: the same declaration with silence past the
    # idle interval (0.15s) but inside the injected busy bound (0.3s) is still
    # honoured. Together the pair pins that the window is ``_BUSY_WAIT_S``,
    # not the idle interval and not the cap.
    monkeypatch.setattr(claude_provider_module, "_BUSY_WAIT_S", 0.3)
    proc = FakeStreamProcess(_after_tool(
        _line(_status("compacting")),
        (0.22, _line(_status(None, compact_result="success"))),
        _line(_assistant_text("answer")),
        _line(_result("answer")),
    ))
    response = _run_stream(proc, _PROFILE)
    assert response.text == "answer"
    assert response.side_effect_state == "committed"


@pytest.mark.parametrize(
    ("progress", "expected_phase"),
    [
        # Full assistant text after the declaration.
        pytest.param([_line(_assistant_text("partial answer"))], "tool_result",
                     id="assistant-text-clears"),
        # A partial text delta (partial-message framing).
        pytest.param([_line(_partial_text("par"))], "tool_result",
                     id="partial-text-clears"),
        # A tool start with an UNUSABLE id: real progress, but it earns no
        # pending-tool allowance, so nothing identified is in flight.
        pytest.param([_line(_started("example", None))], "tool_use",
                     id="unidentified-tool-use-clears"),
        # An identified tool that starts AND returns after the declaration:
        # both frames are real progress and nothing remains in flight.
        pytest.param([_line(_started("example", "call-b")), _line(_finished("call-b"))],
                     "tool_result", id="identified-tool-pair-clears"),
    ],
)
def test_real_progress_after_a_declaration_ends_the_window(progress, expected_phase):
    # Real progress is the CLI moving on: the window ends without an explicit
    # ``status: null`` / boundary, and the silence that follows is ordinary
    # model silence again (idle at the ordinary interval, not the busy bound).
    proc = FakeStreamProcess(_after_tool(
        _line(_status("compacting")),
        *progress,
        (_LONG_SILENCE_S, _line(_result("never"))),
    ))
    with pytest.raises(ProviderIdleTimeoutError) as raised:
        _run_stream(proc, _PROFILE)
    assert raised.value.attempt_telemetry["tool_phase"] == expected_phase
    assert proc.killed is True


def test_a_tool_result_for_the_open_tool_ends_the_window():
    # The tool started BEFORE the declaration and its named result arrives
    # after it: the result is real progress that closes the tool and ends the
    # window in one frame, so the silence after it is ordinary post-tool idle.
    proc = FakeStreamProcess([
        _line(INIT),
        _line(_started("example", "call-a")),
        _line(_status("compacting")),
        _line(_finished("call-a")),
        (_LONG_SILENCE_S, _line(_result("never"))),
    ])
    with pytest.raises(ProviderIdleTimeoutError) as raised:
        _run_stream(proc, _PROFILE)
    telemetry = raised.value.attempt_telemetry
    assert telemetry["tool_phase"] == "tool_result"
    assert telemetry["side_effect_state"] == "committed"
    assert proc.killed is True


def test_declared_compaction_never_outlives_the_absolute_cap():
    # The cap is never relaxed by a declaration: a compaction that outlives it
    # ends as the deadline class, not as idle, and the child is killed.
    config = ModelConfig(
        init_timeout_s=_IDLE_S, first_progress_s=_IDLE_S, idle_timeout_s=_IDLE_S,
        absolute_cap_s=0.5,
    )
    proc = FakeStreamProcess(_after_tool(
        _line(_status("compacting")),
        (30.0, _line(_result("never"))),
    ))
    with pytest.raises(InteractiveDeadlineError):
        _run_stream(proc, config)
    assert proc.killed is True


def test_cancellation_during_declared_compaction_kills_the_child():
    proc = FakeStreamProcess(_after_tool(
        _line(_status("compacting")),
        (30.0, _line(_result("never"))),
    ))

    async def _drive() -> None:
        task = asyncio.create_task(
            ClaudeProvider()._read_stream(proc, "prompt", _PROFILE)
        )
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_drive())
    assert proc.killed is True


def test_a_compact_boundary_alone_ends_the_declared_window():
    # The published boundary frame is a clear on its own: silence after it
    # (with no ``status: null`` yet) is ordinary model silence again.
    proc = FakeStreamProcess(_after_tool(
        _line(_status("compacting")),
        _line(_compact_boundary()),
        (_LONG_SILENCE_S, _line(_assistant_text("never"))),
        _line(_result("never")),
    ))
    with pytest.raises(ProviderIdleTimeoutError):
        _run_stream(proc, _PROFILE)
    assert proc.killed is True


@pytest.mark.parametrize(
    ("frame", "expected"),
    [
        pytest.param(_status("compacting"), [("declared_busy", {"state": "compacting"})],
                     id="compacting-declares"),
        pytest.param(_status(None), [("declared_clear", {})], id="null-clears"),
        pytest.param(_compact_boundary(), [("declared_clear", {})], id="boundary-clears"),
        pytest.param(_status("requesting"), [("heartbeat", {})],
                     id="requesting-is-liveness-only"),
        pytest.param(_status("definitely-undocumented"), [("heartbeat", {})],
                     id="undocumented-is-liveness-only"),
        pytest.param({"type": "system", "subtype": "status", "text": "compacting"},
                     [("heartbeat", {})], id="missing-key-is-liveness-only"),
        pytest.param({"type": "system", "subtype": "status", "status": 1},
                     [("heartbeat", {})], id="non-string-is-liveness-only"),
        pytest.param({"type": "system", "subtype": "tool_heartbeat", "status": "compacting"},
                     [("heartbeat", {})], id="other-subtype-never-declares"),
    ],
)
def test_normalizer_types_only_the_documented_status_lifecycle(frame, expected):
    # The internal contract: exactly one typed event per documented status
    # frame, and plain liveness for everything else on the subtype.
    assert _normalize_stream_obj(frame) == expected

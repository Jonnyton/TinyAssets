"""Tests for FEAT-006 Slice 2 — graph_compiler propagation of provider chain
diagnostics through the ``CompilerError`` wrap and the ``failed`` event.

The router (FEAT-006 Slice 1, already on main) attaches ``chain_state`` and
``attempts`` to ``AllProvidersExhaustedError``. Before this slice, the
graph_compiler wrap stripped both onto ``__cause__`` where chatbots and the
auto-fix loop could not see them — the failure mode that makes BUG-097's
investigation daemon recursively self-block on the same opaque error.

This slice asserts:
1. ``CompilerError`` accepts and stores ``chain_state`` / ``attempts``.
2. ``_wrap_provider_failure`` copies them off an ``AllProvidersExhaustedError``
   and appends a JSON ``[chain_state]:`` suffix to the message.
3. ``_emit_failed_event`` forwards ``chain_state`` to the event sink as
   ``provider_chain`` when available.
4. Older event_sink signatures (no ``provider_chain`` kwarg) still receive
   the failed event without raising.
"""

from __future__ import annotations

import json

from workflow.exceptions import AllProvidersExhaustedError
from workflow.graph_compiler import (
    CompilerError,
    _emit_failed_event,
    _wrap_provider_failure,
)


def _example_chain_state() -> dict:
    return {
        "role": "writer",
        "chain": ["claude-code", "codex", "ollama-local"],
        "attempts": [
            {
                "provider": "claude-code",
                "status": "skipped",
                "skip_class": "not_in_registry",
                "detail": "",
            },
            {
                "provider": "codex",
                "status": "failed",
                "skip_class": "auth_invalid",
                "detail": "401 Unauthorized",
            },
            {
                "provider": "ollama-local",
                "status": "failed",
                "skip_class": "endpoint_unreachable",
                "detail": "connection refused",
            },
        ],
        "api_key_providers_enabled": False,
    }


# ---------------------------------------------------------------------------
# CompilerError carries structured diagnostics
# ---------------------------------------------------------------------------


def test_compiler_error_backward_compat_no_chain_state() -> None:
    err = CompilerError("Provider call failed in node 'x'")
    assert str(err) == "Provider call failed in node 'x'"
    assert err.chain_state is None
    assert err.attempts is None


def test_compiler_error_accepts_chain_state_and_attempts() -> None:
    cs = _example_chain_state()
    attempts = cs["attempts"]
    err = CompilerError("boom", chain_state=cs, attempts=attempts)
    assert err.chain_state == cs
    assert err.attempts == attempts


# ---------------------------------------------------------------------------
# _wrap_provider_failure propagates router diagnostics
# ---------------------------------------------------------------------------


def test_wrap_provider_failure_preserves_chain_state_from_cause() -> None:
    cs = _example_chain_state()
    cause = AllProvidersExhaustedError(
        "All providers exhausted for role=writer. Daemon should retry with backoff.",
        attempts=cs["attempts"],
        chain_state=cs,
    )
    wrapped = _wrap_provider_failure("intake_router", cause)

    assert isinstance(wrapped, CompilerError)
    assert wrapped.chain_state == cs
    assert wrapped.attempts == cs["attempts"]

    msg = str(wrapped)
    assert "Provider call failed in node 'intake_router'" in msg
    assert "All providers exhausted for role=writer" in msg
    # JSON suffix the auto-fix loop / chatbot can parse without __cause__:
    assert "[chain_state]:" in msg
    suffix_json = msg.split("[chain_state]:", 1)[1].strip()
    parsed = json.loads(suffix_json)
    assert parsed["role"] == "writer"
    assert parsed["api_key_providers_enabled"] is False
    skip_classes = {a["skip_class"] for a in parsed["attempts"]}
    assert {"not_in_registry", "auth_invalid", "endpoint_unreachable"} <= skip_classes


def test_wrap_provider_failure_no_chain_state_when_cause_is_plain() -> None:
    cause = RuntimeError("subprocess crashed")
    wrapped = _wrap_provider_failure("some_node", cause)
    assert wrapped.chain_state is None
    assert wrapped.attempts is None
    msg = str(wrapped)
    assert msg == "Provider call failed in node 'some_node': subprocess crashed"
    assert "[chain_state]:" not in msg


def test_wrap_provider_failure_serialization_error_does_not_block_wrap(monkeypatch) -> None:
    """A non-JSON-serializable chain_state must still produce a usable wrap."""
    class _Unserializable:
        def __repr__(self) -> str:
            raise RuntimeError("no repr either")

    cs = {"oops": _Unserializable()}
    cause = AllProvidersExhaustedError("opaque", chain_state=cs)
    wrapped = _wrap_provider_failure("node_x", cause)
    # chain_state still preserved as attribute (for callers that introspect it),
    # even though the JSON suffix had to be skipped.
    assert wrapped.chain_state is cs
    assert "Provider call failed in node 'node_x'" in str(wrapped)


# ---------------------------------------------------------------------------
# _emit_failed_event forwards provider_chain
# ---------------------------------------------------------------------------


class _RecordingSink:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def __call__(self, **kwargs: object) -> None:
        self.calls.append(kwargs)


def test_emit_failed_event_forwards_provider_chain_when_present() -> None:
    cs = _example_chain_state()
    cause = AllProvidersExhaustedError("opaque", chain_state=cs)
    sink = _RecordingSink()
    _emit_failed_event(sink, "intake_router", cause)
    assert len(sink.calls) == 1
    call = sink.calls[0]
    assert call["node_id"] == "intake_router"
    assert call["phase"] == "failed"
    assert call["error_type"] == "AllProvidersExhaustedError"
    assert call["provider_chain"] == cs


def test_emit_failed_event_no_provider_chain_kwarg_when_absent() -> None:
    sink = _RecordingSink()
    _emit_failed_event(sink, "node_x", RuntimeError("plain error"))
    assert len(sink.calls) == 1
    assert "provider_chain" not in sink.calls[0]
    assert sink.calls[0]["error_type"] == "RuntimeError"


def test_emit_failed_event_old_sink_signature_does_not_raise() -> None:
    """Older event_sink callbacks that do not accept ``provider_chain``
    must still receive the failed event without the kwarg."""
    calls: list[dict] = []

    def old_sink(*, node_id: str, phase: str, error: str, error_type: str) -> None:
        calls.append({
            "node_id": node_id,
            "phase": phase,
            "error": error,
            "error_type": error_type,
        })

    cs = _example_chain_state()
    cause = AllProvidersExhaustedError("opaque", chain_state=cs)
    _emit_failed_event(old_sink, "n1", cause)

    assert len(calls) == 1
    assert calls[0]["node_id"] == "n1"
    assert calls[0]["phase"] == "failed"


def test_emit_failed_event_none_sink_is_noop() -> None:
    # No event_sink configured at all is a valid runtime state for the
    # synchronous compile path. Must not raise.
    cs = _example_chain_state()
    cause = AllProvidersExhaustedError("opaque", chain_state=cs)
    _emit_failed_event(None, "n", cause)


def test_emit_failed_event_swallows_sink_exception_when_no_provider_chain() -> None:
    """A sink that raises on the fallback (no-provider_chain) path must
    still not bubble the exception — failed-event emission is best-effort."""
    def broken_sink(**kwargs: object) -> None:
        raise ValueError("sink broken")

    # No chain_state on the exception => we go straight to the broad-kwarg
    # call, which raises; the helper should swallow and log.
    _emit_failed_event(broken_sink, "n", RuntimeError("plain"))

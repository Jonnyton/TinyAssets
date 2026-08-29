"""Tests for the streamed served-attempt reader + failure taxonomy (Slice 1).

Change: ``stream-and-classify-provider-attempts``. These tests NEVER call the
live ``claude`` CLI — they drive :meth:`ClaudeProvider.complete` with a fake
subprocess that replays synthetic ``--output-format stream-json`` NDJSON, and
they exercise the router cooldown map, the interactive no-sleep guarantee, and
the honest-notice mapping against the classified exceptions.

Idle intervals are injected short (sub-second) via ``ModelConfig`` so the
watchdog fires in test time without real 30s waits.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from tinyassets.exceptions import (
    AllProvidersExhaustedError,
    InteractiveDeadlineError,
    ProviderError,
    ProviderIdleTimeoutError,
    ProviderOverloadedError,
    ProviderProtocolError,
    ProviderRateLimitedError,
    ProviderUnavailableError,
)
from tinyassets.providers.base import (
    BaseProvider,
    ModelConfig,
    ProviderResponse,
    SandboxUnavailableError,
)
from tinyassets.providers.claude_provider import ClaudeProvider
from tinyassets.providers.quota import QuotaTracker
from tinyassets.providers.router import ProviderRouter

# ---------------------------------------------------------------------------
# Synthetic stream-json fixtures + a fake subprocess that replays them
# ---------------------------------------------------------------------------


def _line(obj: dict) -> bytes:
    """One NDJSON stdout line (the documented stream-json shape)."""
    return (json.dumps(obj) + "\n").encode("utf-8")


INIT = {"type": "system", "subtype": "init", "session_id": "s-test"}


def _assistant_text(text: str) -> dict:
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def _partial_text(text: str) -> dict:
    return {
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": text},
        },
    }


def _thinking_delta(text: str) -> dict:
    return {
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "thinking_delta", "thinking": text},
        },
    }


def _tool_use(name: str) -> dict:
    return {
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": name, "input": {}}]},
    }


def _tool_result() -> dict:
    return {
        "type": "user",
        "message": {"content": [{"type": "tool_result", "content": "ok"}]},
    }


def _api_retry(error: str, error_status: int, retry_delay_ms: int) -> dict:
    """A REAL Claude 2.1.236 ``system/api_retry`` event.

    The CLI's documented fields are ``error`` (string, e.g. "rate_limit" /
    "overloaded"), ``error_status`` (int HTTP status, 429 / 529), and
    ``retry_delay_ms`` (int). These are the ground-truth field names — NOT
    payloads shaped to the implementation (the change-#1 lesson).
    """
    return {
        "type": "system",
        "subtype": "api_retry",
        "error": error,
        "error_status": error_status,
        "retry_delay_ms": retry_delay_ms,
        "attempt": 1,
    }


def _rate_limit_event(status: str, *, resets_at: float | None = None) -> dict:
    """A REAL Claude 2.1.236 top-level ``rate_limit_event``.

    ``rate_limit_info.status`` == "allowed" is informational (the reference
    trace shows it on a SUCCESSFUL turn); any other status is an active limit,
    with ``resetsAt`` a unix-seconds reset time.
    """
    info: dict = {
        "status": status,
        "rateLimitType": "five_hour",
        "overageStatus": "rejected",
    }
    if resets_at is not None:
        info["resetsAt"] = resets_at
    return {"type": "rate_limit_event", "rate_limit_info": info}


def _result(text: str, *, subtype: str = "success", **extra) -> dict:
    obj = {"type": "result", "subtype": subtype, "result": text}
    obj.update(extra)
    return obj


class FakeStreamProcess:
    """A stand-in for an ``asyncio`` subprocess replaying NDJSON stdout.

    ``stdout_items`` is a list of either raw ``bytes`` (returned immediately)
    or ``(delay_s, bytes)`` tuples (the reader sleeps ``delay_s`` before the
    line arrives — a large delay simulates a hung/idle stream that the watchdog
    catches via ``asyncio.wait_for``).
    """

    def __init__(self, stdout_items, *, stderr: bytes = b"", returncode: int = 0):
        self._items = list(stdout_items)
        self._idx = 0
        self.returncode = returncode
        self.killed = False
        self.stdout = self._Stdout(self)
        self.stderr = self._Stderr(stderr)
        self.stdin = self._Stdin()

    class _Stdout:
        def __init__(self, parent):
            self._p = parent

        async def readline(self):
            p = self._p
            if p._idx >= len(p._items):
                return b""
            item = p._items[p._idx]
            p._idx += 1
            if isinstance(item, tuple):
                delay, data = item
                if delay:
                    await asyncio.sleep(delay)
                return data
            return item

    class _Stderr:
        def __init__(self, data: bytes):
            self._data = data
            self._sent = False

        async def read(self, _n: int) -> bytes:
            if self._sent:
                return b""
            self._sent = True
            return self._data

    class _Stdin:
        def write(self, _b): ...
        async def drain(self): ...
        def close(self): ...

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode


def _run_stream(proc: FakeStreamProcess, config: ModelConfig) -> ProviderResponse:
    """Drive ClaudeProvider._read_stream against a fake process."""
    provider = ClaudeProvider()
    return asyncio.run(provider._read_stream(proc, "prompt", config))


# Short, injected watchdog profile so idle fires in test time.
_FAST = ModelConfig(
    init_timeout_s=0.15,
    first_progress_s=0.15,
    idle_timeout_s=0.15,
    absolute_cap_s=5.0,
)


# ---------------------------------------------------------------------------
# 5.1 Behavior parity: recorded stream assembles the SAME final text
# ---------------------------------------------------------------------------


class TestStreamAssembly:
    def test_terminal_result_is_canonical_final_text(self):
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_assistant_text("Hello")),
            _line(_assistant_text(" world")),
            _line(_result("Hello world", usage={"input_tokens": 12, "output_tokens": 5},
                          total_cost_usd=0.0003)),
        ])
        resp = _run_stream(proc, _FAST)
        assert isinstance(resp, ProviderResponse)
        assert resp.text == "Hello world"
        assert resp.provider == "claude-code"
        assert resp.family == "anthropic"
        assert resp.input_tokens == 12
        assert resp.output_tokens == 5
        assert resp.cost_microunits == 300
        assert resp.ttft_ms is not None

    def test_assembles_from_assistant_deltas_when_result_text_empty(self):
        # Terminal result present (success) but with no result string — the
        # assembled assistant text blocks are the fallback source of truth.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_assistant_text("Hello")),
            _line(_assistant_text(" world")),
            _line(_result("")),
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "Hello world"

    def test_partial_deltas_are_fallback_and_thinking_is_never_relayed(self):
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_thinking_delta("secret reasoning I must never leak")),
            _line(_partial_text("Streamed ")),
            _line(_partial_text("answer")),
            _line(_result("")),
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "Streamed answer"
        assert "secret reasoning" not in resp.text

    def test_tool_events_set_side_effect_state(self):
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_tool_use("write_graph")),
            _line(_tool_result()),
            _line(_assistant_text("done")),
            _line(_result("done")),
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "done"
        assert resp.tool_phase == "tool_result"
        assert resp.side_effect_state == "committed"

    def test_success_result_with_no_text_anywhere_fails_loud(self):
        proc = FakeStreamProcess([_line(INIT), _line(_result(""))])
        with pytest.raises(ProviderError, match="no assistant text"):
            _run_stream(proc, _FAST)


# ---------------------------------------------------------------------------
# 5.2 Idle watchdog: progress keeps it alive; only real idle fails it
# ---------------------------------------------------------------------------


class TestIdleWatchdog:
    def test_long_but_progressing_stream_is_not_failed_for_elapsed_time(self):
        # Each gap (0.08s) is under the idle interval (0.15s); total elapsed
        # (~0.5s) far exceeds any single interval — a naive total deadline of
        # 0.15s would have failed it. Progress keeps resetting the watchdog.
        proc = FakeStreamProcess([
            _line(INIT),
            (0.08, _line(_assistant_text("a"))),
            (0.08, _line(_assistant_text("b"))),
            (0.08, _line(_assistant_text("c"))),
            (0.08, _line(_assistant_text("d"))),
            (0.08, _line(_result("abcd"))),
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "abcd"

    def test_stream_that_goes_idle_yields_provider_idle_timeout(self):
        # init + one delta, then a 10s gap — the 0.15s idle watchdog fires first.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_assistant_text("partial...")),
            (10.0, _line(_result("never arrives"))),
        ])
        with pytest.raises(ProviderIdleTimeoutError):
            _run_stream(proc, _FAST)
        assert proc.killed is True

    def test_no_init_within_init_timeout_is_idle_timeout(self):
        # The very first line stalls past init_timeout — a CLI/MCP startup hang.
        proc = FakeStreamProcess([(10.0, _line(INIT))])
        with pytest.raises(ProviderIdleTimeoutError):
            _run_stream(proc, _FAST)
        assert proc.killed is True

    def test_absolute_cap_yields_interactive_deadline_even_while_progressing(self):
        # Every gap (0.08s) resets the idle watchdog, but the absolute cap
        # (0.3s) is a hard backstop: a still-progressing over-long turn ends as
        # interactive_deadline, NOT idle_timeout.
        config = ModelConfig(
            init_timeout_s=0.2, first_progress_s=0.2, idle_timeout_s=0.2,
            absolute_cap_s=0.3,
        )
        items = [_line(INIT)] + [(0.08, _line(_assistant_text("x"))) for _ in range(20)]
        proc = FakeStreamProcess(items)
        with pytest.raises(InteractiveDeadlineError):
            _run_stream(proc, config)
        assert proc.killed is True


# ---------------------------------------------------------------------------
# 5.3 Failure taxonomy from api_retry / exit / malformed
# ---------------------------------------------------------------------------


class TestFailureTaxonomy:
    def test_real_429_api_retry_then_no_recovery_is_rate_limited(self):
        # REAL schema: error="rate_limit", error_status=429, retry_delay_ms=30000.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_api_retry("rate_limit", 429, 30000)),
        ], returncode=0)
        with pytest.raises(ProviderRateLimitedError) as ei:
            _run_stream(proc, _FAST)
        assert ei.value.retry_after == 30.0  # 30000ms -> 30s
        assert ei.value.failure_class == "provider_rate_limited"
        assert proc.killed is True

    def test_real_529_api_retry_is_overloaded_with_retry_after(self):
        # REAL schema: error="overloaded", error_status=529, retry_delay_ms=5000.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_api_retry("overloaded", 529, 5000)),
        ], returncode=0)
        with pytest.raises(ProviderOverloadedError) as ei:
            _run_stream(proc, _FAST)
        assert ei.value.retry_after == 5.0
        assert ei.value.failure_class == "provider_overloaded"

    def test_real_429_then_quick_exit_1_is_rate_limited_not_unavailable(self):
        # Blocker A (Codex re-review #2): a REAL 429 api_retry followed by a quick
        # exit code 1 must be classified from the TYPED signal (rate-limited, with
        # retry_after), NOT masked as generic "unavailable" by the exit-1 heuristic.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_api_retry("rate_limit", 429, 45000)),
        ], returncode=1)  # quick exit 1 AFTER the typed retry
        with pytest.raises(ProviderRateLimitedError) as ei:
            _run_stream(proc, _FAST)
        assert ei.value.failure_class == "provider_rate_limited"
        assert ei.value.retry_after == 45.0

    def test_real_529_then_quick_exit_1_is_overloaded_not_unavailable(self):
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_api_retry("overloaded", 529, 7000)),
        ], returncode=1)
        with pytest.raises(ProviderOverloadedError) as ei:
            _run_stream(proc, _FAST)
        assert ei.value.failure_class == "provider_overloaded"
        assert ei.value.retry_after == 7.0

    def test_api_retry_classifies_by_error_status_when_string_is_unknown(self):
        # Even if the error STRING is not a recognized word, error_status=429
        # classifies it rate-limited (schema field, not substring luck).
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_api_retry("some_new_wording", 429, 12000)),
        ], returncode=0)
        with pytest.raises(ProviderRateLimitedError) as ei:
            _run_stream(proc, _FAST)
        assert ei.value.retry_after == 12.0

    def test_api_retry_that_recovers_returns_success(self):
        # A rate-limit retry the CLI rides out and then completes must NOT fail.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_api_retry("rate_limit", 429, 2000)),
            _line(_assistant_text("recovered")),
            _line(_result("recovered")),
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "recovered"

    def test_rate_limit_event_allowed_is_informational_not_a_failure(self):
        # status=="allowed" appears on a SUCCESSFUL turn (per the real trace) —
        # it must be a liveness heartbeat, never a rate-limit failure.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_rate_limit_event("allowed", resets_at=9_999_999_999)),
            _line(_assistant_text("fine")),
            _line(_rate_limit_event("allowed", resets_at=9_999_999_999)),
            _line(_result("fine")),
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "fine"

    def test_rate_limit_event_non_allowed_is_rate_limited(self):
        import time as _time
        # A non-"allowed" status is an active limit; retry_after derives from
        # resetsAt (unix seconds).
        resets = _time.time() + 40
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_rate_limit_event("blocked", resets_at=resets)),
        ], returncode=0)
        with pytest.raises(ProviderRateLimitedError) as ei:
            _run_stream(proc, _FAST)
        assert ei.value.failure_class == "provider_rate_limited"
        assert 30 <= ei.value.retry_after <= 45  # ~40s from resetsAt

    def test_known_retry_delay_longer_than_idle_is_not_killed_as_idle(self):
        # Blocker B: a documented retry states a 0.8s wait — longer than the
        # 0.15s idle interval. The idle watchdog must extend to cover it so the
        # turn survives the wait and completes when the CLI recovers, rather than
        # being relabeled provider_idle_timeout at 0.15s.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_api_retry("rate_limit", 429, 800)),  # 0.8s stated wait
            (0.5, _line(_assistant_text("recovered after the wait"))),
            _line(_result("recovered after the wait")),
        ])
        resp = _run_stream(proc, _FAST)  # idle_timeout_s=0.15 << 0.5s gap
        assert resp.text == "recovered after the wait"

    def test_malformed_line_is_protocol_error(self):
        proc = FakeStreamProcess([_line(INIT), b"{not valid json at all\n"])
        with pytest.raises(ProviderProtocolError):
            _run_stream(proc, _FAST)
        assert proc.killed is True

    def test_non_object_json_line_is_protocol_error(self):
        proc = FakeStreamProcess([_line(INIT), b"\"a bare string\"\n"])
        with pytest.raises(ProviderProtocolError):
            _run_stream(proc, _FAST)

    def test_exit_1_quick_without_result_is_unavailable(self):
        proc = FakeStreamProcess([], returncode=1)
        with pytest.raises(ProviderUnavailableError):
            _run_stream(proc, _FAST)

    def test_eof_without_terminal_result_is_classified_protocol_error(self):
        # Blocker J: EOF with a clean exit but NO terminal result is a TRUNCATED
        # stream — classify it as provider_protocol_error, not a bare
        # unclassified ProviderError (which the earlier test wrongly blessed).
        proc = FakeStreamProcess([_line(INIT), _line(_assistant_text("hi"))],
                                 returncode=0)
        with pytest.raises(ProviderProtocolError, match="truncated") as ei:
            _run_stream(proc, _FAST)
        assert ei.value.failure_class == "provider_protocol_error"
        assert proc.killed is True

    def test_bwrap_failure_on_stderr_raises_sandbox_unavailable(self):
        # A bwrap failure remains a terminal outcome even on the streaming path.
        import sys
        if sys.platform == "win32":
            pytest.skip("bwrap is Linux-only")
        proc = FakeStreamProcess(
            [],
            stderr=b"bwrap: No permissions to create a new namespace",
            returncode=1,
        )
        with pytest.raises(SandboxUnavailableError):
            _run_stream(proc, _FAST)

    def test_whitespace_lines_do_not_reset_the_idle_watchdog(self):
        # Blocker C reconciliation: recognized framing (message_start) is now a
        # LIVENESS heartbeat, so the non-liveness input that must NOT reset the
        # watchdog is whitespace-only lines (no events, not malformed). init then
        # a blank line then a long gap still fails idle.
        proc = FakeStreamProcess([
            _line(INIT),
            b"   \n",  # whitespace-only: no events, not malformed, not liveness
            (10.0, _line(_result("late"))),
        ])
        with pytest.raises(ProviderIdleTimeoutError):
            _run_stream(proc, _FAST)
        assert proc.killed is True

    def test_unknown_wellformed_type_does_not_reset_the_idle_watchdog(self):
        # An unknown-but-well-formed JSON object is tolerated (not a protocol
        # error) but is NOT counted as liveness — a hung process emits nothing,
        # so an unrecognized type must not keep a stalled turn alive forever.
        proc = FakeStreamProcess([
            _line(INIT),
            _line({"type": "some_future_event", "detail": "x"}),
            (10.0, _line(_result("late"))),
        ])
        with pytest.raises(ProviderIdleTimeoutError):
            _run_stream(proc, _FAST)


# ---------------------------------------------------------------------------
# 5.4 Router cooldown map by failure_class
# ---------------------------------------------------------------------------


class _RaisingProvider(BaseProvider):
    """A claude-code fake whose complete() raises a chosen exception once,
    then (optionally) succeeds — to prove next-turn eligibility."""

    name = "claude-code"
    family = "anthropic"

    def __init__(self, exc, *, then_ok: bool = False):
        self._exc = exc
        self._then_ok = then_ok
        self.calls = 0

    async def complete(self, prompt, system, config, *, universe_dir=None):
        self.calls += 1
        if self.calls == 1:
            raise self._exc
        if self._then_ok:
            return ProviderResponse(
                text="ok now", provider=self.name, model="claude",
                family=self.family, latency_ms=1.0,
            )
        raise self._exc


def _solo_router(provider):
    quota = QuotaTracker()
    return ProviderRouter(providers={provider.name: provider}, quota=quota), quota


class TestRouterCooldownMap:
    @pytest.mark.asyncio
    async def test_idle_timeout_does_not_cool_the_sole_writer(self):
        provider = _RaisingProvider(ProviderIdleTimeoutError("idle"))
        router, quota = _solo_router(provider)

        with pytest.raises(AllProvidersExhaustedError) as ei:
            await router.call("writer", "prompt", "system")

        assert quota.available("claude-code") is True  # NOT cooled
        assert ei.value.failure_class == "provider_idle_timeout"

    @pytest.mark.asyncio
    async def test_interactive_deadline_does_not_cool_the_sole_writer(self):
        provider = _RaisingProvider(InteractiveDeadlineError("cap"))
        router, quota = _solo_router(provider)

        with pytest.raises(AllProvidersExhaustedError) as ei:
            await router.call("writer", "prompt", "system")

        assert quota.available("claude-code") is True
        assert ei.value.failure_class == "interactive_deadline"

    @pytest.mark.asyncio
    async def test_next_turn_after_idle_timeout_is_attempted_normally(self):
        provider = _RaisingProvider(ProviderIdleTimeoutError("idle"), then_ok=True)
        router, quota = _solo_router(provider)

        with pytest.raises(AllProvidersExhaustedError):
            await router.call("writer", "prompt", "system")
        # The writer stayed eligible: the very next turn goes through.
        resp = await router.call("writer", "prompt", "system")
        assert resp.text == "ok now"
        assert provider.calls == 2

    @pytest.mark.asyncio
    async def test_rate_limited_cools_with_retry_after(self):
        provider = _RaisingProvider(
            ProviderRateLimitedError("rl", retry_after=30)
        )
        router, quota = _solo_router(provider)

        with pytest.raises(AllProvidersExhaustedError) as ei:
            await router.call("writer", "prompt", "system")

        assert quota.available("claude-code") is False  # cooled
        remaining = quota.cooldown_remaining("claude-code")
        assert 25 <= remaining <= 32  # honors retry_after (+1s margin)
        assert ei.value.failure_class == "provider_rate_limited"

    @pytest.mark.asyncio
    async def test_overloaded_cools_with_retry_after(self):
        provider = _RaisingProvider(
            ProviderOverloadedError("ov", retry_after=8)
        )
        router, quota = _solo_router(provider)

        with pytest.raises(AllProvidersExhaustedError):
            await router.call("writer", "prompt", "system")

        assert quota.available("claude-code") is False
        assert 3 <= quota.cooldown_remaining("claude-code") <= 10


# ---------------------------------------------------------------------------
# 5.5 The interactive path does not sleep on a sole-writer timeout
# ---------------------------------------------------------------------------


class TestInteractiveNoSleep:
    def test_call_writer_never_sleeps_on_exhaustion(self, monkeypatch):
        import tinyassets.universe_intelligence as ui

        slept: list[float] = []
        monkeypatch.setattr("time.sleep", lambda s: slept.append(s))

        seen_kwargs = {}

        def _fake_call_provider(*args, **kwargs):
            seen_kwargs.update(kwargs)
            # All-skipped exhaustion => the safe case that used to sleep+retry.
            from tinyassets.providers.diagnostics import ProviderAttemptDiagnostic

            raise AllProvidersExhaustedError(
                "exhausted",
                attempts=[ProviderAttemptDiagnostic(
                    provider="claude-code", status="skipped",
                    skip_class="quota_or_cooldown",
                )],
            )

        monkeypatch.setattr(ui, "call_provider", _fake_call_provider)

        with pytest.raises(AllProvidersExhaustedError):
            ui._call_writer("hi", system="s", universe_context=object(), config=None)

        assert slept == []  # NEVER sleeps on the interactive path
        # And it disables the tenacity backoff in call.py.
        assert seen_kwargs.get("retry_on_exhaustion") is False

    def test_call_provider_no_retry_does_not_engage_tenacity_sleep(self, monkeypatch):
        from unittest.mock import MagicMock

        import tinyassets.providers.call as call_mod

        slept: list[float] = []
        monkeypatch.setattr("time.sleep", lambda s: slept.append(s))

        router = MagicMock()
        router.call_sync.side_effect = AllProvidersExhaustedError("exhausted")
        monkeypatch.setattr(call_mod, "_real_router", router)
        monkeypatch.setattr(call_mod, "_force_mock", False)

        with pytest.raises(AllProvidersExhaustedError):
            call_mod.call_provider("p", role="writer", retry_on_exhaustion=False)

        assert router.call_sync.call_count == 1  # no retry loop
        assert slept == []


# ---------------------------------------------------------------------------
# 5.6 _failure_notice maps failure_class to honest text (timeout != capacity)
# ---------------------------------------------------------------------------


class TestBackwardSafeNonStreaming:
    @pytest.mark.asyncio
    async def test_other_provider_still_returns_terminal_response(self):
        from unittest.mock import AsyncMock, patch

        from tinyassets.providers.codex_provider import CodexProvider

        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(b"codex output", b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.codex_provider._resolve_codex_cmd",
                  return_value=(["codex"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            resp = await CodexProvider().complete("prompt", "system", ModelConfig())

        assert isinstance(resp, ProviderResponse)
        assert resp.text == "codex output"
        assert resp.provider == "codex"

    @pytest.mark.asyncio
    async def test_claude_complete_json_is_unchanged_terminal_response(self):
        from unittest.mock import AsyncMock, patch

        payload = json.dumps({"result": "structured answer"}).encode("utf-8")
        mock_proc = AsyncMock()
        mock_proc.communicate = AsyncMock(return_value=(payload, b""))
        mock_proc.returncode = 0
        mock_proc.kill = AsyncMock()
        mock_proc.wait = AsyncMock()

        with (
            patch("tinyassets.providers.claude_provider._resolve_claude_cmd",
                  return_value=(["claude"], False)),
            patch("asyncio.create_subprocess_exec", return_value=mock_proc),
        ):
            resp = await ClaudeProvider().complete_json(
                "prompt", "system", ModelConfig(),
            )

        assert isinstance(resp, ProviderResponse)
        assert resp.text == "structured answer"
        assert resp.provider == "claude-code"


# ---------------------------------------------------------------------------
# 5.8 Heartbeat liveness (blocker C): a reasoning/thinking-only stretch stays
#     alive; heartbeat content is never relayed.
# ---------------------------------------------------------------------------


def _thinking_tokens(n: int) -> dict:
    return {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": n}


def _signature_delta(sig: str) -> dict:
    return {
        "type": "stream_event",
        "event": {
            "type": "content_block_delta",
            "delta": {"type": "signature_delta", "signature": sig},
        },
    }


def _framing(event_type: str) -> dict:
    return {"type": "stream_event", "event": {"type": event_type}}


class TestHeartbeatLiveness:
    def test_thinking_only_stretch_keeps_the_turn_alive(self):
        # A reasoning stretch emits ONLY thinking_tokens + thinking_delta +
        # signature_delta (verified against the real trace). Each arrives just
        # under the idle interval; a naive reader that ignored them would
        # false-kill this working turn. They are liveness, so the turn survives
        # and completes — and none of the thinking content is relayed.
        proc = FakeStreamProcess([
            _line(INIT),
            (0.08, _line(_thinking_tokens(50))),
            (0.08, _line(_thinking_delta("secret chain of thought"))),
            (0.08, _line(_thinking_tokens(150))),
            (0.08, _line(_signature_delta("SIGSIGSIG"))),
            (0.08, _line(_thinking_delta("more private reasoning"))),
            (0.08, _line(_partial_text("Final answer"))),
            (0.08, _line(_result("Final answer"))),
        ])
        resp = _run_stream(proc, _FAST)  # idle 0.15 > each 0.08 gap
        assert resp.text == "Final answer"
        assert "secret chain of thought" not in resp.text
        assert "reasoning" not in resp.text
        assert "SIGSIGSIG" not in resp.text

    def test_hooks_status_and_framing_are_liveness(self):
        # Hooks, status, notification, and stream framing all keep the turn alive.
        proc = FakeStreamProcess([
            _line({"type": "system", "subtype": "hook_started", "hook_id": "h1"}),
            (0.08, _line({"type": "system", "subtype": "hook_response",
                          "hook_id": "h1", "exit_code": 0})),
            (0.08, _line({"type": "system", "subtype": "init"})),
            (0.08, _line(_framing("message_start"))),
            (0.08, _line({"type": "system", "subtype": "status",
                          "status": "requesting"})),
            (0.08, _line(_partial_text("Hi"))),
            (0.08, _line(_framing("content_block_stop"))),
            (0.08, _line(_result("Hi"))),
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "Hi"


# ---------------------------------------------------------------------------
# 5.9 Absolute cap is a generous backstop, not a 300s total deadline (blocker D)
# ---------------------------------------------------------------------------


class TestAbsoluteCapIsGenerous:
    def test_default_absolute_cap_is_well_past_300s_and_idle_is_30s(self):
        from tinyassets.providers.base import (
            DEFAULT_ABSOLUTE_CAP_S,
            DEFAULT_IDLE_TIMEOUT_S,
            StreamTimeoutProfile,
        )

        # The old single 300s TOTAL deadline is gone: the cap is a generous
        # backstop (>= 600s) so a genuinely progressing turn survives past 300s,
        # while idle (30s) stays the primary fast-hang control.
        assert DEFAULT_ABSOLUTE_CAP_S >= 600
        assert DEFAULT_ABSOLUTE_CAP_S > 300
        assert DEFAULT_IDLE_TIMEOUT_S == 30
        prof = StreamTimeoutProfile()
        assert prof.absolute_cap_s >= 600 > 300
        assert prof.idle_s == 30

    def test_progressing_turn_survives_far_past_any_sub_cap_total_deadline(self):
        # Structural proof that NO total deadline below the absolute cap can kill
        # a progressing turn: idle 0.2s, cap 5s, ~25 events at 0.1s gaps → total
        # elapsed ~2.5s (>> 10x the idle interval and >> any mid-range total
        # deadline the old design enforced). It completes because only idle + cap
        # matter now. Scaled from the real "past 300s" case (cap 600s asserted
        # above); a 300s wait is not feasible in a unit test.
        import time as _t

        config = ModelConfig(
            init_timeout_s=0.3, first_progress_s=0.3, idle_timeout_s=0.2,
            absolute_cap_s=5.0,
        )
        items = [_line(INIT)]
        items += [(0.1, _line(_partial_text("x"))) for _ in range(24)]
        items += [(0.1, _line(_result("done")))]
        proc = FakeStreamProcess(items)
        t0 = _t.monotonic()
        resp = _run_stream(proc, config)
        elapsed = _t.monotonic() - t0
        assert resp.text == "done"
        # Really did run long past a single idle interval without being killed.
        assert elapsed > 2.0


# ---------------------------------------------------------------------------
# 5.10 Cancellation / cleanup (blocker E): caller-cancel kills the subprocess
# ---------------------------------------------------------------------------


_SLOW = ModelConfig(
    init_timeout_s=30.0, first_progress_s=30.0, idle_timeout_s=30.0,
    absolute_cap_s=60.0,
)


class TestCancellationKillsSubprocess:
    @pytest.mark.asyncio
    async def test_caller_cancellation_kills_the_subprocess_and_reaps_tasks(self):
        # The turn stalls (next line is 100s away) with a generous profile so
        # ONLY caller cancellation ends it. Cancelling the reader task must run
        # the finally: kill the process and reap both helper tasks (blocker E:
        # the Codex probe caught killed_after_caller_cancel=False).
        proc = FakeStreamProcess([
            _line(INIT),
            (100.0, _line(_result("never arrives"))),
        ])
        provider = ClaudeProvider()
        task = asyncio.create_task(provider._read_stream(proc, "prompt", _SLOW))
        await asyncio.sleep(0.05)  # let it reach the blocking readline
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert proc.killed is True  # subprocess did NOT leak


# ---------------------------------------------------------------------------
# 5.11 Failure telemetry attached to raised exceptions (blocker K)
# ---------------------------------------------------------------------------


class TestFailureTelemetry:
    def test_idle_timeout_after_a_tool_carries_side_effect_telemetry(self):
        # A tool started (side_effect_state -> possible), then the stream hangs.
        # The raised idle-timeout must carry the attempt telemetry so the router
        # + notice can reason about whether a side effect may have run.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_tool_use("write_graph")),
            (10.0, _line(_result("never"))),
        ])
        with pytest.raises(ProviderIdleTimeoutError) as ei:
            _run_stream(proc, _FAST)
        tele = ei.value.attempt_telemetry
        assert isinstance(tele, dict)
        assert tele["failure_class"] == "provider_idle_timeout"
        assert tele["side_effect_state"] == "possible"
        assert tele["tool_phase"] == "tool_use"
        assert tele["provider"] == "claude-code"
        assert "last_progress_age_ms" in tele
        assert "exit_code" in tele

    def test_rate_limited_exception_carries_telemetry(self):
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_api_retry("rate_limit", 429, 30000)),
        ], returncode=0)
        with pytest.raises(ProviderRateLimitedError) as ei:
            _run_stream(proc, _FAST)
        tele = ei.value.attempt_telemetry
        assert isinstance(tele, dict)
        assert tele["failure_class"] == "provider_rate_limited"
        assert tele["side_effect_state"] == "none"


# ---------------------------------------------------------------------------
# 5.12 Policy-router cooldown by failure_class + authority preserved (blocker F)
# ---------------------------------------------------------------------------


def _policy(provider_name: str) -> dict:
    return {"preferred": {"provider": provider_name}}


class TestPolicyRouterCooldownMap:
    @pytest.mark.asyncio
    async def test_policy_idle_timeout_does_not_cool_the_provider(self):
        provider = _RaisingProvider(ProviderIdleTimeoutError("idle"))
        router, quota = _solo_router(provider)
        with pytest.raises(AllProvidersExhaustedError):
            await router.call_with_policy(
                "writer", "p", "s", _policy("claude-code"), ModelConfig(),
            )
        assert quota.available("claude-code") is True  # NOT cooled

    @pytest.mark.asyncio
    async def test_policy_rate_limited_cools_with_retry_after(self):
        provider = _RaisingProvider(
            ProviderRateLimitedError("rl", retry_after=30)
        )
        router, quota = _solo_router(provider)
        with pytest.raises(AllProvidersExhaustedError):
            await router.call_with_policy(
                "writer", "p", "s", _policy("claude-code"), ModelConfig(),
            )
        assert quota.available("claude-code") is False  # cooled
        assert 25 <= quota.cooldown_remaining("claude-code") <= 32

    @pytest.mark.asyncio
    async def test_policy_overloaded_cools_by_retry_after_not_fixed(self):
        provider = _RaisingProvider(
            ProviderOverloadedError("ov", retry_after=8)
        )
        router, quota = _solo_router(provider)
        with pytest.raises(AllProvidersExhaustedError):
            await router.call_with_policy(
                "writer", "p", "s", _policy("claude-code"), ModelConfig(),
            )
        assert quota.available("claude-code") is False
        assert 3 <= quota.cooldown_remaining("claude-code") <= 10

    @pytest.mark.asyncio
    async def test_policy_preserves_authority_held(self):
        from tinyassets.exceptions import ProviderAuthorityHeldError

        provider = _RaisingProvider(ProviderAuthorityHeldError("held"))
        router, _ = _solo_router(provider)
        # Must be re-raised on the policy path, NOT swallowed as generic error +
        # fallthrough (blocker F).
        with pytest.raises(ProviderAuthorityHeldError):
            await router.call_with_policy(
                "writer", "p", "s", _policy("claude-code"), ModelConfig(),
            )
        assert provider.calls == 1  # no fallthrough retry


# ---------------------------------------------------------------------------
# 5.13 Sync wrapper vs absolute cap (blocker L)
# ---------------------------------------------------------------------------


class TestSyncWrapperTimeout:
    def test_sync_timeout_is_never_below_the_absolute_cap(self):
        from tinyassets.providers.base import DEFAULT_ABSOLUTE_CAP_S
        from tinyassets.providers.router import _sync_call_timeout_s

        # Default cfg: absolute cap 600 -> sync cap >= 600 (+margin).
        assert _sync_call_timeout_s(ModelConfig()) >= DEFAULT_ABSOLUTE_CAP_S
        # A SMALL legacy timeout must NOT drag the sync cap below the stream
        # absolute cap (the blocker-L defect: a sub-cap sync timeout returns
        # failure while the subprocess keeps streaming).
        assert _sync_call_timeout_s(ModelConfig(timeout=10)) >= DEFAULT_ABSOLUTE_CAP_S

    def test_sync_timeout_cancels_and_kills_the_subprocess(self, monkeypatch):
        # On a sync timeout the coroutine is cancelled (via the in-task
        # asyncio.wait_for), which reaches _read_stream's finally and KILLS the
        # subprocess — proven end-to-end through call_sync. The sync cap is
        # patched tiny so the test is fast (the real cap is 600s+).
        from unittest.mock import patch

        import tinyassets.providers.router as router_mod

        # A process that stalls forever before its first line.
        proc = FakeStreamProcess([(100.0, _line(INIT))])
        provider = ClaudeProvider()
        router = ProviderRouter(providers={"claude-code": provider})

        monkeypatch.setattr(router_mod, "_sync_call_timeout_s", lambda cfg: 0.3)

        from tinyassets.exceptions import ProviderTimeoutError as _PTE

        with (
            patch("tinyassets.providers.claude_provider._resolve_claude_cmd",
                  return_value=(["claude"], False)),
            patch("asyncio.create_subprocess_exec", return_value=proc),
        ):
            with pytest.raises(_PTE):
                router.call_sync("writer", "prompt", "system", ModelConfig())

        assert proc.killed is True  # subprocess killed on sync timeout


# ---------------------------------------------------------------------------
# 5.14 NDJSON framing in the UNIT suite: blank lines, interspersed noise,
#      concurrent stderr, an unterminated final line.
# ---------------------------------------------------------------------------


class TestStreamFraming:
    def test_blank_lines_between_events_are_ignored(self):
        proc = FakeStreamProcess([
            _line(INIT),
            b"\n",
            b"   \n",
            _line(_partial_text("Hel")),
            b"\n",
            _line(_partial_text("lo")),
            _line(_result("")),
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "Hello"

    def test_concurrent_stderr_noise_does_not_break_a_successful_turn(self):
        # A non-bwrap stderr stream is drained concurrently and never fails the
        # turn (bwrap signatures are the only stderr that raises).
        proc = FakeStreamProcess(
            [_line(INIT), _line(_assistant_text("ok")), _line(_result("ok"))],
            stderr=b"warning: some benign diagnostic chatter\n" * 100,
        )
        resp = _run_stream(proc, _FAST)
        assert resp.text == "ok"

    def test_unterminated_final_result_line_is_still_parsed(self):
        # The final ``result`` arrives WITHOUT a trailing newline before EOF (the
        # real StreamReader returns the partial tail). It must still parse.
        proc = FakeStreamProcess([
            _line(INIT),
            _line(_assistant_text("done")),
            json.dumps(_result("done")).encode("utf-8"),  # no trailing "\n"
        ])
        resp = _run_stream(proc, _FAST)
        assert resp.text == "done"


# ---------------------------------------------------------------------------
# Codex re-review blockers F / C / D — driven through the REAL classifier
# (not injected pre-classified exceptions), which is what caught the original
# double-execution regression.
# ---------------------------------------------------------------------------


class _StreamCountingProvider(ClaudeProvider):
    """Executes the REAL ``_read_stream`` and counts how many times it runs.

    Injecting a pre-classified exception (the old router tests) could not catch
    the policy-path double-execution — only actually running the classifier and
    counting executions does.
    """

    name = "claude-code"

    def __init__(self, stdout_items):
        self._items = stdout_items
        self.calls = 0
        self.procs: list = []

    async def complete(self, prompt, system, config, *, universe_dir=None):
        self.calls += 1
        proc = FakeStreamProcess(list(self._items))
        self.procs.append(proc)
        return await self._read_stream(proc, prompt, config)


@pytest.mark.asyncio
async def test_policy_idle_after_a_tool_started_does_not_double_execute():
    # Blocker F (Codex re-review #1): an idle/deadline whose attempt had already
    # STARTED A TOOL (side_effect possible) must NOT trigger a fall-through that
    # re-runs the same provider — that could duplicate the effect. It runs ONCE
    # and raises the classified aggregate; self.call() is never reached.
    from unittest.mock import AsyncMock

    # init, tool_use (side_effect -> possible), then idle -> EOF
    p = _StreamCountingProvider([_line(INIT), _line(_tool_use("push")), (1.0, b"")])
    r = ProviderRouter(providers={p.name: p}, quota=QuotaTracker())
    r.call = AsyncMock(side_effect=AssertionError("role-chain fallback must NOT run"))
    cfg = ModelConfig(
        init_timeout_s=0.15, first_progress_s=0.05,
        idle_timeout_s=0.05, absolute_cap_s=2.0,
    )
    with pytest.raises(AllProvidersExhaustedError) as ei:
        await r.call_with_policy(
            "writer", "p", "s", {"preferred": {"provider": "claude-code"}}, cfg,
        )
    assert p.calls == 1, f"served provider ran {p.calls} times (double-execution)"
    assert ei.value.failure_class == "provider_idle_timeout"
    assert all(proc.killed for proc in p.procs)
    r.call.assert_not_awaited()


@pytest.mark.asyncio
async def test_policy_clean_failure_still_falls_back_to_the_role_chain():
    # Codex re-review #2 regression guard: an over-broad "raise on any executed
    # failure" wrongly suppressed genuine cross-provider fallback. A clean idle
    # (NO tool started -> side_effect "none") must fall through to self.call() so
    # a healthy role-chain provider (e.g. Codex) can still answer.
    from unittest.mock import AsyncMock

    p = _StreamCountingProvider([_line(INIT), (1.0, b"")])  # idle, no tool
    r = ProviderRouter(providers={p.name: p}, quota=QuotaTracker())
    fallback = ProviderResponse(text="codex answer", provider="codex",
                                model="codex", family="openai", latency_ms=0.0)
    r.call = AsyncMock(return_value=fallback)
    cfg = ModelConfig(
        init_timeout_s=0.15, first_progress_s=0.05,
        idle_timeout_s=0.05, absolute_cap_s=2.0,
    )
    text, provider, _meta = await r.call_with_policy(
        "writer", "p", "s", {"preferred": {"provider": "claude-code"}}, cfg,
    )
    assert text == "codex answer"
    assert provider == "codex"
    r.call.assert_awaited_once()  # fallback preserved


@pytest.mark.asyncio
async def test_policy_rate_limit_classification_survives_role_chain_exhaustion():
    # Codex re-review #3 regression: a policy provider that hit a REAL rate-limit
    # (classified via the real stream) then fell through to an exhausted role
    # chain must NOT downgrade to a generic notice — the aggregate keeps the
    # rate-limit failure_class + retry_after so the user gets the honest message.
    from unittest.mock import AsyncMock

    # init, real 429 api_retry, then EOF (no recovery) -> provider_rate_limited
    p = _StreamCountingProvider([
        _line(INIT), _line(_api_retry("rate_limit", 429, 30000)),
    ])
    r = ProviderRouter(providers={p.name: p}, quota=QuotaTracker())
    # The role chain also exhausts, with NO class of its own.
    r.call = AsyncMock(side_effect=AllProvidersExhaustedError("role chain empty"))
    cfg = ModelConfig(init_timeout_s=0.15, first_progress_s=0.15,
                      idle_timeout_s=0.15, absolute_cap_s=2.0)
    with pytest.raises(AllProvidersExhaustedError) as ei:
        await r.call_with_policy(
            "writer", "p", "s", {"preferred": {"provider": "claude-code"}}, cfg,
        )
    assert ei.value.failure_class == "provider_rate_limited"
    assert ei.value.retry_after == 30.0
    r.call.assert_awaited_once()  # fallback WAS attempted


def test_tool_progress_and_heartbeats_keep_a_long_tool_turn_alive():
    # Blocker C: a turn emitting ONLY tool_progress / tool_heartbeat / status for
    # far longer than the idle interval is WORKING, not hung — it must survive,
    # and none of that heartbeat content is relayed into the reply.
    tool_progress = {"type": "tool_progress", "name": "build"}
    tool_hb = {"type": "system", "subtype": "tool_heartbeat"}
    status = {"type": "system", "subtype": "status", "text": "thinking"}
    items = [_line(INIT), _line(_tool_use("build"))]
    for _ in range(6):
        items.append((0.04, _line(tool_progress)))
        items.append((0.04, _line(tool_hb)))
        items.append((0.04, _line(status)))
    items.append((0.04, _line(_result("built"))))
    cfg = ModelConfig(
        init_timeout_s=0.2, first_progress_s=0.2, idle_timeout_s=0.1,
        absolute_cap_s=10.0,
    )
    resp = _run_stream(FakeStreamProcess(items), cfg)
    assert resp.text == "built"
    for word in ("thinking", "build", "tool_progress"):
        assert word not in resp.text


def test_legacy_timeout_does_not_reintroduce_a_total_wall_clock_deadline():
    # Blocker D: a tiny legacy ``timeout`` must NOT bound a progressing stream —
    # only the idle watchdog + generous absolute cap govern it. This turn streams
    # for ~0.8s, far past the 0.1s legacy timeout, and still completes.
    items = [_line(INIT)]
    for i in range(15):
        items.append((0.05, _line(_partial_text(str(i)))))
    items.append((0.05, _line(_result("finished"))))
    cfg = ModelConfig(
        timeout=0.1,  # legacy total timeout — must be IGNORED for streaming
        init_timeout_s=0.5, first_progress_s=0.5, idle_timeout_s=0.3,
        absolute_cap_s=30.0,
    )
    resp = _run_stream(FakeStreamProcess(items), cfg)
    assert resp.text == "finished"


@pytest.mark.asyncio
async def test_caller_cancellation_kills_the_subprocess_even_with_blocking_pipes():
    # Blocker E (stronger than the immediate-finish helper): stdout/stderr BLOCK
    # forever; a caller cancellation must still reach the finally and kill+reap
    # the subprocess (no leak).
    class _BlockingProc(FakeStreamProcess):
        def __init__(self):
            super().__init__([])

            class _Block:
                async def readline(self):
                    await asyncio.sleep(3600)
                    return b""

                async def read(self, _n):
                    await asyncio.sleep(3600)
                    return b""

            self.stdout = _Block()
            self.stderr = _Block()

    proc = _BlockingProc()
    provider = ClaudeProvider()
    cfg = ModelConfig(init_timeout_s=100, first_progress_s=100,
                      idle_timeout_s=100, absolute_cap_s=100)
    task = asyncio.create_task(provider._read_stream(proc, "p", cfg))
    await asyncio.sleep(0.05)  # let it start and block on readline
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.killed, "subprocess must be killed on caller-cancellation"

"""The codex reader streams under the idle-watchdog profile - parity with claude.

Founder rule 2026-08-29: *"a turn should continue till finished unless
interrupted by the user or should stop for some other reason."*

What happened: the universe was three clean GitHub round-trips into a five-step
job - main ref, create branch, read ``README.md`` for its blob sha - when the
served turn hit ``timeout=300`` in ``asyncio.wait_for(proc.communicate(...))``.
The generic ``ProviderTimeoutError`` put the provider on a 120s cooldown and the
user read *"Served provider 'codex' exhausted"* - a timer reported as a quota.

Claude's reader had already moved past this (``claude_provider._read_stream``):
an idle watchdog is the hang control, the absolute cap is a backstop, and
neither cools the provider. These tests hold codex to the same profile, plus the
one thing claude's reader does NOT yet do: a turn waiting on its own tool is not
idle (``run_graph`` took 42s live; a 30s idle budget would have killed it).
"""

from __future__ import annotations

import asyncio
import json
import time
import types

import pytest

from tinyassets.exceptions import (
    InteractiveDeadlineError,
    ProviderIdleTimeoutError,
    ProviderTimeoutError,
)
from tinyassets.providers.base import ModelConfig
from tinyassets.providers.codex_provider import _stream_codex_exec


class FakeProc:
    """Replays NDJSON stdout; ``(delay_s, bytes)`` items sleep before arriving."""

    def __init__(self, items, *, stderr: bytes = b"", returncode: int = 0):
        self._items = list(items)
        self._idx = 0
        # A RUNNING process has returncode None; ``_terminate`` only kills in
        # that state (a finished one raises ProcessLookupError). The exit code
        # is what ``wait()`` reveals, exactly like a real subprocess.
        self._exit = returncode
        self.returncode = None
        self.killed = False
        self.stdout = self._Stdout(self)
        self.stderr = self._Stderr(stderr)
        self.stdin = self._Stdin()

    class _Stdout:
        def __init__(self, p):
            self._p = p

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
        def __init__(self, data):
            self._data, self._sent = data, False

        async def read(self, _n):
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
        self.returncode = -9

    async def wait(self):
        # Like a real process: once stdout is exhausted the child has exited,
        # and wait() reveals its exit code. Without this the reader's
        # "closed stdout but did not exit" grace saw None and terminated a
        # child that had in fact finished.
        if self.returncode is None:
            self.returncode = self._exit
        return self.returncode


def _ev(etype: str, **fields) -> bytes:
    return (json.dumps({"type": etype, **fields}) + "\n").encode()


def _tool(etype: str, item_id: str = "call_1", kind: str = "mcp_tool_call") -> bytes:
    return _ev(etype, item={"id": item_id, "type": kind})


_PROFILE = dict(init_timeout_s=1.0, first_progress_s=1.0, idle_timeout_s=0.25,
                soft_slo_s=60.0, absolute_cap_s=5.0)


def _run(proc, **overrides):
    config = ModelConfig(timeout=300, **{**_PROFILE, **overrides})
    return asyncio.run(
        _stream_codex_exec(proc, b"prompt", config, start=time.monotonic())
    )


# --- a turn waiting on its own tool is not idle -------------------------------


def test_a_tool_call_longer_than_the_idle_budget_does_not_kill_the_turn():
    """The case that would have made the new reader WORSE than the 300s cap."""
    proc = FakeProc([
        _ev("thread.started"),
        _tool("item.started"),                 # run_graph begins...
        (0.7, _tool("item.completed")),        # ...answers after 0.7s > idle 0.25
        _ev("item.completed", item={"type": "agent_message", "text": "done"}),
        _ev("turn.completed", usage={"input_tokens": 1, "output_tokens": 1}),
    ])
    out, _err = _run(proc)
    assert b"turn.completed" in out
    assert proc.killed is False


def test_idle_with_no_tool_in_flight_fires_the_watchdog():
    proc = FakeProc([
        _ev("thread.started"),
        (0.7, _ev("turn.completed")),          # silence with nothing running
    ])
    with pytest.raises(ProviderIdleTimeoutError) as info:
        _run(proc)
    assert proc.killed is True
    assert info.value.failure_class == "provider_idle_timeout"
    assert info.value.attempt_telemetry["tool_phase"] is None


def test_the_idle_watchdog_resumes_once_the_tool_completes():
    """Tool-wait suspends idle; it must not disable it for the rest of the turn."""
    proc = FakeProc([
        _ev("thread.started"),
        _tool("item.started"),
        (0.4, _tool("item.completed")),        # tool done
        (0.7, _ev("turn.completed")),          # then a real hang
    ])
    with pytest.raises(ProviderIdleTimeoutError):
        _run(proc)


# --- the cap is a backstop, and it is classified honestly ---------------------


def test_progressing_past_the_absolute_cap_is_an_interactive_deadline():
    """Still working, out of runway: NOT the generic timeout the router cools on."""
    proc = FakeProc([(0.1, _ev("item.started", item={"type": "agent_message"}))
                     for _ in range(20)])
    with pytest.raises(InteractiveDeadlineError) as info:
        _run(proc, absolute_cap_s=0.45)
    assert info.value.failure_class == "interactive_deadline"
    assert isinstance(info.value, ProviderTimeoutError), (
        "must stay a ProviderTimeoutError subclass for legacy except clauses"
    )
    assert proc.killed is True


def test_a_finished_turn_returns_stdout_and_stderr_unchanged():
    """Downstream parsing (agent_message / usage) must see exactly what codex wrote."""
    lines = [
        _ev("thread.started"),
        b"\n",                                  # blank lines are not events
        _ev("item.completed", item={"type": "agent_message", "text": "hi"}),
        _ev("turn.completed", usage={"input_tokens": 3, "output_tokens": 2}),
    ]
    proc = FakeProc(lines, stderr=b"warning: something")
    out, err = _run(proc)
    assert out == b"".join(lines)
    assert err == b"warning: something"
    assert proc.killed is False


def test_non_json_output_keeps_the_process_but_not_the_clock():
    """Chatter proves the process is alive, not that it is making progress."""
    proc = FakeProc([
        _ev("thread.started"),
        (0.15, b"not json\n"),
        (0.15, b"still not json\n"),           # 0.3s since the last real event
        (0.15, _ev("turn.completed")),         # never reached: idle at 0.25
    ])
    with pytest.raises(ProviderIdleTimeoutError):
        _run(proc)


# --- the served turn gets the generous cap, not the library default -----------


def test_the_served_turn_is_bounded_by_a_generous_backstop_not_a_deadline():
    from tinyassets.universe_intelligence import (
        _SERVED_ABSOLUTE_CAP_S,
        _sandboxed_config,
    )

    ctx = types.SimpleNamespace(config=types.SimpleNamespace(timeout=300))
    cfg = _sandboxed_config(ctx, granted=True)
    profile = cfg.stream_timeout_profile()
    assert _SERVED_ABSOLUTE_CAP_S >= 3600, "a five-step GitHub job must fit"
    assert profile.absolute_cap_s == _SERVED_ABSOLUTE_CAP_S
    assert profile.idle_s == 30.0, "the hang control stays fast"


def test_a_universe_may_override_its_own_knobs():
    from tinyassets.universe_intelligence import _sandboxed_config

    ctx = types.SimpleNamespace(
        config=types.SimpleNamespace(timeout=300, absolute_cap_s=120, idle_timeout_s=10)
    )
    profile = _sandboxed_config(ctx, granted=True).stream_timeout_profile()
    assert profile.absolute_cap_s == 120.0
    assert profile.idle_s == 10.0


def test_a_nonsense_override_falls_back_rather_than_disabling_the_cap():
    from tinyassets.universe_intelligence import (
        _SERVED_ABSOLUTE_CAP_S,
        _sandboxed_config,
    )

    ctx = types.SimpleNamespace(
        config=types.SimpleNamespace(timeout=300, absolute_cap_s="forever")
    )
    profile = _sandboxed_config(ctx, granted=True).stream_timeout_profile()
    assert profile.absolute_cap_s == _SERVED_ABSOLUTE_CAP_S


# --- the real vocabulary, recorded from codex-cli 0.146.0 on 2026-08-29 -------


def _real_codex_events():
    """Exactly the event shapes `codex exec --json` emitted for a prompt that ran
    `echo hi` then replied "done" (timings 0.46s .. 8.93s, progressive)."""
    return [
        _ev("thread.started", thread_id="thr_abc"),
        _ev("turn.started"),
        _ev("item.completed",
            item={"id": "item_0", "type": "agent_message", "text": "Running it."}),
        _ev("item.started",
            item={"id": "item_1", "type": "command_execution", "command": "echo hi"}),
        _ev("item.completed",
            item={"id": "item_1", "type": "command_execution", "exit_code": 0}),
        _ev("item.completed", item={"id": "item_2", "type": "agent_message", "text": "done"}),
        _ev("turn.completed", usage={"input_tokens": 10, "output_tokens": 4}),
    ]


def test_the_real_codex_vocabulary_streams_through_and_the_tool_key_matches():
    """Guards the one P0 a wrong event name would cause: if the reader did not
    recognise codex's real events as liveness, `first_progress_s` would kill
    EVERY served turn. Recorded from the installed CLI, not from memory."""
    ev = _real_codex_events()
    # Put the whole tool call beyond the idle budget; it must survive because
    # item_1's started/completed share an id and the wait is a tool wait.
    items = ev[:3] + [ev[3], (0.6, ev[4])] + ev[5:]
    proc = FakeProc(items)
    out, _ = _run(proc)
    assert out == b"".join(ev)
    assert proc.killed is False


def test_a_tool_that_never_completes_is_still_bounded_by_the_cap():
    """The known cost of the tool-in-flight rule: a wedged tool waits for the
    absolute cap, not the idle budget. Acceptable interim; must stay bounded."""
    ev = _real_codex_events()
    proc = FakeProc(ev[:4] + [(5.0, ev[6])])   # item_1 never completes, then silence
    with pytest.raises(InteractiveDeadlineError):
        _run(proc, absolute_cap_s=0.5)
    assert proc.killed is True


def test_an_ungranted_turn_keeps_the_library_cap():
    """Codex round 2 (P1): the synchronous learning extractor calls
    _sandboxed_config with the defaults and runs BEFORE the reply is returned,
    so a generous cap there could withhold an already-generated reply."""
    from tinyassets.providers.base import DEFAULT_ABSOLUTE_CAP_S
    from tinyassets.universe_intelligence import _sandboxed_config

    ctx = types.SimpleNamespace(config=types.SimpleNamespace(timeout=300))
    profile = _sandboxed_config(ctx).stream_timeout_profile()
    assert profile.absolute_cap_s == DEFAULT_ABSOLUTE_CAP_S


# --- round-2 findings on the tool rule -----------------------------------------


def test_a_wedged_tool_is_bounded_by_the_tool_wait_not_the_cap(monkeypatch):
    """Codex round 2 (P1): "not idle until the absolute cap" turned a silent
    wedge into an hour-long wait. The tool allowance is now bounded."""
    from tinyassets.providers import codex_provider

    monkeypatch.setattr(codex_provider, "_TOOL_WAIT_S", 0.3)
    ev = _real_codex_events()
    proc = FakeProc(ev[:4] + [(5.0, ev[6])])   # tool opens, then silence
    with pytest.raises(ProviderIdleTimeoutError) as info:
        _run(proc, absolute_cap_s=60.0)         # the cap is NOT what fires
    assert info.value.attempt_telemetry["tool_phase"] == "in_tool"
    assert proc.killed is True


def test_a_recoverable_error_event_does_not_clear_an_open_tool():
    """Codex round 3 (P1): codex 0.146 emits a top-level `error` for a
    notification whose will_retry is true - the JSONL projection drops the
    flag - while the turn stays Running and the tool is still coming back.
    Clearing the tool on it re-armed idle mid-retry and killed a healthy turn."""
    proc = FakeProc([
        _ev("thread.started"),
        _tool("item.started"),
        _ev("error", message="transient upstream hiccup"),
        (0.7, _tool("item.completed")),         # retry succeeds after 0.7s
        _ev("turn.completed", usage={"input_tokens": 1, "output_tokens": 1}),
    ])
    out, _ = _run(proc)                          # idle is 0.25; must survive
    assert b"turn.completed" in out
    assert proc.killed is False


def test_a_terminal_failure_event_rearms_the_idle_watchdog():
    """`turn.failed` while a tool is open: the tool is not coming back, so
    idle resumes instead of waiting out the tool allowance. (Only turn.failed:
    see the recoverable `error` test above.)"""
    proc = FakeProc([
        _ev("thread.started"),
        _tool("item.started"),
        _ev("turn.failed", error={"message": "boom"}),
        (0.7, _ev("turn.completed")),           # idle (0.25) fires first
    ])
    with pytest.raises(ProviderIdleTimeoutError):
        _run(proc)


# --- round-2 findings that need a REAL subprocess ------------------------------


def _child(code: str):
    """A real asyncio subprocess running `python -c code`, with the reader limit."""
    import sys

    from tinyassets.providers.codex_provider import _STDOUT_READER_LIMIT

    return asyncio.create_subprocess_exec(
        sys.executable, "-c", code,
        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE, limit=_STDOUT_READER_LIMIT,
    )


def test_a_single_event_longer_than_64k_streams_intact():
    """Codex round 2 (P1): asyncio's default 64 KiB line limit raised on one
    70,000-char event. A GET /contents result is the base64 of a whole file."""
    big = "x" * 70_000
    # Built INSIDE the child: a 70 KB `python -c` argv is over the Windows
    # command-line limit (WinError 206), which is a test artefact, not the bug.
    code = (
        "import json,sys;"
        "sys.stdout.write(json.dumps({'type':'item.completed','item':{'id':'i',"
        "'type':'agent_message','text':'x'*70000}})+'\\n');"
        "sys.stdout.write(json.dumps({'type':'turn.completed','usage':{}})+'\\n');"
        "sys.stdout.flush()"
    )

    async def go():
        proc = await _child(code)
        return await _stream_codex_exec(
            proc, b"", ModelConfig(timeout=30, **_PROFILE), start=time.monotonic(),
        )
    out, _ = asyncio.run(go())
    assert big.encode() in out
    assert b"turn.completed" in out


def test_stdout_eof_with_a_live_child_ends_the_child_and_leaks_no_task():
    """Codex round 2 (P1): a child that closes fd 1 and keeps running used to
    leave returncode=None, a live orphan and a pending stderr task."""
    code = (
        "import sys,os,time,json;"
        "sys.stdout.write(json.dumps({'type':'thread.started'})+'\\n');sys.stdout.flush();"
        "os.close(1);time.sleep(30)"
    )

    async def go():
        proc = await _child(code)
        t0 = time.monotonic()
        out, _ = await _stream_codex_exec(
            proc, b"", ModelConfig(timeout=30, **_PROFILE), start=t0,
        )
        pending = [t for t in asyncio.all_tasks()
                   if t is not asyncio.current_task() and not t.done()]
        return out, proc.returncode, time.monotonic() - t0, pending
    out, rc, elapsed, pending = asyncio.run(go())
    assert b"thread.started" in out
    assert rc is not None, "child left running behind a returned reader"
    assert elapsed < 15, f"took {elapsed:.1f}s; EOF grace is bounded"
    assert pending == [], f"leaked tasks: {pending}"


# --- the P0: only the JSON path streams ----------------------------------------


def test_only_the_json_path_streams_and_the_legacy_path_is_verbatim():
    """Codex round 2 (P0): `--json` is added only when sandbox_workspace is set,
    so a plain-text call has no events to reset a watchdog on; streaming it
    killed every long non-served call on the 10s init budget. Structural pin:
    the stream reader sits under the machine_accounting branch and the legacy
    communicate()+wait_for(config.timeout) survives beside it."""
    import inspect

    from tinyassets.providers import codex_provider

    src = inspect.getsource(codex_provider)
    call_site = src.split("if machine_accounting:\n", 1)[1][:1600]
    assert "await _stream_codex_exec(" in call_site
    assert "proc.communicate(input=full_input.encode" in call_site
    assert "timeout=config.timeout," in call_site


# --- round 3: a caller's cancellation must survive the cleanup -----------------


def test_a_callers_cancellation_propagates_through_the_reap():
    """Codex round 3 (P1): `suppress(BaseException)` around the bounded reap
    swallowed a CancelledError delivered during the gather, so the caller got
    `(b'', b'')` back instead of its cancellation. Reproduced with an stderr
    drain that resists its first cancel, so the reap is still in progress when
    the caller cancels."""

    class _ResistantStderr:
        def __init__(self):
            self.resisted = False

        async def read(self, _n):
            try:
                await asyncio.sleep(3600)
            except asyncio.CancelledError:
                if not self.resisted:
                    self.resisted = True
                    await asyncio.sleep(3600)   # ignore the first cancel
                raise
            return b""

    async def go():
        proc = FakeProc([_ev("thread.started"), _ev("turn.completed")])
        proc.stderr = _ResistantStderr()
        task = asyncio.create_task(_stream_codex_exec(
            proc, b"", ModelConfig(timeout=30, **_PROFILE), start=time.monotonic(),
        ))
        # EOF is immediate; the 2s stderr grace then the reap follow. Cancel
        # while the reap's bounded gather is in flight.
        await asyncio.sleep(2.6)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            return "cancelled"
        return "returned"

    assert asyncio.run(go()) == "cancelled"

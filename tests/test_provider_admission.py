"""The bound between 40 concurrent handlers and a 189 MB subprocess each.

Measured 2026-08-28. Each turn spawns a provider CLI at ~189 MB RSS / ~77 MB PSS, floor,
and the container has no memory limit, so an overshoot OOMs the HOST and takes the
Cloudflare tunnel with it — a total outage rather than a slow service.

The pre-existing ceiling was **8**, not the 40 I first claimed: `converse` reaches
providers through `call_provider` -> `ProviderRouter.call_sync`, which runs on a thread
pool of `_SYNC_CALL_MAX_WORKERS = 8`. That 8 is incidental — its own comment gives a
latency rationale — so raising it for throughput, exactly what chasing capacity does,
would multiply memory risk with nothing to warn you.
"""

from __future__ import annotations

import threading
import time

import pytest

from tinyassets import provider_admission as pa


@pytest.fixture(autouse=True)
def _reset():
    pa.reset_for_tests()
    yield
    pa.reset_for_tests()


def test_concurrency_never_exceeds_the_limit(monkeypatch):
    monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "3")
    monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "10")
    live, peak, lock = [0], [0], threading.Lock()
    start = threading.Barrier(12)

    def worker():
        start.wait()
        try:
            with pa.provider_slot():
                with lock:
                    live[0] += 1
                    peak[0] = max(peak[0], live[0])
                time.sleep(0.05)
                with lock:
                    live[0] -= 1
        except pa.ProviderBusy:
            pass

    ts = [threading.Thread(target=worker) for _ in range(12)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    assert peak[0] <= 3, f"{peak[0]} concurrent provider calls with a limit of 3"


def test_it_refuses_rather_than_hanging_when_saturated(monkeypatch):
    """Hard Rule 8. A refusal a user can retry beats an OOM that takes everyone down."""
    monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
    monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "0.05")
    with pa.provider_slot():
        with pytest.raises(pa.ProviderBusy) as exc:
            with pa.provider_slot():
                pass
    assert "busy" in str(exc.value).lower()
    assert "try again" in str(exc.value).lower(), "a refusal must say what to do next"


def test_a_slot_is_released_when_the_call_raises(monkeypatch):
    """A slot leaked on an error is permanent capacity loss — and errors happen
    precisely when the system is already under load."""
    monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
    monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "0.05")
    with pytest.raises(ValueError):
        with pa.provider_slot():
            raise ValueError("provider blew up")
    with pa.provider_slot():  # must not raise ProviderBusy
        pass


def test_a_waiter_is_admitted_when_a_slot_frees(monkeypatch):
    """Bounding must not mean refusing everyone under transient load."""
    monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
    monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "5")
    admitted = []

    def waiter():
        with pa.provider_slot():
            admitted.append(True)

    holder_done = threading.Event()

    def holder():
        with pa.provider_slot():
            time.sleep(0.1)
        holder_done.set()

    h = threading.Thread(target=holder)
    h.start()
    time.sleep(0.02)
    w = threading.Thread(target=waiter)
    w.start()
    h.join(timeout=10)
    w.join(timeout=10)
    assert admitted == [True], "a waiter was refused even though a slot freed up"


def test_the_default_fits_the_box_it_runs_on(monkeypatch):
    """Sized from memory, not from a thread count.

    The pre-existing ceiling was the router's `_SYNC_CALL_MAX_WORKERS = 8` thread pool
    — incidental, since its own comment gives a latency rationale, so raising it for
    throughput would have multiplied memory risk invisibly. This bound is explicitly
    about the ~77 MB each subprocess costs.
    """
    monkeypatch.delenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", raising=False)
    from tinyassets.providers import router

    assert pa._DEFAULT_LIMIT <= router._SYNC_CALL_MAX_WORKERS, (
        "a bound above the thread pool that already gates these calls would never bind"
    )
    assert pa._DEFAULT_LIMIT * 77 + 390 < 2048, (
        "the default must fit the 2 GB box alongside the ~390 MB daemon"
    )


def test_a_bad_limit_falls_back_rather_than_disabling_the_bound(monkeypatch):
    for bad in ("0", "-5", "banana", ""):
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", bad)
        assert pa._positive_int(pa._LIMIT_VAR, pa._DEFAULT_LIMIT) == pa._DEFAULT_LIMIT


class TestTurnDurationInstrumentation:
    """The missing half of every users-per-box claim.

    Capacity in USERS is `slots / turn_duration`. Slots were knowable; turn duration was
    not recorded anywhere — `run_events.started_at/finished_at` sit microseconds apart
    with one event per run, so they are bookkeeping, not execution spans. This context
    manager brackets exactly the provider subprocess's lifetime, which makes it the one
    honest place to measure it.
    """

    def test_it_records_how_long_a_turn_held_its_slot(self):
        with pa.provider_slot():
            time.sleep(0.05)
        snap = pa.admission_snapshot()
        assert snap["admitted"] == 1
        assert snap["samples"] == 1
        assert snap["attempt_seconds"]["p50"] >= 0.04

    def test_a_failed_turn_is_still_timed(self):
        """A turn that dies after 40 s occupied a slot for 40 s. Excluding failures
        would flatter the numbers in exactly the conditions worth measuring."""
        with pytest.raises(ValueError):
            with pa.provider_slot():
                time.sleep(0.05)
                raise ValueError("provider died")
        assert pa.admission_snapshot()["samples"] == 1

    def test_it_publishes_no_derived_throughput_figure(self, monkeypatch):
        """It used to report `limit / p50` as sustainable throughput. That is wrong
        twice over (Codex, 2026-08-28): Little's Law wants effective concurrency over
        MEAN service time, not a limit over a median; and these samples are provider
        ATTEMPTS, so a fallback chain or judge ensemble contributes several per user
        turn. A number that reads authoritative and is not is worse than no number."""
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "10")
        with pa.provider_slot():
            time.sleep(0.02)
        snap = pa.admission_snapshot()
        assert "sustainable_turns_per_second" not in snap
        assert snap["sample_unit"] == "provider attempt, not user turn"
        assert "mean" in snap["attempt_seconds"], "Little's Law needs the mean"

    def test_refusals_are_counted_separately_from_turns(self, monkeypatch):
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
        monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "0.05")
        with pa.provider_slot():
            with pytest.raises(pa.ProviderBusy):
                with pa.provider_slot():
                    pass
        snap = pa.admission_snapshot()
        assert snap["refused"] == 1
        assert snap["admitted"] == 1, "a refusal must not count as a turn"

    def test_peak_concurrency_is_observed_not_assumed(self, monkeypatch):
        """Whether the bound actually binds is a fact about production, not a setting."""
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "4")
        monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "10")
        start = threading.Barrier(3)

        def worker():
            start.wait()
            with pa.provider_slot():
                time.sleep(0.08)

        ts = [threading.Thread(target=worker) for _ in range(3)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=30)
        assert pa.admission_snapshot()["peak_concurrent"] == 3

    def test_the_sample_buffer_is_bounded(self):
        """An unbounded list on a hot path is a leak, and this one is on every turn."""
        for _ in range(pa._MAX_SAMPLES + 50):
            with pa.provider_slot():
                pass
        assert pa.admission_snapshot()["samples"] <= pa._MAX_SAMPLES

    def test_live_returns_to_zero(self):
        """A live counter that drifts up makes the bound look saturated forever."""
        for _ in range(5):
            with pa.provider_slot():
                pass
        with pytest.raises(ValueError):
            with pa.provider_slot():
                raise ValueError("boom")
        assert pa.admission_snapshot()["live"] == 0


class TestTheAsyncSlotDoesNotStallItsOwnLoop:
    """Codex REJECT 2026-08-28, finding 2 — the one that made the cure worse.

    A blocking `acquire()` inside async router code stalls the event loop, so a waiter
    prevents the very holder it is waiting for from finishing. Reproduced with limit 1,
    a 200 ms wait and 10 ms of admitted work: `[0.201, 'ProviderBusy']`. It reaches
    production through `call_judge_ensemble`, which gathers admission-taking tasks onto
    one loop.
    """

    def test_two_coroutines_on_one_loop_do_not_refuse_each_other(self, monkeypatch):
        import asyncio

        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "1")
        monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "2")

        async def one():
            async with pa.provider_slot_async():
                await asyncio.sleep(0.01)
            return "ok"

        async def main():
            return await asyncio.gather(one(), one(), return_exceptions=True)

        got = asyncio.run(main())
        assert got == ["ok", "ok"], (
            f"a waiter starved the holder on the same loop: {got}"
        )


class TestTheBoundActuallyBindsInTheRouter:
    """Codex REJECT 2026-08-28, finding 6 — my unit tests were decorative.

    Codex replaced every router admission context with `nullcontext`, disabling
    enforcement completely, and all 13 tests still passed. They proved the primitive
    worked and said nothing about production using it. This asserts the wiring at the
    place the mutant attacked.
    """

    def test_every_provider_dispatch_is_inside_the_bound(self):
        import pathlib

        from tinyassets.providers import router

        src = pathlib.Path(router.__file__).read_text(encoding="utf-8")
        dispatches = src.count("resp = await provider.complete(")
        guarded = src.count("async with _provider_slot(")
        assert dispatches > 0
        assert guarded == dispatches, (
            f"{dispatches} provider dispatches but {guarded} inside the bound — an "
            "unguarded dispatch spawns a subprocess the limit never counted"
        )
        assert "with _provider_slot(" not in src.replace("async with _provider_slot(", ""), (
            "a SYNC slot in async router code stalls the event loop"
        )

    def test_a_busy_refusal_is_not_charged_as_a_provider_failure(self):
        """Finding 1: acquiring after `before_provider_launch` meant a refusal
        abandoned the budget, cooled a provider that never started, and reached the
        caller as AllProvidersExhaustedError instead of an actionable 'busy'."""
        import pathlib

        from tinyassets.providers import router

        src = pathlib.Path(router.__file__).read_text(encoding="utf-8")
        body = src.split("async with _provider_slot(", 1)[1][:900]
        assert "before_launch()" in body, (
            "before_provider_launch must happen INSIDE the slot, or a refusal charges "
            "a launch that never occurred"
        )
        assert "except _ProviderBusy:" in src, "a busy refusal must propagate, not be classified"


class TestTheLifecycleGapsCodexFound:
    """Codex REJECT 2026-08-28, findings 3 and 4 — a slot freed while its subprocess
    lived, and a real `codex exec` that spawned outside the bound entirely."""

    def test_cancellation_kills_the_subprocess_it_accounted_for(self):
        """Reproduced as `{'slot_live': 0, 'subprocess_killed': False}`: the slot came
        back while the ~189 MB process was still running, so the bound drifted further
        from reality with every cancellation until the box ran out of memory it
        believed was free."""
        import pathlib

        from tinyassets.providers import codex_provider

        src = pathlib.Path(codex_provider.__file__).read_text(encoding="utf-8")
        body = src.split("timeout=config.timeout,", 1)[1][:1400]
        assert "except BaseException:" in body, (
            "only asyncio.TimeoutError was cleaned up; cancellation is the case that "
            "actually happens, and CancelledError is a BaseException"
        )
        # It must actually kill, not merely re-raise.
        after = body.split("except BaseException:", 1)[1]
        assert "_terminate(proc)" in after

    def test_an_already_dead_process_does_not_mask_the_real_exception(self):
        """`proc.kill()` on a finished process raises ProcessLookupError on POSIX,
        which would replace CancelledError with something confusing."""
        from tinyassets.providers.codex_provider import _terminate

        class _Dead:
            returncode = 0

            def kill(self):
                raise ProcessLookupError("already reaped")

        _terminate(_Dead())  # must not raise

    def test_the_auth_probe_is_single_flighted_for_real(self, monkeypatch):
        """A bare lock only SERIALIZES. Codex reproduced two simultaneous misses
        spawning two probes 81 ms apart, because the second took the lock after the
        first released and then ran its own. The second caller has to wait for the
        first's ANSWER."""
        import threading as _t

        from tinyassets.providers import base

        base._auth_probe_memo.invalidate()
        calls, lock = [], _t.Lock()

        def slow_probe(timeout_s):
            with lock:
                calls.append(1)
            time.sleep(0.05)
            return {"status": "ok", "detail": "fake"}

        monkeypatch.setattr(base, "_codex_live_auth_probe_uncached", slow_probe)
        start = _t.Barrier(6)
        out = []

        def worker():
            start.wait()
            out.append(base._codex_live_auth_probe(1.0))

        ts = [_t.Thread(target=worker) for _ in range(6)]
        for t in ts:
            t.start()
        for t in ts:
            t.join(timeout=30)
        assert len(out) == 6, "every caller must get an answer"
        assert len(calls) == 1, (
            f"{len(calls)} probes for 6 simultaneous callers — serialized, not "
            "single-flighted; each spawns a real ~189 MB codex exec"
        )
        base._auth_probe_memo.invalidate()


class TestTheBoundBindsBehaviourally:
    """Codex beat my source-shape assertions TWICE.

    First with a `nullcontext` plugin, then by replacing the router's imported
    `_provider_slot` at runtime with an async no-op: two judge providers overlapped at
    `peak=2` under limit 1, admission reported `admitted=0`, and all 19 tests still
    passed. Source counting cannot see a runtime swap. This drives the real router and
    asserts the ADMISSION LEDGER moved — which no substitution can fake.
    """

    def test_a_real_router_call_holds_a_slot_during_the_provider_call(self, monkeypatch):
        """Constructs a real ProviderRouter and awaits a real dispatch.

        Three weaker versions lost to Codex first: a `nullcontext` plugin, a runtime
        replacement of the module attribute, and finally a LOCAL shadow of
        `_provider_slot` inside each dispatch method — which defeats source counting
        AND `router._provider_slot is provider_slot_async`, because both still look
        right. My previous attempt exercised the primitive and never entered the router
        at all, so it passed the shadow mutant too.

        The only thing a bypass cannot fake is the ledger moving while the provider is
        executing, so that is what this asserts, from inside `complete()` on a real
        router call.
        """
        import asyncio

        from tinyassets.providers.base import ModelConfig, ProviderResponse
        from tinyassets.providers.router import ProviderRouter

        pa.reset_for_tests()
        seen = {}

        class _Observing:
            name = "codex"
            family = "openai"

            async def complete(self, prompt, system, config, *, universe_dir=None):
                seen["live"] = pa.admission_snapshot()["live"]
                return ProviderResponse(
                    text="ok", provider="codex", model="fake", family="openai",
                )

        router = ProviderRouter(providers={"codex": _Observing()})
        asyncio.run(router.call_judge_ensemble("p", "s", ModelConfig()))

        # Deliberately NOT a skip on failure: a test that opts out when it cannot reach
        # the provider is the same decorative failure in a new costume.
        assert "live" in seen, "the router never reached the provider; test proves nothing"
        assert seen["live"] >= 1, (
            "a real router dispatch executed the provider while the admission ledger "
            "showed no slot held — the bound is bypassed on this path"
        )

    def test_nested_work_may_use_the_reserve_that_outer_turns_cannot(self, monkeypatch):
        """Codex round 3: my deferral of nested starvation was not defensible, because
        `run_graph` children already carry a typed `provider_invocation` carrier — the
        distinction is available exactly where it is needed. Six outer holders produced
        six AllProvidersExhaustedError and zero nested launches."""
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "2")
        monkeypatch.setenv("TINYASSETS_PROVIDER_NESTED_RESERVE", "1")
        monkeypatch.setenv("TINYASSETS_PROVIDER_ADMISSION_WAIT_S", "0.05")

        with pa.provider_slot():  # one outer turn: outer limit is 2-1 = 1
            with pytest.raises(pa.ProviderBusy):
                with pa.provider_slot():  # a second OUTER turn must be refused
                    pass
            with pa.provider_slot(nested=True):  # its child may use the reserve
                pass

    def test_the_reserve_can_never_starve_outer_turns_entirely(self, monkeypatch):
        """A reserve at or above the limit would refuse every user turn to protect
        children that only exist because a turn ran."""
        monkeypatch.setenv("TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS", "2")
        monkeypatch.setenv("TINYASSETS_PROVIDER_NESTED_RESERVE", "99")
        assert pa._effective_limit(nested=False) >= 1
        with pa.provider_slot():
            pass

    def test_a_carrier_bearing_call_is_recognised_as_nested(self):
        """The router decides nested-ness from the carrier; if that reading breaks, the
        reserve silently stops applying and the starvation returns."""
        from tinyassets.providers.router import _is_nested

        class _Ctx:
            provider_invocation = object()

        class _Plain:
            provider_invocation = None

        assert _is_nested(_Ctx()) is True
        assert _is_nested(_Plain()) is False
        assert _is_nested(None) is False

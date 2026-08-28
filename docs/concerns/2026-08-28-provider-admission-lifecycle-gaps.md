# Provider admission does not yet bound the provider-process lifecycle

**Filed:** 2026-08-28
**Verified:** 2026-08-28, Windows local checkout at `5797ff62`; focused inline
reproductions plus `python -m pytest tests/test_provider_admission.py -q`
**Severity:** P1

## Source (verbatim)

> `ProviderBusy` is swallowed and converted into provider failure/cooldown after
> launch bookkeeping has already begun; Codex cancellation releases the admission
> slot without killing the subprocess; synchronous acquisition can block an async
> event loop; and the real Codex auth probe spawns outside this bound. Therefore the
> current router-level semaphore is not yet a bound on live provider subprocesses.

## Re-verification

The adversarial cross-family review re-checked the committed implementation, not the
proposal text. Claude independently returned `ADAPT` and identified the first two
router defects below as minimum fixes. Local review found the remaining lifecycle and
coverage defects.

1. `tinyassets/providers/router.py:910-916` runs `before_provider_launch()` before
   admission. A refusal is caught at `:920`, abandons a served reservation at
   `:936-940` or settles a carrier `INDETERMINATE` at `:956-959`, then the generic
   handler at `:1091-1099` cools the provider and hides `ProviderBusy`. Reproduction
   with a held limit-1 slot returned `AllProvidersExhaustedError` advising the caller
   to clear `TINYASSETS_PIN_WRITER`; the provider was never launched.
2. `tinyassets/providers/codex_provider.py:515-520` kills/reaps only
   `asyncio.TimeoutError`; it has no cancellation/unexpected-exception `finally`.
   Cancelling a fake in-flight `communicate()` under `provider_slot()` produced
   `{'slot_live': 0, 'subprocess_killed': False}`.
3. `tinyassets/provider_admission.py:168` performs a blocking
   `threading.BoundedSemaphore.acquire()` inside async router methods. Two coroutines
   with limit 1, a 200 ms admission wait, and a 10 ms admitted sleep produced
   `[0.201, 'ProviderBusy']`: the waiter blocked the loop and prevented the holder
   from releasing. `call_judge_ensemble()` gathers such tasks at
   `tinyassets/providers/router.py:1709-1732`.
4. `tinyassets/providers/base.py:841-880` can run a real `codex exec` auth probe before
   router admission. The cache check/probe/write sequence at `:955-980` has no
   single-flight lock, so a concurrent cold/stale-auth burst can launch multiple
   probes outside the limit.
5. The focused test file never exercises a router call site or a provider subprocess
   lifecycle. A pytest plugin replacing `tinyassets.providers.router._provider_slot`
   with `contextlib.nullcontext` left all 13 tests green (`13 passed in 0.92s`).
6. Runtime limit changes replace the shared semaphore while old holders retain the old
   object (`tinyassets/provider_admission.py:91-100`). A limit-2 pair of holders,
   followed by a change to limit 1 and one new admission, reported `limit=1, live=3`.

The normal synchronous `converse` path does avoid one feared deadlock: fallbacks and
`_call_writer` retries are sequential, and its router event loop is private to one
worker. That does not close the defects above. The concern is resolved only when the
bound follows actual process lifetime on cancellation/errors, refusal remains a typed
non-provider failure before launch accounting, async callers cannot block their event
loop, out-of-router CLI probes are covered/single-flighted, and integration tests kill
the null-admission mutant.

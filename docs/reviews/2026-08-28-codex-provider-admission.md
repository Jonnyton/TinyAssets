# Codex cross-family review — provider admission bound (#2653)

Three rounds on Codex's own budget, 2026-08-28. Verdict trail:
**REJECT → REJECT → REJECT**, every finding reproduced rather than asserted, then a
mechanical re-verification of round 3's own reproductions.

Kept verbatim, the rounds that found real holes included. It caught a bug I
*introduced* while fixing round 1 (a permanent slot leak via `asyncio.to_thread`
cancellation), and beat my tests three times — the last by locally shadowing
`_provider_slot` inside each dispatch method, which defeats both source counting and
module-identity checks.

---

## Round 1

VERDICT: REJECT

The admission concept is necessary, but this implementation does not reliably bound live provider subprocesses.

DISAGREE_EVIDENCE

1. Admission refusal is swallowed and can consume budget without launching.

[router.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:910) performs `before_provider_launch()` before acquiring admission. `ProviderBusy` then follows the generic failure path: budget is abandoned/settled `INDETERMINATE` at [router.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:920), the provider is cooled at line 1091, and the actionable exception disappears.

Reproduction while holding a limit-1 slot returned:

```text
AllProvidersExhaustedError: Pinned writer ... clear TINYASSETS_PIN_WRITER
is_provider_busy False
```

The fake provider never launched. The cross-family Claude review independently identified this budget/cooldown defect.

2. The synchronous acquire can block an event loop.

[provider_admission.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/provider_admission.py:168) calls blocking `BoundedSemaphore.acquire()` from async router methods.

With limit 1, a 200 ms wait, and two coroutines whose admitted work slept 10 ms:

```text
[0.201, 'ProviderBusy']
```

The waiter blocked the loop, preventing the holder from completing its 10 ms sleep. This directly affects `call_judge_ensemble()`, which gathers admission-taking tasks on one loop at [router.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:1709). Two ensembles can reproduce it even with the default limit of 6.

3. Codex cancellation releases the slot while the subprocess remains alive.

[codex_provider.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/codex_provider.py:515) kills/reaps only `asyncio.TimeoutError`; there is no cancellation or unexpected-exception `finally`.

Cancelling a fake in-flight `communicate()` under `provider_slot()` produced:

```text
{'slot_live': 0, 'subprocess_killed': False}
```

Claude’s streaming implementation does have cancellation cleanup. The normal sync `converse` disconnect is generally shielded by AnyIO’s non-abandoning thread execution, so it wastes capacity until completion rather than releasing early. Direct async cancellation, shutdown, or unexpected Codex communication errors remain unsafe.

4. A production CLI path escapes the bound.

[base.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/base.py:841) runs a real `codex exec` authentication probe before router admission. Its cache-check/probe/write sequence has no single-flight lock, so concurrent stale-auth calls can spawn multiple probes outside the semaphore.

`ClaudeProvider.complete_json()` is another latent direct escape, although repository search found no production caller.

The router bound also counts HTTP/Ollama providers that spawn no CLI, so it is simultaneously incomplete and over-inclusive.

5. Runtime reconfiguration violates the advertised limit.

[provider_admission.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/provider_admission.py:91) replaces the semaphore while existing holders retain the old instance. Reproduction:

```text
{'limit': 1, 'live': 3, 'peak_concurrent': 3}
```

That came from two old limit-2 holders followed by one admission after changing the limit to 1.

6. The tests are decorative at the integration boundary.

Both commands passed all 13 tests:

```text
python -m pytest tests/test_provider_admission.py -q
python -m pytest -p output.provider_admission_mutant_plugin tests/test_provider_admission.py -q
```

The mutant replaces every router admission context with `nullcontext`, completely disabling production enforcement. See [provider_admission_mutant_plugin.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/output/provider_admission_mutant_plugin.py:1).

AGREE

- `_call_writer` retries and router fallback chains do not nest admission: each prior `with` exits first.
- Normal exceptions release the Python semaphore.
- Claude’s streaming subprocess cleanup tracks cancellation reasonably.
- The 512-entry sample buffer is memory-safe and its lock overhead is negligible.
- Six processes fit the stated PSS-floor arithmetic: `6×77+390=852 MB`.

DISAGREE_CONCERN

- Six is not justified from a `--version` floor. Using the supplied RSS numbers gives roughly 1.52 GB before the OS, tunnel, Docker, graph workers, page cache, and real-turn growth. Start lower or validate real-turn high-water PSS/RSS under six-way saturation.
- The pre-existing normal sync ceiling was 8, not 40, as now acknowledged in [provider_admission.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/provider_admission.py:12). The stale 40× claim remains in [test_provider_admission.py](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tests/test_provider_admission.py:1).
- A fixed 20-second wait does not bound end-to-end queueing: calls can first wait behind the eight-worker router pool. `ProviderBusy` should carry a request-relative deadline and must bypass provider cooldown/fallback logic.
- `limit / p50` is not sustainable throughput. Little’s Law requires approximately `effective_concurrency / mean_service_time`. These samples are provider attempts, not user turns; fallback and ensemble turns contribute multiple samples. Unlabelled fast failures inflate the figure, while long failures deflate it.
- An outer served CLI can invoke asynchronous `run_graph` and poll it while retaining its slot. Six such outer turns leave no slot for the graph provider calls. The 20-second timeout breaks a permanent deadlock by failing children, but the workload still starves.

The unresolved P1 is recorded in [2026-08-28-provider-admission-lifecycle-gaps.md](/C:/Users/Jonathan/Projects/wf-status-storage-cache/docs/concerns/2026-08-28-provider-admission-lifecycle-gaps.md:1).

---

## Round 2

VERDICT: REJECT

- **DISAGREE_EVIDENCE** — Busy refusal is still swallowed. [router.py:928](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:928) re-raises `ProviderBusy`, but the enclosing handler at [router.py:1114](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:1114) catches it as `Exception`, cools Codex, and eventually raises `AllProvidersExhaustedError`. Full served-request reproduction:

  `provider_calls=0`, reservation `('succeeded', 0, 0)`, cooldown `29s`, outcome `AllProvidersExhaustedError`.

  Token/cost reservation is released, but refusal propagation and no-cooldown behavior remain broken. The suppressed release exception at line 938 can also hide a failed release.

- **DISAGREE_EVIDENCE** — Async cancellation introduced a permanent slot leak. [provider_admission.py:225](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/provider_admission.py:225) cancels the await, not the `to_thread` worker. After the holder released, the abandoned worker acquired the slot:

  `waiter_body_entered=False, admitted=2, live=1, samples=1`.

  Through a real served request, it also left a never-launched reservation `indeterminate`; `provider_calls=0`.

- **DISAGREE_EVIDENCE** — Policy and ensemble branches still classify admission refusal as provider failure at [router.py:1399](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:1399) and [router.py:1740](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:1740). Saturation produced:

  `policy_outcome=AllProvidersExhaustedError, policy_cooldown=29`; judge returned `[]`, judge cooldown `29`; neither provider ran.

- **DISAGREE_EVIDENCE** — New mutant passes. I replaced the router’s imported `_provider_slot` at runtime with an async no-op. Under limit 1, two judge providers overlapped with `peak=2` and admission reported `admitted=0`; nevertheless all 19 tests in `test_provider_admission.py` passed. The source-count assertions at [test_provider_admission.py:263](C:/Users/Jonathan/Projects/wf-status-storage-cache/tests/test_provider_admission.py:263) remain decorative.

- **DISAGREE_EVIDENCE** — `_auth_probe_lock` serializes but does not single-flight. Two simultaneous cache misses at [base.py:882](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/base.py:882) spawned two probes sequentially, 81 ms apart. Admission itself works: with the sole slot occupied, the probe returned `inconclusive` and spawned nothing.

- **AGREE** — Async acquisition no longer blocks the event loop. Limit-1 coroutines returned `['ok', 'ok']`; the judge case returned both providers with peak 1. Two five-provider ensembles at limit 6 returned `[5,5]`, peak 6, zero refusals.

- **AGREE** — Cancellation after Codex has launched now gives `{'slot_live': 0, 'subprocess_killed': True}`.

- **AGREE** — Limit 2 → 1 drains correctly: the third caller was not admitted until both original holders had reduced live occupancy below the new limit.

- **AGREE** — `ClaudeProvider.complete_json()` currently has no production caller; repository search found only its definition, mirror, and one test. I found no other production provider-CLI launch escaping admission.

- **DISAGREE_EVIDENCE** — The raw attempt label is right, but the snapshot can still be internally misleading. One two-attempt user turn produced `p50=0.03`, `p90=0.01`, `p99=0.01` because the quantile indices at [provider_admission.py:177](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/provider_admission.py:177) are inconsistent. Also, [status.py:1498](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/api/status.py:1498) still claims turn duration is surfaced; it is not.

- **DISAGREE_CONCERN** — Nested starvation remains reachable: `run_graph` is exposed to the served CLI, while the outer subprocess holds its slot. Six outer holders produced six `AllProvidersExhaustedError`s and zero nested provider launches. Twenty seconds bounds the failed workload; it does not mitigate the starvation. The newly filed concern correctly records this.

- **AGREE** — Default 6 is defensible as an interim safety bound with substantial PSS-based headroom. It is not validated throughput or a proven safe maximum.

Verification: 434 passed, 4 skipped. `ruff` is red on [test_provider_admission.py:342](C:/Users/Jonathan/Projects/wf-status-storage-cache/tests/test_provider_admission.py:342) for E501.

I restored the durable P1 finding in [provider-admission-lifecycle-gaps.md](C:/Users/Jonathan/Projects/wf-status-storage-cache/docs/concerns/2026-08-28-provider-admission-lifecycle-gaps.md); those documentation changes are uncommitted.

---

## Round 3

VERDICT: REJECT

DISAGREE_EVIDENCE — judge saturation remains reproducible. [router.py:1761](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:1761) still reaches the broad classifier at [router.py:1775](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:1775) without a busy guard. Reproduction: `result=[]`, `provider_calls=0`, `cooldown=29s`. Served-request and policy paths correctly raised `ProviderBusy`, with zero calls and zero cooldown.

DISAGREE_EVIDENCE — auth single-flight works narrowly—six simultaneous misses spawned once—but production double-acquires admission at [base.py:876](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/base.py:876) and [base.py:922](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/base.py:922). Reproduction:

- Limit 1: zero spawns, false `inconclusive`, `admitted=1`, `refused=1`.
- Limit 2: one spawn, but `admitted=2`, `peak=2`.

The test hides this by replacing the entire uncached function at [test_provider_admission.py:349](C:/Users/Jonathan/Projects/wf-status-storage-cache/tests/test_provider_admission.py:349).

DISAGREE_EVIDENCE — a new mutant passed all 20 tests while disabling every router admission. It locally shadowed `_provider_slot` inside each dispatch method, preserving source counts and module identity. A real dispatch then observed `live=0`, `admitted=0`. The “behavioural” test defines a provider but never invokes it; `drive()` directly exercises the primitive at [test_provider_admission.py:406](C:/Users/Jonathan/Projects/wf-status-storage-cache/tests/test_provider_admission.py:406).

DISAGREE_CONCERN — nested starvation is real, but the stated deferral rationale is not fully defensible. `run_graph` child calls already carry typed `provider_invocation` authority at [foreground_run_provider.py:584](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/foreground_run_provider.py:584). Reserving one slot for carrier-backed calls is therefore a cheap mitigation for the currently reachable served-root → child topology. Arbitrary recursive nesting would still require propagated depth.

AGREE — cancellation no longer leaks; polling did not spin hot or lose capacity; quantiles were monotone at 1, 2, 3, and 10 samples.

The capped findings are recorded in [provider-admission-round-3.md](C:/Users/Jonathan/Projects/wf-status-storage-cache/docs/concerns/2026-08-28-provider-admission-round-3.md:1). Only concern documentation remains modified; the temporary mutant was removed. No fourth review.

---

## Re-verification (not a fourth round)

The three-round cap was reached. Codex was asked only whether its OWN round-3
reproductions still reproduce at `8b58f6fd`, explicitly not to review anything:

```
1. PASS — No longer reproduces: raises `ProviderBusy`; `provider_calls=0`, `cooldown=0s`.
2. PASS — Neither reproduces: limit-1 and limit-2 each spawned once with `admitted=1`, `refused=0`, `peak=1`, status `ok`.
3. PASS — No longer reproduces: shadow-mutant suite fails the behavioral test (`22 passed, 1 failed`).
4. PASS — Makes progress: five outer holders occupied the outer allowance; the carrier-backed child took slot 6 and completed.

VERDICT: APPROVE
```

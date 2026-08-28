# Codex cross-family review — sizing the concurrent-turn limit (#2657)

Two rounds, 2026-08-28. **REJECT → ADAPT.** I proposed raising the limit 6 → 10 as free
capacity. Codex refuted it and my own arithmetic was the reason: I reported an AVERAGE
as a MARGINAL cost, concluded page sharing improves with concurrency when my two data
points said the opposite, and budgeted headroom against installed RAM rather than
available. The change reverted to a no-op on the numbers, keeping only the corrected
analysis and a sizing test that no longer licenses what it was written to reject.

---

## Round 1 — REJECT

VERDICT: REJECT

Keep `_DEFAULT_LIMIT = 6` and `_SYNC_CALL_MAX_WORKERS = 8` until representative real-turn high-water is measured. The evidence does refute the original linear `77 MB × N` model, but it does not establish that 10 is safe.

### DISAGREE_EVIDENCE — the claimed marginal cost is arithmetically wrong

From the supplied points:

```text
(874 - 403) / (25 - 13) = 39.25 MB per additional process
```

The 31.44 MB value is the average `786 / 25`, not the marginal slope between the two measurements.

Worse, “25 consumed 786 MB” implies an idle `MemAvailable` of `403 + 786 = 1189 MB`. Against that baseline:

```text
13 processes consumed 315 MB = 24.23 MB/process average
next 12 consumed 471 MB = 39.25 MB/process marginal
```

The observed average increased with concurrency. These points do not demonstrate improving page sharing; if treated as one run, they indicate the opposite total-memory slope.

Reproduction:

```text
python -c "idle=403+786; print((idle-874)/13, (874-403)/(25-13), 786/25)"
# 24.230769... 39.25 31.44
```

That invalid conclusion is embedded at [provider_admission.py:45](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/provider_admission.py:45) and [environment-variables.md:52](/C:/Users/Jonathan/Projects/wf-status-storage-cache/docs/reference/environment-variables.md:52).

### DISAGREE_EVIDENCE — the safety test mixes incompatible baselines

The test at [test_provider_admission.py:118](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tests/test_provider_admission.py:118) computes:

```text
2048 - 390 - 10×31×3 = 728 MB remaining
```

But the probe implies only 1189 MB was available before launching anything. The other host consumption is therefore about:

```text
2048 - 1189 - 390 = 469 MB
```

That 469 MB—kernel, Docker, tunnel and other services—is absent from the test.

Using the probe’s actual baseline:

```text
1189 - 10×31×3 = 259 MB remaining
1189 - 10×39.25×3 = 11.5 MB remaining
```

Thus the proposed “3× headroom” nearly exhausts the box under the correctly derived two-point slope. It is not headroom.

### DISAGREE_EVIDENCE — `--version` does not represent the production process tree

A real turn launches `claude -p` with the system prompt, streaming protocol and tool policy at [claude_provider.py:454](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/claude_provider.py:454), and retains streamed output structures at [claude_provider.py:529](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/claude_provider.py:529).

When engine MCP is enabled, it also supplies a local MCP configuration at [claude_provider.py:407](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/claude_provider.py:407); that configuration starts another Python/FastMCP process, explicitly documented at [engine_mcp_server.py:1](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/engine_mcp_server.py:1). None of that exists under `claude --version`.

A 3× multiplier is therefore an unsupported guess over a different workload, not a conservative measurement.

Ten-millisecond polling is adequate to prove that 25 PIDs existed in one sample, but not that their resident-memory peaks were simultaneous. On 1 vCPU the sampler can also be delayed during a launch storm. Hold synchronized representative turns at steady state and measure the complete descendant trees.

`MemAvailable` is still the right system-level signal to include: the kernel defines it as an estimate of memory available for new applications without swapping, accounting for reclaimable cache, slab and watermarks. It is an estimate, not guaranteed capacity. Overcommit can also leave future untouched allocations invisible until pages are faulted. [Linux `/proc` documentation](https://www.kernel.org/doc/html/latest/filesystems/proc.html), [overcommit documentation](https://www.kernel.org/doc/html/latest/mm/overcommit-accounting.html).

PSS is appropriate for aggregate attribution because RSS double-counts shared pages. OOM victim selection is a separate question involving current memory/swap use and `oom_score_adj`; the kernel does not make the admission bound safe merely because each process’s PSS is low.

### DISAGREE_EVIDENCE — the sizing test admits a dangerous mutant

This mutation probe passed the complete focused file:

```powershell
python -c "import tinyassets.provider_admission as pa; from tinyassets.providers import router; pa._DEFAULT_LIMIT=17; router._SYNC_CALL_MAX_WORKERS=17; import pytest; raise SystemExit(pytest.main(['tests/test_provider_admission.py','-q']))"
# 23 passed
```

Seventeen passes because:

```text
17×31×3 + 390 = 1971 < 2048
```

Yet against the probe’s own baseline:

```text
1189 - 17×31×3 = -392 MB
```

The test validates its chosen formula, not box safety.

The independent peer also found that deleting only the judge fan-out’s `_ProviderBusy` handler at [router.py:1789](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/providers/router.py:1789) still leaves all 23 tests green. The global substring assertion at [test_provider_admission.py:299](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tests/test_provider_admission.py:299) is satisfied by handlers on other paths, while the judge path again returns an empty ensemble and cools a provider that never launched.

### DISAGREE_CONCERN — executor 12 is not itself a correctness break

I found no production path relying on exactly eight workers. These threads primarily wait on remote subprocess I/O, so “12 threads on one core” does not automatically mean harmful CPU contention.

But the executor is fixed at import, while admission is configurable. The claim that explicit admission always binds is false:

```text
TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS=20
reported admission limit: 20
actual sync pool workers: 12
```

The test covers only the defaults. If the limit stays six, the existing eight-worker pool already remains above it; there is no reason to raise the pool in this PR.

### DISAGREE_CONCERN — reserve 1 gives liveness, not nested capacity

At limit 10, nine outer turns can occupy slots while only one nested child proceeds. Eight nested children may wait and refuse after 20 seconds while their parent CLIs remain alive. The reserve implementation is at [provider_admission.py:116](/C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/provider_admission.py:116).

For one simultaneous child per outer turn, reserve `R` must satisfy:

```text
R >= 10 - R  →  R >= 5
```

But reserve 5 reduces outer concurrency to five. Scaling the reserve reallocates capacity; it does not create free capacity. Reserve 1 is acceptable only as a minimum deadlock escape, not as evidence that nine outer turns can make useful nested progress.

### AGREE

- The original `77 MB PSS × concurrency` extrapolation was not a sound marginal model.
- MemAvailable plus complete-tree PSS is better evidence than summing per-process RSS.
- Explicit provider admission is necessary.
- The “resize is the only route beyond six” claim was premature.

The next probe should run real production-shaped turns at 6 and 8, sustain overlap, include the full descendant tree, repeat warm and cold runs, and record minimum `MemAvailable`, cgroup peak/events, memory pressure, and `Pss_Anon/File/Shmem`. Eight can be tried through the environment override as a controlled measurement; I would not promote 8 or 10 to the code default before that evidence exists.

---

## Round 2 — ADAPT (on the revert)

VERDICT: **ADAPT**

- Both constants are restored: `_DEFAULT_LIMIT = 6` and `_SYNC_CALL_MAX_WORKERS = 8`, including packaged mirrors.
- Remaining arithmetic issues in [provider_admission.py](C:/Users/Jonathan/Projects/wf-status-storage-cache/tinyassets/provider_admission.py:55):
  - `(874-403)/(25-12)` should be `(874-403)/(25-13)`.
  - `10 × 39 × 3` leaves **19 MB**, not 12 MB. Twelve is defensible only using the unrounded 39.25 MB slope.
  - “the other ~469 MB” is unclear: `2048-1189 = 859 MB`. If that comprises ~390 MB daemon plus ~469 MB system services, state both.
- The environment-variable catalog’s marginal/average and production-tree explanation is otherwise accurate.
- The 17/17 mutant fails: **22 passed, 1 failed**.
- The largest passing limit is **10**: the complete admission suite passes at 10; 11 fails. That ceiling is not defensible because it leaves only 19 MB—contradicting the module’s own statement that 10 has no meaningful headroom. The test protects 6 but still admits the dangerous 10.
- No revert regression found: as-is admission tests **23 passed**, mirror parity **5 passed**, and Ruff passed. A broader provider/router selection had one unrelated order-dependent integration failure that passed in isolation.

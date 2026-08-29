# Provider admission is sized against host memory, not its cgroup

**Filed:** 2026-08-28
**Verified:** 2026-08-28 against `569fa429`
**Severity:** P1 — a supposedly safe default can cross the daemon's committed memory ceiling

## Source (verbatim)

> 3x the floor leaves ~4650 MB, 5x leaves ~3150 MB, 10x is the first that fails.

## Finding

The capacity test and module rationale subtract provider estimates from the host's
6,907 MB `MemAvailable`. The committed deployment instead caps the daemon at 4 GiB,
and provider plus engine-MCP descendants inherit that cgroup. The deployment records
an already-observed cgroup peak of 1,411.8 MiB.

Using the test's own 300 MiB headroom floor and rounding the maximum observed marginal
30.125 MiB to 31 MiB leaves:

```text
4096 - 1411.8 - 300 = 2384.2 MiB available for the modeled turns
25 * 31 * 3          = 2325 MiB (only 59.2 MiB beyond the headroom floor)
25 * 31 * 5          = 3875 MiB (1490.8 MiB beyond the available turn budget)
```

So 25 is a 3x-carry number under the committed cgroup, not a number that survives 5x;
4x already exceeds it. A 5x carry under the same assumptions yields 15 total slots:

```text
floor(2384.2 / (31 * 5)) = 15
```

The test does not bind its copied constants to deployment. A concrete mutation changing
`deploy/compose.yml` from `mem_limit: 4g` / `memswap_limit: 4g` to 2g still produced
`23 passed` from `python -m pytest tests/test_provider_admission.py -q`.

## Deployment caveat

`docs/concerns/2026-08-27-deploy-drops-compose-sync.md` says the tracked compose file
is not automatically shipped, so the live cgroup ceiling is presently unverified. That
does not make the host-memory calculation durable: the code default must remain safe
when the committed 4 GiB deployment contract is reconciled and applied.

## Resolution

Delete this concern after the admission limit and its test are derived from the effective
cgroup budget (or the deployment ceiling is deliberately changed), and a real-turn
cgroup high-water measurement replaces the `--version` multiplier.

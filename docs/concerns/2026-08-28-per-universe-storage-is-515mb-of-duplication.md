# Storage is ~515 MB per universe, ~99.8% of it platform duplication — and `get_status` under-reports it by ~25,000x

**Filed:** 2026-08-28
**Severity:** P1 — sets the real scaling ceiling, and the reported number is wrong by four
orders of magnitude, so nobody can see it

## The finding

`get_status.storage_utilization` reports the founder's universe
(`u-01kxm1vszd8hwp7em418asq8h9`) at **20 KB**: `checkpoint_db` 20480 B, `activity_log` 0,
`universe_outputs` 0.

On the droplet it is **516.2 MB** — measured directly on the `tinyassets-data` volume:

| Path | Size | What it is |
|---|---|---|
| `.runtime/provider-child` | 315.2 MB | per-universe provider runtime |
| `.credentials/codex` | 118.7 MB | a full materialized Codex home, **per universe** |
| `.runtime/provider-launch-credentials` | 80.5 MB | per-universe launch credentials |
| `wiki` + `soul_versions` + `story.db` + `knowledge.db` + rest | **~0.9 MB** | the actual user content |

So **~515 MB is platform overhead and ~1 MB is the user's**. `api/status.py:1252-1277`
attributes only `checkpoint_db`, `activity_log` and `universe_outputs`, so every one of the
large directories is invisible to the reported number.

## Why it matters

**It sets the scaling ceiling, and it is the wrong ceiling.** At 515 MB/universe:

| Users | Storage | Notes |
|---|---|---|
| 100 | 51.5 GB | **exceeds the current 50 GB disk on its own** |
| 1,000 | 515 GB | ~15 boxes, ~$180/mo |
| 10,000 | 5.15 TB | ~150 boxes, ~$1,800/mo |

If the provider runtime were shared rather than copied per universe, per-universe storage
falls to ~1 MB and the same box holds *thousands* of universes. **Fixing the duplication is
worth roughly 10x on infrastructure cost — a bigger lever than any pricing decision.**

It also invalidated a planning conclusion: the metering/tiers cost model
(`meter-usage-and-tiers`) was written believing per-universe storage was ~20 KB and
therefore not worth billing. That was based on this broken measurement.

## Droplet reality, measured 2026-08-28

- **1 vCPU, 1,967 MB RAM, 50 GB disk** → DigitalOcean **$12/mo**, not the $24 assumed.
- Disk **33 G used / 50 G (69%)**.
- `docker system df`: images 13.56 GB total, **13.4 GB reclaimable (98%)** — stale layers
  from repeated deploys. Reclaiming takes the disk from 69% → ~42%.
- Data volume 11.8 GB: `concordance` 8.9 GB (of which **`checkpoints.db` alone is 8.6 GB**),
  `default-universe` 2.1 GB, founder 516 MB, `wiki` 12.5 MB.
- Daemon container RSS **449.6 MiB** of 1.921 GiB, 2.98% CPU at idle; ~1.1 GB available.

**Memory, not the 4-worker pool, is the concurrency ceiling.** `tinyassets/runs.py:3002`
admits 4 concurrent top-level runs, but each spawns a `codex exec` / `claude -p` subprocess
on a 2 GB box with ~1.1 GB free. Four concurrent provider subprocesses will not fit; the
pool is over-provisioned for this hardware.

## Open

1. **Deduplicate the provider runtime.** Is a per-universe copy of `.credentials/codex` and
   `.runtime/*` actually required for isolation, or can it be shared/hard-linked with only
   the credential material kept per-universe? This is the highest-value question here.
2. **Bound `checkpoints.db`.** `concordance` reached 8.6 GB unbounded. `storage_utilization`
   already reports `subsystem_caps.checkpoints.status = "unbounded"` — it knows, and nothing
   acts on it.
3. **Fix the reported number.** Until `api/status.py` attributes the large directories, the
   storage dimension of any tier is unenforceable and the founder cannot see the truth.
4. **Reclaim 13.4 GB of stale images** — needs a host decision; it is a production mutation,
   low-risk and reversible (images re-pull), but not mine to run unasked.

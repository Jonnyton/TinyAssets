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

## Root cause (measured 2026-08-28)

`_provider_child_runtime_env` (`tinyassets/providers/base.py:459-500`) gives every universe
a private fake `HOME` for its provider subprocess — separate `HOME`, `XDG_*`, `TMPDIR`,
`CLAUDE_CONFIG_DIR`, `CODEX_HOME`. **That isolation is correct and must stay**: it is what
stops one universe's provider child seeing another's state, and an empty auth home is what
prevents ambient credential fallback.

What is wrong is that ~300 MB of the 515 MB is **regenerable cache**, not isolated state:

| Path | Size | Nature |
|---|---|---|
| `.runtime/provider-child/codex/home/.npm` | **207.4 MB** | npm cache — content-addressed, no secrets, **safely shareable** |
| `.runtime/provider-child/codex/auth-empty/codex` | **92.0 MB** | Codex CLI state + plugins written into the dir named *auth-**empty*** |
| `.runtime/provider-child/claude-code` | 15.7 MB | same shape, smaller |

So the fix is not to weaken isolation. It is to stop giving each universe its own copy of a
cache that is identical across all of them:

1. Point `npm_config_cache` at a **shared, read-only** cache mounted into every provider
   child. Isolation is unaffected — an npm cache holds no credential material.
2. Decide whether the Codex plugin/state directory can be seeded from a shared read-only
   base with only per-universe writes layered on top.
3. Either way, add cache eviction: a universe idle for N days does not need 300 MB of
   regenerated cache resident.

Expected effect: per-universe storage falls from ~515 MB to well under 20 MB, which is the
~10x infrastructure lever.

`auth-empty` holding 92 MB also deserves a second look on its own merits — the name asserts
an invariant the directory no longer satisfies. Confirm nothing auth-bearing is landing there.

## Open

1. **Share the npm cache** (see Root cause) — the ~10x lever, no isolation cost.
2. **Bound `checkpoints.db`.** `concordance` reached 8.6 GB unbounded. `storage_utilization`
   already reports `subsystem_caps.checkpoints.status = "unbounded"` — it knows, and nothing
   acts on it. That single file is a third of the data volume.
3. **Fix the reported number.** Until `api/status.py` attributes the large directories, the
   storage dimension of any tier is unenforceable and the founder cannot see the truth.

## Done

- **Reclaimed the stale images, 2026-08-28** (host-authorized). Kept the running `be4f2b67`
  image and the `44c4e205` rollback target; removed nine older ones. Disk **69% → 50%**,
  images 13.56 GB → 3.995 GB. Daemon healthy and public canary green afterwards.

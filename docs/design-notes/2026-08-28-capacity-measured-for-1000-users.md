# Capacity, measured: what one droplet actually serves

**Question (founder, 2026-08-28):** are we ready for 1,000 users, many of them daily
and simultaneous?

**Answer: no, by roughly an order of magnitude, and the binding constraint is one CPU.**
Everything below is measured on the live box on 2026-08-28, not modelled.

---

## The box

| | |
|---|---|
| CPU | **1 vCPU** (`DO-Regular`) |
| RAM | 2 GB, 2 GB swap (141 MB already in use) |
| Disk | 50 GB, **69% full**, 15 GB free |
| Uptime | 126 days |
| Idle load | ~0.2 with two users — the daemon holds ~20% of the single core at rest |

The cost plan in `wise-strolling-flute.md` assumed a $24 2vCPU/4GB droplet. It is a
1vCPU/2GB. Every users-per-box figure derived from that assumption is **half** what it
should have been, at best.

## Measured throughput

`read_graph target=status` — a pure read, no writes, no runs — through the real public
endpoint, each worker holding its own MCP session:

| concurrency | p50 | p95 | max | throughput | errors |
|---:|---:|---:|---:|---:|---:|
| 1 | 421 ms | — | 476 ms | 2.4 req/s | 0 |
| 10 | 1,112 ms | 1,590 ms | 1,631 ms | 7.5 req/s | 0 |
| 25 | 1,583 ms | 2,409 ms | 2,517 ms | **13.0 req/s** | 0 |
| 50 | 3,215 ms | 11,176 ms | 11,617 ms | 8.6 req/s | 0 |
| 100 | 3,215 ms | 17,529 ms | 18,053 ms | 11.1 req/s | 0 |

**Throughput saturates at ~13 req/s around 25 concurrent.** Past that, adding load buys
nothing and costs latency: p95 goes from 2.4 s to 17.5 s. Nothing errors — it queues, so
users experience it as the product being slow, not broken.

At 25 concurrent the daemon sits at **95% of the single core** with a host load average
of **4.94** — five-fold oversubscribed. Memory stays at ~390 MB of 1.9 GB throughout, so
this is **CPU-bound, not memory-bound**, on the read path.

## Where a request goes

| | |
|---|---|
| Warm sequential read, from outside | ~196 ms |
| Same read on container loopback | **67 ms** |
| Difference (Cloudflare edge + tunnel) | ~130 ms |

67 ms of CPU per cheap read on one core predicts ~15 req/s single-threaded. Measured
saturation was 13 req/s. **The model and the measurement agree**, which is the reason to
trust the extrapolation below.

In-process, one status read costs ~48 ms and issues ~71 file opens, 23 SQL statements,
6 fresh SQLite connections and ~140 `stat` calls. The one component that *grows with the
platform* was the recursive storage walk (~3,300 `stat`s); it is now memoized, which is
19% of the request today and much more later. The rest is diffuse — no second smoking gun.

## What this means for 1,000 users

Average load is not the problem. 1,000 users × ~20 calls/day is 0.23 req/s, comfortable.
**Simultaneity is the problem**, and it is what was asked about:

- **~25 concurrent** is the knee for a *cheap read*. Beyond it p95 exceeds 2.4 s.
- A real chat turn is not a cheap read. `converse` spawns an LLM subprocess and takes one
  of **4** top-level run slots (`_DEFAULT_MAX_WORKERS = 4`, `runs.py:3002`) — for the
  entire platform, all users.
- So the honest ceiling on *simultaneous real work* is single digits, not hundreds.

## What would change it, cheapest first

1. **Buy cores.** 1 → 4 vCPU is $12 → $48/mo and should be roughly 4× the read ceiling.
   At $20/user this is paid for by *three* subscribers. This is the single highest-value
   action and it needs no code.
2. **Raise the run pool once cores exist.** 4 workers is conservative given that a run is
   mostly *waiting* on the user's own LLM subscription rather than burning our CPU — but
   the per-subprocess RSS is still unmeasured, and 2 GB is not much room. Measure before
   raising.
3. **Keep O(n) work out of per-request paths.** The storage walk was one. Others will
   appear as data grows; the profile above is the method.
4. **Horizontal scale needs a storage rearchitecture.** SQLite on a local filesystem
   (Hard Rule 1, Hard Rule 2) means a second box cannot simply be added behind a load
   balancer. This is the real limit, and it is a project, not a setting.

## What is NOT the constraint

- **Memory** on the read path: ~390 MB of 1.9 GB under saturating load.
- **Disk from users**: 1,000 universes at ~20 KB each is ~20 MB. The 33 GB in use is
  image layers and system overhead — fixed per box.
- **Inference cost**: the platform supplies no LLM; every universe runs on the user's own
  subscription. This is why the cost-per-user figure stays near $0.12/mo and why buying
  cores is the obvious move.

## Method note

The concurrency probes were read-only `initialize` and `read_graph target=status` calls
against our own endpoint, bounded to ≤100 concurrent and a few seconds each. No writes,
no runs, no spend. Two things worth knowing for anyone repeating this:

- Cloudflare's browser-integrity check returns **1010 Access denied** to a bare `urllib`
  user-agent. Set one, or you will measure the edge refusing you.
- MCP streamable HTTP requires the `initialize` handshake and an `Mcp-Session-Id` header;
  a bare `tools/call` returns `Bad Request: Missing session ID` and measures nothing.

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

## Measured again after deploying the memos

Identical probe, same box, after #2648 shipped — and this is the end-to-end number, not
an in-process one:

| concurrency | p50 before → after | p95 before → after | req/s before → after |
|---:|---|---|---|
| 1 | 421 → **280 ms** | — | 2.4 → 3.6 |
| 10 | 1,112 → **413 ms** | 1,590 → **620 ms** | 7.5 → **22.7** |
| 25 | 1,583 → **654 ms** | 2,409 → **1,824 ms** | 13.0 → **25.8** |
| 50 | 3,215 → **849 ms** | 11,176 → **3,294 ms** | 8.6 → **30.0** |
| 100 | 3,215 → **559 ms** | 17,529 → **5,170 ms** | 11.1 → **38.4** |

**The ceiling moved from ~13 req/s to 38+ req/s, and the shape changed.** Before,
throughput *fell* past 25 concurrent (13.0 → 8.6 → 11.1) — the signature of a queue
forming. Now it *rises* monotonically to 100 concurrent and has not turned over. p95 at
100 concurrent improved 3.4×, from 17.5 s to 5.2 s.

*Caveat, stated because the effect is large enough to want to over-claim:* this is a
before/after across a deploy on a live box, not a controlled A/B — I cannot toggle the
memos without recreating the container, since `env_file` is read at creation. Two things
argue it is real rather than drift: the effect size is far beyond plausible noise, and
the *shape* change is exactly what removing a per-request O(n) cost predicts. It is also
still the `status` handle — the one I optimized — so it bounds connector polling, not
`converse`.

Note this was measured with the memos as merged, which still contain the thundering herd
(#2648 landed at a stale head without the fix). The herd duplicates work precisely under
concurrency, so #2650 should improve the right-hand columns further.

## Where a request goes

| | |
|---|---|
| Warm sequential read, from outside | ~196 ms |
| Same read on container loopback | **67 ms** |
| Difference (Cloudflare edge + tunnel) | ~130 ms |

67 ms of CPU per cheap read on one core predicts ~15 req/s single-threaded. Measured
saturation was 13 req/s. **The model and the measurement agree**, which is the reason to
trust the extrapolation below.

In-process, one status read cost ~73 ms and issued ~71 file opens, 23 SQL statements,
6 fresh SQLite connections and thousands of `stat` calls. Two components dominated, and
both are now memoized. Interleaved A/B on the live box, so page-cache drift hits every
arm equally:

| | p50 | vs baseline |
|---|---:|---:|
| baseline | 73.2 ms | — |
| + storage walk memoized | 30.8 ms | **-58%** |
| + supervisor liveness memoized | 15.3 ms | **-79%** |

**That 4.8× does not generalize, and I claimed it did.** A cross-family review (Codex
ADAPT) reproduced the counter-case: the liveness memo is *per universe* with a 5-second
TTL, and the app polls every 30 seconds, so a thousand distinct universes produce a
thousand misses. Measured directly — 1,000 universes × 2 passes gave **2,000
computations and zero hits**. The 73→15 ms figure is a warm, same-universe benchmark.

What each piece actually buys, stated separately because they differ:

| | Scope | Helps |
|---|---|---|
| Storage-walk memo | **process-global** | every status request, any universe — this one does generalize |
| Liveness memo | per universe, 5 s | repeat reads of the *same* universe inside the window; nothing at 1,000 distinct pollers |
| **Single-flight** | per key | concurrent readers of the same key: measured **50 computations for 400 requests (8×)** |

Single-flight is the part that matters under load, and it was the review's sharpest
finding: before it, 25 concurrent cold callers ran 25 filesystem walks — a stampede at
exactly the concurrency where the box already saturates.

*A correction worth keeping.* I first reported the storage walk as 19%, measured
sequentially on an unusually warm page cache; cProfile separately inflated it to 59%
because it distorts syscall-heavy code. Only the interleaved A/B is trustworthy. That the
figure swings from 19% to 58% with cache state is itself the point: under memory pressure,
when the walk is most expensive, is exactly when the box can least afford it.

## What this means for 1,000 users

Average load is not the problem. 1,000 users × ~20 calls/day is 0.23 req/s, comfortable.
**Simultaneity is the problem**, and it is what was asked about:

- **~25 concurrent** is the knee for a *cheap read*. Beyond it p95 exceeds 2.4 s.
- A real chat turn is not a cheap read. `converse` spawns an LLM subprocess and takes one
  of **4** top-level run slots (`_DEFAULT_MAX_WORKERS = 4`, `runs.py:3002`) — for the
  entire platform, all users.
- So the honest ceiling on *simultaneous real work* is single digits, not hundreds.

## Real work is bound by MEMORY, not CPU — and I had this backwards

I wrote above that the 4-worker run pool was "conservative given that a run is mostly
*waiting* on the user's own LLM subscription rather than burning our CPU". That is true
of CPU and wrong about the thing that actually binds. Measured on the live box:

| | |
|---|---|
| One provider CLI (`claude --version`, no inference) | **197 MB** peak RSS |
| Four concurrent, RSS sum | **+758 MB** (~189 MB each — barely shared) |
| Four concurrent, **PSS** sum (sharing-adjusted) | **+310 MB** (~77 MB each) |
| Peak total container RSS during that | **1,135 MB** on a 2 GB box |

PSS is the honest figure for pressure: **~77 MB of genuinely private memory per
concurrent run**, and that is the FLOOR — `--version` loads no system prompt, no
conversation history and no tool definitions, and performs no inference. A real turn is
larger.

A waiting run is not free. It holds its runtime resident for the whole wait, so "it is
only waiting on the user's LLM" reduces CPU pressure and not memory pressure.

**So the 4-worker pool is not conservative — it is about right for 2 GB, and arguably
already optimistic.** Raising it on this box would not add throughput; it would add
OOMs. Rough sizing for simultaneous *real* turns, at the measured floor:

| Simultaneous turns | Run memory (PSS floor) | + daemon | Realistic box |
|---:|---:|---:|---|
| 4 (today) | ~310 MB | ~700 MB | 2 GB — at the edge |
| 25 | ~1.9 GB | ~2.3 GB | 8 GB |
| 50 | ~3.9 GB | ~4.3 GB | 8–16 GB |

**This changes the buying advice.** It is not "buy cores", it is **buy the 4 vCPU / 8 GB
tier ($48/mo)** — the cores raise the read ceiling and the RAM is what actually unlocks
the run pool. RAM is the constraint on the work users care about.

### And there is no memory limit on the container

`docker inspect` reports `mem_limit=0` — the daemon may consume the entire host. With
the run pool already able to peak at 1.1 GB of 2 GB, an overshoot OOMs the *host*, which
takes `tinyassets-tunnel` with it and drops the public surface completely. A container
limit would convert that into a container restart (`restart=unless-stopped`) with the
tunnel surviving. No OOM has happened yet, which is why this is a hardening item and not
an incident — but the margin is thin and every added worker eats it.

## Turning slots into users — the formula, and the one number we do not have

Concurrent-turn capacity is `slots / turn_duration` turns per second. Slots are now
known and bounded (`TINYASSETS_MAX_CONCURRENT_PROVIDER_CALLS`, default 6; ~25 after the
approved resize). **Turn duration is not measured**, and I tried: `run_events` in
`.runs.db` has `started_at`/`finished_at`, but they sit microseconds apart with one event
per run — bookkeeping records, not execution spans. So the platform does not currently
record how long a real turn takes.

The sensitivity, so the decision does not wait on it:

| slots | 10 s turn | 30 s turn | 60 s turn |
|---:|---:|---:|---:|
| 6 (today) | 0.60 /s | 0.20 /s | 0.10 /s |
| 25 (after resize) | 2.50 /s | 0.83 /s | 0.42 /s |

1,000 users at ~10 turns/day is ~10,000 turns/day, which is **0.12 /s averaged over a
24 h day** and roughly **0.7 /s at a 5× peak in a 12 h active window**. Read against the
table: today's 6 slots carry the average comfortably at any plausible turn length and
miss the peak unless turns are fast; 25 slots carry the peak except at the slow end.

**So the honest answer is that the resize plus the admission bound very likely covers
1,000 users at ordinary intensity, and I cannot prove the peak without measuring turn
duration.** That measurement needs instrumentation the code does not have — a real
`started_at`/`finished_at` around the provider call — and it should land before anyone
claims a users-per-box number rather than a slots number.

What the admission bound changes regardless of that unknown: exceeding capacity now
queues briefly and then refuses honestly, instead of spawning until the host OOMs and
takes the tunnel down. Being *under-provisioned* is a product problem; being *unbounded*
was an outage.

## What would change it, cheapest first

0. **Done, partially free: less CPU on the status path** (above). Worth having, but
   narrower than I first claimed, and **it does not raise the real-turn ceiling at all**:
   `converse` calls neither cached function. It reduces shared overhead and removes a
   stampede; it does not make the platform ready. No throughput claim until a deployed,
   authenticated, multi-universe load test says so.
1. **Buy cores.** 1 → 4 vCPU is $12 → $48/mo and should be roughly 4× the read ceiling
   again, compounding with the above. At $20/user this is paid for by *three*
   subscribers. This is the highest-value remaining action and it needs no code.
2. **Do NOT raise the run pool on this box.** Measured above: ~77 MB PSS / ~189 MB RSS
   per concurrent run, floor. 4 workers already peaks at 1.1 GB of 2 GB. More workers
   here buys OOMs, not throughput. The pool rises *after* the RAM does — which is why
   the tier above matters more than the core count.
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

# Codex review — daemon container memory limit

One round, 2026-08-28. **ADAPT.** I proposed `mem_limit: 1400m`, derived from a
per-process PSS sum. Codex measured the live cgroup and found it has already peaked at
**1411.8 MiB** — my limit was 11.8 MiB *below an observed production peak*, and would
have OOM-killed the daemon under load it had already survived.

The error was in kind, not just degree: a cgroup's `memory.max` charges file cache and
kernel memory too, so a PSS sum cannot size it.

VERDICT: ADAPT

DISAGREE_EVIDENCE — `1400m` is too low. After the approved 8 GB resize, set:

```yaml
mem_limit: 4g
memswap_limit: 4g
```

1. The live cgroup has already peaked at **1,480,417,280 bytes = 1411.8 MiB**. `1400m` is 1400 MiB, so the proposed limit is **11.8 MiB below an observed production peak**.

   More importantly, current cgroup usage was ~935 MiB while Docker showed a ~568 MiB working set and process PSS was lower still. The difference was mostly charged file cache and kernel memory. Therefore `390 + 6×39×3` cannot size `memory.max`.

   On the resized host, `4g`:

   - Is 2.9× the observed 1411.8 MiB peak.
   - Is 3.75× the proposed 1092 MiB workload estimate.
   - Leaves roughly half the nominal 8 GiB host outside the daemon cgroup.
   - Still contains a runaway meaningfully; `6g` would unnecessarily surrender another 2 GiB of host protection.

2. The 3× worst case does not hold as evidence. Under `1400m`, starting from 390 MiB, six slots get only:

   \[
   (1400-390)/6 = 168.3\text{ MiB per turn}
   \]

   There is no measurement showing a real turn plus all children remains below that.

   Yes, provider and engine-MCP subprocesses inherit the daemon’s cgroup; forked children start in their parent’s cgroup, and cgroup limits include descendants. [Linux cgroup v2 documentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html?highlight=freezer)

   However, production currently has **two persistent engine-MCP children**, started at daemon boot—not six per-turn children. They are already included in the at-rest container accounting. A Claude stdio fallback child would also remain inside the same cgroup.

3. Without `memswap_limit`, swap is not unlimited: Docker normally allows swap equal to `mem_limit`, making total memory-plus-swap twice the memory limit. Thus `1400m` could consume 1400 MiB RAM plus 1400 MiB swap. That preserves the RAM ceiling but permits severe thrashing and consumption of most host swap. [Docker Compose memory/swap semantics](https://docs.docker.com/reference/compose-file/services/#memswap_limit)

   Production already showed ~152 MiB charged container swap during my check. With 8 GB RAM and a 4 GiB cap, use `memswap_limit: 4g`; equal values disable container swap and make failure deterministic.

4. Restart is not guaranteed for every cgroup OOM. Live production reports `memory.oom.group=0`, meaning the kernel may kill only the allocating provider/MCP child. `unless-stopped` acts only if the container itself exits. If PID 1 exits, restart should occur; if only a child dies, the daemon stays up and that turn fails. [Kernel OOM-group behavior](https://kernel.org/doc/html/v5.12/admin-guide/cgroup-v2.html), [Docker restart-policy behavior](https://docs.docker.com/engine/containers/start-containers-automatically/)

   Repeated OOMs remain possible if startup alone exceeds the cap, traffic immediately re-saturates it, or the engine supervisor repeatedly respawns a killed child. At 4 GiB versus the observed 1.41 GiB peak, that wedge is substantially less likely.

5. Apply only after the resize, then recreate just the daemon. Verify:

   - `Memory=4294967296`
   - `MemorySwap=4294967296`
   - `memory.max=4294967296`
   - `memory.swap.max=0`
   - public canary green
   - six real concurrent turns, with `memory.peak`, `memory.events`, `OOMKilled`, and `RestartCount` recorded

Current production has only daemon, tunnel, and logs running. The Compose file also defines worker containers outside the daemon cgroup; if those are enabled later, they need their own limits or they can still OOM the host.

Production evidence was collected 2026-08-28 via `scripts/droplet.py`, `docker inspect`, `docker stats`, `docker top`, and the live cgroup v2 memory files.

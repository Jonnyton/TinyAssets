## Context

Full design: `design-notes/universe-harness-design.md` (sections 2-4 and slice
S1). This file records only the decisions S1 had to make that the design left
open, and what was measured to make them.

## Decisions

### D1. The platform runs the tools, through the engine route

The four tools are engine-MCP handles (`engine_mcp_server.py`), added to the
single served inventory (`served_tools.SERVED_ENGINE_MCP_TOOLS`). Every adapter
already reaches that route, so there is no per-vendor wiring and no vendor
tool list. The CLIs' own `Read`/`Bash`/... stay denied on every turn.

### D2. One jail builder, narrower view

`tool_jail_argv` calls `provider_jail.jail_argv` with a `UniverseView` binding
the universe at `/u`, `tmpfs` masks over `.runtime`, `.claude`, `.codex`, and
new keyword arguments `share_net=False`, `clearenv=True`, `seccomp_fd=`.
Provider launches keep the defaults. Path policy is the jail's: a path outside
`/u` is passed through unchanged and simply does not exist inside.

Reads go through the jail too (a jailed `tail | head`), not a daemon-side
open: the jail is then the only thing deciding what is reachable.

### D3. Resource limits without a cgroup

Measured read-only on the production container, 2026-09-24
(`python scripts/droplet.py ssh -- 'docker exec -i tinyassets-daemon sh -s'`):
kernel 6.1.0-52, uid 1001, all capability sets 0, NoNewPrivs 1, cgroup2
mounted **read-only** (`memory.max` 4 GiB, `pids.max` 9482 for the
container), `prlimit` at `/usr/bin/prlimit`, bwrap 0.12. So no per-universe
cgroup can be created from inside the container.

Mechanism: `prlimit` runs INSIDE the jail, after bwrap created the user
namespace. On kernel >= 5.14 `RLIMIT_NPROC` is charged per user namespace:
measured with 9 daemon-uid processes and `--nproc=12`, the jail forked 10
children before `Cannot fork` (a per-uid count would have allowed 2). So the
process limit is per jail, not per daemon user.

The parent adds what an rlimit cannot: wall clock, output cap (killed while
reading), a process-tree watch (count and summed RSS, via
`node_sandbox.read_process_tree`, shared with the workspace watchdog), and a
free-space floor on the data volume. The tree watch also bounds a root-run
jail, where the kernel exempts root from `RLIMIT_NPROC` (the hosted CI
runner's sudo fallback).

Defaults: 512 MiB address space, 64 processes, cpu min(120 s, wall), 32 MiB
per file, 256 files, 120 s wall (bash may ask up to 600 s), 64 KiB output,
768 MiB tree RSS, 1 GiB free disk. Concurrency: 2 jails per universe, 4 per
host (flock slots under the data dir).

Fail closed: no bwrap, no prlimit, or output without the marker the jailed
wrapper prints after prlimit succeeded, and the call is refused with nothing
run.

### D4. No links, no FIFOs

The jail makes the agent's view safe, but the daemon reads the same folder
from outside (persona grounding, config, soul) with ordinary path opens. A
symlink the agent planted towards `/data/<other>/founder.md` dangles inside
the jail and resolves outside it, so another user's file would reach this
universe's prompt. A FIFO would hang the reading thread. A seccomp filter
(`universe_tools.seccomp_program`, x86_64 and aarch64; x32 and unknown
architectures get EPERM for everything) refuses `symlink`, `symlinkat`,
`mknod`, `mknodat`. Hard links cannot leave `/u`: every other visible path is
a different mount (EXDEV). Cost: a `git clone` or package install that
creates symlinks fails for those entries. Residual below.

### D5. Vendor-native harness dirs (design risk 8)

Decision: masked everywhere. `provider_jail.default_view` puts an empty tmpfs
over an existing `.claude/`/`.codex/` (and refuses a symlink or file there);
the tool jail pre-creates both as real directories and masks them, so the
agent can never write a `.claude/settings.json` hook that the next
`claude -p` launch (cwd = universe, `--setting-sources project`) would run
next to the owner's subscription credential. The harness is vendor-neutral
files the platform assembles.

### D6. The skill index

`harness_prompt()` is appended to the system prompt only when the turn has the
tools (`turn_config.engine_mcp_enabled`: a verified founder principal, founder
tier, flag on). It lists `skills/<name>/SKILL.md` with frontmatter
`description`, name = directory name, at most 64, descriptions one line and
<= 300 chars. The daemon reads them with `workspace_fs` descriptor walks and
`O_NOFOLLOW`, so a link is skipped, never read. POSIX only.

## Residuals (tracked, not blocking S1)

- The persona prompt assembly still reads grounding files whole. With the
  32 MiB file cap and the link filter this is owner-scoped cost, not a
  cross-user read; S2 replaces the assembly.
- Total bytes per universe are not charged to a tier quota yet; the disk
  floor protects other users from exhaustion, not the owner from their own
  folder growing.
- `CLAUDE.md` in the universe root is still read by `claude -p`
  (`--setting-sources project`); it is prompt text, not code, but it is a
  vendor-specific harness path. Resolve in S2 when `AGENTS.md` becomes the
  persona.
- Per-universe cgroups (memory.max, pids.max, cpu.weight) need a delegated
  cgroup subtree in the container: a host change, not in this slice.

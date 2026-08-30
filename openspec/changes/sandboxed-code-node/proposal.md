## Why

Founder directive 2026-08-30: shape the architecture to the design mental
model — the user's agent builds *whatever* workflow it wants from powerful
primitives (ground-up design, build, test, redesign), remixes what others
built in the commons, and can build a graph automation it was given a link to.
GitHub is one channel through the channel-agnostic call node; any LLM source
runs the graph.

What happened instead over 2026-08-29/30, live on the founder's own universe:
one job — "change one line of README.md, open the PR, merge it" — needed
four deploys of platform operators (`$ta.base64/from_base64/ref/effect/concat`,
`$ta.replace`, a nearest-match refusal, a truncation hint). Each was generic
in name and a reaction to one failure. Together they are a small programming
language written one operator per bug (finding:
`docs/concerns/2026-08-30-the-graph-has-no-deterministic-compute-step.md`).

The structural cause: a branch node is either an LLM step (lossy for bytes,
and it can only see a 4 KiB preview of a fetch, after the run) or a
declarative effect packet (references earlier results, cannot compute over
them). **Nothing deterministic can run between a fetch and a write.** The
model process is credential-blind on purpose — tokens live in an isolated
worker — but that forbids credentials in the model's reach, not data.

The primitive already half-exists and is dead: `source_code` nodes run
in-process via `exec` behind a founder-approval hash gate that no caller ever
grants (`mark_approved` has zero callers), and a subprocess `NodeSandbox`
exists but is not wired into `compile_branch`
(`openspec/specs/graph-execution-substrate/spec.md`, "source_code nodes
execute in-process behind a fail-closed approval gate").

## What Changes

A **sandboxed code node** becomes a first-class, user-buildable node kind:

- A node with `source_code` runs **deterministic Python in an OS-isolated
  subprocess**: no credentials, no network, no access to the data dir, a
  private temp dir, CPU/memory/wall-clock limits, and stdin/stdout JSON.
  Its inputs are the node's declared `input_keys` from state **plus the
  earlier effect nodes' `response.status` / `response.body` in the same
  branch** (the view `$ta.effect` already has). Its outputs land in state
  under its declared `output_keys`, where a later packet references them with
  `$ta.ref` — so fetch (credentialed worker) → code (bytes, no credentials)
  → write (credentialed worker) is one run.
- **Authority is the sandbox, not a host approval.** A code node authored
  under the universe owner's authority (the owner, or the owner's own
  universe engine via `write_graph`) runs without `approved` /
  `approved_source_hash`; the in-process `exec` path is retired. A remixed
  node's source is re-authored under the new owner (the cross-author strip
  already exists). The pattern-scan denylist stays as defence in depth.
- Effects that reference a code node's output run **after** it, in branch
  order, which requires effect dispatch to interleave with node execution
  rather than run only after the whole graph — the one execution-order change
  in this proposal (design.md).
- `write_graph`'s outbound docs teach the shape; `read_graph` evidence shows
  the code node's stdout/stderr tail and exit status like any other node.
- The `$ta.*` transform vocabulary is frozen at #2717: kept for the branches
  that use it, not extended.

## Impact

- Specs: `graph-execution-substrate` (MODIFIED: source_code execution
  requirement; effect dispatch order), `external-effect-adapters` (MODIFIED:
  a packet may reference a code node's output), `live-mcp-connector-surface`
  (docs only — no new handle; this is an action under `write.graph`).
- Code: `tinyassets/compiler.py`/`branches.py` (node kind + execution),
  `tinyassets/node_sandbox.py` (the subprocess sandbox, hardened and wired),
  `tinyassets/effectors/__init__.py` (per-node dispatch when a later node
  reads an effect), `tinyassets/engine_mcp_server.py` (docs, validation),
  tests, plugin mirror.
- Authority surface: an execution primitive → this proposal + design before
  code; founder approved the direction 2026-08-30; PLAN.md gains the
  principle ("capabilities are primitives the user's agent composes, not
  platform operators") and the code node's place in the node vocabulary.
- Live proof: the founder's universe lands the one-line README fix with a
  fetch → code → write branch it authored itself, no `$ta.replace`,
  uncoached.

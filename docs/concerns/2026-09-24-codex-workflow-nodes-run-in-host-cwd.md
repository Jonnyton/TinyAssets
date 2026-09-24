# Codex workflow nodes run in the host checkout with host-wide reads

**Filed:** 2026-09-24
**Verified:** 2026-09-24, source read at base `1e6f6eba`. Not reproduced live.
**Severity:** P1. This is the cross-user floor: a node's model can read what
the daemon can.

## Source

Found while establishing the parallel-probe latency cause
(`docs/reviews/2026-09-24-provider-latency-rootcause.md`).

The same defect is fixed there for `claude-code`: workflow node calls reached
the CLI with a bare `ModelConfig`, so the CLI ran in the daemon's cwd
(`/app`). There its filesystem and shell builtins read the platform source and
listed `/data`, which holds every universe. That fix marks every workflow node
call `ModelConfig.workflow_node`. Only the claude adapter acts on the mark;
Codex ignores it.

The Codex path has the same shape, and the mechanism differs:

- An ordinary `CodexProvider.complete` call (`sandbox_workspace=False`) runs
  `codex exec -C _codex_workdir()`. `_codex_workdir()` defaults to the
  package's repo root, which is `/app` in the image.
- When bubblewrap is available it passes `--sandbox workspace-write`. Codex's
  own sandbox restricts writes, not reads, so the model can read every
  universe under the data root.
- The foreground and background run providers launch workflow nodes with
  exactly that config.

## What resolving it looks like

Workflow node Codex calls get the OS jail the served turn already uses:
`sandbox_workspace=True`, which gives bwrap with a read-only universe mount or
an empty scratch workspace. That jail has never been exercised for
`run_graph`, and it refuses to launch without bwrap. Prove it with the cloud
pre-push oracle on Linux and one live Codex-node run before `CodexProvider`
acts on `workflow_node`. Then delete this file.

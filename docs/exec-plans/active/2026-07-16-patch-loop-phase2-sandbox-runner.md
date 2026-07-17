# Execution Plan: Patch-Loop Phase-2 Per-Job Sandbox Runner (OUTSTANDING)

## Status

**BLOCKER — not built.** This is the deliberate boundary of the patch-loop
security work. Phase-1 (`S3a`, PR #1468) is ENFORCEMENT-ONLY: it proves that
repo-touching nodes cannot run, and fails them closed. It does NOT run coding
nodes. Full `S3` / gate `G5` (a coding node that actually writes a patch against
a user-bound repo, safely) does **not** land until this runner exists.

## Goal

Build the per-job sandbox runner subsystem so a patch-loop `draft_patch`
(coding), `verify` (repo_exec), and `investigate` (repo_read) node can execute
against a user-bound repo without endangering the capacity host.

## Origin

- The patch loop is a *user branch*: an arbitrary user remixes it, binds their
  own repo, and runs it in OUR cloud. `draft_patch` drives a coding agent
  (`claude -p` / `codex exec`) that writes a patch — a code-execution surface a
  malicious remix could turn into exfiltration/abuse against the host.
- Phase-1 reframe (Codex S3 REJECT r3 C5, host-approved): S3 is
  ENFORCEMENT-ONLY; the runner is a **future host-approved slice**, not S3.
- Related program memory:
  `.claude/agent-memory/developer/` (patch-loop S3 rounds) and
  `MEMORY.md` → "Patch loop is a user branch".

## Phase-1 (S3a) end state — what is already TRUE

- `tinyassets/sandbox_policy.py::coding_nodes_runnable()` returns a hard-coded
  `(False, reason)`. It is the SINGLE readiness truth read by validate
  (`_ext_branch_validate` → `branch_sandbox_status`), `get_status`, the
  `run_branch` / `resume_run` / `run_branch_version` enqueue refusal
  (`_sandbox_enqueue_refusal`), and the graph runtime choke point
  (`_build_node`). Readiness can never drift from runtime.
- Every repo-touching node fails closed deterministically at the FIRST gate in
  `_build_node`, before any `ModelConfig` / provider / scratch / env code runs,
  and emits a terminal `phase="failed"` node event. Capability is classified by:
  (a) the node's ACTUAL executable nature for a `source_code` node — it is
  ALWAYS `source_exec` (in-process host code) regardless of user metadata
  (Codex S3 r11); then (b) the stable `node_kind` (coding / repo_exec /
  repo_read); with node_id backstops.
- **`source_code` nodes are DISABLED in Phase 1.** A `source_code` adapter runs
  arbitrary Python in-process with full builtins — a host-code-execution surface
  stronger than a subprocess coding agent. It fails closed like any repo node.
  This also disables the features DRIVEN THROUGH in-process node code —
  **in-node MCP dispatch (`invoke_mcp_action`) and in-node enqueue** — until the
  runner lands. Security metadata (`node_kind` / `requires_sandbox`) is
  downgrade-locked and bound to source approval so it cannot spoof the classifier
  (Codex S3 r11 #2/#3/#4).
- The only node that RUNS is a plain TEXT (`prompt_template`) node under a CLOSED
  tool surface (`text_node_model_config` → claude `--tools ""`).

## Phase-2 scope — what the runner MUST provide before `coding_nodes_runnable()`
can return True

- **Prepared per-job checkout** — an isolated working copy of the user-bound
  repo, created per job, destroyed after.
- **Tenant / host-path invisibility** — the coding agent cannot see the host
  filesystem, other tenants' data, or the daemon's own repo/credentials.
- **Scoped credential brokering** — only the credentials the job needs, scoped
  to the job, never the host's ambient auth (no MCP account connectors, no host
  vault).
- **Restricted egress** — network policy that blocks exfiltration paths while
  allowing only the provider/API endpoints the job legitimately needs.
- **Resource limits** — CPU / memory / wall-clock / disk caps so a job cannot
  starve or wedge the host.
- **OS-level confinement** — bwrap (or container/VM) enforcement, gated by the
  existing `enforce_os_sandbox` / `os_sandbox_attested` attestation path, so a
  coding agent's tool surface is confined at the OS boundary, not just by CLI
  flags.
- **Sanitized CLI env/config — the managed-hooks vector (Codex S3 r15 #2).** An
  UNTRUSTED CLI turn (`claude -p` / `codex exec`) MUST run inside the isolated
  worker with a sanitized environment and config. Anthropic's MANAGED policy
  settings load regardless of `--setting-sources`, and managed settings can
  define shell-command HOOKS that fire even in `-p` sessions with the normal
  subprocess env — so a prompt could trigger host-side hook execution. There is
  no documented user-space flag to disable managed-policy loading; the worker
  must therefore neutralize it structurally (run under an identity/filesystem
  view where the host's managed-settings path is absent/empty, e.g. inside the
  container/VM with no host `ProgramData` / `/etc/claude-code` / managed-settings
  mount). This is the same conclusion as the converse-sandbox-P0 finding:
  OS-level isolation is the only COMPLETE boundary; the closed CLI tool surface
  is defense-in-depth, not the boundary.

- **Separate `source_exec` (in-process code) attestation — NEVER share the repo
  runner's readiness (Codex S3 r15 #1).** A `source_code` node runs arbitrary
  Python IN-PROCESS with full builtins (`exec`); the per-job REPO runner (a
  prepared checkout for a SUBPROCESS agent) does NOT sandbox in-process `exec`.
  `sandbox_policy.source_exec_runnable()` is a SEPARATE hard-`False` gate so that
  flipping `coding_nodes_runnable()` (repo readiness) can never re-open the
  in-process `exec` surface. `source_exec` stays closed until it runs inside its
  OWN OS-isolation worker (a source-execution attestation), which is a distinct
  deliverable from the repo runner.

## Delivery gate — an executor HANDLE, not a boolean (Codex S3 r16 #1)

**A readiness BOOLEAN is not an execution boundary.** The runtime gate is
`sandbox_policy.resolve_isolated_executor(class)` — it must return a concrete
ISOLATED EXECUTOR handle (subprocess/container dispatcher), and the adapter is
DISPATCHED to it (runs INSIDE the worker), NEVER invoked as `fn(state)` in the
daemon. In Phase 1 it returns `None`, so `coding_nodes_runnable()` /
`source_exec_runnable()` (which DERIVE from it) are `False` and every
sandbox-required adapter is refused. Phase 2 delivers the executor by:

1. Building the subprocess/container executor + its dispatch (the
   `graph_compiler._build_isolated_executor_dispatch_node` seam — currently
   fail-loud) so a repo/source adapter runs INSIDE the isolated worker, with the
   env/config/credential/egress/resource guarantees above.
2. Returning that executor handle from `resolve_isolated_executor` (repo class
   and source_exec class are SEPARATE handles — the in-process `exec` worker is
   distinct from the repo-checkout runner).

Only when the handle + dispatch exist — and after opposite-provider security
review + live proof — does an adapter run. Flipping a readiness flag alone does
NOTHING (the runtime requires the handle). Until then, fail-closed is correct.

## Do NOT

- Do NOT "enable" repo/source nodes by flipping `coding_nodes_runnable()` /
  `source_exec_runnable()` or monkeypatching readiness — a boolean is not a
  boundary; without an executor handle + dispatch the adapter is refused. Wire
  the real isolated executor (subprocess/container) and route through it.
- Do NOT let `resolve_isolated_executor("repo")` vouch for `source_exec` — the
  repo runner does not sandbox in-process `exec`; source_exec needs its OWN
  executor handle (`resolve_isolated_executor("source_exec")`).
- Do NOT call a tool-less `claude -p` a complete sandbox — managed-settings hooks
  load regardless of CLI flags; the OS-isolation worker is the boundary.
- Do NOT weaken the universe-intelligence isolation (WebFetch-only,
  defense-in-depth) to share a code path with the coding runner.

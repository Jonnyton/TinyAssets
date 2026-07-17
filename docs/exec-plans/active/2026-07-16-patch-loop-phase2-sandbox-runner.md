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

- **Readiness = a TYPED isolated executor per class, not a boolean (Codex S3
  r16/r17).** The runtime gate is
  `tinyassets/sandbox_policy.py::resolve_isolated_executor(executor_class)`,
  verified via `executor_satisfies` (an `IsolatedExecutor` Protocol: right
  `executor_class`, `is_healthy()`, callable `dispatch`). There are TWO resolver-
  derived classes — `EXECUTOR_CLASS_REPO` (coding / repo_exec / repo_read) and
  `EXECUTOR_CLASS_SOURCE_EXEC` (in-process `source_code`). In Phase 1
  `resolve_isolated_executor` returns `None` for BOTH, so `coding_nodes_runnable()`
  and `source_exec_runnable()` (which DERIVE from it) are `(False, reason)`. A
  bare `True` / sentinel / wrong-class / unhealthy handle does NOT satisfy
  readiness. The same truth is read by validate (`branch_sandbox_status`),
  `get_status` (both classes exposed), the enqueue refusal, and the runtime choke
  point (`_build_node`) — readiness can never drift from runtime.
- **A sandbox-required adapter is DISPATCHED as a SERIALIZABLE REQUEST, never run
  in the daemon (Codex S3 r16/r17).** The choke point emits
  `build_executor_execution_request()` — pure data (node spec + inputs +
  capability class + serializable context; NO callable) — and hands it to
  `executor.dispatch(request)`; the isolated worker COMPILES + EXECUTES it inside
  itself. The daemon holds NO callable that runs the adapter and NO gate that
  skips the executor (`_skip_executor_gate` was removed). Host-approval of a
  `source_code` node is validated at the daemon (a data check on the source hash)
  BEFORE dispatch. In Phase 1 no executor exists → every sandbox-required adapter
  is refused before dispatch.
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

## Phase-2 scope — the runner is a TYPED executor consuming a serializable request

The runner is not "flip a boolean". It is an `IsolatedExecutor` (Codex S3 r17):
a TYPED, healthy, dispatch-available executor object that
`resolve_isolated_executor(class)` returns and `executor_satisfies` verifies. Its
`dispatch(request)` consumes the SERIALIZABLE execution request
(`build_executor_execution_request` — node spec + inputs + capability class +
serializable context) and COMPILES + EXECUTES it INSIDE the isolated worker. There
are TWO such executors (repo class + source_exec class). Each must provide:

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
- **Sanitized CLI env/config — the managed-hooks vector (Codex S3 r15 #2,
  threat model CORRECTED r19 #5).** An UNTRUSTED CLI turn (`claude -p` /
  `codex exec`) MUST run inside the isolated worker such that host-managed policy
  can neither be read from the host NOR delivered to it. Managed settings can
  define shell-command HOOKS that fire even in non-interactive `-p` sessions, and
  `--setting-sources` controls ONLY the user/project/local sources — it does NOT
  suppress managed policy. Two facts make "hide the host settings file"
  INSUFFICIENT:
    1. **The path was wrong / version-drifting.** Current Claude Code docs place
       enterprise/managed file policy under `Program Files` (Windows) —
       `%ProgramData%\ClaudeCode\managed-settings.json` was the older location,
       and `/etc/claude-code` (Linux) / `/Library/Application Support/ClaudeCode`
       (macOS) round out the set. Enumerating "the" path is a moving target, so a
       negative filesystem check cannot be the boundary.
    2. **Managed settings can arrive REMOTELY at authentication**, not only from a
       local file. A worker with every local managed-settings path absent can
       STILL receive server-managed policy (including command hooks) when the CLI
       authenticates — so removing the on-disk file does not neutralize the
       vector.
  Therefore the worker MUST use ONE of:
    - **(a) A provider invocation path that cannot load managed hooks at all** —
      e.g. an unauthenticated / policy-free execution mode, or a provider whose
      turn is driven without a managed-policy-bearing credential, so no
      server-managed hook can be delivered; OR
    - **(b) OS-level containment that treats ANY loaded hook as hostile** — bwrap
      / container / VM confinement where a hook command that DOES fire executes
      inside the isolated boundary (no host filesystem, no host network beyond the
      job's scoped egress, no host credentials), so a fired hook can do nothing a
      confined job couldn't already do.
  A local-path scrub is at best a defense-in-depth layer on top of (a) or (b),
  never the boundary itself. This is the same conclusion as the
  converse-sandbox-P0 finding: OS-level isolation (or a provider path that cannot
  load the policy) is the only COMPLETE boundary; the closed CLI tool surface and
  any settings-path scrub are defense-in-depth, not the boundary.
  Sources: Claude Code settings, server-managed settings, and CLI-usage docs
  (`code.claude.com/docs/en/{settings,server-managed-settings,cli-usage}`).

- **Separate `source_exec` (in-process code) attestation — NEVER share the repo
  runner's readiness (Codex S3 r15 #1).** A `source_code` node runs arbitrary
  Python IN-PROCESS with full builtins (`exec`); the per-job REPO runner (a
  prepared checkout for a SUBPROCESS agent) does NOT sandbox in-process `exec`.
  `sandbox_policy.source_exec_runnable()` is a SEPARATE hard-`False` gate so that
  flipping `coding_nodes_runnable()` (repo readiness) can never re-open the
  in-process `exec` surface. `source_exec` stays closed until it runs inside its
  OWN OS-isolation worker (a source-execution attestation), which is a distinct
  deliverable from the repo runner.

## Delivery gate — a TYPED executor + complete serializable request (Codex S3 r16/r17/r18)

**A readiness BOOLEAN is not an execution boundary.** The runtime gate is a TYPED
`IsolatedExecutor` returned by `sandbox_policy.resolve_isolated_executor(class)`
and verified by `executor_satisfies` — it DECLARES capabilities (`supports(class)`)
+ request-schema support (`supported_request_schema_versions()`), is `is_healthy()`,
and has a callable `dispatch` (r18 #1: a bare `True`/sentinel/wrong-class/unhealthy/
non-supporting handle is rejected). The adapter is DISPATCHED as a COMPLETE
SERIALIZABLE REQUEST (`graph_compiler.build_executor_execution_request`, versioned
by `EXECUTION_REQUEST_SCHEMA_VERSION`) carrying everything `compile_branch`
computes — node spec, inputs, capability class, domain, state schema, effective
`llm_policy`, concurrency budget, a SERIALIZABLE provider-bridge reference (never
the callable), data-dir ref + lineage + enqueue context — so the worker can run
ANY node (source_exec / coding+prompt_template / opaque). It runs INSIDE the
worker, NEVER as `fn(state)` in the daemon. The adapter builders
(`_build_prompt_template_node` / `_build_source_code_node` / `_build_opaque_node`)
are PURE (r18 #1: no second gate) — the single gate is `_build_node`; the isolated
worker uses the pure builders. A worker failure emits a terminal `failed` event
(r18 #2). In Phase 1 `resolve_isolated_executor` returns `None`, so
`coding_nodes_runnable()` / `source_exec_runnable()` (which DERIVE from it) are
`False` and every sandbox-required adapter is refused. Phase 2 delivers by:

1. Building the subprocess/container executor: a concrete `IsolatedExecutor` that
   `supports()` its class + the request schema and whose `dispatch(request)`
   compiles + executes the request INSIDE the isolated worker, with the
   env/config/credential/egress/resource guarantees above. (The daemon holds NO
   adapter callable — the worker is the only thing that turns the request into
   execution; the request is the runner's complete input contract.)
2. Returning that TYPED executor from `resolve_isolated_executor` (repo class and
   source_exec class are SEPARATE executors — the in-process `exec` worker is
   distinct from the repo-checkout runner).

Only when a TYPED, healthy executor exists — and after opposite-provider security
review + live proof — does an adapter run. Returning a bare `True`/handle does
NOTHING (`executor_satisfies` rejects it). Until then, fail-closed is correct.

## Do NOT

- Do NOT "enable" repo/source nodes by flipping `coding_nodes_runnable()` /
  `source_exec_runnable()` or by returning a bare `True`/sentinel from
  `resolve_isolated_executor` — a boolean/handle is not a boundary; without a
  TYPED, healthy executor + serializable-request dispatch the adapter is refused.
  Wire the real isolated executor (subprocess/container) and route through it.
- Do NOT let `resolve_isolated_executor("repo")` vouch for `source_exec` — the
  repo runner does not sandbox in-process `exec`; source_exec needs its OWN
  executor handle (`resolve_isolated_executor("source_exec")`).
- Do NOT call a tool-less `claude -p` a complete sandbox — managed-settings hooks
  load regardless of CLI flags; the OS-isolation worker is the boundary.
- Do NOT weaken the universe-intelligence isolation (WebFetch-only,
  defense-in-depth) to share a code path with the coding runner.

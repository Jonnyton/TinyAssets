## Context

Two as-built facts drive the shape (map taken 2026-08-30 against `origin/main`):

1. **Effects fire only after the whole graph**, in branch *storage* order
   (`runs.py:2864` → `effectors/__init__.py:113-116`). Nothing inside the
   graph — code or LLM — can see a fetch result during the run. `$ta.effect`
   reads an in-memory `chain` that exists only inside that post-run loop.
2. **`source_code` nodes run in-process via `exec`** with full builtins
   behind an approval-hash gate nobody grants (`graph_compiler.py:1809-1907`,
   `mark_approved` has zero callers). A subprocess `NodeSandbox`
   (`node_sandbox.py`) exists, filters state to declared keys, allowlists
   imports and kills on timeout — and is used only by the authoring preview.

Fact 1 is why the `$ta.*` vocabulary grew: it is the only compute that can
touch a fetched body. Fact 2 is why the user's agent could never write the
three lines of Python that would have replaced all of it.

**Review history.** Codex round 1 (2026-08-30, design only) returned REJECT
with seven P0s and eleven P1s; every one is folded below and marked *(R1)*.
The shape (effects in-graph, code in an OS sandbox) was agreed; the
authority argument, cardinality, settlement, resume, the sandbox switch and
the output cap were not, and are now different. Round 2 (code) returned
REJECT with six P0s (resume without an execution context, RPC outside the
request's ContextVars, effects before LangGraph's reducer rejection and
before the merge-writer guard, an at-most-once race, a settlement race);
round 3 (code) returned REJECT with four P0s (the context lost one hop
earlier at the executor, parallel overwrite conflicts firing before the
barrier, "at most once" and the RPC cap resetting on resume, settlement
misordered under same-thread re-entrance and read-then-write). All are
folded and pinned *(R2)*, *(R3)*. Three rounds is the cap
(`AGENTS.md`); the round-3 folds are Claude-reviewed only, and are reported
to the founder as such.

## Decisions

### D1. Effects fire at node time, in graph order

When a node's function returns its state delta, the node's declared
`effects` fire **immediately**, inside the same node step, against a view of
state = current state merged with the delta (append/merge reducers applied
to the view exactly as LangGraph will apply them — the node's *own*
snapshot; under parallel fan-out a sibling's contribution is not in it, and
the join node sees more *(R1 P1, documented, not claimed equal)*). The full
adapter result goes into a run-scoped `EffectChain` (in memory:
`results[node_id]`, `evidence[node_id][sink]` bounded, `fired[(sink,
verb)]`); the chain is created by the runner **before** `compile_branch`,
registered under the run id, returned on `CompiledBranch.effect_chain`.

- **References are graph-defined.** `$ta.effect` and a code node's
  `effects` may name only the node's graph **ancestors** (plain and
  conditional edges, computed once at compile time). Not "whatever completed
  first" — the same branch must never resolve on one run and refuse on the
  next *(R1 P1)*. A reference outside the ancestry is refused as
  `invalid_body_transform`.
- **At most once per run.** A node's effects fire on its first visit; a
  cycle that revisits it fails the node with `effect_already_fired` instead
  of firing the same PUT up to the recursion ceiling under one admission
  *(R1 P0: cardinality)*. Effect identity is therefore `node_id` per run.
- **Failure rule.** A refused-before-the-wire packet, a crashed adapter and
  a dead sink always fail the node. A delivered call answered ≥ 400 fails
  the node **whatever its verb** — the HTTP method is not intent: a GraphQL
  query is a POST, and a required GET that 404s must not feed an error body
  downstream *(R1 P1)* — **unless the packet declares that status**:
  `"accept_statuses": [404]` at the packet's top level makes it data
  (probe-then-branch). Budget accounting (read vs write) stays verb-based
  and independent. Failing the node raises `EffectFailedError` → the run
  ends `failed` with the exact message shape #2713 classifies
  (`external write failed - <node>/<sink>: <error> [<kind>]`), so
  `external_write_failed` / `external_write_refused` keep their
  actionability. Later nodes do not run: no `open_pr` 422 after a refused
  `write_readme`, no dangling `auto/tiny-*` branches.
- **Evidence persists on every terminal status**, and a run that fired a
  delivered effect and then failed carries `failed_after_effects: [node
  ids]` in its output — "failed after writes" is a state the surfaces show,
  not accounting policy *(R1 P2)*.
- **Settlement has exactly one owner.** `update_run_status` looks the chain
  up by run id on any terminal status, settles from its `fired` list, THEN
  forgets it *(R3)*; the completion paths do not settle *(R2)*. `settle()`
  waits (bounded, 30 s) for adapters still running on an active-dispatch
  count — unrelated effects stay parallel *(R3 P1)* — defers when called
  from inside a dispatch on the same thread *(R3 P0)*, and closes the chain;
  a dispatch that finishes after settlement re-settles. In the ledger a
  **write settlement is final in both directions**: a read that arrived
  first no longer leaves the admission row a read *(R3 P0)*. The old
  `settle(run_id, [])` read-shortcut runs only when no chain exists.
- **At most once and the RPC cap survive an interrupt.** On any non-completed
  terminal status the chain persists `effects_fired_before`, `rpc_calls` and
  `invocation_depth`; resume seeds the new chain from them, so a resumed
  cycle cannot refire and the depth is not reset *(R3 P0/P1)*.
- **Parallel overwrite conflicts are refused at compile.** Two fan-out
  siblings that both write a field with no reducer would fire their effects
  and then be rejected together at LangGraph's barrier; `compile_branch`
  refuses that shape *(R3 P0)*. Per-node reducer validation still runs
  before every dispatch *(R2)*.
- **The request's context reaches the node thread.** The run's worker is
  submitted with `contextvars.copy_context().run`, and the code node copies
  that context around the RPC invoker *(R2, R3 P0)*.
- **One dispatch per node, never two.** The completion paths (normal and
  resume) read the chain's evidence; `run_effects_for_branch` remains only
  for callers that compile without a chain (tests, legacy) *(R1 P1)*.
- **Resume refuses, never guesses.** The chain is in memory. After an
  interrupt, a later node that references an effect fired before it gets
  `no earlier node … in this run` — a refusal, never a decode of the 4 KiB
  persisted preview into a wrong PUT *(R1 P0)*. Semantic resume across
  effects (a durable private full-result artifact) is a follow-up, not this
  change.
- Dry-run threading is unchanged: `base_path=None` → adapters dry-run.

### D2. `source_code` nodes run in an OS-isolated subprocess with data and no credentials

`_build_source_code_node` dispatches to `NodeSandbox.run_sync`: a child
Python process, `stdin` JSON in / `stdout` JSON out, launched through a
**`BwrapLauncher`** on Linux (`--unshare-all --die-with-parent --new-session
--clearenv --chdir /tmp --tmpfs /tmp --setenv HOME /tmp`, read-only `/usr
/bin /lib /lib64` and the interpreter prefix, **no** `--share-net`, no
`/data`, no universe root, no credential mounts; parent `close_fds=True`,
private cwd) with `RLIMIT_AS` 512 MiB, `RLIMIT_CPU` = node timeout,
`RLIMIT_FSIZE` 16 MiB, `RLIMIT_NOFILE` 64 set **first thing in the child**
(no `preexec_fn` in a multithreaded parent) *(R1 P1)*. The in-process
`exec` path is deleted.

- **No environment switch.** The unsandboxed `PlainSubprocessLauncher`
  exists for the test suite and is chosen only by dependency injection
  (`NodeSandbox(launcher=…)`); production code reads no variable to pick it
  — four `env_file` sources reach production, so an env flag was a
  reachable escape hatch *(R1 P0)*. No bwrap → `SandboxUnavailableError` →
  run `failed` as `sandbox_unavailable`.
- **Output cap while reading.** stdout/stderr are read incrementally and
  the child is killed the moment stdout exceeds 8 MiB or stderr 64 KiB;
  `communicate()`'s accumulate-then-slice is not used *(R1 P0)*. User
  `print()` goes to a bounded buffer that becomes `stdout_tail`; the result
  JSON is written to the real fd only by the runner, so nothing the user
  prints can forge a result *(R1 P1)*.
- **Contract.** The source defines `def run(state, effects=None) -> dict`
  (one- or two-argument accepted). `state` = the node's declared
  `input_keys` plus schema-defaulted keys; `effects` = `{node_id: {"status",
  "body"}}` for the node's graph **ancestors'** authenticated calls, bodies
  full (from the chain, not the preview; JSON parsed). **Never headers**:
  `$ta.effect` denies them and persisted evidence strips their values
  because a `Set-Cookie` there is a credential — code gets exactly what a
  packet could already reference *(R1 P0)*. The return must be a dict; the
  sandbox hands it back **unfiltered** and it passes through exactly as the
  in-process node's did: the compiler's single-merge-writer guard sees an
  undeclared merge field and refuses it *(R1 P1)*; other undeclared keys land
  in state and are named in the node's event (`undeclared_outputs`). Message
  in ≤ 16 MiB, output ≤ 8 MiB, tails of 2 KiB as evidence.
  `invoke_mcp_action` inside the child is a **synchronous RPC** over the
  sandbox's pipes: the child asks, the parent answers through the run's
  invoker with the run's authority (node-enqueue, `wiki_read`, …); the child
  never holds the invoker, 32 calls per run, replies capped at 1 MiB.
  Non-zero exit, exception, timeout, bad JSON → `CodeNodeError` /
  `NodeTimeoutError`; the run classifies as **`code_node_failed`**
  (actionable by the chatbot: fix `run()` with `write_graph`) or `timeout`
  *(R1 P1: a new class, added, not assumed)*.
- **A code node may declare `effects` too.** Its returned delta carries the
  packet under an `output_key`, exactly as an LLM node's output does, and
  the packet fires at node time (D1). Fetch → edit → write can be three
  deterministic nodes and zero model calls at run time; the model designs
  the branch once.
- **Authority: authorship decides *whose* code runs; the sandbox bounds
  *what* it can touch.** A source_code node executes only when the run's
  `caller_provenance` is `own` — the branch was authored by the actor the
  run executes as (`runs.py` builds this once from the authenticated run
  row and the branch's `author`, the same predicate the sanitized-invoke
  design uses). `run_graph` admits a PUBLIC foreign branch directly and the
  cross-author strip only runs on fork, so this is checked where the run's
  identity exists: a foreign branch with code refuses at compile with
  `ForeignCodeError` → class **`node_not_accepted`** (chatbot: "remix it
  into your universe with `write_graph fork_from`, then run your copy") —
  remixing re-authors the code under the caller and *is* the acceptance
  *(R1 P0)*. `approved` / `approved_source_hash` become provenance only;
  `mark_approved` stays as the API's provenance stamp.
- **Data egress rule (explicit).** Data fetched under a universe's grants
  belongs to that universe: it may flow into that run's state, run output,
  code nodes and LLM nodes (the owner's own subscription reading the
  owner's own fetched data), and it leaves the universe only through that
  universe's consent-gated effects to destinations the owner granted. This
  is a new model-visible path for authenticated data — the packet contract
  deliberately kept full bodies out of evidence — and it is the intended
  payoff (`GET page → deterministic extraction → LLM reviews → conditional
  write` in one run). What bounds it is the same thing that bounds an
  engine-authored packet: the owner's grants and destinations. Foreign
  code cannot widen it because foreign code does not run (above)
  *(R1 P0)*.
- **The served sanitizer's rationale changes in this change.** The served
  `write_graph` strips approval so that engine-authored `source_code` was
  inert behind the runtime gate (its RCE backstop, in-process `exec`).
  With the gate replaced by sandbox + authorship, engine-authored code in
  the engine's own universe is *meant* to run: the sanitizer keeps stripping
  approval/author/fork (provenance hygiene) and its comment and the
  `sanitize-served-invoke-branch` design note are revised to name the new
  backstop — a foreign branch's code refuses by authorship, and no code
  runs in-process *(R1 P0)*.
- `invoke_mcp_action` inside the sandbox is the synchronous RPC described
  above (the parent answers with the run's authority, inside the request's
  copied `ContextVar` context so the authenticated actor - never the daemon's
  env identity - is what the invoker sees, 32 calls per RUN); the "approved
  source nodes enqueue" clause becomes "owner-authored source nodes enqueue"
  (spec delta).
- **Hosts without bwrap** (Windows, the desktop plugin runtime): a code
  node fails loudly with `sandbox_unavailable` and the message says to run
  the branch on the cloud universe. A portable isolation backend is part of
  the eventual shape and a named follow-up, not a test detail *(R1 P1)*;
  production today is the Linux daemon, which already runs served codex
  turns under bwrap inside the container. The exact code-node argv is what
  the sandbox tests exercise (`/proc/1/environ`, `/proc/self/fd`, `/data`,
  network, cwd), on the production host as live proof *(R1 P1)*.

### D3. Surface: no new handle, one node kind made real

`write_graph` accepts what it already accepts. Validation adds: a
`source_code` node must declare `output_keys`; source ≤ 50 KB; a denylist
hit is named. The tool description teaches the shape:

    fetch (effect GET, packet from a template or code; "accept_statuses": [404] if a miss is data)
    → edit (source_code: def run(state, effects): … return {"content": …, "sha": …})
    → write (effect PUT, body {"content": {"$ta.base64": {"$ta.ref": "content"}}, "sha": {"$ta.ref": "sha"}})

`read_graph` shows a code node's duration, exit status and stdout/stderr
tails like any other node's evidence, and a failed run's
`failed_after_effects`. This is an action under `write.graph` (PLAN Scoping
Rule 1: no new top-level primitive; the irreducibility finding is that
"deterministic compute over state and earlier responses" has one useful
shape).

### D4. `$ta.*` is frozen

The transform vocabulary stays for stored branches and is not extended. A
future edit shape is code, not an operator.

## Spec deltas (R1 P1: the full list)

- `graph-execution-substrate`: MODIFIED "source_code nodes execute
  in-process behind a fail-closed approval gate" → OS-isolated, authorship-
  gated; MODIFIED failure taxonomy (+ `code_node_failed`,
  `node_not_accepted`, `effect_already_fired` kind); MODIFIED "sandbox
  demand is advisory" (code nodes *require* it; `requires_sandbox` stays
  advisory for prompt nodes); MODIFIED "approved source nodes enqueue" →
  owner-authored, and no `invoke_mcp_action` inside the sandbox; ADDED
  effects fire at node time with the D1 rules.
- `external-effect-adapters`: MODIFIED "dispatch after run completion" →
  at node time, ancestry references, `accept_statuses`, full-result
  lifetime = the run, refusal after resume; the `$ta.*` requirement is
  unchanged and frozen.
- `engine-run-admissions`: MODIFIED the clauses asserting a failed or
  cancelled run fired nothing → settles from what fired; the existing
  "write fired then later failed stays a write" scenario already agrees.

## Alternatives rejected

- **Code as an effect sink on the post-run chain** (smallest change): keeps
  effects invisible to the graph, so an LLM node still cannot reason over a
  fetched page in the same run, and every future "see the result" need
  grows another chain feature. Wrong shape; rejected on the founder's
  2026-08-30 direction — and Codex round 1 agreed, with the concrete
  payoff case above.
- **Keep the approval-hash gate and add a `mark_approved` caller**: a host
  approval for the user's own code contradicts "every user is founder of
  their own universe" and would never be exercised by an uncoached universe.
  Authorship is the predicate instead.
- **Verb-based failure (reads never fail)**: wrong for GraphQL and for
  required reads; packet-declared `accept_statuses` instead *(R1)*.
- **An env flag for the unsandboxed launcher**: production-reachable;
  dependency injection instead *(R1)*.
- **Modelling the authenticated call as a separate explicit graph step
  with durable receipts and per-root budgets** (R1 concern): the effect IS
  declared on an explicit node today; ancestry, once-per-run and the
  effector's existing consent/idempotency receipts cover ordering,
  cardinality and replay for this change. Durable full-result artifacts for
  semantic resume are the named follow-up.
- **`asyncio` sandbox inside the sync node fn**: nested-loop hazards inside
  the worker thread; a plain subprocess with capped incremental reads is
  simpler and identical in behaviour.

## Risks the reviewer should attack (round 2)

1. Any remaining path where sandboxed code sees or emits more than a packet
   could (headers gone, ancestry only, egress rule) — including the
   stdout/stderr tails and the run output surface.
2. The authorship predicate: is `caller_provenance` derived from anything a
   node spec or a mutable row could influence? Does any path compile a
   branch for execution without an execution context?
3. Reducer view under fan-out; the merge-writer guard now seeing the full
   sandbox return.
4. Settlement: one owner, `forget` on every terminal status, no path left
   that settles `[]` while a chain exists.
5. `accept_statuses` as packet vocabulary: refusal shapes, interaction with
   the settlement verb rule.
6. The launcher DI: any code path constructing `NodeSandbox()` without a
   launcher in production, and the bwrap argv itself.

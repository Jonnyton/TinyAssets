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

## Decisions

### D1. Effects fire at node time, in graph order

When a node's function returns its state delta, the node's declared
`effects` fire **immediately**, inside the same node step, against a view of
state = current state merged with the delta (append/merge reducers applied
to the view exactly as LangGraph will apply them). The full adapter result
goes into a run-scoped `EffectChain` (in memory: `results[node_id]`,
`evidence[node_id][sink]` bounded, `fired[(sink, verb)]`); the chain is
created by `compile_branch` and returned on `CompiledBranch.effect_chain`.

- `$ta.effect` semantics are unchanged (`response.status` / `response.body`
  of an *earlier* node) — "earlier" now means *completed earlier in this
  run*, which for a linear branch is the storage order it always was. A
  reference to a node that has not completed (a parallel sibling) is
  refused as `invalid_body_transform`, not resolved to nothing.
- **A refused-before-the-wire packet fails the node.** So does a write
  (any verb but GET/HEAD) the far side answered ≥ 400. A **read** answered
  ≥ 400 does not: its status is data (probe-then-branch stays possible; a
  code node or conditional edge reads it). Failing the node raises
  `EffectFailedError` → the run ends `failed` with the exact message shape
  #2713 classifies (`external write failed - <node>/<sink>: <error>
  [<kind>]`), so `external_write_failed` / `external_write_refused` and their
  actionability keep working. Later nodes do not run: no `open_pr` 422 after
  a refused `write_readme`, no dangling `auto/tiny-*` branches.
- Evidence persists on **every** terminal status. Today a failed run stores
  `output={}`; a run that created a branch and then failed must still show
  the branch it created. `external_write_results` / `external_write_errors`
  are written from the chain at completion *and* at failure/cancel.
- Settlement uses the chain's `fired` list on every terminal path. A run
  that fired a write and then failed settles as a write (write is final);
  the FAILED→read shortcut in `update_run_status` applies only when nothing
  fired.
- The post-run dispatcher `run_effects_for_branch` stays for callers that
  compile without an effect chain (tests, legacy) and is **not** called from
  the completion path any more — one dispatch per node, never two.
- Resume after interrupt: the chain is in memory. A later node referencing
  an effect that fired before the interrupt resolves from the persisted
  bounded evidence (status + 4 KiB preview + `truncated`), never silently
  from nothing. Documented; the code node can test `truncated`.
- Dry-run threading is unchanged: `base_path=None` → adapters dry-run.

### D2. `source_code` nodes run in an OS-isolated subprocess with data and no credentials

`_build_source_code_node` dispatches to `NodeSandbox.run_sync`: a child
Python process, `stdin` JSON in / `stdout` JSON out, wrapped in **bwrap** on
Linux (the argv shape of `codex_provider.py:794-845` minus `--share-net`,
minus every credential mount: `--unshare-all --die-with-parent --new-session
--clearenv --tmpfs /tmp --setenv HOME /tmp`, read-only `/usr /bin /lib
/lib64` and the interpreter prefix, **no** `/data`, no universe root), plus
`RLIMIT_AS` 512 MiB, `RLIMIT_CPU` = node timeout, `RLIMIT_FSIZE` 16 MiB,
`RLIMIT_NOFILE` 64 in the child. The in-process `exec` path is deleted.

- **Contract.** The source defines `def run(state, effects=None) -> dict`
  (one- or two-argument accepted). `state` = the node's declared
  `input_keys` plus schema-defaulted keys; `effects` = `{node_id: {"status",
  "headers", "body"}}` for every *earlier* authenticated call in this run,
  bodies **full** (from the chain, not the 4 KiB preview; JSON bodies
  parsed). The return is filtered to `output_keys`; undeclared keys are a
  warning in evidence, not an error. Message in ≤ 16 MiB, output ≤ 8 MiB
  (the transformed-body cap), stdout/stderr tails of 2 KiB kept as
  evidence. Non-zero exit, exception, timeout, bad JSON → the node fails
  with `code_node_failed` / `timeout` (existing taxonomy) and the stderr
  tail in the message.
- **A code node may declare `effects` too.** Its returned delta carries the
  packet under an `output_key`, exactly as an LLM node's output does, and
  the packet fires at node time (D1). So fetch → edit → write can be three
  deterministic nodes and zero model calls at run time; the model designs
  the branch once.
- **Authority is the sandbox, not a host approval.** A node authored under
  the universe owner's authority (the owner, or the owner's own engine via
  `write_graph`) runs without `approved` / `approved_source_hash`; those
  fields become provenance only. Argument: the child has no network, no
  credentials, no data dir, and its only output is a state delta — which
  reaches the world solely through the owner's consent-gated connections,
  exactly like a packet the engine writes directly. A shared link cannot
  make this worse than an engine-authored packet already could. Cross-author
  remix keeps the existing strip (`_clear_source_code_approval`): the new
  owner's engine re-stores the node, which is the acceptance. The
  `FORBIDDEN_PATTERNS` denylist and the import allowlist stay as defence in
  depth; `requests`/`httpx` leave the allowlist (no network by design);
  `base64`, `io`, `csv`, `html`, `unicodedata`, `zlib`, `struct`, `operator`,
  `heapq`, `bisect`, `time` join it.
- **No bwrap → fail loudly.** Windows or a host whose probe fails
  (`providers/base.py:probe_sandbox_available`) raises
  `SandboxUnavailableError` → run `failed` with class `sandbox_unavailable`
  (already in the taxonomy). The plain-subprocess fallback exists only
  behind `TINYASSETS_CODE_NODE_UNSANDBOXED=1` for the test suite, never
  read in production (`deploy/compose.yml` does not set it). The droplet
  already runs served codex turns under bwrap inside the daemon container,
  so production has the sandbox today.
- `invoke_mcp_action` is not available inside the sandbox (it never had a
  caller in stored branches).

### D3. Surface: no new handle, one node kind made real

`write_graph` accepts what it already accepts. Validation adds: a
`source_code` node must declare `output_keys`; source ≤ 50 KB; a denylist
hit is named. The tool description teaches the shape:

    fetch (effect GET, packet from a template or code)
    → edit (source_code: def run(state, effects): … return {"content": …, "sha": …})
    → write (effect PUT, body {"content": {"$ta.base64": {"$ta.ref": "content"}}, "sha": {"$ta.ref": "sha"}})

`read_graph` shows a code node's duration, exit status and stdout/stderr
tails like any other node's evidence. This is an action under `write.graph`
(PLAN Scoping Rule 1: no new top-level primitive; the irreducibility finding
is that "deterministic compute over state and earlier responses" has one
useful shape).

### D4. `$ta.*` is frozen

The transform vocabulary stays for stored branches and is not extended. A
future edit shape is code, not an operator.

## Alternatives rejected

- **Code as an effect sink on the post-run chain** (smallest change): keeps
  effects invisible to the graph, so an LLM node still cannot reason over a
  fetched page in the same run, and every future "see the result" need
  grows another chain feature. Wrong shape; rejected on the founder's
  2026-08-30 direction.
- **Keep the approval-hash gate and add a `mark_approved` caller**: a host
  approval for the user's own code contradicts "every user is founder of
  their own universe" and would never be exercised by an uncoached universe.
- **Per-node effects but read failures also fail the node**: kills the
  probe-then-branch pattern (does this ref exist?). Reads are data.
- **`asyncio` sandbox inside the sync node fn**: nested-loop hazards inside
  the worker thread; a plain `subprocess` with `communicate(timeout=)` is
  simpler and identical in behaviour.

## Risks the reviewer should attack

1. The authority argument in D2 (sandboxed, credential-free code authored by
   the owner's engine needs no second approval).
2. Reducer correctness of the "view" a packet renders against at node time
   (append/merge fields).
3. Double dispatch: any path that still calls `run_effects_for_branch` after
   a chain-compiled run.
4. Settlement on failure/cancel after a write fired.
5. Parallel nodes firing effects concurrently — chain ordering and the
   "earlier" rule.
6. bwrap argv: anything that leaks `/data`, env, or network into the child.
7. Resume semantics (in-memory chain lost).

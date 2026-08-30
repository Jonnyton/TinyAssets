## 1. Shape (proposal + design, then one cross-family shape review)

- [x] 1.1 Proposal: why, what changes, impact (this change).
- [x] 1.2 Design: node kind, sandbox mechanism (bwrap inside the daemon
      container, as served codex turns already use), input/output contract,
      effects at node time, authorship as the authority predicate, limits,
      failure taxonomy.
- [x] 1.3 Codex round 1 on the design: REJECT (7 P0 / 11 P1) - headers to
      code, no owner predicate, per-visit cardinality, read-shortcut
      settlement, resume from truncated evidence, env-var sandbox switch,
      output cap after the fact; all folded (design.md "(R1)").
- [x] 1.4 Codex round 2 on the code: REJECT (6 P0 / 7 P1 / 2 P2), each
      reproduced - resume compiled without an execution context (foreign
      code failed open), RPC answered outside the request's ContextVars
      (daemon identity), effects fired before LangGraph's reducer rejection
      and before the merge-writer guard, at-most-once raced, a late dispatch
      settled a write as a read; plus graph-node vs def-id identity, evidence
      on INTERRUPTED, accepted 404 re-reported, one settlement owner, RPC cap
      per run, rlimits fail-loud, doc/spec contradictions. All folded, each
      pinned by a test in `tests/test_effects_at_node_time.py`.
- [x] 1.5 Codex round 3 on the code (the cap): REJECT (4 P0 / 4 P1 / 1 P2) -
      the request context was lost one hop earlier (the run's worker thread
      submitted without it), parallel fan-out siblings overwriting one field
      fired their effects before LangGraph rejected the step, "at most once"
      and the RPC cap reset on resume (fresh chain), settlement misordered
      under same-thread re-entrance and read-then-write; plus the run-wide
      dispatch lock serialising unrelated effects, resume resetting depth,
      the legacy dispatcher keyed by definition, obsolete approval guidance,
      a stale docstring. All folded and pinned (`copy_context().run` at the
      executor, `_validate_parallel_overwrites`, `seed_from_output`, an
      active-dispatch count with deferral and re-settle, write-final in both
      directions in the ledger). No fourth round: these folds are
      Claude-reviewed only and are reported to the founder as such.

## 2. Build the vertical slice

- [x] 2.1 `NodeSandbox.run_sync` is the only path for `source_code` nodes;
      in-process `exec` deleted; authorship (`caller_provenance == "own"`)
      replaces the approval gate (`ForeignCodeError` → `node_not_accepted`);
      denylist + 50 KB + syntax checks kept.
- [x] 2.2 Sandbox: `BwrapLauncher` (no network, no `/data`, no universe root,
      `--clearenv --chdir /tmp`, private tmpfs, rlimits first in the child,
      capped incremental reads, user stdout redirected), launchers injected -
      no env var; `PlainSubprocessLauncher` tests-only via `conftest`;
      `sandbox_unavailable` fails loudly. Live jail probe on the production
      container 2026-08-30 (real argv): network `ENETUNREACH`; `/data`,
      `/app`, `/etc/hostname` absent; `/usr` read-only; env = the six
      declared vars; `/proc/1/environ` is the jail's own init (19 bytes);
      fresh PID namespace; positive control edited the README bytes
      correctly with `effects` passed through.
- [x] 2.3 `run(state, effects)`: declared `input_keys` (+ schema defaults;
      `strict_input_isolation=False` = whole state) and ancestors'
      `{status, body}` (no headers); the return passes through to state
      (merge guard sees it); `$ta.ref` reads it from the next packet;
      `invoke_mcp_action` is a synchronous RPC answered by the parent.
- [x] 2.4 Effects fire at node time in graph order (`EffectChain`,
      `_wrap_with_effects`); at most once per node per run; ancestry-only
      references; fail-the-node rule with packet `accept_statuses`;
      evidence + `failed_after_effects` persisted on every terminal status;
      settlement from `fired`, one owner.
- [x] 2.5 `write_graph` docs teach fetch → code → write (CODE NODES section);
      the served sanitizer / approval verb name the new backstop.
- [x] 2.6 Tests: `tests/test_effects_at_node_time.py` (10, incl. fetch → code
      → write through the real sandbox subprocess and `code_node_failed`),
      `tests/test_node_sandbox.py` (85 + 6 bwrap-only), gate tests rewritten
      to authorship, taxonomy fixtures, node-enqueue over RPC (37).
- [x] 2.7 Plugin mirror rebuilt; spec deltas written (`specs/`).

## 3. Prove and close

- [ ] 3.1 Live: the founder's universe lands the README one-liner with its
      own fetch → code → write branch, no `$ta.*` operator, uncoached.
      2026-08-30 09:31Z, prod `81b1fe19`: the universe merged #2720 (-2/+1,
      exactly the fix) uncoached, retrying itself twice inside ONE turn. Its
      first attempt WAS a code node (fetch → edit → write, merge packet built
      by code) and my provenance rule refused it as foreign - the served turn
      stores the founder user id as author while runs execute as
      universe:<id>; it then fell back to `$ta.replace`, which the #2717
      nearest-match refusal unblocked. Fix: own = authored by the actor OR by
      an admin of the run universe (`_caller_provenance`). The code-node
      live proof is the next task once that ships.
- [x] 3.2 PLAN.md Design Decision "Capabilities are primitives the user's
      agent composes, not platform operators" (founder-approved 2026-08-30),
      naming effects-at-node-time and the sandboxed code node.
- [ ] 3.3 Delete
      `docs/concerns/2026-08-30-the-graph-has-no-deterministic-compute-step.md`;
      archive.

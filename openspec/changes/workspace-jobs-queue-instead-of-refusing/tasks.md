## 1. Make the existing wait reachable

- [ ] 1.1 Failing test first: two same-universe workspace jobs, the second
      submitted while the first holds the universe lock. Assert the second is
      admitted after the first releases, and that it does NOT raise
      `workspace_busy` at submit. Drive the real `admit()` with an injected
      clock/sleep (no wall-clock sleeping in the suite), and prove it RED
      against the current tree.
- [ ] 1.2 Pass a bounded `wait_s` from both `effectors/workspace.py::_admit()`
      call sites, derived from what the node can afford. The bound is the
      caller's; a packet-supplied wait is refused.
- [ ] 1.3 Confirm the wait still applies ONLY to `REFUSED_BUSY`: a quota, a full
      pool and the startup barrier must keep refusing immediately. Test each,
      and assert no sleep happens on those paths.
- [ ] 1.4 The sweep-once-retry-once path and the bounded wait must not compound
      into a multi-minute stall. Pin the total worst-case admission time.

## 2. Say what happened

- [ ] 2.1 A job admitted after waiting records that it waited, and for how long,
      so "it was queued" is visible rather than inferred from a latency bump.
- [ ] 2.2 A job that exhausts the wait still refuses with `workspace_busy` and a
      detail naming the holding run — the message already names it; keep it.

## 3. Evidence

- [ ] 3.1 Mutation table: default `wait_s` back to 0; drop the `REFUSED_BUSY`
      guard so quota waits too; make the wait unbounded. Each must go red.
- [ ] 3.2 Ruff + the touched suites + plugin mirror parity.
- [ ] 3.3 Cross-family review (Codex) — concurrency and admission are exactly
      the class `AGENTS.md` requires an independent reviewer for.
- [ ] 3.4 Live proof in the founder's universe: start two workspace jobs back to
      back and show the second completing without a manual retry.
- [ ] 3.5 **Tiny's verdict on row 6.** A bounded wait is not a durable queue;
      tiny decides whether it passes. Do not mark the row done.

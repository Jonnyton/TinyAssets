## 1. Shape (proposal + design, then one cross-family shape review)

- [x] 1.1 Proposal: why, what changes, impact (this change).
- [ ] 1.2 Design: node kind, sandbox mechanism (reuse the served-turn
      isolation path), input/output contract, effect interleaving,
      authority model, limits, failure taxonomy.
- [ ] 1.3 Codex refute of the design (shape, single-user safety holes).
      One round; fold; escalate only structural disagreement.

## 2. Build the vertical slice

- [ ] 2.1 `NodeSandbox` wired into `compile_branch` for `source_code` nodes;
      in-process `exec` path retired; no `approved`/hash gate for
      owner-authored nodes; denylist kept.
- [ ] 2.2 Sandbox: subprocess with no network, no data dir, private tmp,
      CPU/mem/wall limits, stdin/stdout JSON; portable (no POSIX HOME
      hardcode); `sandbox_unavailable` fails the run loudly.
- [ ] 2.3 Inputs: declared `input_keys` + earlier effects' `response.*`;
      outputs: declared `output_keys` into state; `$ta.ref` reads them.
- [ ] 2.4 Effect dispatch interleaves with node execution when a later node
      reads an earlier effect (branch order preserved).
- [ ] 2.5 `write_graph` docs teach fetch → code → write; validation names a
      missing `output_keys` / oversized source.
- [ ] 2.6 Tests: end-to-end branch with a fake provider; sandbox limits;
      no-network; refusal shapes; differential test against `$ta.replace`
      on the live README shape.
- [ ] 2.7 Plugin mirror; spec deltas synced.

## 3. Prove and close

- [ ] 3.1 Live: the founder's universe lands the README one-liner with its
      own fetch → code → write branch, no `$ta.*` operator, uncoached.
- [ ] 3.2 PLAN.md principle + node vocabulary entry (founder-approved
      direction 2026-08-30).
- [ ] 3.3 Delete
      `docs/concerns/2026-08-30-the-graph-has-no-deterministic-compute-step.md`;
      archive.

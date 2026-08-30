## 1. Shape

- [x] 1.1 Proposal: the two ceilings (read a codebase, run it) and the primitive.
- [x] 1.2 Design: workspace sink (checkout/push/discard) on the credentialed
      worker, workspace-bound code nodes with `ws.run`, consent-gated
      provisioning, usage limits, authority, taxonomy.
- [ ] 1.3 Codex round on the design (credential helper path, provision jail,
      path safety, exhaustion, push semantics, resume). Fold; three rounds is
      the cap.

## 2. Build

- [ ] 2.1 `tinyassets/effectors/workspace.py`: sink `workspace`, ops
      `checkout` / `push` / `discard`, packets validated against the
      connection's endpoint allowlist, consent for push, evidence bounded.
- [ ] 2.2 Worker-side git credential helper (`GIT_ASKPASS` from an fd; token
      never in argv/config/evidence); clone/fetch/push in the outbound worker.
- [ ] 2.3 `node_sandbox.py`: `run_sync(workspace=…)` binds `/workspace` RW,
      workspace limits profile, `ws` helper (`run/read/write/glob/path`),
      provision jail (`--share-net`, consent-gated), one-job lock.
- [ ] 2.4 `graph_compiler.py`: `workspace` node attribute resolved through the
      effect chain (ancestor checkout) or `$ta.ref`; timeout up to 3600 s.
- [ ] 2.5 Quota + GC per universe; taxonomy classes; `write_graph` docs teach
      checkout → code → push → PR → merge; plugin mirror; tests (unit +
      Linux-only jail tests + the live jail probe on the production host).
- [ ] 2.6 Spec deltas: `external-effect-adapters`, `graph-execution-substrate`,
      `engine-run-admissions`, outbound/credential.

## 3. Prove and close

- [ ] 3.1 Live, uncoached: the founder's universe checks out its repo, answers
      "how many Python files does the project have" from the checkout, runs
      `python -m compileall tinyassets`, commits, pushes, opens and merges the
      PR.
- [ ] 3.2 PLAN.md: the workspace joins the primitive list under the 2026-08-30
      decision; archive.

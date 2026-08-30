## 1. Shape (specs before code)

- [x] 1.1 Proposal: the two ceilings (read a codebase, run it) and the primitive.
- [x] 1.2 Design v1; Codex round 1 REJECT (credential path, provision network,
      aggregate limits, disk bounds, budgets in place of shape caps, lease
      lifecycle, consent typing, admissions, resume) — all folded into design v2.
- [x] 1.3 Delta specs written in the shape phase: `external-effect-adapters`
      (workspace sink), `graph-execution-substrate` (workspace-bound code
      nodes), `engine-run-admissions` (workspace admission kind),
      `credential-vault` (credentialed git), `scratch-storage` (new).
- [ ] 1.4 Codex round 2 on design v2 + delta specs. Fold. Round 3 is the cap.

## 2. Build — slice A: checkout, run, push

- [ ] 2.1 `tinyassets/scratch.py`: lease store (opaque ids bound to universe/
      connection/repo/class/generation), state machine, release outbox
      processed after the terminal commit, startup + periodic sweepers,
      quarantine-rename-delete, pool bytes accounting.
- [ ] 2.2 Outbound worker: `git_read`/`git_write` grant scopes per (host,
      repo); staging-repo clone/fetch/push with the trusted credential
      helper, from-empty environment, forced options, DNS/IP classification,
      intent journal + `ls-remote` reconciliation, stderr scrubbing.
- [ ] 2.3 `tinyassets/effectors/workspace.py`: sink `workspace`, ops
      `checkout`/`push`/`discard`, typed consents, branch policy (remote HEAD
      refused, `tiny/…` only, exact-SHA fast-forward), bounded evidence,
      failure classes.
- [ ] 2.4 `node_sandbox.py`: exact-path workspace bind, `ws.run/read/write/glob`
      with incremental bounded drains and whole-jail timeout, workspace
      limits profile, RSS watchdog, command/evidence caps.
- [ ] 2.5 `graph_compiler.py` + `runs.py`: `workspace:` resolved only through
      the chain capability; per-universe + box-wide job lock; `workspace`
      admission consumed on checkout, external-write settled as read.
- [ ] 2.6 `write_graph` docs; taxonomy; plugin mirror; tests (unit, Linux-only
      jail, live jail probe on the production host).

## 3. Build — slice B: provisioning

- [ ] 3.1 Resolver jail (no checkout, egress limited to declared registries
      after DNS/IP validation; option-line rejection), offline install into a
      workspace-local venv / `npm ci --offline`; consent `workspace_provision`.

## 4. Companion: `run-usage-budgets`

- [ ] 4.1 Per root run: ≤ 500 effect dispatches, ≤ 256 MiB outbound bytes;
      per universe per hour: ≤ 5,000 dispatches, ≤ 2 GiB; refusal
      `effect_budget_exhausted` naming the budget; tier-raisable.

## 5. Prove and close

- [ ] 5.1 Live, uncoached: the founder's universe checks out its repo, answers
      "how many Python files does the project have", runs
      `python -m compileall tinyassets`, commits, pushes `tiny/…`, opens and
      merges the PR.
- [ ] 5.2 PLAN.md: the workspace joins the primitive list; named follow-ups
      recorded (runner sidecar / cgroup, scratch filesystem with quotas,
      toolchain profiles); archive.

# Tasks: detect stranded local lanes

## 1. Lock the behavior with failing tests

- [x] 1.1 Add a temporary-repository test proving a scratch clone with an ahead
  commit and no pushed branch is enumerated, named, and returns 2.
- [x] 1.2 Extend the fixture so a pushed branch plus stubbed PR returns 0.
- [x] 1.3 Add coverage for remote-branch-without-PR and dubious-ownership-style
  unknown results.

## 2. Implement the read-only detector

- [x] 2.1 Implement registered-worktree plus scratch/sibling union enumeration.
- [x] 2.2 Implement ahead, pushed-branch, and PR checks with explicit
  `STRANDED`/`UNKNOWN` rendering and exit codes 0/2.
- [x] 2.3 Keep all runtime subprocesses read-only and surface command failures.

## 3. Prove the guard is non-vacuous

- [x] 3.1 Run the focused tests green.
- [x] 3.2 Temporarily delete the core stranded predicate, run the focused test
  red, restore it, and rerun green.
- [x] 3.3 Run the command against the `2c1f63cb`-era local inventory and capture
  output naming `.codex-scratch-uptime-canary-1461`.

## 4. Review and publish without merging

- [x] 4.1 Run lint/focused regression checks and inspect the complete diff.
- [ ] 4.2 Obtain opposite-family independent review and resolve findings.
- [ ] 4.3 Commit, push `feat/check-stranded-lanes`, and open a draft PR whose body
  includes acceptance output, detector limitations, and follow-up wiring advice.

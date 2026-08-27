# Exact-head cross-family reviews of the harness cut (PR #2561)

**Reviewer:** Codex (`scripts/peer_agent.py codex`, read-only, `--effort high`), opposite family
**Subject:** `harness-cut2` vs `origin/main` — 522 files, +535 / −72,350
**Why gated:** the PR edits `.github/heavy-test-files.txt`, a **gate-defining** file. A PR touching
the files that define the required-test gate can weaken the check judging it, so
`pr-scope-guard.yml` demands an exact-head review receipt regardless of branch name. Self-stamping
it would be precisely the self-attestation the mechanism exists to prevent.

## Rounds

| # | Head | Verdict | Findings | Fixed in |
|---|---|---|---|---|
| 1 | `ceee8139` | **REJECT** | 7 | `7eaaeaf0` |
| 2 | `7eaaeaf0` | **REJECT** | 4 | `fd765b90` |
| 3 | `91ecc713` | **REJECT** | 4 | `925928ac` |

Three independent REJECTs on a change I had already convinced myself was finished. Every round
found something a self-review had not.

## Round 1 (7 findings)

1. **Live data-loss risk.** `clear_sandbox_temp_dirs.ps1` matched residue roots with `StartsWith`,
   so `.claude` also matched `.claude/agent-memory` — irreplaceable content that
   `-IncludeTestResidue` would have deleted recursively. The "fail-closed" claim was false. Now an
   exact allowlist plus anchored patterns, proven with a decoy worktree holding
   `.claude/agent-memory/MEMORY.md` beside a `.pytest_cache`: refused, memory intact. **The founder
   had already run this script once.**
2. **Unquarantined test regression.** `test_canary_scripts_import_smoke.py` still named the deleted
   `navigator_wiki_sweep` — the third deletion in one session to escape a name-based check, because
   the reference was a bare string inside a tuple.
3. **The dispatch hook emitted a command that cannot run** — `peer_agent.py --out …` with no
   positional `claude|codex`, which argparse rejects.
4. **Spec sync wrong in both directions.** It kept SHALLs for deleted machinery *and* retired three
   requirements whose machinery survives — exact-head receipts, lane-local worktree dispatch,
   consoleless launch. A blanket block retirement deleted live contracts.
5. **The queue.** I archived 5 and argued the other 62 "carry real progress" — against a 14-day
   idle rule I wrote in this same reset. 46 of 62 qualified. 62 → 16 active.
6–7. Two smaller corrections, folded into `7eaaeaf0`.

## Round 2 (4 findings)

Fixed in `fd765b90`; see that commit for the itemised list.

## Round 3 (4 findings)

Codex confirmed the heavy-test edit itself is safe: both removed entries' test files are deleted by
this PR, and removal would otherwise move a surviving test into the fast lane, not drop it from CI.

1. **Spec drift the archive created.** `2026-08-26-reconcile-stale-retired-fleet-artifacts` is
   complete and its machinery runs (`tinyassets/runtime_reconcile.py:168`), but its four ADDED
   requirements never reached the as-built spec. Archiving without syncing is the "landed change
   with unsynced deltas" AGENTS.md calls a failing gate — opened by the round-1 fix that archived
   51 changes. All 51 audited the same way; exactly one had complete tasks plus unsynced deltas.
2. **Fail-closed dispatch lost its tests.** Eleven tests covered the fail-closed contract against
   `codex_review.py`; consolidating onto `peer_agent.py` deleted them with the script. Six ported,
   and **mutation-proven** — injecting `return 0` at `peer_agent.py:375`, `:381`, `:416` fails
   exactly one test each.
3. **The skill promised enforcement that no longer exists** — `peer-agents/SKILL.md:58` credited
   `peer_agent.py` with an adversarial preamble and VERDICT enforcement it does not have.
4. **A resumed lane's mandated review command could not run** — `RESUME-SPEC.md:116` still executed
   the deleted `codex_review.py`.

## What this says about the reset

The gate worked. Its whole purpose is that a change touching the gate cannot vouch for itself, and
in three rounds it caught a data-loss risk in a script the founder runs, a test regression, a spec
that asserted deleted machinery *and* dropped live contracts, and a fail-closed contract whose
coverage had silently gone to zero. None of those were visible from inside the change.

The recurring shape is worth naming: **every finding was a claim of mine that no executable check
could contradict.** Name-based deletion checks, "fail-closed" asserted rather than mutated, tests
that passed because they no longer tested anything. The reset's own thesis — gates that can
actually fail — is what the review kept enforcing against the reset.

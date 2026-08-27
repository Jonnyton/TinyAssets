# Handoff — open lanes as of 2026-08-26

> **SUPERSEDED 2026-08-27.** Two of its three lanes are closed:
> **Lane 2** (`claude/fleet-slice1-reconciler`) already landed —
> `tinyassets/runtime_reconcile.py` carries `build_stale_fleet_plan` and
> `reconcile-stale-retired-fleet-artifacts` is archived complete, confirming what
> this document guessed. **Lane 3** (PR #2561) merged as `a44aed2c`.
>
> **Lane 1 (`claude/run-provider-session`, PR #2559) is still the live lane** and
> its warning below still stands — the last commit is unreviewed WIP and the
> `_PURPOSE.md` describes a different lane than the commits.
>
> Current state: `docs/handoffs/2026-08-27-closed-branch-index.md`.

Written for a **fresh session with no resumed history**. Everything below is on
GitHub; nothing depends on a local worktree, and all local `wf-*` worktrees were
removed after this was written.

`main` is at the merged harness reset (`e4180697`), deployed and verified live.

---

## Lane 1 — foreground run provider authority *(the active lane)*

**Branch:** `claude/run-provider-session` · **Head:** `19524770` · pushed
**OpenSpec change:** `openspec/changes/run-provider-authority/`

Four commits ahead of `main`:

| Commit | What |
|---|---|
| `be7a3a4b` | openspec: proposal — foreground runs need their own provider authority |
| `0389e6b8` | runs: foreground runs mint their own provider authority |
| `3eb798eb` | inventory: record the foreground-run execution callsites this change added |
| `19524770` | **wip**, committed only so a worktree teardown could not lose it |

**That last commit is unreviewed and unverified.** It carries 213 insertions
across `tinyassets/runs.py`, `tinyassets/foreground_run_provider.py`, both
packaging mirrors, `tests/test_run_provider_session.py`, and the change's
proposal/design/tasks. It was uncommitted work in a worktree; committing it was
preservation, not a claim it is finished. **Read the diff before trusting it.**

To resume:

```bash
git fetch origin
git worktree add -b resume/run-provider-authority ../wf-run-provider origin/claude/run-provider-session
cd ../wf-run-provider
python -m pytest tests/test_run_provider_session.py -q
git log -p 3eb798eb..19524770        # the unreviewed part
```

**Note the lane drifted.** Its `_PURPOSE.md` still describes the earlier
"assigned consumer activation + visible refusal" work (branch
`claude/consumer-activation-visibility`, live finding 2026-08-25 19:14Z, task
`bt2_acab8c31` stuck at `no_live_compatible_worker`). The branch was repurposed
for provider authority without updating it. **Decide which lane you are in
before building** — the purpose file and the commits disagree, and the commits
are the truth.

Memory refs from the original lane: `background-executor-carrier-path-implemented`,
`no-review-loops-on-dark-mvp`.

## Lane 2 — fleet slice 1 reconciler *(likely already done)*

**Branch:** `claude/fleet-slice1-reconciler` · **Head:** `2e5b21a1` · pushed
2 commits ahead of `main`; the substantive one is *"safe stale-fleet reconciler
(dry-run-first, CAS + digest, no delete)"*.

Its OpenSpec change, `reconcile-stale-retired-fleet-artifacts`, was **7/7 tasks
complete** and was archived on 2026-08-26 as complete-but-unarchived. So this
branch probably just needs a PR, or dropping if it already landed by another
route. **Check before rebuilding it.**


## Lane 3 — the cut-list PR *(open, awaiting a review receipt)*

**PR #2561** · branch `harness-cut2` · head `f2c8a0fe` · pushed
72,000+ deletions completing the post-reset cut list.

**It is blocked on one thing:** it edits `.github/heavy-test-files.txt`, which is
gate-defining, so `pr-scope-guard` requires an **exact-head review receipt** in
the PR body:

```
Drain-Review-Verdict: APPROVE
Drain-Review-Head: f2c8a0fed4059de4b8a1d772005cd9583e2f0fcc
Drain-Review-Artifact: <path-or-url>
```

Two cross-family reviews already ran against earlier heads and both returned
REJECT; all eleven findings were fixed. A third was dispatched and had not returned when this
session ended; note the head has since moved, so any receipt must name the
current sha. **Do not self-stamp the
receipt** — the mechanism exists precisely so the approval is not written by the
author. Dispatch a fresh one:

```bash
python scripts/peer_agent.py codex --out review.txt --prompt-file brief.md --cwd .
```

Worth knowing before you trust the diff: the two prior reviews caught a
destructive fail-open in `scripts/clear_sandbox_temp_dirs.ps1`, 115 broken path
references that **the passing test suite did not reveal** (they were docstrings),
and an OpenSpec spec that validated as syntactically fine while being
semantically wrong in both directions. A green suite was not sufficient evidence
on this branch, twice.

If the PR is unwanted, closing it costs nothing — everything it deletes is
still on `main` and recoverable.

## What changed under you

The harness reset merged and deployed. If you have habits from before
2026-08-25, these are gone:

- **`STATUS.md` is retired.** Live state has typed homes: `openspec/changes/`
  (queue, via `python scripts/openspec_flow.py audit`), `docs/concerns/`
  (findings), `docs/host-actions.md` (founder-only), git branches (ownership).
  A smoke test now *asserts* `STATUS.md` stays absent.
- **No Agent Teams, no fleet, no drain, no Cowork.** Two providers — Claude Code
  and Codex CLI — dispatching to each other as subprocess peers via the
  `peer-agents` skill. `scripts/codex_review.py` is gone; use
  `scripts/peer_agent.py`.
- **7 skills, not 34.** No router; read the one named for your task.
- **Gates can fail now.** `invariants` is a required check.
  `check_context_budget` is HARD and follows `@imports`. `scripts/deployed_sha.py`
  makes "merged is not deployed" executable. `pr-scope-guard` requires an
  exact-head receipt for `tinyassets/auth/`, `credential_vault.py`, and
  `api/{permissions,interlocutor,visibility,engine_helpers}.py`.
- **Spec what is hard to reverse; build the rest.** A change directory is
  required for public surface, storage shape, authority, migrations, and money.
  Everything else: build it, prove it live, write the spec from what shipped.

Read `AGENTS.md` (255 lines) and `CLAUDE.md` (49). They are current.

## Open, and not owned by any lane

- **16 active OpenSpec changes**, 1 in flight (PR #2561 archives 51 that were
  idle past the 14-day rule). `python scripts/openspec_flow.py audit` ranks them.
  If #2561 is closed rather than merged, the queue reverts to 67.
- **9 open concerns** in `docs/concerns/`, two P0. Start at its `README.md`.
- **Founder-only items** in `docs/host-actions.md`.
- `deployed_sha` proves the *receipt*, not the running binary — a rollback with
  an intact receipt reads as shipped. Tracked as its own concern; the fix is a
  product change to `tinyassets/api/status.py`.

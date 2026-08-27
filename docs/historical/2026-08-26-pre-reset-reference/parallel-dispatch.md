# Parallel dispatch — multi-provider coordination

**HISTORICAL — superseded.** Describes machinery deleted by the 2026-08-25/26 harness reset. Do not cite as live; see [README.md](README.md).

Canonical procedure for working alongside other providers on this repo.
Pointer-loaded per [ADR-002](../decisions/ADR-002-static-vs-dynamic-context-budget.md):
`AGENTS.md` § *Parallel Dispatch* keeps the contract and the session-start
checklist; everything below is the detail.

This file is the ONE home for the session-start ritual, the provider-context
feed checkpoints, the Work-table row schema, stale-claim reaping, the pre-claim
collision guard, and worktree lane discipline. If you find any of it restated
elsewhere, replace the copy with a link here.

**Multi-provider concurrent execution is the default operating mode.**
Multiple providers (Claude Code, Codex, Cursor, Cowork, future) work on
this project at the same time. The host does not announce when a new
provider is started; coordination flows through STATUS.md, not through
chat. Treat any session-start as "the team is already running; what's
safe to claim?"

The complete coordination contract is: **STATUS.md Work table is the
authoritative claim surface.** No external locks. No runtime signaling.
A provider with a fresh checkout, no chat history, and no announcement
should be able to start working productively in under a minute.

## Provider session-start ritual

Every provider, every session, in this order:

0. **Run `python scripts/session_sync_gate.py`.** Fetches with `--prune` and
   warns if the primary checkout is off `main` or behind origin/main — the
   "1,209 behind / stale refs" trap. Advisory; never mutates the tree. Claude
   Code fires it automatically via the `SessionStart` hook.
1. **Read STATUS.md.** Concerns + Work table + Next.
2. **Run `python scripts/worktree_status.py`.** This shows dirty current
   checkouts, worktrees that need `_PURPOSE.md`, orphaned or missing paths,
   lanes that need PR/STATUS promotion, and parked draft lanes. Do not switch
   a dirty checkout to `main`; start a clean main-based worktree for new
   live-ready work.
3. **Run `python scripts/claim_check.py --provider <yourname>`.**
   Output classifies every Work row into CLAIMABLE / BLOCKED / IN-FLIGHT
   / HOST-OWNED / STALE-CLAIM. The CLAIMABLE list is what's safe to
   start on right now; BLOCKED tells you why something isn't; IN-FLIGHT
   shows files off-limits.
4. **Run `python scripts/provider_context_feed.py --provider <yourname> --phase claim`.**
   This scans provider memories/configs, shared ideas, recent research
   artifacts, worktree handoffs, and provider automation notes. It is a
   context feed, not a backlog writer. Relevant candidates must be promoted
   into a current STATUS/worktree/PR lane before they become build authority.
   Claim phase deliberately includes durable memory/brain notes authored by
   other AI families, not only your own provider. Search the feed for the
   issue/request slug and related domain terms before assuming no prior
   Claude/Codex/Cursor/Cowork context exists.
5. **Claim by editing STATUS.md.** Change the chosen row's Status cell
   to `claimed:<yourname>`. Use a session-specific provider name when
   more than one session from the same tool may be active (for example
   `codex-gpt5-desktop`, `codex-cli-2`, `cursor-gpt55`). Commit that
   edit on your branch (or directly to main if you're operating without
   a worktree). The edit IS the claim — no other notification required.
6. **Scan cross-implications before building.** Before implementation,
   compare your claimed task against active `STATUS.md` rows,
   `ideas/PIPELINE.md` Active Promotions, and recent research/design
   artifacts for matching domain terms, files, primitives, or user surfaces.
   If a research-derived finding may affect your design, read its artifact
   before coding and either add a `Depends` edge / note to your row or record
   why it does not apply. Do not bypass an opposite-provider review gate just
   because your task is named differently.
7. **Work in a worktree or branch.** `git worktree add ../wf-<task>` or
   feature branch. Do not write outside your row's Files write-set
   without first updating STATUS.md to reflect the new write-set. A branch is
   isolation, not memory; make sure the lane has `_PURPOSE.md`,
   `.agents/worktrees.md`, STATUS row, or draft PR metadata before leaving it.
8. **On land**, change Status -> `done` and delete the row in the same
   commit. The commit is the audit trail.

## Provider-context feed checkpoints

`provider_context_feed.py` is a lifecycle gate, not a session-start-only
ritual. Run it whenever a provider is about to narrow or advance durable work:

- `--phase claim` before claiming or adding a STATUS row.
- `--phase plan` before writing a plan, design note, exec plan, or
  `_PURPOSE.md`.
- `--phase build` before implementation starts and again before broadening a
  Files cell.
- `--phase review` before reviewing another provider's work.
- `--phase foldback` before pushing, opening/updating a PR, merging, or
  retiring a STATUS row.
- `--phase memory-write` after writing provider memory, idea-feed entries,
  research artifacts, reflections, or `_PURPOSE.md` so related candidates can
  be folded into the current lane immediately.

If a harness supports automatic hooks or automations, wire those checkpoints
there too, but the shared contract remains the script + STATUS/worktree/PR
promotion. The scanner may produce noisy candidates; the agent must read the
relevant ones and then either promote them into the lane or explicitly note why
they do not apply. `ideas/INBOX.md` remains a loose idea feed at the bottom of
lanes, never design truth or permission to build.
The phase filters are coarse triage, not proof that unrelated context is
absent. Bare CLI use should start with the default limit for a broad sweep,
use `--limit 10` for compact hook-like triage, and use `--limit 200` when
auditing whether a category is absent.

## Work-table row schema

Every row must have:

- **Files** — specific files or directories this task will write.
  This is the collision boundary. Be concrete: `tinyassets/api/wiki.py, tinyassets/storage/__init__.py`
  not `backend`. Read-only dependencies go in Depends, not Files. Use
  comma or semicolon between atoms.
- **Depends** — which tasks must merge first. Include both task
  dependencies (`#18, #23`) and file-read dependencies. If your task
  needs to read `api.py` after another task rewrites it, that is a
  dependency.
- **Status** — one of: `pending`, `claimed:<provider>`, `in-flight`,
  `dev-ready`, `host-action`, `host-decision`, `host-review`,
  `monitoring`, `done`. Provider is the tool/session name: `codex`,
  `claude-code`, `cursor`, `cowork`, or a more specific label such as
  `codex-gpt5-desktop` / `cursor-gpt55` when generic names would be
  ambiguous. `claimed:*` and `in-flight` mean the row's Files are
  off-limits to others until status flips.

## Stale-claim reaping

A claim is stale if its Files have seen no commits in 24h and the row
has no fresh active-date heartbeat. `claim_check.py` flags these as
STALE-CLAIM CANDIDATES. Any provider may reap a stale claim by editing
the row Status to `reaped:<yourname>:no-activity-24h`, then re-claiming
as their own (`claimed:<yourname>`). No daemon, no permission needed;
the convention is the policy. If a provider is actively building or
testing before a commit lands, add `ACTIVE YYYY-MM-DD` to the Work row
task text or status note. That heartbeat keeps the claim live for the
date shown and prevents uncommitted active work from being reaped just
because it has not landed yet.

## Pre-claim collision guard

Before adding a new row or broadening a Files cell, run
`python scripts/claim_check.py --provider <yourname> --check-files "path/a.py, docs/foo.md"`.
It warns if your prospective claim's Files overlap any in-flight row's
Files. Substring match either direction. If overlap fires, EITHER add a
Depends edge (the overlap is real coordination) OR refine your row's
Files to be narrower (the overlap was a hint, not a real write).

## Worktree lanes

GitHub is the integration model: a worktree is the local checkout for one branch,
the branch folds back through a PR, and `STATUS.md` is the claim surface. **A
branch is not durable memory** — it remembers commits, not why it exists, whether
it is live-safe, or who owns it.

Canonical procedure — the four lane states, the `_PURPOSE.md` template, numbered
creation steps, `worktree_status.py` diagnostic states, and the branch-lifecycle
automation layers → **[`worktree-discipline.md`](worktree-discipline.md)**. That
file is the single home; do not restate it here.

The two invariants that gate claiming, repeated because they are cheap and
load-bearing:

- **Never switch a dirty checkout to `main`.** Start a clean main-based worktree
  for live-ready work; merging to `main` is production-impacting.
- **Review-blocked work still gets a visible lane** but must not advance past
  planning/scaffolding until the required opposite-provider review returns
  `approve` / `adapt`.

## Staying unblocked

If `claim_check.py` shows zero CLAIMABLE rows, look for cross-cutting
work that doesn't appear in the Work table: docs hygiene, skill audits,
test surface, design-note classifications, audit follow-ups. Add a new
Work row for the task you pick up rather than working off-table — that
keeps the next provider's `claim_check.py` accurate.

---

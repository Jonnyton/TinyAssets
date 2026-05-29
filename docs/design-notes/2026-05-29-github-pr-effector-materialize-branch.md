# github_pull_request effector must materialize the change into a branch (BUG-111)

**Status:** DESIGN — writer:claude, needs checker:codex cross-family review before build.
**Date:** 2026-05-29
**Tracks:** BUG-111 (wiki). Follows BUG-110 (gh install, fixed via PR #1134).

## Problem

The `github_pull_request` effector (`workflow/effectors/github_pr.py`) opens a PR
by shelling out to `gh pr create --repo <dest> --title --body --base --head`.
It never creates or pushes the head branch, and it **ignores the packet's
`changes_json` entirely** — `_invoke_gh_pr_create(payload, destination)` only
reads `title`/`body`/`base_branch`/`head_branch`/`draft`/`labels` from the
payload.

So even with a perfectly authored node and all gates passing, the loop cannot
ship code. Verified live after BUG-110's fix deployed:

- Run `f1f241258ef24995` (branch `96f4cc46f4d6`) — a user-authored
  `prompt_template` node emitting a valid `external_write_packet` with `effects:
  [github_pull_request]`.
- The packet reached the effector; `gh pr create` ran against GitHub and was
  rejected by the API:

```
external_write_results.open_pr.github_pull_request = {
  "error_kind": "gh_nonzero_exit",
  "stderr": "pull request create failed: GraphQL: Head sha can't be blank,
             Base sha can't be blank, No commits between main and
             autolab/probe-v3-k9x4m2, Head ref must be a branch (createPullRequest)",
  "destination": "Jonnyton/Workflow", "phase": "phase_2"
}
```

This confirms two prior gates are now clear: `gh` is **installed** (BUG-110)
and **authenticated** (the call reached GitHub's GraphQL API, not an auth
error). The remaining gap is that the head ref does not exist and has no
commits — because nothing in the pipeline ever wrote `changes_json` to files,
committed them, or pushed the branch.

## Root cause

The effector assumes a pre-existing remote head branch. Nothing in the
external-write path creates one. The packet carries the change set
(`payload.changes_json` — a `{path: full-new-contents}` map) but the effector
discards it. The PR-opening capability is therefore incomplete: it can open a
PR *shell* between two refs, but cannot produce the head ref from a change set.

## Constraint: no git checkout in the runtime image

The daemon runtime image (root `Dockerfile`, second stage) COPYs only the
Python package trees (`workflow/`, `domains/`, `fantasy_daemon/`, …). There is
**no `.git` checkout of `Jonnyton/Workflow`** on the daemon and **no `git`
binary** in the runtime apt block. So a "clone → write files → commit → push"
approach would require adding: the `git` binary (another image line, a
BUG-110-shaped follow-on), a runtime clone (network + disk + a push-scoped
token), and push auth wiring.

## Options

**Option A — local clone + git push.** Add `git` to the image; at effector
time, shallow-clone the destination at `base_branch`, write `changes_json`,
commit, push `head_branch`, then `gh pr create`. Familiar, but heaviest:
per-run clone latency/disk, a second binary, and a push-scoped token wired into
git credentials.

**Option B — GitHub Git Data API via `gh api` (recommended).** `gh` is already
installed and authenticated. Build the branch entirely through the API, no
local repo:
1. `gh api repos/<dest>/git/ref/heads/<base>` → base commit sha + tree sha.
2. For each `(path, contents)` in `changes_json`: `gh api ... /git/blobs` →
   blob sha.
3. `gh api ... /git/trees` with `base_tree` = base tree sha + the blob entries
   → new tree sha.
4. `gh api ... /git/commits` (parent = base commit) → new commit sha.
5. `gh api ... /git/refs` create `refs/heads/<head_branch>` → commit sha (or
   update if it exists, gated by idempotency).
6. `gh pr create --head <head_branch> --base <base_branch> …` (unchanged).

No git binary, no clone, no second token — minimal-primitives aligned, and it
reuses the auth the effector already proved works. Deletions/renames in
`changes_json` need an explicit tree-entry convention (e.g. `sha: null`).

## Recommendation

Option B, implemented as a new step inside `run_github_pr_effector` between the
idempotency reservation (Gate 3) and `_invoke_gh_pr_create`, fired only on the
real-write path (never on a dry-run). The reservation/receipt machinery and all
four existing gates are unchanged. `changes_json` becomes load-bearing input;
packets that declare a head branch but carry no `changes_json` should fail
loudly (no silent empty-branch PR).

## Open questions for review (checker:codex)

1. **Token scope.** The gh auth the effector reaches GitHub with — is it
   `contents:write` + `pull_requests:write` for `Jonnyton/Workflow`? Git Data
   API writes need `contents:write`. Confirm before build.
2. **Idempotency across the new steps.** The existing reservation covers the PR
   create. A re-run that already created the ref but failed at `pr create`
   should detect+reuse the ref (step 5 update-or-skip) rather than error.
3. **Failure-mode surface.** Each API step needs a distinct `error_kind`
   (`blob_create_failed`, `tree_create_failed`, `ref_exists`, …) so triage is
   not just `gh_nonzero_exit`.
4. **Scope boundary.** This stays an effector (platform) capability — users
   cannot push to the repo without the effector's authority — so it is *not* a
   user-composable primitive. Confirm that framing holds.

## Out of scope

- The misleading `node_not_approved` failure_class on body-less nodes
  (separate, unfiled).
- The triage classifier flagging concrete bugs (BUG-110, BUG-111) as
  `effort_class: ghost-risk` on observed/expected length ratio (separate
  loop-health item; watch for recurrence).
- The autoresearch-lab v2 loop wiring (separate; unblocked once this lands —
  `open_pr` is a `prompt_template` node emitting the packet, proven).

# Auto-merge landed #2773 six minutes after its Codex verdict said REJECT

**Filed:** 2026-09-02, from the Google Play launch lane (PR #2773, branch
`claude/play-store-launch`).
**Verified:** yes — timestamps from `gh pr view 2773`, `gh run list --workflow
auto-enroll-merge.yml`, and the review file's mtime:

| UTC | Event |
|---|---|
| 05:56:20 | PR opened (non-draft), Codex review already dispatched on the same head |
| 05:59:53 | `auto-enroll-merge.yml` enrolled it for auto-merge |
| 06:03:35 | `output/codex-review-2773.md` written: **VERDICT: REJECT**, 4 × P1 |
| 06:09:00 | Required checks green → GitHub merged `1a289a16` as `f2ca621d` |

The agent read the verdict after the merge (context compaction sat between the
two). The fixes went into a second PR carrying a different branch; nothing on
`main` broke, but `main` carried a privacy page the reviewer had called
"neither comprehensive nor fully true" and a runbook claiming a launch
readiness it did not have.
**Severity:** P2 — no outage, no data path; the cross-family gate that
`AGENTS.md` says gates landing was bypassed by timing alone, for a
public-surface change.

## What happened

`auto-enroll-merge.yml` enrols every non-draft same-repo PR on `opened`,
`synchronize`, `ready_for_review` (its one condition is
`github.event.pull_request.draft == false`). The Codex review is a background
subprocess whose verdict lands in a file nobody but the dispatching agent
reads. Nothing binds the two: when the review takes longer than CI, CI wins.
`docs/concerns/2026-08-31-the-exact-head-receipt-loops-against-iterative-review.md`
is the same seam from the other side — the exact-head receipt is the one
mechanism that DOES bind a review to a head, and it only covers `AUTHORITY_RE`
paths, not a `WebSite/` privacy page or a release workflow.

Memory already recorded the pattern twice ("Codex gate invisible to
auto-deploy", "Auto-merge can land a stale head"). A memory is advice to the
next agent; this is the third landing, so it needs a home a gate can read.

## Fix candidates (not chosen here)

1. **Open as draft until the verdict.** Measured: auto-enroll skips drafts.
   `gh pr ready` after folding the verdict fires `ready_for_review` and
   enrols. Zero infra change; it is a process rule for `peer-agents` +
   `AGENTS.md` ("a dispatched review gates landing"). The drawback is the
   2026-08-30 concern: a naive universe merging a draft costs three asks.
2. **Auto-enroll requires a verdict line.** `auto-enroll-merge.yml` reads the
   PR body for `Codex verdict: APPROVE @ <head-sha>` and enrols only when the
   sha is the current head — the exact-head receipt shape, generalised, with
   the receipt-loop concern's caveat that every fold voids it.
3. **Leave it.** Accept that a REJECT can land and be fixed forward, since
   the follow-up PR is cheap and `main` auto-deploys either way. This is what
   happened; it cost one extra PR and a stale public page for a few hours.

Option 1 is what this lane will do from now on. Whether it becomes the rule
is the founder's call — it trades merge friction for review binding on every
PR, not just authority paths.

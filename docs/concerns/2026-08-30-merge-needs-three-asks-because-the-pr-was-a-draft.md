# Merging a PR the universe opened took three rail asks, because it opened it as a draft

**Filed:** 2026-08-30, from the live naive-user merge test (production,
universe `u-01kxm1vszd8hwp7em418asq8h9`, PR #2691).
**Verified:** yes — thread turns 621–632; runs `21aaff7265b14d06` (merge →
`405 Pull Request is still a draft`), `c06653031c314158` (`POST
…/pulls/2691/ready_for_review` → `404`, the endpoint does not exist),
`9f4404d51df84449` (merge retry → `405`), `d9e92c4757f0470b` (GraphQL
`markPullRequestReadyForReview` → `isDraft: false`), `74653585e4f144b3`
(merge → `200`, commit `771c5875`). Merged 02:42:22Z.
**Severity:** P2 — the goal was met (a naive founder said "merge it" and it
merged), but it cost three approvals and one nudge where one approval would
do, and the universe stopped once without proposing a next move.

## What happened

1. "#2691 looks right to me, go ahead and merge it." → one `extend_http` ask
   for `PUT …/pulls/{pull_number}/merge` (correct, minimal). Approved; the
   approval relayed itself into the thread (#2698) and the universe resumed.
2. GitHub refused: the PR was a **draft** — the universe's own choice when it
   opened it the day before (`draft: true`), never asked for.
3. It asked for `POST …/pulls/{n}/ready_for_review`. **That REST endpoint
   does not exist**; un-drafting is GraphQL-only. Approved; `404`; merge
   retried; `405`. The universe then **stopped** with a status report and no
   next move — a naive founder is stuck here.
4. Nudged with the plain "so how do we get it out of draft? do whatever you
   need to", it found GraphQL itself: one more ask, `POST api.github.com/graphql`.
   Approved; undrafted; merged.

## What is in tension

- A draft is the safe default for a PR nobody asked to merge; but when the
  founder asks for "a PR" and later "merge it", the draft costs two extra
  asks and one dead end. The universe knew the PR was a draft (it reported
  `draft: true`) and still asked for a merge endpoint first.
- A `POST /graphql` grant is not "one endpoint": it is every query and
  mutation the token can perform, through one path. The rail presented it
  like any other path grant. Per-endpoint granularity (`{path+}` templates,
  `param_patterns`) has no GraphQL equivalent (an operation-name allow-list).
- Stopping after two refusals with a status report violates the founder's
  rule that a turn runs until finished or blocked on the founder — it was
  blocked on nothing; the next move existed.

## Options

1. **Guidance (smallest):** in `write_graph`'s outbound docs and the
   `control_station` row: open PRs as non-draft unless the founder asked for
   a draft; un-drafting is GraphQL `markPullRequestReadyForReview`, there is
   no REST path; when GitHub refuses with a reason you can act on, act.
2. **GraphQL grant shape:** an `extend_http` for `/graphql` carries an
   `operations` allow-list (`mutation markPullRequestReadyForReview`,
   `query …`) that the effector enforces by parsing the request body's
   operation; the rail shows the operations, not the path. Authority change
   → OpenSpec proposal first.
3. Both. 1 now, 2 when a second GraphQL grant is requested live.

## How to resolve this file

Delete it when a naive "open a PR … merge it" completes with at most ONE
rail ask (the merge endpoint), verified live with run ids, and the GraphQL
grant shape (option 2) is either specced or explicitly declined in
`docs/host-actions.md`.

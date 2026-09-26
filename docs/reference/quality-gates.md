# Quality gates

Canonical procedure. `AGENTS.md` keeps the invariants and points here;
this file is the detail. Pointer-loaded per ADR-002 — read it before a
review, a merge, or a completion claim.

---

**Review sequencing — shape before hardening (founder directive 2026-08-20).**
Reviews run in a fixed order, and the order is load-bearing:
1. **Pre-first-build / first-draft review = SHAPE + APPROACH.** One pass, not a
   gauntlet. It catches architecture/approach problems (fail-closed vs fail-open,
   one general primitive vs per-channel spaghetti, the right authority/ownership
   model) and basic-safety holes that leak/exfil/bypass even for a single user.
   Architectural reviews and rebuilds belong here.
2. **Ship LIVE as MVP** — flip the dark flags on, deploy — and **test as a real
   user** through Slack / the app / the chatbot connector. The live user path is
   the shape oracle: it is the only thing that proves the shape + UX flow are
   right.
3. **THEN harden what live use shows matters.** Concurrency, TOCTOU,
   durability/crash, timing side-channels, migrations of hypothetical prior
   state, abuse-at-scale: these are tracked as concerns and re-judged after live
   use. They are not a pre-release gauntlet.
Do NOT gate a first-draft MVP behind multiple hardening rounds. That is
"endless hardening of the wrong shape", and only live users reveal whether the
shape is right. The split: a hole that leaks, exfiltrates or bypasses for ONE
founder is the floor and is fixed pre-live. An edge that only bites
multi-tenant, concurrent or crash cases is deferred and tracked.

**Review depth is risk-tiered, with a hard stop** (2026-09-24; the tier
definitions, the floor, and the primitive trigger are in `AGENTS.md` Quality
Gates; the evidence is in `docs/reviews/2026-09-24-review-deploy-practice.md`).
Tier 0 gets no review. Tier 1 gets one review that never blocks. Tier 2 (the
floor or gate-defining files) gets one blocking review. Every tier stops at two
rounds or one day. Round 2 only verifies the round-1 floor fixes. A floor
finding still open after round 2 triggers a primitive redesign, not round 3.

**Risk-tiered review policy (full text; adopted 2026-09-24).** `AGENTS.md`
carries the summary. Evidence: `docs/reviews/2026-09-24-review-deploy-practice.md`.

- **Ship to learn.** Done = deployed, used through the real app (`ui-test` /
  app-agent checklist), regressions green, spec synced. Unknowns about users
  are answered by deploying, not by reviewing. Compare a change against what
  production does today, never against an ideal design.
- **Risk tier sets review depth** (by what the change can do, not its size):
  - *Tier 0 - no review:* docs, tests, UI/copy, refactors under unchanged
    tests, anything dark or default-off, anything one revert fully undoes.
  - *Tier 1 - one review, never blocking:* new user-visible behaviour or a new
    primitive. One shape review before code; findings off the floor go to
    `docs/concerns/`, not into the PR.
  - *Tier 2 - one blocking review:* the floor below, or gate-defining files.
    Other family by default; same family if it is rate-limited (the
    cross-family check is then owed, not waived).
- **The floor, and only the floor, blocks a deploy:** cross-user read/effect;
  auth or credential exposure; unrecoverable loss of user data; wrong money;
  an irreversible external act without consent; public connector down.
  Durability at the margins, concurrency the founder's usage cannot reach,
  and "a future X could break" are tracked, and re-judged after live use.
- **Hard stop: two rounds, one day.** Round 2 only verifies round-1 floor
  fixes; anything new that is off the floor becomes a concern. Autonomous - no
  founder escalation, and no third round. A floor finding still open after
  round 2 means the shape is wrong: apply the primitive rule.
- **A finding must cite the PR head** (file:line). A finding against a
  retired architecture, an unbuilt capability or an unread file is dropped
  without a round. Ask for `AGREE` / `DISAGREE_EVIDENCE` / `DISAGREE_CONCERN`.
- **Recurring findings = missing primitive.** Trigger: a floor finding in
  two consecutive rounds, 3+ follow-up PRs in one area within 7 days, or a
  concern open 7+ days with built-but-unwired components. Stop patching;
  write half a page naming the primitive that deletes the class (one writer
  per fact; user-composable instead of platform policy) and build that as
  the next slice.
- **Small, live slices.** A PR deploys and is testable on its own; over 1,500
  added non-test lines needs a stated reason. New capability ships dark on
  the founder's universe first, then to users.
- **Live failures become evals.** Every failure seen in the real app becomes
  a regression test or checklist row before the fix lands. A rendered
  conversation is the proof; scripts and canaries support it.
- **A dispatched review gates landing, not progress.** Take the next lane.

**Verification is structural.** A substantive change needs test or check
evidence, plus live use through the real app, before it counts as landed.
Self-review alone never suffices for a Tier 2 change. If the other model family
is rate-limited, an independent same-family review stands in, and the
cross-family check is recorded as owed.

**`main` enforces a behavioural test gate (live 2026-08-03).** Required contexts
were originally `policy`, `Diff scope declared`, and `required-tests`, with
`strict` on. Reverified September 9, 2026 UTC via
`gh api repos/Jonnyton/TinyAssets/branches/main/protection/required_status_checks`:
the current required contexts are `Diff scope declared`, `required-tests`,
`invariants`, and `slow-tests`, with `strict: false`. Do not infer a mandatory
branch refresh from the historical strict setting; inspect current merge
eligibility and the actual tested checkout. This observation changes no policy.
`required-tests` fails on any test failure not already listed in
`.github/known-failing-tests.txt` — that ledger is a one-way ratchet, so adding
a line to excuse a test you broke is a visible, reviewable edit on a
scope-guarded path. It runs a ~5-minute subset; the excluded heavy files run in
the non-required `heavy-tests` job on a best-effort schedule -- which is RED
at baseline (107 unquarantined failures as of 2026-08-27), so a failure there
is compared against the previous run, not read as a regression. Updating a drain
PR's branch invalidates any exact-head review receipt and triggers a new test
run; a future restoration of strict protection would also require it to be
up to date with `main`.
Details and rollback: `docs/decisions/ADR-003-required-test-aggregator.md`.

**Review-provider limit fallback.** Opposite-provider review is first choice.
If that provider hits a hard account/subscription/usage limit, record dated
evidence, then dispatch a fresh-context independent reviewer from the
available provider against the exact commit. The reviewer is never the
author; blocking findings must be resolved before landing/rollout.
Inconvenience or disagreement does not activate this fallback.

**A blocking review verdict is a REQUIRED CHECK (live 2026-09-26).** A verdict
posted as a PR comment is advisory: auto-merge reads required checks, not
comments. PR #3989 auto-merged at the exact head its Tier 2 reviewer had
BLOCKED. So `pr-scope-guard` — already required — now fails unless the PR body
carries an exact-head receipt, whenever the PR

* touches a release-critical path (`.github/workflows/`, `deploy/`, `Dockerfile`,
  the two test ledgers, `scripts/ci_required_tests.py`,
  `scripts/drain_review_gate.py`) or an authority path (`AUTHORITY_RE`), **or**
* carries the `infra-change` label, **or**
* declares `Tier 2` in its title.

Satisfying it takes **two steps, both required, and each receipt goes at the TOP
of its text** — only blank lines may precede it.

First the reviewer POSTS the verdict as a comment on the PR. These are its first
two non-blank lines, with the reasoning below them:

```
Drain-Review-Verdict: APPROVE
Drain-Review-Head: <the PR's current 40-hex head>
```

Then the PR BODY cites that comment. These are its first three non-blank lines:

```
Drain-Review-Verdict: APPROVE
Drain-Review-Head: <the same head>
Drain-Review-Artifact: https://github.com/<owner>/<repo>/pull/<this PR>#issuecomment-<id>
```

Mechanics worth knowing before you plan work:

- **Only `APPROVE`.** `BLOCK`, `DENY`, lower-case `approve`, or `APPROVE` with
  trailing prose all fail, and an `APPROVE` stacked beside a `BLOCK` fails — in
  the body and in the comment alike.
- **The artifact must be a real comment on THIS PR** — a top-level comment, a
  submitted review, or an inline review comment — authored by a repository
  owner, member or collaborator, **and that comment must itself carry the
  APPROVE lines for the current head**. Checked against the API, so an invented
  comment id, an approval on a different PR, a drive-by commenter, a citation of
  the reviewer's BLOCK comment, and a citation of a pre-push approval all fail.
  A `docs/…md` artifact still satisfies the older drain-branch receipt but not
  this one.
- **Only the top is read.** Nothing above a receipt can hide it, because nothing
  can precede the first line of a document; and nothing below it can void it. A
  receipt in a fenced block, an HTML comment, a `<details>`, a blockquote or a
  list is simply not at the top and does not count. If an honest receipt is being
  refused, move it up. This replaced a markdown scanner that three cross-family
  review rounds broke in both directions — hidden approvals it accepted, honest
  ones it refused after a heading or a code example.
- **Stamping the body re-runs the check** (`edited` is a trigger), so a verdict
  unblocks a PR with no push. **Any push voids the receipt** — the head must
  match exactly, so batch your fixes and re-stamp once.
- **Two content proofs stand down the requirement**, and only when they account
  for the PR's whole release-critical/authority footprint: a deletion-only
  quarantine-ledger edit, and an authority file whose AST is unchanged
  (`scripts/authority_behavior_check.py`). Neither stands down a Tier 2 title.
- **Fails closed.** An unreadable file list or comment inventory denies.
- **Self-stamping is not prevented.** The receipt lives in the PR body, which
  the author can edit, and this repository has one account with write access, so
  "stamper differs from author" would be unsatisfiable. What the receipt makes
  impossible is the #3989 accident: a BLOCK cannot merge, a receipt for an older
  head cannot merge, and a verdict never published on the PR cannot merge. The
  honesty note in `.github/workflows/pr-scope-guard.yml` states what is and is
  not closed.

Measured blast radius: of the 60 most recently merged PRs, 29 would have needed
a receipt (24 by path, 15 by label, 22 by Tier 2 title).

**High-risk PRs stay draft until exact-head approval.** Auth, storage,
migration, concurrency, public-surface, and data-loss-risk PRs open as drafts
so auto-enrollment cannot merge them ahead of review. Ready only after an
approval artifact names the unchanged head SHA; any head-changing update
converts back to draft until fresh exact-head approval. For a first-draft MVP
that approval is the SHAPE + basic-safety pass (§ Review sequencing) — not a
completed hardening gauntlet. Hardening is re-judged post-live, under the two-round stop.

**Final chatbot-surface verification is a rendered chatbot conversation**
through the live connector at `https://tinyassets.io/mcp` (`ui-test` skill)
for any change affecting public MCP behavior, chatbot UX, connector tool
descriptions, user-visible node/workflow state, or `tinyassets.io`.
Host-visible rendered chatbot use is the
invariant; the automation transport is provider-specific. Direct MCP calls,
scripts, and canaries are supporting evidence, not final proof. Log rendered
prompt/result in `output/user_sim_session.md`.

**Post-fix clean-use evidence.** After fix + `ui-test`, look for real-user
clean use since the fix (production traces, logs, user-visible history),
freshness-stamped. None visible yet? Say so and leave a STATUS watch item
for public-surface/high-risk changes.

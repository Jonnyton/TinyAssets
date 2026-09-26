# Quality gates

Canonical procedure. `AGENTS.md` § *Quality Gates* keeps the invariants and
points here. Read it before a review, a merge, or a completion claim.

---

## Review sequencing — shape before hardening (founder, 2026-08-20)

1. **One shape review**, on the first draft: architecture and approach
   (fail-closed vs fail-open, one general primitive vs per-channel spaghetti) plus
   holes that leak, exfiltrate or bypass even for a single user. Rebuilds belong
   here.
2. **Ship live as an MVP** — flip the dark flags on, deploy — and **test as a real
   user** through the app or the chatbot connector. The live user path is the
   shape oracle.
3. **Then harden what live use shows matters.** Concurrency, durability,
   abuse-at-scale: tracked as `docs/concerns/` files and re-judged after live use,
   not run as a pre-release gauntlet.

The split: a hole that bites ONE founder is the floor and is fixed pre-live; an
edge that only bites multi-tenant, concurrent or crash cases is tracked.

## Review depth

- **Cross-family review runs for floor-class changes** (the floor list is in
  `AGENTS.md` § *Quality Gates*) **and for PRs a gate already receipt-gates** —
  gate-defining or authority-critical paths and `drain/` branches, per
  [`executable-gates.md`](executable-gates.md); those are blocked until an
  exact-head receipt exists regardless of the floor. One round, dispatched in
  parallel once the PR is open, on the peer's own budget (`peer-agents`).
  Everything else — docs, UI, refactors under unchanged tests, anything dark or
  one-revert-reversible — ships with no review.
- **P2 findings go to `docs/concerns/`**, one file each, not into the PR.
- **A finding must cite the PR head** (`file:line`); one against a retired
  architecture, an unbuilt capability or an unread file is dropped without a
  round. Ask for `AGREE` / `DISAGREE_EVIDENCE` / `DISAGREE_CONCERN` — structured
  disagreement beat adding reviewers.
- **Backstop: three rounds, then escalate**, because round N+1's findings are
  often caused by round N's fixes.
- **Recurring findings mean a missing primitive.** A floor finding in two
  consecutive rounds, or 3+ follow-up PRs in one area within 7 days: stop
  patching, name the primitive that deletes the class and build that slice.
- **If the other family is rate-limited**, an independent same-family reviewer
  against the exact commit stands in and the cross-family check is owed.
  Inconvenience does not activate this.

## Landing

- **Small, live slices.** A PR deploys and is testable on its own; a new
  capability ships dark on the founder's universe first.
- **Open floor-class PRs as drafts** so auto-enrollment cannot merge them ahead
  of review. That is a convention, not a gate: `scripts/drain_review_gate.py`
  mechanically requires an exact-head receipt only on the `AUTHORITY_RE` and
  gate-defining paths listed in [`executable-gates.md`](executable-gates.md).
- **Locally run the relevant tests, including affected heavy files.** Required PR
  CI runs the suite MINUS `.github/heavy-test-files.txt`, and `heavy-tests` does
  not run on pull requests at all, so nothing else covers them before merge.
  Required checks: [`executable-gates.md`](executable-gates.md).

## Proof

**Final chatbot-surface verification is a rendered chatbot conversation** through
the live connector at `https://tinyassets.io/mcp` (`ui-test` skill) for any change
affecting public MCP behaviour, chatbot UX, connector tool descriptions,
user-visible workflow state, or `tinyassets.io`. Direct MCP calls, scripts and
canaries are supporting evidence, never proof. Log the rendered prompt and result
in `output/user_sim_session.md`.

Then look for real-user clean use since the fix (production traces, logs,
user-visible history), freshness-stamped. If none is visible yet, say so.

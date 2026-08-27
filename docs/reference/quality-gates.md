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
3. **THEN the deep security-hardening rounds** — concurrency, TOCTOU,
   durability/crash, timing side-channels, migrations of hypothetical prior
   state, abuse-at-scale. These run AFTER live-MVP user testing.
Do NOT gate a first-draft MVP behind multiple hardening rounds — that is
"endless hardening of the wrong shape," and only live users reveal whether the
shape is right. The split: a hole that leaks/exfils/bypasses for ONE founder =
fix pre-live (basic-safety); an edge that only bites multi-tenant / concurrent /
crash = defer to post-live hardening, tracked in the change's `REVIEW.md`.

**Verification is structural.** Substantive changes need test/check evidence
plus an independent review path before they count as landed. The PRE-live review
is the shape/approach pass above (one round); the multi-round adversarial
hardening is post-live-MVP. Self-review alone is never enough for public-surface,
storage, auth, migration, concurrency, or data-loss-risk changes — but for a
first-draft MVP the pre-live bar is shape + basic-safety, and deep hardening
follows live user testing.

**`main` enforces a behavioural test gate (live 2026-08-03).** Required contexts
are `policy`, `Diff scope declared`, and `required-tests`, with `strict` on. So:
a PR merges only if `required-tests` is green, and only while up to date with
`main`. `required-tests` fails on any test failure not already listed in
`.github/known-failing-tests.txt` — that ledger is a one-way ratchet, so adding
a line to excuse a test you broke is a visible, reviewable edit on a
scope-guarded path. It runs a ~5-minute subset; the excluded heavy files run in
the non-required `heavy-tests` job on a best-effort schedule -- which is RED
at baseline (107 unquarantined failures as of 2026-08-27), so a failure there
is compared against the previous run, not read as a regression. Two consequences
worth knowing before you plan work: falling behind `main` costs a re-run, and
updating a drain PR's branch invalidates any exact-head review receipt.
Details and rollback: `docs/decisions/ADR-003-required-test-aggregator.md`.

**Review-provider limit fallback.** Opposite-provider review is first choice.
If that provider hits a hard account/subscription/usage limit, record dated
evidence, then dispatch a fresh-context independent reviewer from the
available provider against the exact commit. The reviewer is never the
author; blocking findings must be resolved before landing/rollout.
Inconvenience or disagreement does not activate this fallback.

**High-risk PRs stay draft until exact-head approval.** Auth, storage,
migration, concurrency, public-surface, and data-loss-risk PRs open as drafts
so auto-enrollment cannot merge them ahead of review. Ready only after an
approval artifact names the unchanged head SHA; any head-changing update
converts back to draft until fresh exact-head approval. For a first-draft MVP
that approval is the SHAPE + basic-safety pass (§ Review sequencing) — not a
completed hardening gauntlet; the deep hardening rounds re-run post-live.

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

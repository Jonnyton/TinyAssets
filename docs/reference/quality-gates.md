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

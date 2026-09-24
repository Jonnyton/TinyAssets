# Review and deployment practice for a pre-PMF, AI-built platform

Research for the TinyAssets founder, 2026-09-24. External sources were fetched on 2026-09-24.
Local measurements were taken against `origin/main` @ `1e6f6eba` (2026-09-24 18:45 UTC) with `gh` and `git`.
Nothing in the repo was changed.

---

## 1. Executive answer (10 lines)

1. The research agrees with you. Heavyweight approval does not lower change-failure rates. Small batches, fast feedback and production signals do (DORA). AI-driven review loops also degrade: vulnerabilities rise about 38% after five "improvement" rounds, and LLMs fail to self-correct without external feedback.
2. Review is worth one bounded pass, focused on the **irreversible floor**: cross-user access, auth and credential custody, loss of user data, money, gate files. Everything else is a two-way door. Ship it dark or behind a revert and learn from live use.
3. Here, the measured spiral is **not** slow PRs. The median time from first commit to merge is 0.6 h, and from merge to deploy 0.1 h. Only 13 of 500 closed PRs were abandoned.
4. The spiral happens at the **lane** level. PRs are huge (#3832 "MVP" added 49k lines across 346 files in 138 commits; #2732 added 40k). One area produces swarms of follow-up PRs and review artifacts: 66 of 237 artifacts are on the model/provider/credential cluster. Components also get built "unwired" while the root P0 stays open. The credential-refresh P0 was filed 2026-09-01 and is still open after 23 days.
5. Reviews do catch real floor bugs, and those must stay blocking. #2774 round 2 caught a cross-user deletion P0. #2561 round 5 caught the deletion of a gate script. But many rounds were driven by gate-scoping mismatches and by comparing an MVP to an ideal design instead of to today's broken production.
6. Proposed rule: risk tier decides depth. Tier 0 gets no review, Tier 1 gets one non-blocking review, Tier 2 (the floor) gets one blocking review plus one verification-only round. **Two rounds maximum, and never "as many as needed"**: PR #3945's wording has no terminator.
7. Only floor findings block a deploy. Everything else becomes a `docs/concerns/` row that is re-judged after real-user use.
8. Live-user proof (ui-test / app-agent checklist) is the acceptance gate. Every live failure becomes a regression eval, as Anthropic's eval guidance recommends. Speculative "future X could break" findings are tracked, not built.
9. Recurring findings in one area mean a missing primitive, not a need for more review. The trigger is a floor finding in two consecutive rounds, three or more follow-up PRs in 7 days, or a concern open 7+ days with components built but unwired. Stop patching, name the primitive that deletes the class, and build that as the next slice. Churn predicts defects (Microsoft).
10. On gates: keep test, invariant, scope, canary and deployed-sha. Relax the exact-head receipt. Today it covers 34% of merged PRs (102 of 300) because AUTHORITY_RE includes hub files, and any push voids it, which created #2755's no-exit loop.

---

## 2. External findings

Evidence strength: **[STRONG]** means peer-reviewed or large-sample empirical work. **[MODERATE]** means vendor data, industrial case studies or official policy. **[PRACTITIONER]** means argued opinion or a single-team report.

### 2.1 Review economics for AI-generated code

- **[STRONG] Heavyweight approval does not reduce failures.** DORA's change-approval capability page (dated 2025-10-30) says: "no evidence was found to support the hypothesis that a more formal, external review process was associated with lower change fail rates." Heavyweight approval leads "to the release of larger batches less frequently … higher change fail rates." The recommended alternative is lightweight peer review plus "continuous testing, continuous integration, and comprehensive monitoring … to rapidly detect, prevent, and correct bad changes." https://dora.dev/capabilities/streamlining-change-approval/
- **[STRONG] Code review finds fewer defects than people expect.** Bacchelli & Bird, ICSE 2013, Microsoft: reviews are "less about defects than expected" and more about knowledge transfer, awareness and alternative solutions. https://www.microsoft.com/en-us/research/publication/expectations-outcomes-and-challenges-of-modern-code-review/
- **[STRONG] AI raises both throughput and instability.** The DORA 2025 State of AI-assisted Software Development report (Sept 2025) finds higher AI adoption associated with more throughput **and** more instability. It names small batches as the "critical countermeasure." https://dora.dev/dora-report-2025/ and https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report
- **[MODERATE] LLM review adds latency and noise in industry.** Cihan et al., "Automated Code Review In Practice" (arXiv 2412.18531, Dec 2024), studied 4,335 PRs at Beko. 73.8% of LLM comments were resolved. Mean PR closure time rose from 5h52m to 8h20m. Drawbacks named: "faulty reviews, unnecessary corrections, and irrelevant comments." https://arxiv.org/abs/2412.18531
- **[MODERATE] A tuned commercial reviewer yields about 0.5 real bugs per PR, and about 30% of its flags go unacted.** Cursor, "Building a better Bugbot" (2026-01-15): resolution rate rose "from 52% to over 70%", with bugs flagged per run rising from 0.4 to 0.7, so resolved bugs per PR went from "roughly 0.2 to about 0.5". The gains came from a better agentic design, not from more passes. The earlier version used eight parallel passes with voting. https://cursor.com/blog/building-bugbot
- **[MODERATE] LLM-assisted review carries false-positive and trust costs.** Aðalsteinsson et al. (arXiv 2505.16339, 2025-05-22), WirelessCar industrial study. https://arxiv.org/abs/2505.16339
- **[STRONG] Same-family review is biased.** Panickssery, Bowman & Feng, NeurIPS 2024: LLM evaluators recognise their own outputs and favour them. This supports keeping one reviewer from the *other* family. It does not support running more rounds. https://proceedings.neurips.cc/paper_files/paper/2024/hash/7f1f0218e45f5414c79c0679633e47bc-Abstract-Conference.html
- **[STRONG] Iterative self-refinement degrades.**
  - Huang et al., ICLR 2024: "LLMs struggle to self-correct their responses without external feedback, and at times, their performance even degrades after self-correction." https://arxiv.org/abs/2310.01798
  - Shukla, Joshi & Syed, IEEE-ISTAS 2025 (arXiv 2506.11022, June 2025): over 400 samples and 40 rounds of LLM "improvement", critical vulnerabilities rose **37.6% after five iterations**. They call this "feedback loop security degradation." https://arxiv.org/abs/2506.11022
  - Interpretation: an agent-fixes, agent-reviews, agent-fixes loop is the setting where these results apply. The external signal that breaks the loop is a real run or a real user, not another reviewer.
- **[STRONG] Multi-agent setups fail at verification.** Cemri et al., "Why Do Multi-Agent LLM Systems Fail?" (arXiv 2503.13657, NeurIPS 2025 D&B), studied 1,600+ traces. Task verification is one of three failure categories, and multi-agent gains on benchmarks are "often minimal." https://arxiv.org/abs/2503.13657
- **[STRONG] Stale-architecture anchoring has a mechanism.** Chroma, "Context Rot" (July 2025) tested 18 frontier models. All degrade as input grows, and semantically similar distractors hurt most. Old design notes and retired architecture sitting in context are exactly such distractors. https://www.trychroma.com/research/context-rot
- **[MODERATE] Models over-build by default.** Anthropic's official prompting guidance says recent Opus models "have a tendency to overengineer by creating extra files, adding unnecessary abstractions, or building in flexibility that wasn't requested." The fix is "Only make changes that are directly requested or clearly necessary." Page current as of 2026-09. https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices
  - This is the published basis for your "reviewer asks for more complexity" observation. No study measuring "reviewer asks for complexity" rates directly was found.
- **[STRONG] AI code duplicates more and refactors less.** GitClear 2025 (211M changed lines): within-commit copy/paste exceeded moved (refactored) code for the first time in 2024. Moved code fell from 24.1% in 2020 to 9.5% in 2024. Two-week churn rose from 3.1% to 5.7%. https://www.gitclear.com/ai_assistant_code_quality_2025_research
- **[STRONG] AI can slow experienced developers without them noticing.** METR RCT (2025-07-10): experienced OSS developers were 19% slower with AI while believing they were 20% faster. METR changed the study design in 2026-02, so treat this as dated. https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/
- **[MODERATE] Agent PR outcomes (2026).**
  - Peralta et al., MSR 2026 (arXiv 2605.22534, 2026-05-21), 9,799 human-reviewed agent PRs. Only 35.7% of rejections were genuine agent failures, 31.2% were workflow constraints, and 33.1% had no visible rationale. Codex and Cursor PRs usually merged "with minimal interaction." https://arxiv.org/abs/2605.22534
  - Xu et al. (arXiv 2607.04697, 2026-07-06): concurrent agent PRs are the norm, with 79.4% co-active. Conflict rate is 19.8% between same-agent pairs and 41.7% between cross-agent pairs. This supports "serialize merges on shared files." https://arxiv.org/abs/2607.04697
- **[PRACTITIONER, single team] OpenAI "Harness engineering"** (Ryan Lopopolo, OpenAI Engineering, Feb 2026). Direct fetch returned 403; quotes come from the mirror https://www.engineering.fyi/article/harness-engineering-leveraging-codex-in-an-agent-first-world. Original: https://openai.com/index/harness-engineering/
  - "With agent throughput far exceeding human attention, corrections become cheap while waiting becomes expensive."
  - The team runs "minimal blocking merge gates, short-lived pull requests," and handles test flakes "with follow-up runs rather than blocking progress."
  - Review is agent-to-agent.
  - Architecture is enforced "mechanically through custom linters and structural tests rather than relying on documentation."
  - Agents verify through Chrome DevTools snapshots and a queryable observability stack.
  - A recurring cleanup ("garbage collection") agent handles entropy.
- **Not found / not verified.** `AGENTS.md` cites "defect counts … 15, 8, 12, 2, 8, 1, 4, 1, 0 over nine rounds" and "three well-structured agents beat five" as *published evidence*. Commit `07d5151a` (#2565, 2026-08-26) introduced both with no source, and I found none. Your own data shows the same shape: #2755 went 7→5→1→3 findings and #2774 went 9→7→8. Per the Truth-and-Freshness rule, cite those instead.

### 2.2 Pre-PMF deployment practice

- **[STRONG] Small batches are how learning happens.** DORA's small-batches capability uses Ries's definition of an MVP, "just enough features to enable validated learning," and says small batches "reduce the time it takes to get feedback." Feedback sources are "users, system monitoring, quality assurance, and automated tests." Users come first. https://dora.dev/capabilities/working-in-small-batches/
- **[PRACTITIONER] YC: do the unscalable thing by hand.** Paul Graham, "Do Things that Don't Scale" (July 2013): Stripe delivered "instant" merchant accounts by signing users up manually, and "you can sometimes get away with doing by hand things that you plan to automate later." https://paulgraham.com/ds.html
- **[PRACTITIONER] Shape Up fixes time and varies scope.** Basecamp's circuit breaker: "If they don't finish, by default the project doesn't get an extension". It exists to prevent runaway projects, and a miss is read as a shaping failure, not a reason to add time. https://basecamp.com/shapeup/2.2-chapter-08
- **[PRACTITIONER] Test in production.** Charity Majors / Honeycomb (Increment, updated 2019-09-04): "Testing in production is a superpower. It's our inability to acknowledge that we're doing it, and then invest in the tooling and training to do it safely, that's killing us." https://www.honeycomb.io/blog/i-test-in-prod
- **[MODERATE] Minimum safety floor.** These are the places to spend review. Each is irreversible, touches someone else, or is regulated:
  - Cross-tenant access and effects.
  - Authentication and credential custody.
  - User-data loss or unrecoverable migration.
  - Money.
  - Irreversible external acts, such as sending, publishing or pushing to someone else's repo.
  - The gate that judges gates.
  - Everything else is Type 2 (see §2.3).
  - Regulated obligations are usually lighter than engineers assume. Google Play's account-deletion policy does **not** require automated deletion. Developers must let users *request* deletion (in-app, or via "a customer service email or a form") and "complete their requests within a reasonably quick period of time." Retention for security, fraud or regulatory reasons is allowed if disclosed. https://support.google.com/googleplay/android-developer/answer/13327111

### 2.3 Stopping rules

- **[STRONG as an operating model] Error budgets.** Google SRE, "Embracing Risk": "as long as there is error budget remaining—new releases can be pushed". When it is spent, releases halt. "100% is probably never the right reliability target." https://sre.google/sre-book/embracing-risk/
  - This is the principled answer to "when is it safe enough": a budget judged against production, not against an imagined perfect design.
- **[PRACTITIONER] Reversibility-based gating.** Bezos's Type 1 / Type 2 decisions: one-way doors deserve care, two-way doors "should be made quickly" with a light process. The 2016 letter says to decide at about 70% of the information. https://www.aboutamazon.com/news/company-news/2016-letter-to-shareholders
- **[MODERATE, codified at Google] "Better, not perfect."** Google's review standard: "favor approving a CL once it is in a state where it definitely improves the overall code health … even if the CL isn't perfect," and "There is no such thing as 'perfect' code—there is only better code." https://google.github.io/eng-practices/review/reviewer/standard.html
  - Applied here: compare a candidate against **current production**, not against the ideal design.
- **[PRACTITIONER] Time boxing.** Shape Up's circuit breaker (above) is the best-known published hard stop.
- **Result.** No published convergence rule for LLM review rounds exists. Every principled stopping rule found is external to the review: a budget, reversibility, "better than current", or a time box. That is why the cap has to be a rule. It cannot be "as many as genuinely needed."

### 2.4 Recurring findings as an architecture signal

- **[STRONG] Relative churn predicts defect density.** Nagappan & Ball, ICSE 2005, Windows Server 2003: relative churn discriminated fault-prone binaries with 89% accuracy. Repeated rework in one area is itself the defect signal. https://www.microsoft.com/en-us/research/publication/use-of-relative-code-churn-measures-to-predict-system-defect-density/
- **[PRACTITIONER] The wrong abstraction.** Sandi Metz, "The Wrong Abstraction" (2016-01-20): parameters and conditionals piling onto one abstraction mean it is wrong. "The fastest way forward is back." https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction
- **[PRACTITIONER] Primitives, not frameworks.** Werner Vogels / AWS (TechCrunch, 2021-12-07): give customers composable building blocks, because a framework takes years to build and is outdated when it lands. https://techcrunch.com/2021/12/07/why-amazon-cto-werner-vogels-isnt-ready-to-retire-just-yet/
  - This matches PLAN.md's "enabling primitives, not pre-built complexity."
- **[PRACTITIONER, single team] Encode invariants mechanically.** OpenAI Harness Engineering, above: recurring agent mistakes are fixed by encoding the invariant as a linter or structural test with remediation text. They are not fixed by reviewing harder.
- **Local corroboration (already in memory, not external).** "Two definitions of one fact" and "oscillating review verdicts mean wrong shape" were both written after multi-round spirals. Both concluded the defect was structural.

### 2.5 How agent-driven teams verify instead

- **[MODERATE] Evals from real failures.** Anthropic, "Demystifying evals for AI agents" (2026-01-09): start with "20–50 tasks" drawn from real failures, and "Begin with the manual checks you run during development … and common tasks end users try." Regression evals should sit near 100%. Production monitoring "catches issues that synthetic evals miss." https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents
- **[MODERATE] Add complexity only when it demonstrably helps.** Anthropic, "Building effective agents" (2024-12-19): "consider adding complexity *only* when it demonstrably improves outcomes." The evaluator-optimizer loop fits only "when we have clear evaluation criteria, and when iterative refinement provides measurable value." Open-ended review of speculative risks meets neither condition. https://www.anthropic.com/engineering/building-effective-agents
- **[PRACTITIONER] Executable gates, UI-level agent checks, queryable telemetry, minimal blocking merge gates, follow-up fixes over blocking.** OpenAI Harness Engineering, above.
- **[STRONG] Monitoring and fast correction replace approval.** DORA, §2.1.

---

## 3. Local measurements (read-only, 2026-09-24)

Commands were run from `C:\Users\Jonathan\Projects\TinyAssets`. Intermediate data is in `scratchpad/rd/`.

```bash
gh pr list --state merged --limit 300 --json number,title,createdAt,mergedAt,additions,deletions,changedFiles,body,headRefName
gh pr list --state merged --limit 300 --json number,comments,reviews
gh pr list --state closed --limit 500 --json number,title,createdAt,closedAt,mergedAt,body,headRefName
gh api graphql  # 3 pages: pullRequests(states:MERGED) { commits(first:1){totalCount, authoredDate} mergeCommit }
gh run list --workflow "Deploy prod" --limit 600 --json headSha,createdAt,updatedAt,conclusion,event
git show origin/main:docs/reviews/*  (237 files) ; git show origin/main:docs/concerns/* (96 files)
gh api repos/{owner}/{repo}/branches/main/protection --jq .required_status_checks.contexts
python scratchpad/rd/an.py ; an2.py ; an3.py   # parsing scripts
```

### 3.1 PR latency: fast

Sample: the last 300 merged PRs, #2665–#3944, 2026-08-29 → 2026-09-24.

| Measure | median | p75 | p90 | max |
|---|---|---|---|---|
| PR open → merge (h) | 0.4 | 0.8 | 2.1 | 95.8 |
| first commit → merge (h) | 0.6 | 1.8 | 9.2 | 120.4 (#3832) |
| merge → next successful `Deploy prod` (h) | 0.1 | 0.6 | 2.3 | 78.1 |
| first commit → deployed (h) | 1.1 | 3.2 | 16.4 | 120.6 |
| commits per PR | 2 | 5 | 9 | 138 (#3832) |
| additions per PR | 324 | — | 2,062 | 49,261 (#3832) |

- Deploy prod since 2026-08-29: 170 successes, 9 failures, 12 skipped. Merged-to-deployed is healthy.
- Of 53 merged PRs citing a `docs/reviews/` artifact, the earliest cited review predates the merge by a median of 0 days (max 1). Reviews happen *before* the PR opens, which matches the "verdict before opening" memory. That is why open→merge looks instant.
- Abandonment is rare: **13 of 500** closed PRs were unmerged, and 10 of those say superseded, replaced or duplicate. Only 1 had 2+ review rounds (#2575).
- **Conclusion:** PR-level review latency is not where time goes.

### 3.2 Review rounds (lower bound from text)

- 252 of 300 merged PR bodies mention review, Codex or a verdict.
- 48 of 300 name a round ≥ 2: 17 at round 2, 24 at round 3, 1 at round 4 (#2680).
- 102 of 300 (34%) carry an exact-head `Drain-Review` receipt, all `APPROVE`. That is the share of ordinary feature PRs that `pr-scope-guard`'s AUTHORITY_RE / gate list pulls into the blocking-review path.
- Required checks on `main`: `Diff scope declared`, `required-tests`, `invariants`, `slow-tests`.

### 3.3 Review artifacts: where the effort goes

- `docs/reviews/`: 237 files. 3 are from July, 20 from August and **214 from September**. Peak days: 36 on 09-10, 34 on 09-09.
- First verdict word: ADAPT 67, APPROVE 40, REJECT 7, none 121.
- **66 of 237 (28%)** cover the model / provider / credential / refresh / connect cluster. 16 cover voice and 6 cover workspace.
- Only about **4 of 237** are live-user acceptance artifacts:
  - `2026-09-08-workflow-checklist-live-acceptance`
  - `2026-09-22-owned-run-activity-acceptance`
  - `2026-09-23-cloud-admission-deployed-acceptance`
  - `2026-09-04-voice-capability-live-fix`
  - By contrast, 73 are "proof" files, which are mostly scripted or local.
- **Findings judged wrong, stale or overstated.** The measurement is a lower bound, because the text does not reliably encode direction.
  - 21 of 237 artifacts (9%) explicitly record a claim that was withdrawn, retracted, overstated, not adopted, "not a defect", "root corrected" or "did not survive" re-verification.
  - 72 of 237 (30%) contain structured `DISAGREE_EVIDENCE` or `DISAGREE_CONCERN` lines. Across them: 126 AGREE, 45 DISAGREE_EVIDENCE and 47 DISAGREE_CONCERN dispositions, so 42% of dispositions disagree.
  - 12 of 96 concern files record the author's own overstatement or correction. Example: the auth-sync concern on this branch, "downgrade … I overstated the blast radius."
- **Concerns:** 94 open, median age 24 days, 74 older than 14 days. By severity: P0 4, P1 13, P2 39, unlabelled 37. 70 mention review or rounds.
- **Worktrees:** `git worktree list` shows 271 registered worktrees on the host checkout. That count is a lane-sprawl indicator, not a defect.

### 3.4 Case studies

| # | Case | What happened | Would MVP + live test short-circuit it? | Would a cleaner primitive? |
|---|---|---|---|---|
| 1 | **PR #2561** (harness cut, +1,248/−71,562, 526 files; PR open 3.3 h) | Five exact-head REJECT rounds (six reviews). Per the PR body, the trigger was a **two-line edit to `.github/heavy-test-files.txt`** that made a 526-file deletion PR need a receipt. Fix: revert those two lines and move them to their own PR. Rounds 4–5 found weaknesses in tests written one round earlier. Round 5 also caught a real error: a gate script (`check_background_authority_inventory.py`) deleted as "dead". | No. This was a deletion PR, with no user surface. | **Yes, via gate scoping.** Splitting the floor-touching lines into a tiny PR would have cut this to 1–2 rounds. Round 5's real catch argues for keeping *one* blocking review on gate files, not six. |
| 2 | **PR #2755** (credential remove, +4,315, 40 files, 27 commits) | Four passes with 7→5→1→3 findings, non-monotonic. Two of round 4's three findings were **pre-existing** bugs the change made reachable. The receipt was voided by every push, and the cap forbade the pass that would restore it, so there was no exit (concern `2026-08-31-the-exact-head-receipt-loops…`). Ownership and orphan residue is still open (`2026-08-31-credential-removal-leaves-ownership-and-orphans`). | Partly. "Remove = delete vault entry + connection row" was the MVP and was proven by 3 mutation tests. Pre-existing bugs belonged in concerns, not in the merge gate. | **Yes.** The real defect is that credential ownership has two definitions (deposit-ownership row vs. connection row). One ownership fact would delete the class. |
| 3 | **#2773 → #2774** (Play account deletion, +4,056, 41 files) | Three Codex REJECTs: 9 findings, then P0 + 6 P1, then 7 P1 + 1 P2. Stopped at the cap with a residue concern, "on a product with one real user". Round 2's P0 (deletion reaching other people's rows) was a **genuine floor catch**. | **Yes.** Play requires a deletion *request* path fulfilled "within a reasonably quick period", and manual fulfilment is allowed. An MVP (request form plus founder-processed deletion, with self-universe delete automated) meets policy on day one. | **Yes.** Round 3's structural fix, a deletion set derived from the live schema instead of a hand list, was the primitive. Building it first would have removed rounds 2–3. |
| 4 | **PR #3832** "selectable agent models … safe fallback **MVP**" (+49,261, 346 files, 138 commits, ~120 h from first commit to merge) | Built runtime, API, storage, authority and UI for main-agent plus per-workflow/task choices, saved defaults, ordered fallbacks and discovery in one PR, with 4+ review/proof artifacts. Within 48 h of deploy, live use produced six fix PRs (#3851, #3852, #3859, #3862, #3863, #3877), all about sign-in failures, reconnect and picker clarity. | **Yes, strongly.** The real MVP was one picker plus a saved default for the main agent. The live failures (sign-in, reconnect wiping setup, invisible tab override) were found by *use*, not by review. | Partly. The follow-ups work around case 5's missing primitive. |
| 5 | **Native credential refresh lane.** P0 `2026-09-01-a-subscription-credential-dies-permanently-at-its-first-token-expiry`; recurrence `2026-09-24-codex-refresh-signin-recurrence` (0a7f worktree); hold `2026-09-24-refresh-concurrency-integration-hold`. | 23 days open. The 2026-09-24 concern names about 17 dispatched agents (Claude/peer/builder/review IDs). It lists components built and cloud-proven but **"UNWIRED"**: lease foundation, try-acquire, durable material helper, workspace mask/floor. Designs were rejected, including the two-span seed/harvest MVP (concurrent last-writer-wins) and the whole-process lease (nested deadlock). Reviewer errors were caught along the way: root corrected 4303's token-ingress conflation, withdrew an "atomic rename" claim and rejected Opus92522's inference. Meanwhile about six symptom PRs shipped (Automatic avoids failed sources, truthful sign-in clues). | **Yes.** The MVP was judged against a perfect concurrent design, not against production. Production **dies with certainty at first expiry**, so even a write-back with a per-credential lock held only for the copy strictly improves on the status quo for a one-user universe. Its concurrency risk only matters under parallel same-credential refresh. Ship, observe, then harden. | **Yes, decisively.** The pinned Codex source already serializes refresh in process: `AuthManager` holds a `Semaphore(1)`, and app-server shares one `Arc<AuthManager>` across threads. The primitive is **one long-lived native process per credential that owns its own refresh**, a single writer. Rotating secrets should not be copied into per-call read-only snapshots. That is the "two definitions of one fact" class again. |

Case 5 is my analysis, not a finding from the lane's own reviewers. The lane's per-thread-isolation result (73147: VIABLE at thread start, GAP for mid-turn renewal) supports the direction.

---

## 4. Proposed policy: replacement for AGENTS.md "Quality Gates" bullets

This replaces the current bullets on `main` ("Shape before hardening" … "Final chatbot-surface proof"). It also replaces PR #3945's "Reviews are autonomous, not an endless gate" bullet, whose "as many bounded reviews as a release genuinely needs" has no terminator. Keep #3945's "carry to verified completion", "next step" and "test through the app agent" bullets as they are. 38 lines:

```markdown
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
```

### Executable gates: keep, relax or change

| Gate | Recommendation | Reason |
|---|---|---|
| `required-tests`, `slow-tests`, `invariants` (context budget, drift, mirror parity, mojibake) | **Keep required** | Cheap, mechanical, deterministic. This is what OpenAI's harness post means by "enforce invariants mechanically." |
| `pr-scope-guard` → "Diff scope declared" (SENSITIVE_RE, 3000-file cap) | **Keep** | Catches the #1491 lineage-smuggling class, and costs nothing on normal PRs. |
| `pr-scope-guard` exact-head receipt on **gate-defining files** (`tests.yml`, `pr-scope-guard.yml`, known-failing ledger adds, `heavy-test-files.txt`, `ci_required_tests.py`, `drain_review_gate.py`) | **Keep blocking** | "A PR cannot neuter its judge" is Tier 2. #2561 shows the cost when a gate edit rides inside a big PR, so the policy is to split it out, not to drop the gate. |
| Exact-head receipt on **AUTHORITY_RE** | **Narrow and relax.** (a) Shrink to true floor files: `auth/`, `execution_authority/`, `credential_vault.py`, `api/permissions.py`, `api/visibility.py`. Drop hub files such as `providers/router.py`, `provider_assignment.py`, `foreground_run_provider.py`, `provider_serving_binding.py`, which ordinary feature work touches. (b) Make the receipt **range-valid**: it stays valid when later commits touch only tests or the files the review's findings named. | It covers 34% of merged PRs (102/300). "Voided by any push" plus a round cap produced #2755's no-exit loop. Diffing the reviewed head against the shipped head keeps the anti-self-attestation property without re-review. |
| `auto-enroll-merge` | **Keep, with a change:** Tier 2 PRs open only after the verdict, so no draft dance. Tier 0/1 auto-merge on CI. | Addresses concern #2773 (auto-merge landed before a REJECT was read) without slowing Tier 0/1. |
| `deploy-prod` → `mcp_public_canary.py --assert-handles`, `deployed_sha.py --assert-contains`, `release-reconcile.yml` | **Keep** | These *are* the production-signal gates. Merged-is-not-deployed stays a hard rule. |
| `actionlint`, `docker-build`, `preview-security`, `linux-jail-proof`, `release-reconcile-regression`, `uptime-layer2-regression` on PR | **Keep, non-required and path-filtered** | Informative for their paths. Making them required would slow Tier 0 work for no floor benefit. |
| Cloud pre-push oracle, cloud-only-preflight | **Keep as optional tools** | Useful Linux truth for sandbox/fs changes. Not a gate. |
| AGENTS.md's unsourced "15, 8, 12, 2, 8, 1, 4, 1, 0" and "three agents beat five" | **Replace** with local evidence (#2755: 7→5→1→3; #2774: 9→7→8) plus the §2.1 citations | No source was found. Truth-and-Freshness requires fixing the citation. |

**Not recommended:** removing cross-family review entirely. Self-preference bias is measured (NeurIPS 2024), and the floor catches in #2774 and #2561 were real. The fix is fewer rounds scoped to the floor, not zero review.

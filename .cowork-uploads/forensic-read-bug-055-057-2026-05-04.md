# Forensic Read — BUG-055/056/057 + Recent Auto-Change Branches

**By:** cowork-vision
**Date:** 2026-05-04T22:00Z
**Scope:** durable artifacts only (activity.log, git history, PR diffs, auto-change branch contents) — no live chatbot tab access from this session.

## Findings

### 1. Universal stale-base kitchen-sink-diff in auto-change branches

Every recent auto-change branch shows the deletion-heavy pattern (deletions massively exceed additions vs current main):

| Branch | Topic | Insertions | Deletions | Net |
|---|---|---:|---:|---:|
| issue-246 (BUG-057) | wiki write-back | 62 | 3,012 | -2,950 |
| issue-245 (BUG-056) | patch-request misframing | 10 | 5,324 | -5,314 |
| issue-244 (autonomy roadmap) | design-note | 64 | 5,234 | -5,170 |
| issue-274 (latency probe TINY) | smoke | 117 | 1,042 | -925 |
| issue-273 (latency probe TINY) | smoke | 52 | 698 | -646 |
| issue-271 (FEAT-004 trigger receipt smoke) | smoke | 278 | 460 | -182 |
| issue-265 (COWORK-SMOKE-2) | smoke | 184 | 354 | -170 |

**Implication:** PR #284 (stale-base guard) is **structurally load-bearing**, not just useful. Until it lands, every loop-produced PR carries kitchen-sink-diff that requires human review-and-bridge to disambiguate real payload from stale-base noise. This is exactly the regression class incident #3 produced at substrate scale.

### 2. The "real" payload is small + sometimes destructive

Filtering issue-246 (BUG-057) to non-stale files:
- `STATUS.md` +1 row (auto-ship #3 task)
- `scripts/wiki_bug_sync.py` _change_kind() simplification — REMOVES handling for `pages/feature-requests/`, `pages/patch-requests/`, `pages/design-proposals/` paths. Collapses routing taxonomy to only `pages/plans/feature-`, `pages/plans/patch-` patterns.
- `tests/test_wiki_bug_sync.py` -45 lines — DELETES three tests covering patch-request lane, legacy-bug-typed patch-request lane, and feature-request lane routing.
- Plugin mirrors of the same.

**Loop investigation pattern:** When given architectural friction (BUG-057's "evidence_manifest write-back"), the loop produced a code change that *simplifies by removing capability*. It deleted the routing taxonomy and the tests covering it. Net effect if merged: the routing logic stops handling community-contributed pages outside `pages/plans/`. That's a regression dressed as a simplification.

Issue-245 (BUG-056) is even more extreme: its real payload is **10 lines added across 5,324 lines deleted**, including `workflow/api/auto_ship_actions.py` (96 lines), `workflow/auto_ship_pr.py` (368 lines), `tests/test_validate_ship_packet_action.py` (149 lines), `tests/test_bug_investigation_dispatcher.py` (177 lines), `tests/test_fuse_safe_commit.py` (162 lines). If merged, that branch would have **deleted the entire auto-ship substrate**. The stale-base inflation is so severe the actual signal is invisible.

### 3. Mechanical filings vs architectural filings show divergent loop behavior

| Filing class | Examples | Loop output | Outcome |
|---|---|---|---|
| Mechanical bugs (precise scope, deterministic fix) | BUG-053 wiki lint scoping, BUG-055 worldbuild_stuck, BUG-058 ledger semantics | Clean small PRs (PR #240, #239, #287) | All merged successfully |
| Architectural / meta-process filings | BUG-056 patch-request misframing, BUG-057 wiki write-back, autonomy roadmap | Kitchen-sink-diff branches, sometimes destructive | Held / superseded / never merged |

The pattern: the loop's investigation routine works for "what's the smallest code change that fixes this specific behavior" but doesn't have a separate code path for "what's the right design here, and should this even produce a code change?" Architectural filings get force-fit through the code-change pipeline and produce simplification-by-deletion.

### 4. PR #284 as loop self-protection — emerged from the very pattern it fixes

BUG-059 (the friction that became PR #284's stale-base guard) was filed about exactly this kitchen-sink-diff pattern. The loop produced unmergeable branches (visible to busyclever's review work bridging them); the reviewer's friction surfaced as a filing; the filing produced the substrate fix. Beautiful self-correcting loop instance — friction-as-filing → patch → substrate evolution.

Once PR #284 lands and deploys:
- Loop's PR-creation primitive checks `behind_by == 0 AND status in {"ahead", "identical"}` against the base branch via GitHub Compare API
- Stale-base auto-change branches are rejected before opening a PR (`pr_create_stale_head` error_class)
- The kitchen-sink-diff class structurally vanishes
- Reviewer cognitive load drops massively

This makes PR #284 a tier-1 priority for the queue.

## Implications for next user-sim filings

**Highest-value targets** the forensic read surfaces:

**Target A — test-coverage erosion concern (medium specificity, high impact):**
File via user-sim chatbot: "Loop investigations sometimes delete test coverage in auto-change branches without producing replacement coverage. Example: issue-246 (BUG-057 wiki write-back) deletes 45 lines from `tests/test_wiki_bug_sync.py` covering patch-request lane, legacy-bug-typed patch-request lane, and feature-request lane routing. If the loop's simplification removes capability (these routing paths), the change is structurally destructive even when wrapped as a fix. Substrate gap: the loop should detect *capability removal* in its diff and either (a) flag it for review, (b) refuse to produce a destructive simplification, or (c) require explicit confirmation that the removed capability is intentionally retired."

This filing exercises the loop on its own behavior and tests whether it can produce a meta-fix for its own pattern. Closely watching the response tells us whether the loop can introspect on its own design.

**Target B — architectural-vs-mechanical routing (high specificity, structural):**
File via user-sim chatbot: "When a filing is architectural/design-shaped (e.g., 'patch-request loop is misframed,' 'wiki should write back evidence_manifest'), the loop currently routes it through the same code-change investigation pipeline as mechanical bug fixes. Result: architectural filings produce kitchen-sink-diff branches that simplify by deletion (issue-246, issue-245). Substrate gap: the chatbot or dispatcher should detect filing-shape (mechanical vs architectural) and route differently — architectural to design-note draft, mechanical to auto-change branch."

This is more architectural and may produce the same kitchen-sink pattern when the loop tries to fix it. But the meta-question is exactly the question we want it to surface.

**Target C — keep-loop-moving small mechanical filing (low risk, demonstrates pattern):**
File a small mechanical observation that the loop has a track record of fixing cleanly. Candidates: a wiki lint observation, a STATUS.md cleanup, a test coverage gap that's clearly additive. Pick one to keep the queue flowing while the architectural concerns work themselves out.

**Recommendation:** sequence is C → A → B. Start with a low-risk mechanical filing to demonstrate the loop is healthy and keep it moving. Once #284 lands and stabilizes, escalate to A (test-coverage-erosion is mid-architectural). B is highest-value but riskiest; save until A's response shows whether the loop can self-introspect.

## Cross-references
- `f086853` (cowork-vision role transition entry)
- `fd9131e` (cowork-vision checker keys YES on #284/#291)
- `b0c145c` (busyclever cross-PR finding — same regression class)
- `.cowork-uploads/durable-coordination-research-2026-05-04.md` (broader synthesis)

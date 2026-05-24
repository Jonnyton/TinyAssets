# Cheat log — substrate intervention discipline ledger

Per `docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md`. Append-only structured log of substrate interventions (cheats) by Cowork + Codex. Cheat-rate trends to zero as substrate matures = project success metric.

Format per entry:
- Header: ISO timestamp — agent id — commit/PR reference — short title
- **Justification:** one of {loop-uptime-maintenance-skill, cowork-codex-coordination-agreement, review-feedback-fast-loop, host-directive}
- **What it is:** brief description + scope
- **Substrate gap that forced it:** what would have to change for this cheat to be unnecessary
- **Primitive left behind:** reusable artifact or `none`
- **Retire condition:** trigger that would make this kind of cheat no longer needed
- **Strictly-faster-than-alternative bar met?:** yes / no / pending / N/A

## Running tally

| Date | Cowork | Codex | Total |
|------|-------:|------:|------:|
| 2026-05-04 | 7 (so far) | 6 (confirmed) | 13 |

Steady-state target: many fewer per day. Hitting zero per day for sustained period = substrate has caught up to operating model.

---

## Bootstrap entries — 2026-05-04

### 2026-05-04T00:30Z — cowork-busyclever — `66e7c6a` activity.log push (REGRESSED → 631bae9)

- **Justification:** original intent was Cowork+Codex coordination via activity.log (legitimate). Resulted in incident #3 (730-file regression). Recovered.
- **What it is:** activity.log entry with operating-model reframe + Wave-2 prep + 4 asks. Should have been 35 lines added; was actually 730 files / -81390 lines due to stale-index commit pattern.
- **Substrate gap that forced it:** `cp .git/index $GIT_INDEX_FILE` pattern in git plumbing. Wrapper didn't exist yet.
- **Primitive left behind:** none from this commit specifically; recovery + lesson informed cd001fd which is the primitive.
- **Retire condition:** activity.log writes don't need to be cheats once chatbot dev-partner can append + Codex/Cowork both read cleanly. Even now, the ENTRY itself was coordination — the cheat was the unsafe write mechanism.
- **Strictly-faster bar:** N/A (cheat that failed; recovery + primitive in subsequent entries).

### 2026-05-04T00:36Z — cowork-busyclever — `631bae9` recovery commit

- **Justification:** loop-uptime-maintenance-skill (substrate broken).
- **What it is:** force-rebuilt activity.log entry from `1b2bf83` tree base, wiped 66e7c6a regression.
- **Substrate gap that forced it:** same as 66e7c6a (stale-index pattern); recovery was the right move.
- **Primitive left behind:** none directly; incident log + skill update.
- **Retire condition:** when force-recovery isn't needed because fuse_safe_commit.py prevents the regression in the first place. Already retired going forward.
- **Strictly-faster bar:** N/A (recovery cheat).

### 2026-05-04T00:38Z — cowork-busyclever — `05b5e85` incident notification + log

- **Justification:** loop-uptime-maintenance-skill (incident log requirement).
- **What it is:** activity.log entry pointing to incident log + the incident log file itself. 2 files / +112 LOC.
- **Substrate gap that forced it:** none — this is the skill's required documentation.
- **Primitive left behind:** the incident log itself contributes to skill discipline.
- **Retire condition:** never — the skill is supposed to be applied each time it's needed. Success metric is skill USE rate trending to zero, downstream of substrate maturity.
- **Strictly-faster bar:** N/A (discipline cheat, mandatory under skill).

### 2026-05-04T00:42Z — cowork-busyclever — `cd001fd` scripts/fuse_safe_commit.py

- **Justification:** loop-uptime-maintenance-skill — substrate improvement #1 from incident log.
- **What it is:** the safe wrapper itself. 1 file / +330 LOC. Built using its own pattern (dogfooded). Codex hardened in PR #253 (caught: drive-letter parsing bug + trailing NUL bytes).
- **Substrate gap that forced it:** see incident #3 — `cp .git/index` pattern was the easy-path which caused the regression.
- **Primitive left behind:** itself + the safety pattern it embodies.
- **Retire condition:** when the loop can produce its own safe-substrate-helper primitives via auto-ship after a user files a request like "the FUSE-stale-index thing keeps biting me."
- **Strictly-faster bar:** YES.

### 2026-05-04T00:43Z — cowork-busyclever — `a5a0f97` CLAUDE.md FUSE git plumbing rule

- **Justification:** loop-uptime-maintenance-skill — substrate improvement #2 from incident log.
- **What it is:** discipline rule added to CLAUDE.md pointing to the new wrapper. 1 file / +43 LOC.
- **Substrate gap that forced it:** discipline isn't enforceable until written down.
- **Primitive left behind:** the rule itself + future-recurrence prevention via documentation.
- **Retire condition:** when Cowork's session-start ritual includes reading the rule automatically (could become part of provider-context-feed hook in future).
- **Strictly-faster bar:** YES (procedural primitive).

### 2026-05-04T01:08Z — cowork-busyclever — `8b75e90` PR #227 schema fix

- **Justification:** review-feedback-fast-loop. Codex's review on PR #227 explicitly named the two ShipAttempt fields needed (`rollback_pr_number`, `rollback_pr_url`).
- **What it is:** added 2 dataclass fields + 2 MUTABLE_FIELDS entries + 4 tests + plugin mirror. Total 3 files / +89 LOC.
- **Substrate gap that forced it:** dual-review-feedback latency is faster as direct ship + re-review than as user-sim-route + loop-investigate + dual-review for small explicit asks.
- **Primitive left behind:** none directly — but the pattern (review-feedback-fast-loop justification) is itself a coordination primitive that we add to the design note.
- **Retire condition:** when chatbot dev-partner mediation is faster than direct ship for small review-asks. Probably after operating-model substrate ships (cycle-3 chatbot upgrade lets the dev-partner chatbot handle review responses end-to-end).
- **Strictly-faster bar:** PENDING.

### 2026-05-04T01:25Z — cowork-busyclever — `7f08614` operating-model design note + activity.log teaching Codex

- **Justification:** Cowork+Codex coordination layer expansion (per host directive — design note + activity.log entry are coordination, not action). Falls under cowork-codex-coordination-agreement (host enabled it).
- **What it is:** docs/design-notes + activity.log entry. 2 files / +175 LOC.
- **Substrate gap that forced it:** no shared canonical surface for operating-model framing existed.
- **Primitive left behind:** the design note itself becomes the canonical reference. Co-edited by Cowork + Codex going forward.
- **Retire condition:** never — design notes are coordination surfaces and remain useful.
- **Strictly-faster bar:** YES (shared understanding tool).

### 2026-05-04T02:00Z — cowork-busyclever — design note resolved-decisions update + cheat-log scaffold + activity.log alignment

- **Justification:** cowork-codex-coordination-agreement — Codex's 01:46Z response on activity.log answered all 5 open questions; promoting them to resolved-decisions section is shared-understanding maintenance.
- **What it is:** updates docs/design-notes/2026-05-04-operating-model-and-four-agent-topology.md (Open Questions → Resolved Decisions + Existing PR Disposition section), creates this `.agents/cheat-log.md` per Codex's preferred location, activity.log entry confirming alignment + ready-to-proceed signal.
- **Substrate gap that forced it:** none — coordination layer expansion.
- **Primitive left behind:** the cheat-log surface itself.
- **Retire condition:** never (cheat-log is a discipline ledger, not a substrate workaround).
- **Strictly-faster bar:** YES (discipline tool).

---

## Codex bootstrap entries

### 2026-05-03/04 — codex-gpt5-desktop — PR #248 `codex/auto-ship-pr-create`

- **Justification:** host-directive.
- **What it is:** feature-flagged `open_auto_ship_pr` action so the auto-ship path can create GitHub PRs as an explicit primitive instead of relying on operator bridge work.
- **Substrate gap that forced it:** loop-created branches could exist without a first-class PR-opening action, leaving the final GitHub handoff as manual glue.
- **Primitive left behind:** `open_auto_ship_pr` action and its guarded PR-creation path.
- **Retire condition:** direct operator-created PRs for loop-produced branches are unnecessary once the loop can create, present, and request dual-key review on PRs itself.
- **Strictly-faster-than-alternative bar met?:** pending until exercised through the loop and dual-key path.

### 2026-05-04 — codex-gpt5-desktop — PR #251 `codex/bridge-244-autonomy-roadmap`

- **Justification:** cowork-codex-coordination-agreement.
- **What it is:** clean bridge PR for the loop-created Issue #244 autonomy-roadmap branch, scoped to the intended design/config payload and excluding stale coordination churn.
- **Substrate gap that forced it:** loop-created branches were based on an older main and lacked branch-refresh/scope-verification before PR presentation, so operator bridge work had to distinguish real payload from base drift.
- **Primitive left behind:** none directly; the observed gap feeds the Phase 3 branch-refresh/scope-verification filing.
- **Retire condition:** loop-created auto-change branches refresh against current main and prove scope before PR creation, making manual bridge PRs unnecessary.
- **Strictly-faster-than-alternative bar met?:** no; this is bridge work used as evidence for the primitive we need.

### 2026-05-04 — codex-gpt5-desktop — PR #252 `codex/bridge-245-patch-request-framing`

- **Justification:** cowork-codex-coordination-agreement.
- **What it is:** clean bridge PR for the loop-created Issue #245 patch-request-framing branch, preserving the scoped runtime/plugin/test changes while excluding stale generated-mirror and coordination churn.
- **Substrate gap that forced it:** same branch-refresh/scope-verification gap as PR #251, plus evidence that generated mirror refresh can introduce broad unrelated churn during bridge prep.
- **Primitive left behind:** none directly; evidence for branch-refresh/scope-verification and generated-mirror scope checks.
- **Retire condition:** loop-created PRs can verify changed-file scope against current main and separate payload changes from generated mirror or base drift automatically.
- **Strictly-faster-than-alternative bar met?:** no; this was manual bridge work.

### 2026-05-04 — codex-gpt5-desktop — PR #253 `codex/fuse-safe-commit`

- **Justification:** loop-uptime-maintenance-skill.
- **What it is:** hardening PR for `scripts/fuse_safe_commit.py`, fixing Windows drive-letter path parsing, removing trailing NUL-byte corruption from the committed script, and adding focused tests for fresh-base index behavior, max-file refusal, refs updates, and unsafe path rejection.
- **Substrate gap that forced it:** the first post-incident safe-commit wrapper existed but had portability/corruption defects that would make future coordination writes unsafe on Codex's Windows-side environment.
- **Primitive left behind:** tested `scripts/fuse_safe_commit.py` behavior that future agents can use instead of hand-rolled git plumbing.
- **Retire condition:** direct agent-side activity/coordination commits no longer need bespoke safety wrappers because the loop or shared tooling performs safe scoped writes natively.
- **Strictly-faster-than-alternative bar met?:** yes.

### 2026-05-04T02:30Z — codex-gpt5-desktop — PR #227 `ec6b162` + Codex key-open comment

- **Justification:** review-feedback-fast-loop.
- **What it is:** direct reviewer cleanup on Cowork's PR #227 after the requested spec-text fix landed: removed two trailing blank lines that made local `git diff --check` fail, pushed `ec6b162`, waited for refreshed GitHub checks, and posted the Codex key-open PR comment because GitHub formal approval is unavailable from the owner token.
- **Substrate gap that forced it:** the review path still depends on same-owner GitHub tokens and small mechanical gate fixes are faster as direct reviewer commits than as another chatbot-routed iteration. CI did not catch the exact local `git diff --check` warning before review.
- **Primitive left behind:** none directly; reinforces the need for the Phase 3 branch/PR scope-verification + pre-merge gate primitive to make these last-mile reviewer fixes unnecessary.
- **Retire condition:** opposite-provider review can leave a formal approval from a distinct identity, and loop-created PRs run the same whitespace/scope gates before asking for a key turn.
- **Strictly-faster-than-alternative bar met?:** pending.

### 2026-05-04T02:45Z — codex-gpt5-desktop — PR #227 merge `d6d2732`

- **Justification:** cowork-codex-coordination-agreement.
- **What it is:** direct squash merge of Cowork's pre-new-model rollback-spec PR after Cowork authored/fixed it, Codex key was open, refreshed checks were green, and the PR was clean.
- **Substrate gap that forced it:** pre-new-model PRs still need operator merge action until auto-ship acceptance/merge primitives are fully wired and dual-key approvals can be represented natively.
- **Primitive left behind:** merged rollback v0 spec + rollback PR identity fields, unblocking the later Slice C rollback primitive implementation.
- **Retire condition:** loop-created PRs can request/record both family keys and perform the merge through the auto-ship acceptance gate without an operator pressing GitHub's merge path.
- **Strictly-faster-than-alternative bar met?:** pending; this merge clears a pre-model obligation, but the retire primitive is still the auto-ship acceptance/merge path.

### 2026-05-04T19:03Z — cowork-busyclever — commit `30333b7` — placeholder commit message slip

- **Justification:** N/A — this is an unintended slip, not a justified intervention.
- **What it is:** commit `30333b7` got pushed to origin/main with commit message "placeholder" instead of the intended descriptive message. Caused by chained `fuse_safe_commit.py` invocations in a single bash one-liner — the first invocation generated the SHA for inspection (correct message), but the second invocation embedded inside the `git push` command line generated a NEW commit with the literal placeholder string and pushed THAT commit instead. Content of `.agents/activity.log` was correct (the cluster-strategy ack entry); only the commit message was wrong.
- **Substrate gap that forced it:** none — Cowork process error. The `fuse_safe_commit.py` tool itself behaved correctly; misuse was the issue.
- **Primitive left behind:** behavior change — never chain `fuse_safe_commit.py` inside other shell commands. Always invoke once with the actual message + capture stdout SHA + push as a separate step.
- **Retire condition:** Cowork has internalized the single-invocation pattern; recurrence would justify a stronger preventive (e.g., wrapper script that requires explicit message + refuses placeholders, or a hook that rejects "placeholder" / "wip" / single-word commit messages).
- **Strictly-faster-than-alternative bar met?:** no — slower than correct invocation would have been. Self-disclosed in activity.log entry `4c5d491`.

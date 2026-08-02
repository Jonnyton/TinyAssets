**Verdict: `adapt`** — the diagnosis is real and independently confirmed; four small text-level adaptations are required before implementation. This file is the durable review artifact; the reviewer edited no implementation files and made no commits.

**What I recomputed — every audit number checks out:**
- `openspec list --json`: 34 audit-basis changes (35 with this change itself, which has 7 tasks), 1,200 total / 366 done / 834 unchecked, median unchecked 16.5, 12 changes >25 unchecked — all exact matches.
- 12 active changes absent from STATUS.md (holding **300** unchecked by my count vs. the audit's 291 — minor, direction unchanged), and `scoped-wiki-canary-token` confirmed at 12/12 complete-but-unarchived.
- Git window since 2026-07-25: exactly 100 commits, 20 new active change dirs vs 5 archives, 31 commits touching runtime/tests/tooling. 374 registered worktrees; STATUS.md at 20,238 bytes vs ~4 KB guidance; primary checkout 240 behind.
- `worktree_status.py` scaling diagnosis follows from the code, not just the observed timeout: up to 6 `rev-parse` calls per worktree in `_merge_base_candidates` plus ~5 more per candidate inside squash-aware `is_merged_into` — thousands of subprocess spawns at 374 worktrees.
- The change passes `openspec validate --strict`, and no existing script joins OpenSpec state with STATUS ownership, so the inspector duplicates nothing.

**Sources re-checked directly:** OpenSpec really does warn against bulk conversion ("Forcing a one-time bulk conversion tends to produce a large, stale spec nobody trusts") and prescribes one intent / one owner / one branch per change; Kanban supplies the WIP mechanism ("stop starting, start finishing"). The OpenAI page 403s to unauthenticated fetch but search snippets corroborate the "~an hour / few hundred lines" scoping claim.

**Required adaptations (all text-level):**
1. **Define the WIP-counting identity.** AGENTS.md mandates session-specific provider names, so per-provider-one is both violated today by every fleet name (`fable-fleet-codex` sits on ~5 rows) and trivially evadable by minting a new session suffix per claim. Decide the identity, report global WIP alongside, and name renaming-to-evade a process violation — before the policy text ratchets into AGENTS.md/config/skill.
2. **Pin invocation points** — admission/dispatch-time only, explicitly not a fifth mandatory session-start command; the audit itself names coordination overhead as a root cause.
3. **Correct one citation:** the Anthropic harness-design article ends by *removing* sprint decomposition on a stronger model, and OpenAI says task size grows with capability — so the 12-task ceiling must be framed as a dated, reviewable calibration (the Watch row already exists; tie it in).
4. **Fix the STATUS row's Files cell:** it names `.codex/skills/openspec/SKILL.md`, but `.codex/` doesn't exist and AGENTS.md says Codex has no mirror — Codex reads `.agents/skills/` directly.

On the challenge questions: the arrival/WIP diagnosis is supported (agents produced 31 runtime commits while change arrival outpaced archival 4:1); 12 tasks is a defensible v1 backstop (generous versus the sources' "one focused session"); one-active-change-per-session is the right first limit once the identity is defined; and the scoped slice is already close to the minimal safe implementation — with two zero-code wins (archive `scoped-wiki-canary-token`, triage the 12 untracked changes) that shouldn't wait for the tool.

One line on the Codex-dispatch reflex: skipped deliberately — this task *is* the opposite-provider review of Codex-authored work, so routing it back to Codex would defeat the gate's independence.

Sources: [OpenSpec: existing projects](https://openspec.dev/docs/existing-projects), [OpenSpec: team workflow](https://openspec.dev/docs/team-workflow), [OpenSpec: writing specs](https://openspec.dev/docs/writing-specs), [How OpenAI uses Codex](https://openai.com/business/guides-and-resources/how-openai-uses-codex/), [Anthropic: effective harnesses](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents), [Anthropic: harness design](https://www.anthropic.com/engineering/harness-design-long-running-apps), [Kanban guide](https://kanban.university/kanban-guide/)

VERDICT: ADAPT

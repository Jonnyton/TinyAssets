All evidence is in. `output/` is ignored; `.superpowers/` is not (which also means the existing SDD ledger path is unignored — a pre-existing latent issue the implementation can fix in passing). I have everything needed for the verdict.

One process note, restated for the record: I skipped the Codex-dispatch reflex deliberately — this review is itself the cross-family gate on a Codex-originated proposal, so routing the verdict through Codex would collapse the independence the gate exists to provide.

---

# Claude Review: Context Engineering Comprehensive Revision

**Review date:** 2026-07-28
**Reviewer:** Claude (Claude Code, model `claude-fable-5`)
**Proposal under review:** `docs/audits/2026-07-28-context-engineering-comprehensive-handoff.md` (initial provider: Codex; baseline `ce83a44f`)
**Review basis:** all ten listed project files read in full at this worktree's checkout; live re-runs of `scripts/check_context_budget.py` and `git check-ignore`; live re-fetch of primary external sources on 2026-07-28.

## Verdict

**ADAPT**

## Sources re-checked

Checked live on 2026-07-28 against current source state, not the report's characterization:

- [Anthropic — Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) — confirms "smallest possible set of high-signal tokens," subagents isolating detailed search context, and compaction / structured notes / just-in-time retrieval. Characterization accurate.
- [Gemini CLI `codebase-investigator.ts` @ `d29268d3`](https://github.com/google-gemini/gemini-cli/blob/d29268d360fd9fb71342c2add9b1244725ae08b8/packages/core/src/agents/codebase-investigator.ts) — confirms the `objective` input contract, structured report schema, exactly LS/ReadFile/Glob/Grep tools, `maxTimeMinutes: 10` / `maxTurns: 50`, and selection for vague/root-cause/refactoring tasks. Also confirms `ExplorationTrace` is in the output schema — the proposal's recommendation to keep the trace out of the coder handoff is a real, correctly identified adaptation.
- [Gemini CLI `read-only.toml` @ same commit](https://github.com/google-gemini/gemini-cli/blob/d29268d360fd9fb71342c2add9b1244725ae08b8/packages/core/src/policy/policies/read-only.toml) — mostly as described; nuance: it also permits internal task-tracker write tools, so "read-only policy" is slightly imprecise. Immaterial (the proposal's own scout default is stricter).
- [LangChain deepagents `middleware/subagents.py` @ `43eb196c`](https://github.com/langchain-ai/deepagents/blob/43eb196cf7faa993f2fa372dcc1fa65572d8a301/libs/deepagents/deepagents/middleware/subagents.py) — confirms per-subagent spec/permission controls (~L34–120) and fresh child state that strips parent messages, injects only the focused task description, and returns a filtered result (~L500–577). Characterization accurate.
- [FastContext, arXiv:2606.14066](https://arxiv.org/abs/2606.14066) — confirmed withdrawn (v4, "product IP issues... needs to be withdrawn and re-approved"), no license on the withdrawn version. The proposal's Watch-only classification is correct and is exactly the right call.
- [ContextBench, arXiv:2602.05892](https://arxiv.org/abs/2602.05892) — confirms "substantial gaps exist between explored and utilized context" and "LLMs consistently favor recall over precision." Accurate.
- [OpenAI — Harness engineering](https://openai.com/index/harness-engineering/) (direct fetch 403; corroborated via [mirrored excerpts](https://zby.github.io/commonplace/sources/harness-engineering-leveraging-codex-agent-first-world/)) — confirms the monolithic-AGENTS.md-crowds-out-the-task claim and the table-of-contents + pointer-loaded docs replacement. Accurate.

Not individually re-fetched (accepted on consistency with the verified sample and my own knowledge of the sources): Anthropic multi-agent research system, OpenAI prompt-injection post, LivePI, SWE-Explore, OpenHands CodeScout, Agentless, OpenAI Agents SDK handoffs. Nothing in the proposal's use of these carries load the verified sample doesn't already carry.

Local claims verified: the context-budget table matches `check_context_budget.py` live output byte-for-byte; ADR-002 says what the proposal says it says; PLAN.md's Harness & Coordination module explicitly places skill content out of scope, so the "no PLAN.md / AGENTS.md changes" position is correct.

## What is sound

- **The diagnosis of the current skill is accurate and complete.** I read the current 293-line skill: it is a generic greenfield tutorial (React/Express `AGENTS.md` template, static MCP product table, unsupported `<2,000 lines` threshold), its Brain Dump section contradicts its own selective-include guidance, its "no precedent → stop and ask" rule conflicts with `using-agent-skills` Core Behavior 2 (reversible defaults) and AGENTS.md Hard Rule 4 (autonomous defaults), and its Inline Planning section duplicates `planning-and-task-breakdown`. Every row of the weakness table checks out.
- **Citation discipline is unusually good.** Commit-pinned links, full SHAs, an honestly downgraded withdrawn paper, and a live budget-checker snapshot that reproduces exactly. One report-of-local-state error found (below), zero external citation errors.
- **The replacement architecture fits existing project authority.** The lifecycle operationalizes ADR-002 without duplicating its numbers (pointing at the checker as the single owner — correct per open question 5); the authority ladder matches the router's confusion-management norms; the truth-type mapping matches AGENTS.md's typed-truth rules; scoping detail into a specialist scout rather than growing the router matches `skill-authoring`'s thin-router rule.
- **The scout's security envelope is right.** Untrusted-content boundary, no secrets/writes/execution, read-only tools, compact typed return, partial-results-on-timeout — consistent with the verified Gemini and deepagents precedents and with this repo's fail-closed posture. Dropping ExplorationTrace from the handoff is a genuine improvement over the Gemini pattern.
- **Internal-precedent-before-external, the three-repo normal cap with a stated-reason escape, evaluation by utilization and downstream outcome rather than token count, and the Task 1 baseline-scenarios-before-rewrite ordering** are all sound and match `skill-authoring`'s test-with-subagents discipline.
- **The defer list is correctly conservative** (no trained models, no persistent cache, no harness auto-dispatch hooks in slice one).

## Required adaptations before implementation

**Blocking (must be incorporated; each is testable):**

1. **`.superpowers/sdd/` is not gitignored — the proposal's storage premise is false.** `git check-ignore .superpowers/sdd/progress.md` exits 1 at this checkout; `output/` *is* ignored. As written, scout artifacts would pollute `git status` in every lane and are committable — this repo has documented kitchen-sink-diff incidents. Fix: Task 3 must add `.superpowers/` to `.gitignore` (which also fixes the pre-existing unignored SDD ledger) or relocate transient scout artifacts under the already-ignored `output/`. Acceptance: `git check-ignore` exits 0 on the chosen path.
2. **Drop or correct the "encoding damage" rationale.** Both `.agents/skills/context-engineering/SKILL.md` and the `.claude` mirror are valid UTF-8 with intact box-drawing characters at baseline. The damage was almost certainly the observing tool's codepage (a documented Codex-on-Windows failure class), not the file. The rewrite deletes the diagram anyway, so nothing changes materially — but a review-gated artifact must not carry an unreproducible defect claim as justification.
3. **Define the Task Context Manifest's relationship to existing artifacts.** The repo already carries `_PURPOSE.md`, SDD task briefs (`scripts/task-brief`), and STATUS rows. A mandatory per-task manifest as a *fourth* parallel document duplicates responsibility — the exact drift AGENTS.md's coordination hygiene fights. The rewrite must state: the manifest is a **field contract that existing artifacts adopt** (a `_PURPOSE.md` section, a task-brief shape), and a standalone manifest file is written only when no existing artifact covers the task. Acceptance: the rewritten skill contains this precedence rule explicitly.
4. **State the scout's relationship to `peer-agents` and read-only Explore-type subagents.** The proposal never mentions `peer-agents`, yet that skill's description ("offloading a long grind (research…)") will co-trigger with the scout's. Per `skill-authoring`, descriptions must be narrowed until the handoff is obvious. Required: the scout skill defines itself as the *role and return contract*, names `peer-agents` as one dispatch mechanism (running the scout on the opposite family's budget is often the right move), and distinguishes itself from internal-codebase exploration agents. The router entry and both descriptions must not collide. Acceptance: no two skills trigger on "find external implementation examples."
5. **Enforcement lives in the dispatch, not the prose.** Per the documented team-mode caveat (role-file frontmatter does not reliably enforce permissions), the scout's read-only/no-secrets/no-shell boundary must be enforced through the spawn prompt and tool allowlist of the actual dispatch mechanism, and the skill must say so. Acceptance: the skill's dispatch template includes the allowlist; Task 5's malicious-README scenario is run against the real dispatch path.
6. **Define the review-gate boundary for scout output.** AGENTS.md requires opposite-provider review for research-derived concepts before implementation. Left ambiguous, agents will either dispatch a cross-family review per scout run (unusable) or use the scout to launder strategic research past the gate (dangerous). Required rule: a scout source-map is **task-scoped implementation evidence** consumed inside an already-authorized lane and covered by normal code review; if scout findings would change design truth (PLAN/OpenSpec-level shape, a new capability direction), the work must escalate to `external-research-implications` and its cross-provider gate. Acceptance: this rule appears in both the scout skill and the `external-research-implications` boundary edit.

**Optional follow-ups (non-blocking):**

- The 6–12-turn scout target is likely too tight against the verified production precedent (Gemini uses 50 turns / 10 min). Let the time budget dominate and calibrate the turn number from Task 5 measurements rather than hard-coding it.
- Note the `read-only.toml` nuance (internal tracker writes permitted) if the citation is kept.
- Treat the 150–190-line size target for the rewritten skill as guidance, not a gate — the proposal rightly criticizes magic numbers elsewhere.
- On the open questions, I concur with all five recommendations as written: `-scout` naming, JSON contract with optional Markdown rendering, `required | optional | skip`, no shell by default, and no ADR-002 number duplication.

## OpenSpec decision

**No OpenSpec change is required.** The skill rewrite, the new scout skill, and the router/planning/subagent/research-skill edits are process documentation: the host's 2026-07-19 OpenSpec directive scopes to platform behavior (MCP/API surface, storage shapes, capabilities, security posture of the product), PLAN.md explicitly places skill content outside the Harness & Coordination module, and ADR-002 is already the accepted decision this work operationalizes. Land directly as skill edits through the normal PR path with the proposal's own gates (mirror sync, `validate_skills.py`, fresh-agent scenarios, before-push cross-family diff review).

One boundary: the proposal's Defer list — harness-level auto-dispatch hooks, persistent precedent caches, any runtime primitive for context selection — **does** cross into OpenSpec territory. If any of those are ever picked up, they start as an OpenSpec change. State this in the landing so the boundary survives the handoff.

## Implementation gate

**Codex may begin implementation after incorporating the six blocking adaptations.** No further Claude research re-review is needed before build starts; this verdict satisfies the `ideas/PIPELINE.md` gate ("Build remains blocked on the independent review"). The proposal's own sequencing stands: Task 1 baseline scenarios before the Task 2 rewrite; the scout skill (Task 3) only after the core lifecycle is stable; before-push opposite-provider **code** review of the actual skill diffs still applies per AGENTS.md and the proposal's worktree landing packet. The PIPELINE.md row and the eventual STATUS row should be updated to `adapt` with a pointer to this artifact by whichever session lands it — this review session was read-only by instruction and has written nothing.

# Workflow Skills Audit — Refactor Prep

> **STATUS: EXECUTED 2026-06-23.** Refactored 60 → **32** skills (best-of-both
> merges, no duplicates). All overlapping skills consolidated; project-specific
> knowledge (FUSE, loop, MCP user-sim, BUG-019 edge testing, Cloudflare/GoDaddy
> ops) preserved into survivors. `validate_skills.py` passes; `.agents/.claude/
> .codex` mirrors byte-identical. Key calls: kept `spec-driven-development` as the
> native spec methodology and collapsed the 5 OpenSpec CLI skills into one
> `openspec`; merged cloudflare+godaddy into `infra-ops`; folded ponytail into
> `code-simplification`; absorbed the superpowers enforcement rule into the
> `using-agent-skills` router. The analysis below is the original plan, kept for
> reference.


**Scope:** all 60 skills in `.agents/skills/` (canonical), mirrored to `.claude/skills/` and `.codex/skills/`.
**Totals:** 60 skills · 114 files · ~12,960 lines of `SKILL.md`.
**Goal of this doc:** map overlap and propose a smaller set. No changes made yet.

---

## 1. How the 60 got here (provenance)

| Group | Count | Lines | Origin |
|------|------|------|--------|
| Project engineering skills | 35 | ~8,400 | Built for Workflow over time; the original set |
| `superpowers-*` | 14 | 3,381 | obra/superpowers, added this session, namespaced |
| `openspec-*` | 5 | 801 | Fission-AI/OpenSpec CLI, added by another session, just conformed |
| `ponytail*` | 6 | 341 | DietrichGebert/ponytail, added this session |

The headline problem: **the 14 `superpowers-*` skills were namespaced specifically because they duplicate domains the 35 project skills already cover.** That duplication, plus a few thin/low-value skills, is where the count can shrink. ~95% of the redundancy is in the dev-loop (TDD, debugging, review, planning, git, brainstorm, skill-authoring).

---

## 2. The core decision

For every dev-loop domain there are now **two competing skills**: a Workflow-native one (project context, conventions, BUG references, FUSE/loop specifics) and a `superpowers-` one (a coherent, enforced, cross-tool methodology with subagent dispatch and strict TDD). Shrinking the set means picking a policy:

- **Policy A — Adopt superpowers as the dev-loop spine.** Keep `superpowers-*` for the generic process (brainstorm→plan→TDD→debug→review→finish), retire the generic project equivalents, and keep only the project skills that carry *Workflow-specific* knowledge superpowers can't (loop, FUSE, MCP user-sim, BUG-019 edge testing, website, ops). **Biggest reduction, one coherent methodology.**
- **Policy B — Keep project skills as the spine, drop the duplicate superpowers.** Retire the `superpowers-` skills whose project equivalent already exists; keep only the genuinely-new superpowers ideas (subagent-driven-development, verification-before-completion). **Smallest disruption, loses the enforced auto-trigger loop you just installed.**
- **Policy C — Merge per domain** into one skill each that takes the best of both. **Best quality, most authoring work.**

**Recommendation: Policy A**, because you explicitly wanted superpowers' *enforcement* ("the setup that ensures they're used correctly"), and that property lives in the suite, not the project skills. The merges below assume A but note what to salvage from the project version.

---

## 3. Overlap clusters → consolidation

Each cluster currently = N skills; arrow shows the proposed single survivor and what to fold in.

**TDD** — `test-driven-development` (379L) + `superpowers-test-driven-development` (371L) → **1**. Keep superpowers' RED-GREEN-REFACTOR enforcement; fold any Workflow test-runner specifics from the project one.

**Debugging** — `debugging-and-error-recovery` (326L) + `superpowers-systematic-debugging` (296L) → **1**. (`conditional-edge-testing` stays separate — it's narrow BUG-019/021/022 routing, not general debugging.)

**Code review** — `code-review-and-quality` (347L) + `superpowers-requesting-code-review` (103L) + `superpowers-receiving-code-review` (213L) → **1–2**. Either one "code-review" skill, or split request-side vs receive-side. Fold `superpowers-verification-before-completion` (139L) in here as the "evidence before done" gate.

**Planning** — `planning-and-task-breakdown` (223L) + `superpowers-writing-plans` (174L) + `superpowers-executing-plans` (70L) → **1–2** (plan authoring + plan execution).

**Spec/ideation** — `idea-refine` (181L) + `superpowers-brainstorming` (159L) + `openspec-explore` (283L) + `spec-driven-development` (207L) all crowd the "figure out what to build" space. → **2**: one ideation/brainstorm skill, one spec skill. Decide whether OpenSpec *is* your spec system (then retire `spec-driven-development`) or a parallel option.

**Git** — `git-workflow-and-versioning` (369L) + `superpowers-using-git-worktrees` (202L) + `superpowers-finishing-a-development-branch` (241L) → **1** (worktrees + finish are sub-sections of git workflow).

**Skill authoring** — `skill-authoring` (128L) + `superpowers-writing-skills` (689L!) → **1**. The superpowers one is the single largest skill in the repo; trim it and fold in the Workflow validator/mirror conventions from `skill-authoring`.

**Subagent/parallel** — `superpowers-subagent-driven-development` (418L) + `superpowers-dispatching-parallel-agents` (185L) → **1**. (`team-iterate` is distinct — it tunes agent-team *definitions*, not dispatch.)

**Simplification/minimalism** — `code-simplification` (331L) + `ponytail` (106L) → **1–2**. `ponytail` is a tight, high-value ruleset; keep it as the lightweight enforcement and slim `code-simplification`, or merge.

**Deploy** — `ci-cd-and-automation` (390L) + `shipping-and-launch` (309L) overlap on release. → consider **1** "ship" skill, or keep split (pipeline vs launch checklist) if you use both distinctly.

**Concepts** — `domain-model` (83L) + `ubiquitous-language` (81L) are both "is the concept/term right?" → candidate **merge to 1**. `improve-codebase-architecture` (98L) and `zoom-out` (73L) are distinct lenses; keep.

---

## 4. Cut candidates (low standalone value)

- `ponytail-gain` (45L) — a benchmark "scoreboard" display. Marketing, not a workflow. **Cut.**
- `ponytail-help` (66L) — a help reference; the router already does discovery. **Cut** (or fold into `ponytail`).
- `ponytail-audit` (35L) / `ponytail-review` (50L) — overlap `code-review-and-quality` + `code-simplification`. **Fold** into those or into `ponytail` as modes.
- `ponytail-debt` (39L) — niche (harvest `ponytail:` comments). Keep only if you adopt the `ponytail:` comment convention; else **cut**.
- `openspec-archive-change` (113L) + `openspec-sync-specs` (143L) — thin CLI wrappers; **merge to 1** ("finalize change"). Keep `explore`/`propose`/`apply` as the live trio.
- `superpowers-using-superpowers` (121L) — its job (route to skills, enforce "invoke before acting") **duplicates `using-agent-skills`**. Fold its enforcement rule into the router and **cut**.

---

## 5. Keep as-is (distinct, Workflow-specific, low overlap)

`using-agent-skills` (router), `context-engineering`, `auto-iterate`, `external-research-implications`, `incremental-implementation`, `api-and-interface-design`, `security-and-hardening`, `performance-optimization`, `documentation-and-adrs`, `deprecation-and-migration`, `frontend-ui-engineering`, `game-prototyping`, `website-editing`, `browser-testing-with-devtools`, `ui-test`, `conditional-edge-testing`, `loop-uptime-maintenance`, `cloudflare-ops`, `godaddy-ops`, `team-iterate`, `improve-codebase-architecture`, `zoom-out`.

---

## 6. Target sizes

| Tier | Result | What it does |
|------|--------|--------------|
| **Conservative** | **60 → ~42** | Merge only the exact superpowers↔project duplicates (TDD, debugging, git, skill-authoring) + cut the 4 weak ponytail aux + fold `superpowers-using-superpowers` into the router. Low risk. |
| **Recommended** | **60 → ~32** | All of §3 cluster merges (Policy A) + §4 cuts. One coherent dev-loop, project-specific knowledge preserved, suites trimmed. |
| **Aggressive** | **60 → ~24** | Above + merge concepts (domain-model+ubiquitous-language), deploy (ci-cd+shipping), simplification (code-simplification+ponytail), and the openspec trio→2. Leanest; some nuance lost. |

---

## 7. Risks / migration notes (for whoever executes)

1. **Cross-references.** `superpowers-*` bodies reference each other by their (now prefixed) names. Any merge/rename must update those references or they dangle.
2. **Router coverage is enforced.** `scripts/validate_skills.py` fails if any skill folder isn't named in `using-agent-skills`. Update the router in the same change as any delete.
3. **Mirrors must stay byte-identical.** Every change to `.agents/skills/` must re-sync `.claude/skills/` + `.codex/skills/` (`scripts/sync-skills.ps1` on Windows). The `skills-valid` pre-commit invariant blocks drift.
4. **Frontmatter is strict.** Only `name` + `description`; description must contain a "Use when" trigger; `name` must equal the folder. Merged skills must keep this.
5. **Don't lose Workflow knowledge.** The project skills carry BUG references, FUSE rules, loop specifics, MCP user-sim discipline — salvage these into survivors before deleting.
6. **OpenSpec needs the `openspec` CLI**; if you're not committed to that dependency, the 5 openspec skills are the first cut, not a merge.

---

## 8. One-line disposition per skill

KEEP = stays · MERGE→x = fold into x · CUT = remove

| Skill | Disposition |
|------|-------------|
| using-agent-skills | KEEP (router; absorb superpowers-using-superpowers' enforcement rule) |
| superpowers-using-superpowers | MERGE→using-agent-skills, then CUT |
| test-driven-development | MERGE→tdd |
| superpowers-test-driven-development | KEEP as `tdd` survivor |
| debugging-and-error-recovery | MERGE→debugging |
| superpowers-systematic-debugging | KEEP as `debugging` survivor |
| conditional-edge-testing | KEEP (BUG-specific) |
| code-review-and-quality | KEEP as `code-review` survivor |
| superpowers-requesting-code-review | MERGE→code-review |
| superpowers-receiving-code-review | MERGE→code-review |
| superpowers-verification-before-completion | MERGE→code-review |
| planning-and-task-breakdown | KEEP as `planning` survivor |
| superpowers-writing-plans | MERGE→planning |
| superpowers-executing-plans | MERGE→planning (or KEEP as `executing-plans`) |
| idea-refine | KEEP as ideation survivor |
| superpowers-brainstorming | MERGE→idea-refine |
| spec-driven-development | KEEP or CUT (decide vs OpenSpec) |
| openspec-explore | KEEP |
| openspec-propose | KEEP |
| openspec-apply-change | KEEP |
| openspec-sync-specs | MERGE→openspec-archive-change |
| openspec-archive-change | KEEP as `openspec-finalize` survivor |
| git-workflow-and-versioning | KEEP as `git` survivor |
| superpowers-using-git-worktrees | MERGE→git |
| superpowers-finishing-a-development-branch | MERGE→git |
| skill-authoring | MERGE→skills (salvage validator/mirror rules) |
| superpowers-writing-skills | KEEP as `skills` survivor (trim 689L) |
| superpowers-subagent-driven-development | KEEP as subagent survivor |
| superpowers-dispatching-parallel-agents | MERGE→subagent |
| code-simplification | KEEP (slim) |
| ponytail | KEEP (minimalism ruleset) |
| ponytail-review | MERGE→code-review or ponytail |
| ponytail-audit | MERGE→code-simplification or ponytail |
| ponytail-debt | CUT (unless adopting `ponytail:` convention) |
| ponytail-gain | CUT |
| ponytail-help | CUT |
| ci-cd-and-automation | KEEP or MERGE→ship |
| shipping-and-launch | KEEP as `ship` survivor |
| domain-model | KEEP or MERGE→concepts |
| ubiquitous-language | MERGE→concepts or KEEP |
| improve-codebase-architecture | KEEP |
| zoom-out | KEEP |
| incremental-implementation | KEEP |
| context-engineering | KEEP |
| auto-iterate | KEEP |
| external-research-implications | KEEP |
| api-and-interface-design | KEEP |
| security-and-hardening | KEEP |
| performance-optimization | KEEP |
| documentation-and-adrs | KEEP |
| deprecation-and-migration | KEEP |
| frontend-ui-engineering | KEEP |
| game-prototyping | KEEP |
| website-editing | KEEP |
| browser-testing-with-devtools | KEEP |
| ui-test | KEEP |
| loop-uptime-maintenance | KEEP |
| cloudflare-ops | KEEP |
| godaddy-ops | KEEP |
| team-iterate | KEEP |

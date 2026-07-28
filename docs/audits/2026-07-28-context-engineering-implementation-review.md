All evidence is in: three audit docs, all seven canonical skills, mirror parity, gitignore state, validator, diff-check, diff scope, and the context-budget report. One process note for the record: I skipped the Codex-dispatch reflex deliberately — this review is itself the cross-family gate on Codex's implementation, and the brief forbids dispatching agents.

**TLDR: ADAPT — five of six blocking adaptations are fully implemented and verified, the rejected content is gone, mirrors are byte-identical, and the validator passes. One Important contract defect remains (the scout's return contract is unsatisfiable via its own recommended `peer-agents` dispatch path, because read-only mode denies the artifact write), and the adversarial scenario run that blocking adaptation #5's acceptance requires is still recorded as "to be completed." Both are small; fix the one sentence, run the documented scenario suite, then land.**

Per the established pattern from the prior review round, this session writes nothing — the implementing session should land the following as `docs/audits/2026-07-28-context-engineering-claude-implementation-review.md`.

---

# Claude Implementation Review: Context Engineering

**Review date:** 2026-07-28
**Reviewer:** Claude (Claude Code, model `claude-fable-5`)
**Under review:** working-tree implementation on `codex/context-engineering-handoff` (branch head `bf692610` + uncommitted skill edits), against the ADAPT verdict in `docs/audits/2026-07-28-context-engineering-claude-review.md` and the handoff in `docs/audits/2026-07-28-context-engineering-comprehensive-handoff.md`.
**Evidence run live this review:** `diff -r` across all seven `.agents/skills/` ↔ `.claude/skills/` pairs (all byte-identical); `git check-ignore` on `output/precedent-scout/` (ignored, `.gitignore:71`) and `.superpowers/sdd/progress.md` (still not ignored); `python scripts/validate_skills.py` (passed); `git diff --check` (clean); `git diff origin/main --stat` (scope matches the STATUS row's Files cell, plus `.claude/.fleet_warn_stamp`); `python scripts/check_context_budget.py` (STATUS.md over hard byte budget — pre-existing, reported below).

## Verdict

**ADAPT**

One Important defect (a one-to-two-sentence fix) and one outstanding acceptance run stand between this implementation and PASS. Everything else verified clean.

## Blocking adaptation coverage

| # | Adaptation | Status | Evidence |
|---|---|---|---|
| 1 | `.superpowers/` storage premise false → relocate or ignore | **Implemented** | Scout artifacts relocated to `output/precedent-scout/<task-slug>.json` (`implementation-precedent-scout/SKILL.md:55`, `subagent-driven-development/SKILL.md:79`); `git check-ignore` exits 0 on that path via `.gitignore:71 output/`. Handoff corrected (`comprehensive-handoff.md:473-475`). |
| 2 | Drop/correct the "encoding damage" rationale | **Implemented** | Handoff now states the diagram is valid UTF-8 and the garbling was a Windows code-page display problem, "not a justification for the rewrite" (`comprehensive-handoff.md:58-60`). |
| 3 | Manifest reuses existing artifacts first | **Implemented** | "Populate it inside the existing `_PURPOSE.md`, SDD task brief, accepted plan, or handoff. Create a standalone manifest only when no existing artifact covers the task" (`context-engineering/SKILL.md:68-73`); same precedence in the handoff (§2) and scenarios doc (required behavior 1). |
| 4 | Scout ↔ `peer-agents` ↔ internal-explorer boundary | **Implemented** | Scout names `peer-agents` as one dispatch mechanism and excludes local-codebase exploration and general delegation (`implementation-precedent-scout/SKILL.md:3,17-26`); `peer-agents` description redirects external-example asks to the scout (`peer-agents/SKILL.md:3,51-52`); router has exactly one entry (`using-agent-skills/SKILL.md:31`). No two descriptions co-trigger on "find external implementation examples." |
| 5 | Enforcement lives in the dispatch, not prose | **Partial** | The dispatch template with ALLOWED/FORBIDDEN/UNTRUSTED/RETURN blocks, "role prose is not a permission boundary," and "if the mechanism cannot enforce the allowlist, do not use it" are all present (`implementation-precedent-scout/SKILL.md:60-79`), wired into SDD (`subagent-driven-development/SKILL.md:74-82`). But the acceptance's second half — the malicious-README scenario run **against the real dispatch path** — is recorded in the scenarios doc as still to be completed. See Landing gate. |
| 6 | Task-scoped evidence vs design-changing research gate | **Implemented** | Stated in both directions: scout "Authority and escalation" (`implementation-precedent-scout/SKILL.md:139-150`) and `external-research-implications` "Boundary with implementation precedent" (`external-research-implications/SKILL.md:18-31`). Harness auto-dispatch/caching correctly flagged as future OpenSpec territory. |

## Findings

### Critical

None.

### Important

1. **The scout's return contract cannot be satisfied through its own recommended `peer-agents` dispatch path.** The template requires the scout to "write only the exact output artifact" and deliver a "verified source map at the requested path" with a final message containing "only status, artifact path, stop reason, and concerns" (`implementation-precedent-scout/SKILL.md:66-75`) — while also mandating `peer-agents` **default read-only mode, never `--write`** (`:79`). But peer-agents default mode denies all writes for both CLIs (`peer-agents/SKILL.md:38`: claude `-p` edit-denied; codex `-s read-only`), so the peer cannot write the JSON artifact itself. The only delivery route is the wrapper's `--out` capture of the final message — which then must contain the full JSON, violating the status-only final-reply clause. A fresh agent following the skill literally hits a contradiction on the primary named mechanism and will either improperly grant write or improvise. Fix is one or two sentences in the scout skill (+ mirror): when dispatching via `peer-agents`, point `--out` at `output/precedent-scout/<task-slug>.json`, have the peer emit the source-map JSON (with status/stop_reason/concerns carried in the JSON's own fields) as its final message, and treat the wrapper-written file as the artifact; the status-only reply contract applies to harness subagents that can write the artifact directly.

### Minor

2. **`.claude/.fleet_warn_stamp` is modified in the working tree** and sits outside the claimed write-set. Exclude it from the landing commit (scope hygiene; this repo has documented kitchen-sink-diff incidents).
3. **`docs/audits/2026-07-28-context-engineering-skill-scenarios.md` is untracked.** It is inside the claimed Files glob and must be `git add`ed with the landing commit, updated with post-rewrite results (see Landing gate).
4. **`.superpowers/sdd/` remains unignored** (`git check-ignore` exit 1), and `subagent-driven-development/SKILL.md:86` still homes the SDD ledger there. The blocking adaptation was an OR and is satisfied by the `output/` relocation; this is the pre-existing latent issue the prior review said could be fixed in passing. Non-blocking; worth a one-line `.gitignore` follow-up in this or a hygiene lane.
5. **Orient step 4 says "budget checks" generically** (`context-engineering/SKILL.md:61`) where the skill elsewhere names `provider_context_feed.py` explicitly (`:147`). Naming `scripts/check_context_budget.py` once would make the ADR-002 operationalization concrete without duplicating its numbers. Optional polish.

Nothing else. The rejected content is verifiably gone: no Brain Dump (only the anti-pattern warning against "brain dumps" remains), no fixed MCP product catalog, no `<2,000 lines` or any universal size threshold (the governing rule explicitly forbids one), and no automatic stop-and-ask ("Missing precedent alone is not a reason to stop," `context-engineering/SKILL.md:140-141`). The rewrite is 191 lines against the 293-line baseline, internally consistent, and all cross-skill integrations are pointers/contracts — the router adds one line plus a quick-reference row, planning adds a two-field task annotation, SDD adds one paragraph, peer-agents adds a description clause plus two bullets, ERI adds one boundary section. No duplicated workflows.

## Scenario assessment

Against the eight baseline scenarios in the scenarios doc, walked on the rewritten skill text:

1. **Resume after compaction** — covered: §7 preserve-list carries revision, boundaries, verification + freshness, artifact paths, next action; final checklist item requires fresh-agent resumability.
2. **Plan → implementation** — covered: phase naming (§1), refresh-on-phase-change (§7), and the manifest separates "Authoritative requirements" from "Current implementation evidence."
3. **Huge failing-test log** — covered: §5 runtime packet (command, time/environment/revision, exit status, first causal failure, raw-artifact path, delta since last pass, hypothesis labeled as inference).
4. **Strong internal precedent** — covered: §3 ranks canonical-vs-legacy and records differences; syntactic similarity explicitly not authority.
5. **No internal precedent** — fixed: scout dispatch conditions + reversible-default rule replace the old harmful stop-and-ask.
6. **User requests varied open-source examples** — covered: explicit scout dispatch condition; closest/alternative/caution coverage; direct source-map return.
7. **Malicious external README** — covered in prose (trust/safety section, UNTRUSTED INPUT template clause, enforce-in-dispatch rule); **live adversarial run against the real dispatch path not yet recorded** — this is the outstanding half of blocking adaptation #5, and the same run would have surfaced the Important finding above.
8. **Spec/code/runtime conflict** — fixed: authority ladder, typed-truth labeling, reversible in-scope default, ask only on material/irreversible choices.

## Landing gate

**Do not land yet.** Required before landing, in order:

1. Apply the Important fix (peer-agents artifact-delivery sentence in `implementation-precedent-scout/SKILL.md`), re-run `powershell -ExecutionPolicy Bypass -File scripts/sync-skills.ps1`.
2. Run the post-rewrite scenario suite the scenarios doc defers — at minimum the malicious-README adversarial case through the real dispatch path (peer-agents default mode with the template in the prompt) and the varied-examples case — and record results in `docs/audits/2026-07-28-context-engineering-skill-scenarios.md`. This is the documented before-commit gate and the unfinished acceptance of blocking adaptation #5.
3. Re-run and confirm green: `python scripts/validate_skills.py`; `git diff --check -- .agents/skills .claude/skills .codex/skills`; mirror parity spot-check. (All pass on the current tree; re-verify after the fix.)
4. Commit scope: the seven skill pairs, the three audit docs, `ideas/PIPELINE.md`, `STATUS.md` — and **not** `.claude/.fleet_warn_stamp`.

Once items 1–2 are done and green, this implementation is fit to land without a further Claude re-review; this artifact plus the fix evidence satisfies the before-push cross-family review for the skill diffs. Context-budget report for the record: `STATUS.md` is over its hard byte budget (20,234/4,096 bytes; 59/60 lines) and `AGENTS.md`/`CLAUDE.md` remain over soft targets — all pre-existing, outside this lane's write authority, reported as evidence per the handoff's own rule.

---

That is the full review. The implementing session should land it as the durable artifact, apply the one-sentence scout fix, run the deferred adversarial scenarios, and then merge — no further research-review round from me is needed.

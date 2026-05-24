# Provider Context Feed + Worktree Discipline — Claude Review

Date: 2026-05-02
Reviewer: Claude (Cowork session, opus-4-7)
Counterpart finding/implementation: Codex (`docs/audits/2026-05-02-provider-context-feed-frontier-research.md`)

## Verdict

**ADAPT.** Substance is sound, frontier framing holds up, drift is clean. One real
bug must land before merge; feed-noise / phase-filter behavior should be either
fixed or explicitly documented as advisory before push; two alignment touch-ups
should land before the convention is treated as final. Ship-ready in ~1 small
follow-up commit; everything else is sequencing, not redesign.

## Scope

Re-reviewed targets:

- `AGENTS.md` (esp. §"GitHub-Aligned Worktree Discipline" lines 345–446 and
  §"Provider-context feed checkpoints" lines 280–301)
- `.agents/skills/git-workflow-and-versioning/SKILL.md` (lines 173–240)
- `.claude/skills/git-workflow-and-versioning/SKILL.md` (byte-identical mirror;
  `diff -q` clean)
- `scripts/worktree_status.py`
- `tests/test_worktree_status.py`
- `scripts/provider_context_feed.py`
- `tests/test_provider_context_feed.py`
- `.claude/hooks/provider_context_feed_hook.py`
- `.agents/worktrees.md`
- STATUS.md row 37 (the discipline lane) and row 38 (this review gate)

## Independent validation re-run

Run on the Linux sandbox over the FUSE mount, 2026-05-02:

- `python -m pytest tests/test_worktree_status.py tests/test_provider_context_feed.py -q --noconftest` → **20 passed**, matches Codex's reported result.
- `python -m ruff check scripts/worktree_status.py tests/test_worktree_status.py scripts/provider_context_feed.py tests/test_provider_context_feed.py .claude/hooks/provider_context_feed_hook.py` → **All checks passed.**
- `python scripts/validate_skills.py` → **Skill validation passed.**
- `python scripts/check_cross_provider_drift.py` → **0 drift across 1 watched file.**
- `python scripts/worktree_status.py` (live, no flags) → crashed (`FileNotFoundError`) on a sibling worktree whose path is not reachable from this mount. See Finding #4. Does not invalidate the test suite — surfaces a real cross-environment fragility.

## Findings

### Question 1 — Does the convention prevent forgotten branches, ideas, past work?

Largely yes, with one structural asymmetry.

- **Forgotten branches:** `worktree_status.py` enumerates everything `git worktree list` returns and forces every entry into one of 11 diagnostic states. The 4 lane states + required `_PURPOSE.md` + `.agents/worktrees.md` create-event log + STATUS row reference + 24h staleness + `ORPHANED` / `READY_TO_REMOVE` cover the main loss vectors. Strong.
- **Forgotten ideas:** `ideas/INBOX.md` + `ideas/PIPELINE.md` + `_PURPOSE.md`'s required "Idea feed refs" section + `idea-feed` source type in the scanner cover the captured-but-not-yet-built path. Reasonable.
- **Forgotten past agent work:** Memory-refs requirement + `.claude/agent-memory/` scan + `.agents/activity.log` scan + handoff search guidance in AGENTS.md (lines 399–407) are correct in shape. The asymmetry (Finding #8) is that today only Claude has a durable per-role memory tree to scan; if Codex/Cursor add equivalents, the scanner needs to grow.

Edge case: the convention says "retrofit `_PURPOSE.md` on next touch" (AGENTS.md:444–446). A worktree that is never touched again never retrofits. The fallback is the 24h `ORPHANED` classification, which works — but only if a provider actually runs `worktree_status.py`. Suggest the AGENTS.md session-start ritual run it implicitly (it isn't currently in the §"Provider session-start ritual" list at lines 244–278; only `claim_check.py` and `provider_context_feed.py` are).

### Question 2 — Are the four lane states clear and operational?

The four canonical lane states (Active / Parked draft / Idea-reference / Abandoned-swept) are described correctly and identically in AGENTS.md (lines 358–372) and SKILL.md (lines 186–197). Operational.

The diagnostic state set in `worktree_status.py` is **richer** (11 states), which is good for surfacing intermediate "fix it before this is a real lane" cases — but the mapping back to the 4 canonical lanes is not documented anywhere. A cold-start provider sees `DIRTY_CURRENT_NEEDS_PURPOSE` or `NEEDS_PR_OR_STATUS` in the table output and has to infer the canonical lane action. Add a short state→lane legend either at the top of `render_table` output or in AGENTS.md §"GitHub-Aligned Worktree Discipline". See Finding #6.

`Idea/reference only` correctly has no scanner state because items in that lane have no worktree — clean separation, worth a one-liner in the script docstring so this isn't read as a gap.

### Question 3 — Branch-selector safety rule

Reads correctly. The rule appears in three places consistently:

- AGENTS.md lines 374–380 — full prose statement.
- SKILL.md (both copies) lines 225–229 — same four-part rule.
- `worktree_status.py:_action_for_state` — appends `"Do not switch this dirty checkout to main."` to the ACTION column whenever the state is `DIRTY_CURRENT_*`.

Gap: documentation + diagnostic only; nothing at the runtime layer actually blocks a `git checkout main` from a dirty worktree. Hard Rule #12 (AGENTS.md:471) covers `git reset --hard` / `git restore` / `git clean` / force-push as cleanup, but does not mention branch-selector switching. Recommend: either add `git checkout` from a dirty checkout to Hard Rule #12's blocklist, or add a pre-checkout hook. Defer-acceptable; not a land-blocker.

### Question 4 — Does `worktree_status.py` make state obvious for cold-start providers?

Mostly yes. Strengths:

- Default text table is self-describing (SLUG / STATE / CUR / DIRTY / LIVE / UPSTREAM / BRANCH / AGE_H / MEM / ACTION / PURPOSE).
- The ACTION column carries the actual instruction string per state — providers do not need to look up the state name.
- `STATE_PRIORITY` sorts dirty/current/orphaned states first.
- `--sweep-orphaned` emits dry-run remove commands.
- `--json` and `--provider <substr>` are present and useful.

Weaknesses (see Findings #1, #4, #6).

### Question 5 — Does `provider_context_feed.py --phase claim` surface useful context without too much noise?

Mixed. Live measurements on the current repo state (Linux sandbox, 2026-05-02):

- `--phase claim --limit 80`: 80 candidates, 68 (85%) are `exec-plan` content; 4 each from `worktree-inventory`, `idea-pipeline`, `vetted-specs`. Zero `provider-memory`, `worktree-purpose`, `research-artifact`, or `proposed-design` reach the cut. Phase filter has no effect because the dominant `coordination` signal passes every phase set.
- `--phase memory-write --limit 80`: byte-identical signal/source distribution as `--phase claim`. The four "implementation" phases (claim/plan/build/foldback/memory-write) all produce essentially the same feed at default limit.
- `--phase claim --limit 10` (the hook's setting): 4 worktree-inventory + 4 idea-pipeline + 2 vetted-specs. Useful for orienting a new session to *the convention itself*; surfaces no active-lane content (no `_PURPOSE.md` present in the inventoried sibling worktrees yet) and no recent agent memory.

Root causes:

1. `SOURCE_PRIORITY` puts `exec-plan` at 30, ranked above `research-artifact` (40), `provider-memory` (50), and `provider-automation` (55). Combined with `MAX_CANDIDATES_PER_FILE=4` and many active exec-plan files, exec-plan saturates every slot below the small high-priority head.
2. There is no per-source-type cap (only per-file).
3. The signal regexes for `coordination` and `task` are wide enough that almost every line in any planning doc matches; the phase filter's variation between phases is invisible in practice.

Recommendations (any subset will help; first two have biggest leverage):

- Add a per-source-type cap (e.g., 8 entries per source type, regardless of file count).
- Demote `exec-plan` priority below `research-artifact` and `provider-memory`, or add a recency cliff (drop exec-plan entries older than ~14 days).
- Re-rank within priority bands by mtime so recent audits/memories beat old exec plans.
- Optional: tighten phase signal sets (e.g., `build` excludes `idea`; `foldback` weights `automation`).

If the team prefers not to redesign the ranker now: document in AGENTS.md (lines 280–301) that the `--limit` default is sized for hook injection, that bare-CLI runs should pass `--limit 10` for a triage view and `--limit 200` for a full sweep, and that phase filters are advisory headers more than functional filters today. That documentation alone makes the noise non-blocking.

Useful behaviors the script does correctly:

- The `worktree-purpose` source has its own per-file cap (8) and label-priority ranking (`Purpose:` first, then `STATUS/Issue/PR:` etc.), which is exactly the right shape — when `_PURPOSE.md` files actually exist they should rise to the top. The labels match the AGENTS.md template.
- Provider-family aliasing in `_provider_scope` ("codex-gpt5-desktop" → codex family + shared) works and is tested.
- Hook output is bounded to 220 chars per line and 10 candidates — appropriate for hookSpecificOutput injection.

### Question 6 — Are AGENTS.md and the git workflow skill aligned?

Yes. Substance is consistent:

- Both files describe the 4 lane states with identical wording on what artifacts each lane requires.
- Both state the branch-selector safety rule with identical four parts.
- Both reference `worktree_status.py` and `provider_context_feed.py` with identical invocation patterns.
- `check_cross_provider_drift.py` reports 0 drift on the watched files.
- The `_PURPOSE.md` 12-field template in AGENTS.md (lines 392–397) is mirrored verbatim in `REQUIRED_PURPOSE_FIELDS` (`scripts/worktree_status.py:20–33`) and in the format block of `.agents/worktrees.md:20–35`.

Minor: SKILL.md (lines 197–201) sketches the `_PURPOSE.md` field set loosely; AGENTS.md is the canonical enumeration. Recommend SKILL.md add a one-line "see AGENTS.md §GitHub-Aligned Worktree Discipline for the canonical 12-field template" rather than partially restating. Not a land-blocker; reduces future drift.

The provider-specific bits are correctly placed: the Claude hook lives only in `.claude/hooks/`; AGENTS.md (lines 296–301) explicitly says other providers run the script manually. No provider-only rule is hidden in only one file.

## Numbered findings (file/line refs)

1. **`READY_TO_REMOVE` action branch is dead code.** `scripts/worktree_status.py:360` reads `state == "READY-TO-REMOVE"` (hyphen). The state string is `"READY_TO_REMOVE"` everywhere else (lines 45, 219). Real entries in this state fall through to either the `LIVE_MAIN` branch (only if branch is `main`) or the default `"Inspect before pickup."` — losing the explicit "log remove/sweep in `.agents/worktrees.md` after ideas are extracted" instruction. **Severity: land-blocker (one-character fix).** Add a regression test in `tests/test_worktree_status.py` to pin `_action_for_state(state="READY_TO_REMOVE", ...)` to the documented string.

2. **Feed dominated by exec-plan content at default limit.** `scripts/provider_context_feed.py` SOURCE_PRIORITY + per-file cap interaction; live measurement above. **Severity: adapt before push** (or document the limit advice in AGENTS.md lines 280–301).

3. **Phase filter is functionally a no-op for most repo content.** Same file. `coordination` regex (lines 86–93) and `task` regex (lines 61–68) match too widely; phases `claim` / `plan` / `foldback` / `memory-write` produce identical feeds on this repo. **Severity: adapt before push** (or document phases as advisory).

4. **`worktree_status.py` crashes on missing worktree path.** `scripts/worktree_status.py:238` — when a worktree directory in `git worktree list --porcelain` does not exist on disk (cross-mount, FUSE, externally-deleted), `subprocess.run(..., cwd=path)` raises `FileNotFoundError` and the whole script aborts. Wrap each per-worktree call to emit a `"MISSING"` state row and continue. **Severity: adapt; not blocking on Windows host.** Reproduced live in this review — first call crashed on `C:/Users/Jonathan/Projects/Workflow-bug037-live2`.

5. **`_PURPOSE.md` glob is too narrow.** `scripts/provider_context_feed.py:188–193` only matches `root.parent.glob("wf-*/_PURPOSE.md")`. The current `.agents/worktrees.md` inventory contains `Workflow/origin/main`, `Workflow-bug037-live2`, `Workflow-scorched-pwa-live`, `Workflow/.claude/worktrees/agent-a54683e4`, `wf-review-NNN/`, none of which match `wf-*` from `root.parent`. Either widen to additional patterns (`Workflow*/_PURPOSE.md`, `Workflow/.claude/worktrees/*/_PURPOSE.md`) or have `worktree_status.py` emit the canonical purpose-path list for the scanner to consume. **Severity: adapt; not blocking until those worktrees retrofit `_PURPOSE.md`.**

6. **State-set vs lane-state mapping is undocumented.** `worktree_status.py` produces 11 diagnostic states; AGENTS.md / SKILL.md describe 4 canonical lane states. No mapping is published. **Severity: adapt before treating convention as final.** Two small fixes:
   - Add a state→lane legend paragraph to AGENTS.md §"GitHub-Aligned Worktree Discipline" (right after the lane-states list at lines 358–372).
   - Print a one-line legend at the top of `render_table` output (e.g., `# state map: ACTIVE_LANE/PARKED_DRAFT = canonical lanes; DIRTY_*, NEEDS_*, IN_FLIGHT, ORPHANED, READY_TO_REMOVE = action-required intermediates`).

7. **Branch-selector safety has no runtime block.** Documentation + diagnostic exist; nothing prevents a `git checkout main` from a dirty branch at runtime. Hard Rule #12 (AGENTS.md:471) does not currently include branch-selector switches. **Severity: defer to follow-up hardening.** Track in the "Next Hardening" section of `2026-05-02-provider-context-feed-frontier-research.md`.

8. **Memory-refs scan is provider-asymmetric.** `worktree_status.py:_memory_refs` (lines 283–291) only matches `.claude/agent-memory/` and `.agents/activity.log`. The frontier-research doc itself notes Cursor memories and GitHub Copilot Memory are emerging. **Severity: defer until a non-Claude memory tree actually lands in this repo.** When that lands, update `default_specs` (provider_context_feed.py) and `_memory_refs` (worktree_status.py) together so the scanner stays symmetric.

9. **SKILL.md `_PURPOSE.md` field list is informal vs AGENTS.md canonical.** `.agents/skills/git-workflow-and-versioning/SKILL.md:197–201` sketches the fields; AGENTS.md:392–397 enumerates them. Replace SKILL.md's restatement with `"see AGENTS.md §GitHub-Aligned Worktree Discipline for the canonical 12-field template"` to prevent future drift. **Severity: minor; nice-to-have, non-blocking.**

10. **Session-start ritual omits `worktree_status.py`.** AGENTS.md §"Provider session-start ritual" (lines 244–278) lists `claim_check.py` and `provider_context_feed.py` but not `worktree_status.py`. The script is mentioned later (line 396) but only "at session start or before a cleanup pass." Promote it into the numbered ritual so cold-start providers actually see orphaned/dirty worktrees from prior sessions before they start a new lane. **Severity: adapt; small docs change.**

## Future / convergence framing

The frontier-research doc cites the right movement: GitHub-as-control-plane (Codex app worktrees → PR; Copilot cloud-agent → PR; Jules → PR), repository-scoped advisory memories (Claude Code memory, Cursor memories, Copilot Memory, Jules memory), and continuous-loop automation (SessionStart hooks, Codex automations, Jules suggested tasks). The thesis "memory feeds lanes; STATUS/worktree/PR is build authority; memory never edits truth" is well-aligned with where every major coding-agent vendor's own docs are landing — they all explicitly classify their memories as advisory and validate against the codebase before applying. This convention will not be invalidated by longer context windows or stronger per-provider memory; if anything it gets *more* valuable as more independent memory layers proliferate.

Two scaling caveats worth tracking:

- **Static `SOURCE_PRIORITY` will not age well.** Today's repo has many active exec-plans drowning everything else (Finding #2). Tomorrow's repo will have many research artifacts and many provider memories drowning everything else. Recency-weighted ranking with per-source caps scales; static priority does not.
- **Trunk-based 1–3 day cadence vs review-gated weeks.** The 24h `ORPHANED` threshold is calibrated for trunk-based development (correctly cited in SKILL.md lines 18–28). But this repo also legitimately has review-gated lanes that stay open for weeks waiting on the opposite-provider verdict — those will trip the threshold falsely. Stronger signal than age: STATUS row presence + active `claimed:<provider> ACTIVE YYYY-MM-DD` heartbeat (already documented for `claim_check.py` reaping at AGENTS.md:324–334; mirror the heartbeat semantics into `worktree_status.py`).
- **Machine-parseable `_PURPOSE.md` frontmatter** will be useful once IDE/agent integrations want to extract specific fields without regex search. Not needed now; flag for the next iteration.

## Land/push gating

| Phase | Gating |
|---|---|
| **Land (merge to main)** | Fix Finding #1 (`READY-TO-REMOVE` typo + regression test). One-character fix, single commit. |
| **Push (open PR / draft public)** | Address Findings #2 + #3 — either the small ranking adjustments described above, or document `--limit` and phase advisory nature in AGENTS.md §"Provider-context feed checkpoints" (lines 280–301) so providers running the bare CLI command don't drink from the exec-plan firehose. |
| **Convention final / retire STATUS row 38** | Findings #5 and #6 — broaden `_PURPOSE.md` glob and publish a state→lane legend. Finding #10 (promote `worktree_status.py` into the numbered session-start ritual) is in the same change set and small. |
| **Follow-up (own STATUS rows)** | Finding #4 (worktree path-missing crash hardening); Finding #7 (branch-selector runtime stop / Hard Rule #12 expansion); Finding #8 (cross-provider memory tree symmetry). All non-blocking. |

## Bottom line

This is a strong, well-grounded slice. The convention captures the right
abstraction for the multi-provider, GitHub-as-spine direction the field is
moving in. The implementation has one real bug, one ranking-noise issue worth
addressing or documenting, and a handful of small alignment touch-ups. After
Finding #1 lands, I'd `approve` for merge to `main`; the rest can sequence as
listed without blocking the discipline from being live.

Verdict: **ADAPT** — land after Finding #1; push after Findings #2+#3; convention
final after Findings #5, #6, #10.

## Codex follow-up resolution

Date: 2026-05-02
Implementer: Codex (`codex-gpt5-desktop`)

Resolution summary:

- Finding #1 fixed: `READY_TO_REMOVE` action branch now matches the state name,
  with a regression test.
- Finding #2 fixed: provider context feed now has per-source caps and exec-plan
  content is ranked below worktree purpose, research, and provider memory.
- Finding #3 addressed: phase filters remain coarse by design, and AGENTS/skill
  now document limit guidance and advisory phase semantics.
- Finding #4 fixed: missing worktree paths produce a `MISSING` row instead of
  crashing the scanner.
- Finding #5 fixed: `_PURPOSE.md` discovery now uses `git worktree list` plus
  sibling and nested fallback patterns, not only `wf-*`.
- Finding #6 fixed: AGENTS and `worktree_status.py` now publish a diagnostic
  state to canonical lane-state legend.
- Finding #7 addressed: Hard Rule #12 now forbids switching a dirty worktree to
  `main`; new live-ready work must start from a clean main-based worktree.
- Finding #8 fixed for the current repo shape: `worktree_status.py` now reads a
  provider-agnostic `Memory refs:` block and recognizes Claude/Codex/Cursor/
  activity-log memory refs.
- Finding #9 fixed: the git workflow skill points at AGENTS.md for the
  canonical 12-field `_PURPOSE.md` template instead of restating it loosely.
- Finding #10 fixed: `worktree_status.py` is now part of the numbered provider
  session-start ritual.
